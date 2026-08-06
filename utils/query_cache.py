import threading
from collections.abc import Callable
from typing import Any

import streamlit as st

from utils.runtime_config import uses_postgres
from utils.user_scope import get_user_scope


_revision_lock = threading.Lock()
_force_revisions: dict[str, int] = {}
_all_data_revisions: dict[str, int] = {}
_table_revisions: dict[tuple[str, str], int] = {}


_READER_TABLES: dict[str, tuple[str, ...]] = {
    "get_projects": ("projects",),
    "get_chats": ("chats",),
    "get_project_workspace": ("chats", "messages", "project_ideas"),
    "get_messages": ("messages",),
    "get_audio_records": ("audio_records",),
    "get_audio_record_by_message_id": ("audio_records",),
    "get_experiment_ai_messages": ("experiment_ai_messages",),
    "get_project_messages": ("messages", "chats"),
    "get_project_ideas": ("project_ideas",),
    "get_chat_summary": ("summaries",),
    "get_project_summary": ("summaries",),
    "get_all_project_summaries": ("summaries", "chats"),
    "get_mindmap_last_sync": ("mindmap_source_state",),
    "get_mindmap_node_by_key": ("mindmap_nodes",),
    "get_mindmap_nodes": ("mindmap_nodes",),
    "get_mindmap_edges": ("mindmap_edges",),
    "get_library_folders": ("library_folders", "library_items"),
    "get_library_item": (
        "library_items",
        "library_folders",
        "library_item_projects",
        "library_item_tags",
        "library_tags",
        "projects",
    ),
    "get_library_items": (
        "library_items",
        "library_folders",
        "library_item_projects",
        "library_item_tags",
        "library_tags",
        "projects",
    ),
    "get_library_item_count": (
        "library_items",
        "library_item_projects",
        "library_item_tags",
        "library_tags",
    ),
    "get_library_stats": ("library_items", "library_folders"),
    "get_library_external_keys": ("library_items",),
    "get_project_discovery_results": (
        "project_discovery_sets",
        "project_discovery_set_papers",
    ),
    "get_latest_project_discovery_results": (
        "project_discovery_sets",
        "project_discovery_set_papers",
    ),
    "get_manuscripts": (
        "manuscripts",
        "manuscript_sections",
        "manuscript_sources",
        "manuscript_versions",
    ),
    "get_manuscript_workspace": (
        "manuscripts",
        "projects",
        "manuscript_sections",
        "manuscript_sources",
        "library_items",
        "manuscript_assets",
        "manuscript_submission_profiles",
    ),
    "get_manuscript_ai_context": ("manuscript_ai_contexts",),
    "get_manuscript_ai_messages": ("manuscript_ai_messages",),
    "get_manuscript_evidence": ("manuscript_evidence",),
    "get_project_library_sources": (
        "library_items",
        "library_item_projects",
    ),
    "get_project_evidence_candidates": (
        "chats",
        "summaries",
        "project_ideas",
    ),
    "get_manuscript_version": ("manuscript_versions",),
    "get_manuscript_versions_page": (
        "manuscript_versions",
        "manuscript_version_comments",
    ),
    "get_manuscript_version_comments_for_versions": (
        "manuscript_version_comments",
    ),
    "get_analysis_runs": ("analysis_runs",),
    "get_analysis_run": ("analysis_runs",),
}


def _scope_key() -> str:
    scope = get_user_scope()

    if scope is None:
        raise RuntimeError("Cached private data requires an authenticated user scope.")

    return scope.storage_key


def _reader_tables(reader: Callable) -> tuple[str, ...] | None:
    return _READER_TABLES.get(reader.__name__)


def current_user_data_revision(
    tables: tuple[str, ...] | None = None,
) -> tuple[int, ...]:
    key = _scope_key()

    with _revision_lock:
        force_revision = _force_revisions.get(key, 0)

        if tables is None:
            return (force_revision, _all_data_revisions.get(key, 0))

        return (
            force_revision,
            *(
                _table_revisions.get((key, table), 0)
                for table in sorted(set(tables))
            ),
        )


def invalidate_user_data_cache(tables=None) -> tuple[int, ...]:
    """Invalidate only readers that depend on the committed tables."""
    key = _scope_key()
    normalized_tables = {
        str(table).strip().lower()
        for table in (tables or ())
        if str(table).strip()
    }

    with _revision_lock:
        _all_data_revisions[key] = _all_data_revisions.get(key, 0) + 1

        if not normalized_tables:
            _force_revisions[key] = _force_revisions.get(key, 0) + 1
            return (
                _force_revisions[key],
                _all_data_revisions[key],
            )

        revisions = []

        for table in sorted(normalized_tables):
            table_key = (key, table)
            _table_revisions[table_key] = _table_revisions.get(table_key, 0) + 1
            revisions.append(_table_revisions[table_key])

        return tuple(revisions)


@st.cache_data(ttl=30, max_entries=512, show_spinner=False)
def _cached_read(
    scope_key: str,
    revision: tuple[int, ...],
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
    revision = current_user_data_revision(_reader_tables(reader))
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
