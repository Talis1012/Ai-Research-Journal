import mimetypes
import os
import re
from pathlib import Path
from uuid import uuid4


MAX_LIBRARY_FILE_SIZE = 25 * 1024 * 1024

_TYPE_BY_EXTENSION = {
    ".pdf": "pdf",
    ".csv": "dataset",
    ".tsv": "dataset",
    ".xls": "dataset",
    ".xlsx": "dataset",
    ".json": "dataset",
    ".mp3": "audio",
    ".wav": "audio",
    ".m4a": "audio",
    ".ogg": "audio",
    ".aac": "audio",
    ".flac": "audio",
    ".doc": "document",
    ".docx": "document",
    ".txt": "document",
    ".md": "document",
    ".rtf": "document",
    ".ppt": "document",
    ".pptx": "document",
}


def get_library_storage_path() -> Path:
    storage_path = Path(
        os.getenv("LIBRARY_STORAGE_PATH", "data/library")
    ).expanduser()
    storage_path.mkdir(parents=True, exist_ok=True)

    return storage_path


def infer_library_item_type(filename: str) -> str:
    return _TYPE_BY_EXTENSION.get(Path(filename).suffix.lower(), "other")


def title_from_filename(filename: str) -> str:
    title = Path(filename).stem.replace("_", " ").replace("-", " ")
    title = re.sub(r"\s+", " ", title).strip()

    return title or "Untitled file"


def _safe_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower()

    if not suffix or not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
        return ""

    return suffix


def _path_inside_library(path: str | Path) -> Path:
    storage_path = get_library_storage_path().resolve()
    resolved_path = Path(path).expanduser().resolve()

    if resolved_path != storage_path and storage_path not in resolved_path.parents:
        raise ValueError("The requested file is outside the library storage area.")

    return resolved_path


def save_library_upload(uploaded_file) -> dict:
    original_filename = Path(str(uploaded_file.name or "")).name.strip()

    if not original_filename:
        raise ValueError("The uploaded file must have a name.")

    file_bytes = uploaded_file.getvalue()
    file_size = len(file_bytes)

    if file_size == 0:
        raise ValueError("The uploaded file is empty.")

    if file_size > MAX_LIBRARY_FILE_SIZE:
        raise ValueError("The file is larger than the 25 MB upload limit.")

    stored_filename = f"{uuid4().hex}{_safe_extension(original_filename)}"
    file_path = get_library_storage_path() / stored_filename
    file_path.write_bytes(file_bytes)
    mime_type = (
        getattr(uploaded_file, "type", None)
        or mimetypes.guess_type(original_filename)[0]
        or "application/octet-stream"
    )

    return {
        "title": title_from_filename(original_filename),
        "item_type": infer_library_item_type(original_filename),
        "original_filename": original_filename,
        "file_path": str(file_path),
        "mime_type": mime_type,
        "file_size": file_size,
    }


def read_library_file(file_path: str) -> bytes:
    safe_path = _path_inside_library(file_path)

    if not safe_path.is_file():
        raise FileNotFoundError("The stored file could not be found.")

    return safe_path.read_bytes()


def delete_library_file(file_path: str | None):
    if not file_path:
        return

    safe_path = _path_inside_library(file_path)

    if safe_path.is_file():
        safe_path.unlink()
