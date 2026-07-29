import io
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from utils.user_scope import scoped_path


MAX_FIGURE_FILE_SIZE = 25 * 1024 * 1024
MAX_FIGURE_PIXELS = 50_000_000


def get_manuscript_asset_storage_path() -> Path:
    storage_path = scoped_path(
        os.getenv("MANUSCRIPT_ASSET_STORAGE_PATH", "data/manuscript_assets")
    )
    storage_path.mkdir(parents=True, exist_ok=True)
    return storage_path


def _path_inside_asset_storage(path: str | Path) -> Path:
    storage_path = get_manuscript_asset_storage_path().resolve()
    resolved_path = Path(path).expanduser().resolve()

    if resolved_path != storage_path and storage_path not in resolved_path.parents:
        raise ValueError("The requested figure is outside manuscript storage.")

    return resolved_path


def save_figure_upload(uploaded_file, manuscript_id: int) -> dict:
    original_filename = Path(str(uploaded_file.name or "")).name.strip()

    if not original_filename:
        raise ValueError("The uploaded figure must have a file name.")

    file_bytes = uploaded_file.getvalue()

    if not file_bytes:
        raise ValueError("The uploaded figure is empty.")

    if len(file_bytes) > MAX_FIGURE_FILE_SIZE:
        raise ValueError("The figure is larger than the 25 MB upload limit.")

    try:
        with Image.open(io.BytesIO(file_bytes)) as opened:
            opened.load()
            image = ImageOps.exif_transpose(opened)

            if image.width * image.height > MAX_FIGURE_PIXELS:
                raise ValueError("The figure dimensions are too large.")

            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")

            target_dir = get_manuscript_asset_storage_path() / str(int(manuscript_id))
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / f"{uuid4().hex}.png"
            image.save(target_path, format="PNG", optimize=True)
            width, height = image.size
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Upload a valid PNG, JPEG, WEBP, GIF, BMP or TIFF image.") from exc

    return {
        "original_filename": original_filename,
        "storage_path": str(target_path),
        "mime_type": "image/png",
        "content": {
            "width": width,
            "height": height,
            "file_size": target_path.stat().st_size,
        },
    }


def read_manuscript_asset_file(storage_path: str) -> bytes:
    safe_path = _path_inside_asset_storage(storage_path)

    if not safe_path.is_file():
        raise FileNotFoundError("The stored figure could not be found.")

    return safe_path.read_bytes()


def delete_manuscript_asset_file(storage_path: str | None):
    if not storage_path:
        return

    safe_path = _path_inside_asset_storage(storage_path)

    if safe_path.is_file():
        safe_path.unlink()


def render_equation_png(latex: str, *, dpi: int = 220) -> bytes:
    expression = str(latex or "").strip()

    if not expression:
        raise ValueError("Equation LaTeX is required.")

    if expression.startswith("$") and expression.endswith("$"):
        expression = expression[1:-1].strip()

    matplotlib_cache = Path(
        os.environ.setdefault(
            "MPLCONFIGDIR",
            str(Path(tempfile.gettempdir()) / "research-journal-matplotlib"),
        )
    )
    matplotlib_cache.mkdir(parents=True, exist_ok=True)

    try:
        from matplotlib.mathtext import math_to_image
    except ImportError as exc:
        raise RuntimeError(
            "Equation export requires the matplotlib dependency."
        ) from exc

    output = io.BytesIO()

    try:
        math_to_image(
            f"${expression}$",
            output,
            dpi=dpi,
            format="png",
            color="#111827",
        )
    except (ValueError, RuntimeError) as exc:
        raise ValueError("The equation contains unsupported LaTeX syntax.") from exc

    return output.getvalue()
