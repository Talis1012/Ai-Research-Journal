from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from faster_whisper import WhisperModel


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
    audio_dir = Path("data/audio")
    audio_dir.mkdir(parents=True, exist_ok=True)

    unique_name = f"chat_{chat_id}_{uuid4().hex}.wav"
    file_path = audio_dir / unique_name

    with open(file_path, "wb") as f:
        f.write(audio_file.getvalue())

    return str(file_path)


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
    path = Path(file_path)

    if path.exists() and path.is_file():
        path.unlink()