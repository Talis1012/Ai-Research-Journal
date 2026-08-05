import os
from typing import Any


def _streamlit_runtime_active() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx(suppress_warning=True) is not None
    except (ImportError, RuntimeError):
        return False


def _secret(*keys: str) -> Any:
    if not _streamlit_runtime_active():
        return None

    try:
        import streamlit as st

        value: Any = st.secrets

        for key in keys:
            value = value[key]

        return value
    except (KeyError, TypeError, AttributeError, FileNotFoundError):
        return None
    except Exception:
        return None


def postgres_url() -> str:
    configured = str(os.getenv("SUPABASE_DATABASE_URL") or "").strip()

    if configured:
        return configured

    return str(_secret("connections", "supabase_postgres", "url") or "").strip()


def supabase_url() -> str:
    configured = str(os.getenv("SUPABASE_URL") or "").strip()

    if configured:
        return configured.rstrip("/")

    return str(_secret("supabase", "url") or "").strip().rstrip("/")


def supabase_publishable_key() -> str:
    configured = str(os.getenv("SUPABASE_PUBLISHABLE_KEY") or "").strip()

    if configured:
        return configured

    return str(_secret("supabase", "publishable_key") or "").strip()


def database_backend() -> str:
    explicit = str(os.getenv("DATABASE_BACKEND") or "").strip().lower()

    if explicit in {"postgres", "postgresql", "supabase"}:
        return "postgres"

    if explicit == "sqlite":
        return "sqlite"

    # Streamlit uses Supabase automatically when its connection secret exists.
    # Unit tests and maintenance scripts stay on SQLite unless they opt in.
    return "postgres" if postgres_url() else "sqlite"


def uses_postgres() -> bool:
    return database_backend() == "postgres"


def uses_supabase_storage() -> bool:
    return uses_postgres() and bool(supabase_url() and supabase_publishable_key())
