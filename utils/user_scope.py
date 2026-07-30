import hashlib
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UserScope:
    issuer: str
    subject: str
    storage_key: str


_current_user_scope: ContextVar[UserScope | None] = ContextVar(
    "research_journal_user_scope",
    default=None,
)
_allow_unscoped_paths: ContextVar[bool] = ContextVar(
    "research_journal_allow_unscoped_paths",
    default=False,
)


def activate_user_scope(issuer: str, subject: str) -> UserScope:
    normalized_issuer = str(issuer or "").strip().rstrip("/")
    normalized_subject = str(subject or "").strip()

    if not normalized_issuer or not normalized_subject:
        raise ValueError("The authenticated identity must include iss and sub claims.")

    digest = hashlib.sha256(
        f"{normalized_issuer}\0{normalized_subject}".encode("utf-8")
    ).hexdigest()
    scope = UserScope(
        issuer=normalized_issuer,
        subject=normalized_subject,
        storage_key=digest[:24],
    )
    _current_user_scope.set(scope)
    return scope


def clear_user_scope():
    _current_user_scope.set(None)


def get_user_scope() -> UserScope | None:
    return _current_user_scope.get()


@contextmanager
def allow_unscoped_paths():
    """Explicitly allow legacy paths for migrations and isolated tests only."""
    token = _allow_unscoped_paths.set(True)

    try:
        yield
    finally:
        _allow_unscoped_paths.reset(token)


def _uses_legacy_workspace(scope: UserScope) -> bool:
    legacy_subject = os.getenv("AUTH0_LEGACY_OWNER_SUB", "").strip()

    if not legacy_subject or legacy_subject != scope.subject:
        return False

    legacy_issuer = os.getenv("AUTH0_LEGACY_OWNER_ISSUER", "").strip().rstrip("/")
    return not legacy_issuer or legacy_issuer == scope.issuer


def scoped_path(base_path: str | Path) -> Path:
    """Return a private path for the active user.

    Access fails closed without an authenticated scope. Migrations and tests
    must opt into an unscoped legacy path explicitly. A configured legacy owner
    keeps the old single-user paths after successful authentication.
    """
    base = Path(base_path).expanduser()
    scope = get_user_scope()

    if scope is None:
        if _allow_unscoped_paths.get():
            return base

        raise RuntimeError(
            "Private storage cannot be accessed without an authenticated user scope."
        )

    if _uses_legacy_workspace(scope):
        return base

    return base.parent / "users" / scope.storage_key / base.name
