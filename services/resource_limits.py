import os
import shutil
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from utils.user_scope import get_user_scope


class ResourceLimitError(RuntimeError):
    """Raised when a request would exceed an application resource limit."""


def env_int(
    name: str,
    default: int,
    *,
    minimum: int = 1,
    maximum: int = 9_223_372_036_854_775_807,
) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default

    return max(minimum, min(value, maximum))


def _rate_limit_db_path() -> Path:
    configured = os.getenv("RATE_LIMIT_DATABASE_PATH", "").strip()

    if configured:
        return Path(configured).expanduser()

    database_path = Path(os.getenv("DATABASE_PATH", "data/app.db")).expanduser()
    return database_path.with_name("security_limits.db")


def _connect() -> sqlite3.Connection:
    db_path = _rate_limit_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    try:
        db_path.parent.chmod(0o700)
    except OSError:
        pass

    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usage_counters (
            resource TEXT NOT NULL,
            principal TEXT NOT NULL,
            window_seconds INTEGER NOT NULL,
            window_start INTEGER NOT NULL,
            request_count INTEGER NOT NULL,
            PRIMARY KEY (resource, principal, window_seconds, window_start)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS resource_leases (
            resource TEXT NOT NULL,
            lease_id TEXT PRIMARY KEY,
            principal TEXT NOT NULL,
            expires_at INTEGER NOT NULL
        )
        """
    )
    conn.commit()

    try:
        db_path.chmod(0o600)
    except OSError:
        pass

    return conn


def _principal() -> str:
    scope = get_user_scope()
    return scope.storage_key if scope else "local-workspace"


def purge_current_principal_usage():
    scope = get_user_scope()

    if scope is None:
        return

    conn = _connect()

    try:
        with conn:
            conn.execute(
                "DELETE FROM usage_counters WHERE principal = ?",
                (scope.storage_key,),
            )
            conn.execute(
                "DELETE FROM resource_leases WHERE principal = ?",
                (scope.storage_key,),
            )
    finally:
        conn.close()


def consume_rate_limit(
    resource: str,
    *,
    per_user_hour: int,
    per_user_day: int,
    global_per_minute: int,
    global_per_day: int | None = None,
):
    """Atomically consume one request from user and application-wide quotas."""
    if get_user_scope() is None and os.getenv("ENFORCE_UNSCOPED_LIMITS", "0") != "1":
        return

    now = int(time.time())
    policies = [
        (_principal(), 3600, per_user_hour, "hourly user quota"),
        (_principal(), 86400, per_user_day, "daily user quota"),
        ("*", 60, global_per_minute, "application-wide minute quota"),
    ]

    if global_per_day is not None:
        policies.append(("*", 86400, global_per_day, "application-wide daily quota"))
    conn = _connect()

    try:
        conn.execute("BEGIN IMMEDIATE")

        for principal, window_seconds, limit, label in policies:
            window_start = now - (now % window_seconds)
            row = conn.execute(
                """
                SELECT request_count
                FROM usage_counters
                WHERE resource = ? AND principal = ?
                  AND window_seconds = ? AND window_start = ?
                """,
                (resource, principal, window_seconds, window_start),
            ).fetchone()
            current = int(row[0]) if row else 0

            if current >= limit:
                raise ResourceLimitError(
                    f"{resource} {label} reached. Please wait before trying again."
                )

        for principal, window_seconds, _, _ in policies:
            window_start = now - (now % window_seconds)
            conn.execute(
                """
                INSERT INTO usage_counters (
                    resource, principal, window_seconds, window_start, request_count
                ) VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(resource, principal, window_seconds, window_start)
                DO UPDATE SET request_count = request_count + 1
                """,
                (resource, principal, window_seconds, window_start),
            )

        conn.execute(
            "DELETE FROM usage_counters WHERE window_start < ?",
            (now - 172800,),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def concurrency_slot(
    resource: str,
    *,
    global_limit: int,
    lease_seconds: int,
):
    """Acquire an application-wide lease that is safe across local processes."""
    if get_user_scope() is None and os.getenv("ENFORCE_UNSCOPED_LIMITS", "0") != "1":
        yield
        return

    now = int(time.time())
    lease_id = uuid4().hex
    conn = _connect()

    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM resource_leases WHERE resource = ? AND expires_at <= ?",
            (resource, now),
        )
        active = conn.execute(
            "SELECT COUNT(*) FROM resource_leases WHERE resource = ?",
            (resource,),
        ).fetchone()[0]

        if int(active) >= global_limit:
            raise ResourceLimitError(
                f"Too many {resource} operations are already running. Try again shortly."
            )

        conn.execute(
            """
            INSERT INTO resource_leases (resource, lease_id, principal, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (resource, lease_id, _principal(), now + lease_seconds),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise

    try:
        yield
    finally:
        try:
            conn.execute("DELETE FROM resource_leases WHERE lease_id = ?", (lease_id,))
            conn.commit()
        finally:
            conn.close()


def directory_usage(root: str | Path) -> tuple[int, int]:
    path = Path(root)

    if not path.exists():
        return 0, 0

    total = 0
    count = 0

    for candidate in path.rglob("*"):
        try:
            if candidate.is_file() and not candidate.is_symlink():
                total += candidate.stat().st_size
                count += 1
        except OSError:
            continue

    return total, count


def directory_size_bytes(root: str | Path) -> int:
    return directory_usage(root)[0]


def enforce_storage_quota(
    root: str | Path,
    incoming_bytes: int,
    *,
    quota_bytes: int,
    label: str,
    max_files: int | None = None,
    reclaim_bytes: int = 0,
    replacing_file: bool = False,
):
    incoming = max(0, int(incoming_bytes))
    used, file_count = directory_usage(root)
    effective_used = max(0, used - max(0, int(reclaim_bytes)))

    if effective_used + incoming > quota_bytes:
        quota_mb = quota_bytes // (1024 * 1024)
        raise ResourceLimitError(
            f"The {label} storage quota of {quota_mb} MB would be exceeded."
        )

    if max_files is not None and file_count >= max_files and not replacing_file:
        raise ResourceLimitError(
            f"The {label} limit of {max_files} stored files has been reached."
        )

    reserve = env_int(
        "MIN_FREE_DISK_BYTES",
        1024 * 1024 * 1024,
        minimum=100 * 1024 * 1024,
    )
    disk = shutil.disk_usage(Path(root))

    if disk.free - incoming < reserve:
        raise ResourceLimitError(
            "The server is low on free disk space and cannot store another file."
        )
