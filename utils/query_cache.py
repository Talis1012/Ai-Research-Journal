import threading
from collections.abc import Callable
from typing import Any

import streamlit as st

from utils.runtime_config import uses_postgres
from utils.user_scope import get_user_scope


_revision_lock = threading.Lock()
_user_revisions: dict[str, int] = {}


def _scope_key() -> str:
    scope = get_user_scope()

    if scope is None:
        raise RuntimeError("Cached private data requires an authenticated user scope.")

    return scope.storage_key


def current_user_data_revision() -> int:
    key = _scope_key()

    with _revision_lock:
        return _user_revisions.get(key, 0)


def invalidate_user_data_cache() -> int:
    """Advance the active user's cache revision after a committed mutation."""
    key = _scope_key()

    with _revision_lock:
        revision = _user_revisions.get(key, 0) + 1
        _user_revisions[key] = revision
        return revision


@st.cache_data(ttl=30, max_entries=512, show_spinner=False)
def _cached_read(
    scope_key: str,
    revision: int,
    reader_name: str,
    args: tuple,
    kwargs: tuple[tuple[str, Any], ...],
    _reader: Callable,
):
    del scope_key, revision, reader_name
    return _reader(*args, **dict(kwargs))


@st.cache_data(ttl=240, max_entries=256, show_spinner=False)
def _cached_identity_read(
    scope_key: str,
    reader_name: str,
    args: tuple,
    kwargs: tuple[tuple[str, Any], ...],
    _reader: Callable,
):
    del scope_key, reader_name
    return _reader(*args, **dict(kwargs))


@st.cache_data(ttl=120, max_entries=4, show_spinner=False)
def _cached_blob_read(
    scope_key: str,
    reader_name: str,
    args: tuple,
    kwargs: tuple[tuple[str, Any], ...],
    _reader: Callable,
):
    del scope_key, reader_name
    return _reader(*args, **dict(kwargs))


def cached_read(reader: Callable, *args, **kwargs):
    """Cache a PostgreSQL read briefly and isolate it by user and revision.

    SQLite remains uncached so local tests and filesystem-backed development
    preserve their existing immediate-read semantics.
    """
    if not uses_postgres():
        return reader(*args, **kwargs)

    scope_key = _scope_key()
    revision = current_user_data_revision()
    reader_name = f"{reader.__module__}.{reader.__qualname__}"
    return _cached_read(
        scope_key,
        revision,
        reader_name,
        tuple(args),
        tuple(sorted(kwargs.items())),
        _reader=reader,
    )


def cached_identity_read(reader: Callable, *args, **kwargs):
    """Cache stable private reads such as identity and short-lived URLs."""
    if not uses_postgres():
        return reader(*args, **kwargs)

    return _cached_identity_read(
        _scope_key(),
        f"{reader.__module__}.{reader.__qualname__}",
        tuple(args),
        tuple(sorted(kwargs.items())),
        _reader=reader,
    )


def cached_blob_read(reader: Callable, *args, **kwargs):
    """Cache a few large private objects briefly to bound server memory."""
    if not uses_postgres():
        return reader(*args, **kwargs)

    return _cached_blob_read(
        _scope_key(),
        f"{reader.__module__}.{reader.__qualname__}",
        tuple(args),
        tuple(sorted(kwargs.items())),
        _reader=reader,
    )
