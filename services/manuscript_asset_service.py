import io
import os
import shutil
import tempfile
import warnings
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from services.resource_limits import enforce_storage_quota, env_int
from services.supabase_storage import (
    delete_object,
    delete_user_objects,
    download_bytes,
    enforce_user_storage_quota,
    is_storage_reference,
    storage_object_size,
    upload_bytes,
)
from utils.runtime_config import uses_supabase_storage
from utils.user_scope import scoped_path


MAX_FIGURE_FILE_SIZE = 25 * 1024 * 1024
MAX_FIGURE_PIXELS = 50_000_000


def get_manuscript_asset_storage_path() -> Path:
    storage_path = scoped_path(
        os.getenv("MANUSCRIPT_ASSET_STORAGE_PATH", "data/manuscript_assets")
    )
    storage_path.mkdir(parents=True, exist_ok=True, mode=0o700)

    try:
        storage_path.chmod(0o700)
    except OSError:
        pass

    return storage_path


def _path_inside_asset_storage(path: str | Path) -> Path:
    storage_path = get_manuscript_asset_storage_path().resolve()
    resolved_path = Path(path).expanduser().resolve()

    if resolved_path != storage_path and storage_path not in resolved_path.parents:
        raise ValueError("The requested figure is outside manuscript storage.")

    return resolved_path


def save_figure_upload(
    uploaded_file,
    manuscript_id: int,
    *,
    replacing_storage_path: str | None = None,
) -> dict:
    original_filename = Path(str(uploaded_file.name or "")).name.strip()

    if not original_filename:
        raise ValueError("The uploaded figure must have a file name.")

    file_bytes = uploaded_file.getvalue()

    if not file_bytes:
        raise ValueError("The uploaded figure is empty.")

    if len(file_bytes) > MAX_FIGURE_FILE_SIZE:
        raise ValueError("The figure is larger than the 25 MB upload limit.")

    max_pixels = env_int(
        "MAX_FIGURE_PIXELS",
        MAX_FIGURE_PIXELS,
        maximum=MAX_FIGURE_PIXELS,
    )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)

            with Image.open(io.BytesIO(file_bytes)) as opened:
                width, height = opened.size

                if width <= 0 or height <= 0 or width * height > max_pixels:
                    raise ValueError("The figure dimensions are too large.")

                if int(getattr(opened, "n_frames", 1)) != 1:
                    raise ValueError("Animated or multi-page images are not supported.")

                opened.verify()

            with Image.open(io.BytesIO(file_bytes)) as opened:
                image = ImageOps.exif_transpose(opened)
                image.load()

                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert(
                        "RGBA" if "transparency" in image.info else "RGB"
                    )

                normalized = io.BytesIO()
                image.save(normalized, format="PNG", compress_level=6)
                normalized_bytes = normalized.getvalue()
                width, height = image.size

        max_normalized_size = env_int(
            "MAX_NORMALIZED_FIGURE_SIZE",
            50 * 1024 * 1024,
            maximum=100 * 1024 * 1024,
        )

        if len(normalized_bytes) > max_normalized_size:
            raise ValueError("The normalized figure is too large to store.")

        if uses_supabase_storage():
            replaced_size = (
                storage_object_size(
                    replacing_storage_path,
                    bucket="manuscript-assets",
                )
                if replacing_storage_path
                and is_storage_reference(replacing_storage_path)
                else 0
            )
            enforce_user_storage_quota(
                "manuscript-assets",
                len(normalized_bytes),
                quota_bytes=env_int(
                    "MAX_MANUSCRIPT_ASSET_STORAGE_BYTES",
                    250 * 1024 * 1024,
                    minimum=max_normalized_size,
                ),
                label="manuscript figure",
                max_files=env_int(
                    "MAX_STORED_MANUSCRIPT_FIGURES",
                    500,
                    maximum=5000,
                ),
                reclaim_bytes=replaced_size,
                replacing_files=1 if replaced_size > 0 else 0,
            )
            storage_path = upload_bytes(
                "manuscript-assets",
                f"manuscripts/{int(manuscript_id)}/{uuid4().hex}.png",
                normalized_bytes,
                content_type="image/png",
            )

            if replacing_storage_path and is_storage_reference(replacing_storage_path):
                delete_object(replacing_storage_path, bucket="manuscript-assets")
        else:
            asset_root = get_manuscript_asset_storage_path()
            replaced_size = 0

            if replacing_storage_path:
                replaced_path = _path_inside_asset_storage(replacing_storage_path)

                if replaced_path.is_file():
                    replaced_size = replaced_path.stat().st_size

            enforce_storage_quota(
                asset_root,
                len(normalized_bytes),
                quota_bytes=env_int(
                    "MAX_MANUSCRIPT_ASSET_STORAGE_BYTES",
                    250 * 1024 * 1024,
                    minimum=max_normalized_size,
                ),
                label="manuscript figure",
                max_files=env_int(
                    "MAX_STORED_MANUSCRIPT_FIGURES",
                    500,
                    maximum=5000,
                ),
                reclaim_bytes=replaced_size,
                replacing_file=replaced_size > 0,
            )
            target_dir = asset_root / str(int(manuscript_id))
            target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            target_path = target_dir / f"{uuid4().hex}.png"
            target_path.write_bytes(normalized_bytes)

            try:
                target_dir.chmod(0o700)
                target_path.chmod(0o600)
            except OSError:
                pass

            storage_path = str(target_path)
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
    ) as exc:
        raise ValueError("Upload a valid PNG, JPEG, WEBP, GIF, BMP or TIFF image.") from exc

    return {
        "original_filename": original_filename,
        "storage_path": storage_path,
        "mime_type": "image/png",
        "content": {
            "width": width,
            "height": height,
            "file_size": len(normalized_bytes),
        },
    }


def read_manuscript_asset_file(storage_path: str) -> bytes:
    if is_storage_reference(storage_path):
        return download_bytes(storage_path, bucket="manuscript-assets")

    safe_path = _path_inside_asset_storage(storage_path)

    if not safe_path.is_file():
        raise FileNotFoundError("The stored figure could not be found.")

    return safe_path.read_bytes()


def delete_manuscript_asset_file(storage_path: str | None):
    if not storage_path:
        return

    if is_storage_reference(storage_path):
        delete_object(storage_path, bucket="manuscript-assets")
        return

    safe_path = _path_inside_asset_storage(storage_path)

    if safe_path.is_file():
        safe_path.unlink()

    storage_root = get_manuscript_asset_storage_path().resolve()
    parent = safe_path.parent

    if parent != storage_root:
        try:
            parent.rmdir()
        except OSError:
            pass


def delete_manuscript_asset_directory(manuscript_id: int):
    if uses_supabase_storage():
        delete_user_objects(
            "manuscript-assets",
            f"manuscripts/{int(manuscript_id)}",
        )
        return

    directory = _path_inside_asset_storage(
        get_manuscript_asset_storage_path() / str(int(manuscript_id))
    )

    if directory.is_symlink():
        directory.unlink()
    elif directory.is_dir():
        shutil.rmtree(directory)


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
