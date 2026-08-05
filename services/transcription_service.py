import io
import os
import tempfile
import wave
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from services.resource_limits import (
    concurrency_slot,
    consume_rate_limit,
    enforce_storage_quota,
    env_int,
)
from services.supabase_storage import (
    delete_object,
    download_bytes,
    enforce_user_storage_quota,
    is_storage_reference,
    upload_bytes,
)
from utils.runtime_config import uses_supabase_storage
from utils.user_scope import scoped_path


load_dotenv()

_whisper_model = None


def get_whisper_model():
    global _whisper_model

    if _whisper_model is None:
        # Importing faster-whisper also loads CTranslate2 and NumPy. Keep that
        # work off normal page loads and pay the cost only for transcription.
        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel(
            "base",
            device="cpu",
            compute_type="int8"
        )

    return _whisper_model


def save_audio_file(audio_file, chat_id: int) -> str:
    audio_bytes = audio_file.getvalue()
    validate_wav_bytes(audio_bytes)
    unique_name = f"chat_{chat_id}_{uuid4().hex}.wav"

    if uses_supabase_storage():
        enforce_user_storage_quota(
            "audio",
            len(audio_bytes),
            quota_bytes=env_int(
                "MAX_AUDIO_STORAGE_BYTES",
                250 * 1024 * 1024,
                minimum=env_int("MAX_AUDIO_FILE_SIZE", 25 * 1024 * 1024),
            ),
            label="audio",
            max_files=env_int(
                "MAX_STORED_AUDIO_FILES",
                500,
                maximum=5000,
            ),
        )
        return upload_bytes(
            "audio",
            unique_name,
            audio_bytes,
            content_type="audio/wav",
        )

    audio_dir = get_audio_storage_path()
    audio_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    enforce_storage_quota(
        audio_dir,
        len(audio_bytes),
        quota_bytes=env_int(
            "MAX_AUDIO_STORAGE_BYTES",
            250 * 1024 * 1024,
            minimum=env_int("MAX_AUDIO_FILE_SIZE", 25 * 1024 * 1024),
        ),
        label="audio",
        max_files=env_int("MAX_STORED_AUDIO_FILES", 500, maximum=5000),
    )

    file_path = audio_dir / unique_name

    with open(file_path, "wb") as f:
        f.write(audio_bytes)

    try:
        audio_dir.chmod(0o700)
        file_path.chmod(0o600)
    except OSError:
        pass

    return str(file_path)


def get_audio_storage_path() -> Path:
    return scoped_path(os.getenv("AUDIO_STORAGE_PATH", "data/audio"))


def validate_wav_bytes(audio_bytes: bytes) -> dict:
    max_size = env_int(
        "MAX_AUDIO_FILE_SIZE",
        25 * 1024 * 1024,
        maximum=100 * 1024 * 1024,
    )

    if not audio_bytes:
        raise ValueError("The audio recording is empty.")

    if len(audio_bytes) > max_size:
        raise ValueError(
            f"The audio recording exceeds the {max_size // (1024 * 1024)} MB limit."
        )

    if not (
        audio_bytes.startswith(b"RIFF")
        and len(audio_bytes) >= 12
        and audio_bytes[8:12] == b"WAVE"
    ):
        raise ValueError("Only uncompressed WAV recordings can be transcribed.")

    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as audio:
            channels = audio.getnchannels()
            sample_width = audio.getsampwidth()
            sample_rate = audio.getframerate()
            frame_count = audio.getnframes()

            if audio.getcomptype() != "NONE":
                raise ValueError("Compressed WAV recordings are not supported.")

            if channels not in (1, 2):
                raise ValueError("Audio must contain one or two channels.")

            if sample_width not in (1, 2, 3, 4):
                raise ValueError("The WAV sample width is not supported.")

            if not 8_000 <= sample_rate <= 96_000:
                raise ValueError("The WAV sample rate must be between 8 and 96 kHz.")

            if frame_count <= 0:
                raise ValueError("The audio recording contains no samples.")

            duration = frame_count / sample_rate
            max_duration = env_int(
                "MAX_AUDIO_DURATION_SECONDS",
                600,
                maximum=3600,
            )

            if duration > max_duration:
                raise ValueError(
                    f"The audio recording exceeds the {max_duration // 60} minute limit."
                )

            expected_bytes = frame_count * channels * sample_width
            decoded_frames = audio.readframes(frame_count)

            if len(decoded_frames) != expected_bytes:
                raise ValueError("The WAV recording is truncated or malformed.")
    except (EOFError, wave.Error) as exc:
        raise ValueError("The WAV recording is malformed.") from exc

    return {
        "duration_seconds": duration,
        "channels": channels,
        "sample_rate": sample_rate,
        "frame_count": frame_count,
    }


def _path_inside_audio_storage(file_path: str | Path) -> Path:
    storage_path = get_audio_storage_path().resolve()
    resolved_path = Path(file_path).expanduser().resolve()

    if resolved_path != storage_path and storage_path not in resolved_path.parents:
        raise ValueError("The requested file is outside the audio storage area.")

    return resolved_path


def transcribe_audio(audio_path: str, language: str | None = None) -> str:
    max_size = env_int("MAX_AUDIO_FILE_SIZE", 25 * 1024 * 1024)

    if is_storage_reference(audio_path):
        audio_bytes = download_bytes(audio_path, bucket="audio")
    else:
        safe_path = _path_inside_audio_storage(audio_path)

        with safe_path.open("rb") as audio_stream:
            audio_bytes = audio_stream.read(max_size + 1)

    validate_wav_bytes(audio_bytes)
    consume_rate_limit(
        "Transcription",
        per_user_hour=env_int(
            "TRANSCRIPTIONS_PER_USER_HOUR",
            12,
            maximum=500,
        ),
        per_user_day=env_int(
            "TRANSCRIPTIONS_PER_USER_DAY",
            50,
            maximum=5000,
        ),
        global_per_minute=env_int(
            "TRANSCRIPTIONS_GLOBAL_PER_MINUTE",
            10,
            maximum=1000,
        ),
        global_per_day=env_int(
            "TRANSCRIPTIONS_GLOBAL_PER_DAY",
            200,
            maximum=10000,
        ),
    )

    with concurrency_slot(
        "Transcription",
        global_limit=env_int(
            "MAX_CONCURRENT_TRANSCRIPTIONS",
            1,
            maximum=16,
        ),
        lease_seconds=3600,
    ):
        model = get_whisper_model()

        if is_storage_reference(audio_path):
            temporary_audio = tempfile.NamedTemporaryFile(suffix=".wav")
            temporary_audio.write(audio_bytes)
            temporary_audio.flush()
            model_path = temporary_audio.name
        else:
            temporary_audio = None
            model_path = str(safe_path)

        transcript_parts = []
        transcript_chars = 0
        max_transcript_chars = env_int(
            "MAX_TRANSCRIPT_CHARS",
            100_000,
            maximum=500_000,
        )

        try:
            segments, _ = model.transcribe(
                model_path,
                language=language,
                beam_size=env_int("WHISPER_BEAM_SIZE", 3, maximum=5),
            )

            for segment in segments:
                part = segment.text.strip()

                if not part:
                    continue

                transcript_chars += len(part) + 1

                if transcript_chars > max_transcript_chars:
                    raise ValueError("The generated transcript is too long to store safely.")

                transcript_parts.append(part)
        finally:
            if temporary_audio is not None:
                temporary_audio.close()

    return " ".join(transcript_parts).strip()


def read_audio_file(file_path: str) -> bytes:
    if is_storage_reference(file_path):
        return download_bytes(file_path, bucket="audio")

    path = _path_inside_audio_storage(file_path)

    if not path.is_file():
        raise FileNotFoundError("The stored audio recording could not be found.")

    return path.read_bytes()


def delete_audio_file(file_path: str):
    if is_storage_reference(file_path):
        delete_object(file_path, bucket="audio")
        return

    path = _path_inside_audio_storage(file_path)

    if path.exists() and path.is_file():
        path.unlink()
