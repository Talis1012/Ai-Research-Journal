import os
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from faster_whisper import WhisperModel

from utils.user_scope import scoped_path


load_dotenv()

_whisper_model = None


def get_whisper_model():
    global _whisper_model

    if _whisper_model is None:
        _whisper_model = WhisperModel(
            "base",
            device="cpu",
            compute_type="int8"
        )

    return _whisper_model


def save_audio_file(audio_file, chat_id: int) -> str:
    audio_dir = get_audio_storage_path()
    audio_dir.mkdir(parents=True, exist_ok=True)

    unique_name = f"chat_{chat_id}_{uuid4().hex}.wav"
    file_path = audio_dir / unique_name

    with open(file_path, "wb") as f:
        f.write(audio_file.getvalue())

    return str(file_path)


def get_audio_storage_path() -> Path:
    return scoped_path(os.getenv("AUDIO_STORAGE_PATH", "data/audio"))


def _path_inside_audio_storage(file_path: str | Path) -> Path:
    storage_path = get_audio_storage_path().resolve()
    resolved_path = Path(file_path).expanduser().resolve()

    if resolved_path != storage_path and storage_path not in resolved_path.parents:
        raise ValueError("The requested file is outside the audio storage area.")

    return resolved_path


def transcribe_audio(audio_path: str, language: str | None = None) -> str:
    model = get_whisper_model()

    segments, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=5
    )

    transcript_parts = []

    for segment in segments:
        transcript_parts.append(segment.text.strip())

    return " ".join(transcript_parts).strip()


def delete_audio_file(file_path: str):
    path = _path_inside_audio_storage(file_path)

    if path.exists() and path.is_file():
        path.unlink()
