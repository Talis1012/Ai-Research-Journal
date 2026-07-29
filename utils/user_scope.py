import hashlib
import os
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


def _uses_legacy_workspace(scope: UserScope) -> bool:
    legacy_subject = os.getenv("AUTH0_LEGACY_OWNER_SUB", "").strip()

    if not legacy_subject or legacy_subject != scope.subject:
        return False

    legacy_issuer = os.getenv("AUTH0_LEGACY_OWNER_ISSUER", "").strip().rstrip("/")
    return not legacy_issuer or legacy_issuer == scope.issuer


def scoped_path(base_path: str | Path) -> Path:
    """Return a private path for the active user.

    Without an active authenticated scope (for example, in unit tests), the
    original path is preserved. A configured legacy owner also keeps the old
    single-user paths so existing data remains available only to that account.
    """
    base = Path(base_path).expanduser()
    scope = get_user_scope()

    if scope is None or _uses_legacy_workspace(scope):
        return base

    return base.parent / "users" / scope.storage_key / base.name
