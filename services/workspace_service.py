import os
import shutil
from pathlib import Path

from db.database import get_connection
from services.resource_limits import purge_current_principal_usage
from services.supabase_storage import ALLOWED_BUCKETS, delete_user_objects
from utils.runtime_config import uses_postgres, uses_supabase_storage
from utils.user_scope import get_user_scope, scoped_path


def _configured_workspace_paths() -> tuple[Path, ...]:
    return (
        scoped_path(os.getenv("DATABASE_PATH", "data/app.db")),
        scoped_path(os.getenv("AUDIO_STORAGE_PATH", "data/audio")),
        scoped_path(os.getenv("LIBRARY_STORAGE_PATH", "data/library")),
        scoped_path(os.getenv("DATA_ANALYSIS_STORAGE_PATH", "data/analysis")),
        scoped_path(
            os.getenv(
                "MANUSCRIPT_ASSET_STORAGE_PATH",
                "data/manuscript_assets",
            )
        ),
    )


def current_user_workspace_roots() -> tuple[Path, ...]:
    scope = get_user_scope()

    if scope is None:
        raise RuntimeError("An authenticated user scope is required.")

    roots = set()

    for configured_path in _configured_workspace_paths():
        resolved = configured_path.expanduser().resolve(strict=False)
        root = next(
            (
                candidate
                for candidate in (resolved, *resolved.parents)
                if candidate.name == scope.storage_key
                and candidate.parent.name == "users"
            ),
            None,
        )

        if root is None:
            raise RuntimeError(
                "Automatic workspace deletion is unavailable for the legacy "
                "owner or for storage paths outside the scoped user directory."
            )

        roots.add(root)

    return tuple(sorted(roots, key=str))


def delete_current_user_workspace():
    if uses_postgres():
        if uses_supabase_storage():
            # Storage RLS can resolve the owner only while app_users still
            # contains the identity, so objects must be removed first.
            for bucket in sorted(ALLOWED_BUCKETS):
                delete_user_objects(bucket)

        conn = get_connection()

        try:
            conn.execute("SELECT public.delete_current_workspace()")
            conn.commit()
        finally:
            conn.close()
        return

    roots = current_user_workspace_roots()
    purge_current_principal_usage()

    for root in roots:
        if root.exists():
            shutil.rmtree(root)
