import atexit
import os
import re
import shutil
import sqlite3
import time
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from utils.runtime_config import postgres_url, uses_postgres
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


@lru_cache(maxsize=2)
def _limit_postgres_pool(dsn: str):
    try:
        from psycopg_pool import ConnectionPool
    except ImportError as exc:
        raise RuntimeError("The PostgreSQL driver is not installed.") from exc

    pool = ConnectionPool(
        conninfo=dsn,
        min_size=0,
        max_size=env_int("MAX_RESOURCE_LIMIT_POOL_SIZE", 4, maximum=16),
        timeout=10,
        max_lifetime=1800,
        max_idle=300,
        kwargs={
            "connect_timeout": 10,
            "application_name": "research-journal-resource-limits",
        },
        open=True,
    )
    atexit.register(pool.close)
    return pool


@contextmanager
def _connect_postgres():
    dsn = re.sub(
        r"^postgresql\+psycopg://",
        "postgresql://",
        postgres_url(),
        count=1,
    )

    if not dsn:
        raise RuntimeError("The PostgreSQL connection is not configured.")

    with _limit_postgres_pool(dsn).connection() as conn:
        yield conn


def _principal() -> str:
    scope = get_user_scope()

    if scope is None:
        return "local-workspace"

    if uses_postgres():
        from db.database import get_current_app_user_id
        from utils.query_cache import cached_identity_read

        return cached_identity_read(get_current_app_user_id)

    return scope.storage_key


def purge_current_principal_usage():
    scope = get_user_scope()

    if scope is None:
        return

    if uses_postgres():
        principal = _principal()
        with _connect_postgres() as conn:
            with conn.transaction():
                conn.execute(
                    "DELETE FROM app_private.usage_counters WHERE principal = %s",
                    (principal,),
                )
                conn.execute(
                    "DELETE FROM app_private.resource_leases WHERE principal = %s",
                    (principal,),
                )
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
    principal = _principal()
    policies = [
        (principal, 3600, per_user_hour, "hourly user quota"),
        (principal, 86400, per_user_day, "daily user quota"),
        ("*", 60, global_per_minute, "application-wide minute quota"),
    ]

    if global_per_day is not None:
        policies.append(("*", 86400, global_per_day, "application-wide daily quota"))
    if uses_postgres():
        _consume_postgres_rate_limit(resource, policies, now)
        return

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


def _consume_postgres_rate_limit(resource: str, policies: list, now: int):
    with _connect_postgres() as conn:
        with conn.transaction():
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (resource,),
            )

            for principal, window_seconds, limit, label in policies:
                window_start = now - (now % window_seconds)
                row = conn.execute(
                    """
                    SELECT request_count
                    FROM app_private.usage_counters
                    WHERE resource = %s AND principal = %s
                      AND window_seconds = %s AND window_start = %s
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
                    INSERT INTO app_private.usage_counters (
                        resource, principal, window_seconds, window_start, request_count
                    ) VALUES (%s, %s, %s, %s, 1)
                    ON CONFLICT(resource, principal, window_seconds, window_start)
                    DO UPDATE SET request_count =
                        app_private.usage_counters.request_count + 1
                    """,
                    (resource, principal, window_seconds, window_start),
                )

            conn.execute(
                "DELETE FROM app_private.usage_counters WHERE window_start < %s",
                (now - 172800,),
            )


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

    if uses_postgres():
        with _postgres_concurrency_slot(
            resource,
            global_limit=global_limit,
            lease_seconds=lease_seconds,
        ):
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


@contextmanager
def _postgres_concurrency_slot(
    resource: str,
    *,
    global_limit: int,
    lease_seconds: int,
):
    now = int(time.time())
    lease_id = uuid4()
    with _connect_postgres() as conn:
        with conn.transaction():
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (resource,),
            )
            conn.execute(
                """
                DELETE FROM app_private.resource_leases
                WHERE resource = %s AND expires_at <= %s
                """,
                (resource, now),
            )
            active = conn.execute(
                """
                SELECT COUNT(*) FROM app_private.resource_leases
                WHERE resource = %s
                """,
                (resource,),
            ).fetchone()[0]

            if int(active) >= global_limit:
                raise ResourceLimitError(
                    f"Too many {resource} operations are already running. Try again shortly."
                )

            conn.execute(
                """
                INSERT INTO app_private.resource_leases (
                    resource, lease_id, principal, expires_at
                ) VALUES (%s, %s, %s, %s)
                """,
                (resource, lease_id, _principal(), now + lease_seconds),
            )
        try:
            yield
        finally:
            with conn.transaction():
                conn.execute(
                    "DELETE FROM app_private.resource_leases WHERE lease_id = %s",
                    (lease_id,),
                )


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
