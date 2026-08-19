import atexit
import json
import os
import re
import shutil
import sqlite3
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from services.resource_limits import ResourceLimitError, env_int
from utils.runtime_config import postgres_url, uses_postgres
from utils.user_scope import get_user_scope, scoped_path


try:
    import psycopg
    from psycopg_pool import ConnectionPool
    from psycopg.rows import dict_row
except ImportError:  # SQLite-only test and maintenance environments.
    psycopg = None
    ConnectionPool = None
    dict_row = None


DatabaseIntegrityError = (
    (sqlite3.IntegrityError, psycopg.IntegrityError)
    if psycopg is not None
    else (sqlite3.IntegrityError,)
)


load_dotenv()


def get_db_path() -> str:
    base_path = os.getenv("DATABASE_PATH", "data/app.db")
    return str(scoped_path(base_path))


_IDENTITY_TABLES = {
    "projects",
    "chats",
    "messages",
    "experiment_ai_messages",
    "audio_records",
    "summaries",
    "project_ideas",
    "mindmap_nodes",
    "mindmap_edges",
    "mindmap_source_state",
    "library_folders",
    "library_items",
    "library_tags",
    "research_cases",
    "analysis_runs",
    "project_discovery_set_papers",
    "manuscripts",
    "manuscript_sections",
    "manuscript_evidence",
    "manuscript_citations",
    "manuscript_versions",
    "manuscript_version_comments",
    "manuscript_ai_messages",
    "manuscript_assets",
}


def _postgres_dsn() -> str:
    dsn = postgres_url()

    if not dsn:
        raise RuntimeError(
            "Conexiunea PostgreSQL nu este configurată. Definește "
            "`SUPABASE_DATABASE_URL` sau `[connections.supabase_postgres].url`."
        )

    # Streamlit/SQLAlchemy examples commonly include the driver suffix, while
    # psycopg expects the standard PostgreSQL URI scheme.
    return re.sub(r"^postgresql\+psycopg://", "postgresql://", dsn, count=1)


def _replace_qmark_placeholders(statement: str) -> str:
    output = []
    quote = None
    index = 0

    while index < len(statement):
        character = statement[index]

        if quote:
            output.append(character)

            if character == quote:
                if index + 1 < len(statement) and statement[index + 1] == quote:
                    output.append(statement[index + 1])
                    index += 1
                else:
                    quote = None
        elif character in {"'", '"'}:
            quote = character
            output.append(character)
        elif character == "?":
            output.append("%s")
        else:
            output.append(character)

        index += 1

    return "".join(output)


def _translate_postgres_sql(statement: str) -> str:
    translated = statement
    ignored_insert = bool(
        re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", translated, re.I)
    )
    translated = re.sub(
        r"\bINSERT\s+OR\s+IGNORE\s+INTO\b",
        "INSERT INTO",
        translated,
        flags=re.I,
    )
    translated = re.sub(r"\s+COLLATE\s+NOCASE\b", "", translated, flags=re.I)
    translated = re.sub(r"\bLIKE\b", "ILIKE", translated, flags=re.I)
    translated = re.sub(
        r"ON\s+CONFLICT\s*\(\s*project_id\s*,\s*node_key\s*\)",
        "ON CONFLICT(user_id, project_id, node_key)",
        translated,
        flags=re.I,
    )
    translated = re.sub(
        r"ON\s+CONFLICT\s*\(\s*project_id\s*,\s*source_type\s*,\s*source_id\s*\)",
        "ON CONFLICT(user_id, project_id, source_type, source_id)",
        translated,
        flags=re.I,
    )

    if ignored_insert and not re.search(r"\bON\s+CONFLICT\b", translated, re.I):
        translated = translated.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

    return _replace_qmark_placeholders(translated)


def _insert_table(statement: str) -> str | None:
    match = re.match(
        r"\s*INSERT\s+INTO\s+(?:public\.)?([a-zA-Z_][a-zA-Z0-9_]*)",
        statement,
        re.I,
    )
    return match.group(1).lower() if match else None


def _mutated_tables(statement: str) -> set[str]:
    normalized = str(statement or "").lstrip()
    patterns = (
        r"\bINSERT\s+INTO\s+(?:public\.)?([a-zA-Z_][a-zA-Z0-9_]*)",
        r"\bUPDATE\s+(?:public\.)?([a-zA-Z_][a-zA-Z0-9_]*)",
        r"\bDELETE\s+FROM\s+(?:public\.)?([a-zA-Z_][a-zA-Z0-9_]*)",
    )
    return {
        match.group(1).lower()
        for pattern in patterns
        for match in re.finditer(pattern, normalized, re.I)
    }


def _mutates_data(statement: str) -> bool:
    return bool(_mutated_tables(statement))


class _PostgresCursor:
    def __init__(self, connection, cursor=None):
        self._connection = connection
        self._cursor = cursor or connection._raw.cursor()
        self._lastrowid = None

    def execute(self, statement, params=None):
        translated = _translate_postgres_sql(str(statement))
        table = _insert_table(translated)

        if table in _IDENTITY_TABLES and not re.search(
            r"\bRETURNING\b",
            translated,
            re.I,
        ):
            translated = translated.rstrip().rstrip(";") + " RETURNING id"

        self._connection._execute_in_request_context(
            self._cursor,
            translated,
            params if params is not None else (),
        )
        self._connection._dirty_tables.update(_mutated_tables(translated))
        self._lastrowid = None

        if table in _IDENTITY_TABLES:
            returned = self._cursor.fetchone()

            if returned:
                self._lastrowid = int(returned["id"])

        return self

    def executemany(self, statement, params_seq):
        translated = _translate_postgres_sql(str(statement))
        self._connection._executemany_in_request_context(
            self._cursor,
            translated,
            params_seq,
        )
        self._connection._dirty_tables.update(_mutated_tables(translated))
        self._lastrowid = None
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def lastrowid(self):
        return self._lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def close(self):
        self._cursor.close()


class _PostgresConnection:
    def __init__(self, raw, pool):
        self._raw = raw
        self._pool = pool
        self._context_ready = False
        self._closed = False
        self._dirty_tables: set[str] = set()

    @staticmethod
    def _request_claims_json():
        scope = get_user_scope()

        if scope is None:
            raise RuntimeError(
                "A PostgreSQL connection requires an authenticated user scope."
            )

        claims = dict(scope.claims)
        claims["iss"] = scope.issuer
        claims["sub"] = scope.subject
        claims.setdefault("role", "authenticated")
        return json.dumps(claims, separators=(",", ":"))

    def _execute_in_request_context(self, cursor, statement, params):
        if self._context_ready:
            return cursor.execute(statement, params)

        claims_json = self._request_claims_json()

        with self._raw.cursor() as context_cursor:
            # Pipeline the RLS setup and the application query so a database
            # operation needs one network round trip instead of several. Using
            # set_config for `role` is equivalent to SET LOCAL ROLE and remains
            # scoped to this transaction.
            with self._raw.pipeline():
                context_cursor.execute(
                    """
                    select
                        set_config('request.jwt.claims', %s, true),
                        set_config('role', 'authenticated', true)
                    """,
                    (claims_json,),
                )
                result = cursor.execute(statement, params)

        self._context_ready = True
        return result

    def _executemany_in_request_context(self, cursor, statement, params_seq):
        if self._context_ready:
            return cursor.executemany(statement, params_seq)

        claims_json = self._request_claims_json()

        with self._raw.cursor() as context_cursor:
            with self._raw.pipeline():
                context_cursor.execute(
                    """
                    select
                        set_config('request.jwt.claims', %s, true),
                        set_config('role', 'authenticated', true)
                    """,
                    (claims_json,),
                )
                result = cursor.executemany(statement, params_seq)

        self._context_ready = True
        return result

    def cursor(self):
        return _PostgresCursor(self)

    def execute(self, statement, params=None):
        return self.cursor().execute(statement, params)

    def executemany(self, statement, params_seq):
        return self.cursor().executemany(statement, params_seq)

    def fetch_many(self, query_specs):
        """Run independent read queries in one PostgreSQL pipeline round trip."""
        specs = list(query_specs)
        cursors = []
        context_cursor = None

        try:
            if not self._context_ready:
                context_cursor = self._raw.cursor()

            with self._raw.pipeline():
                if context_cursor is not None:
                    context_cursor.execute(
                        """
                        select
                            set_config('request.jwt.claims', %s, true),
                            set_config('role', 'authenticated', true)
                        """,
                        (self._request_claims_json(),),
                    )

                for statement, params, mode in specs:
                    translated = _translate_postgres_sql(str(statement))

                    if _mutates_data(translated):
                        raise ValueError("fetch_many accepts read-only queries only.")

                    if mode not in {"one", "all"}:
                        raise ValueError("fetch_many mode must be 'one' or 'all'.")

                    cursor = self._raw.cursor()
                    cursor.execute(translated, params if params is not None else ())
                    cursors.append((cursor, mode))

            self._context_ready = True
            return [
                cursor.fetchone() if mode == "one" else cursor.fetchall()
                for cursor, mode in cursors
            ]
        finally:
            if context_cursor is not None:
                context_cursor.close()

            for cursor, _ in cursors:
                cursor.close()

    def commit(self):
        self._raw.commit()
        self._context_ready = False

        if self._dirty_tables:
            from utils.query_cache import invalidate_user_data_cache

            dirty_tables = set(self._dirty_tables)
            self._dirty_tables.clear()
            invalidate_user_data_cache(dirty_tables)

    def rollback(self):
        self._raw.rollback()
        self._context_ready = False
        self._dirty_tables.clear()

    def close(self):
        if self._closed:
            return

        try:
            self._raw.rollback()
        finally:
            self._context_ready = False
            self._dirty_tables.clear()
            self._closed = True
            self._pool.putconn(self._raw)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False


@lru_cache(maxsize=2)
def _postgres_pool(dsn: str):
    max_size = env_int("MAX_POSTGRES_POOL_SIZE", 8, maximum=32)
    min_size = env_int(
        "MIN_POSTGRES_POOL_SIZE",
        1,
        minimum=0,
        maximum=max_size,
    )
    pool = ConnectionPool(
        conninfo=dsn,
        min_size=min_size,
        max_size=max_size,
        timeout=10,
        max_lifetime=1800,
        max_idle=300,
        kwargs={
            "row_factory": dict_row,
            "connect_timeout": 10,
            "application_name": "research-journal-streamlit",
        },
        open=True,
    )
    atexit.register(pool.close)
    return pool


def _get_postgres_connection():
    if psycopg is None or ConnectionPool is None:
        raise RuntimeError(
            "Driverul PostgreSQL lipsește. Instalează dependențele din requirements.txt."
        )

    pool = _postgres_pool(_postgres_dsn())
    raw = pool.getconn(timeout=10)
    return _PostgresConnection(raw, pool)


def _get_sqlite_connection():
    db_path = get_db_path()
    db_parent = Path(db_path).parent

    db_parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    try:
        db_parent.chmod(0o700)
    except OSError:
        pass

    reserve = env_int(
        "MIN_FREE_DISK_BYTES",
        1024 * 1024 * 1024,
        minimum=100 * 1024 * 1024,
    )

    if shutil.disk_usage(db_parent).free < reserve:
        raise ResourceLimitError(
            "The server is low on free disk space and cannot update the workspace."
        )

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row #project[0] -> project["name"]
    conn.execute("PRAGMA foreign_keys = ON") #Activează relațiile dintre tabele în SQLite
    page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
    max_database_bytes = env_int(
        "MAX_USER_DATABASE_BYTES",
        250 * 1024 * 1024,
        minimum=10 * 1024 * 1024,
    )
    max_pages = max(1, max_database_bytes // page_size)
    conn.execute(f"PRAGMA max_page_count = {max_pages}")

    try:
        Path(db_path).chmod(0o600)
    except OSError:
        pass

    return conn


def get_connection():
    if uses_postgres():
        return _get_postgres_connection()

    return _get_sqlite_connection()


def fetch_many(query_specs):
    """Fetch several independent result sets, pipelined on PostgreSQL."""
    conn = get_connection()

    try:
        if isinstance(conn, _PostgresConnection):
            return conn.fetch_many(query_specs)

        results = []

        for statement, params, mode in query_specs:
            if _mutates_data(statement):
                raise ValueError("fetch_many accepts read-only queries only.")

            cursor = conn.execute(statement, params if params is not None else ())

            if mode == "one":
                results.append(cursor.fetchone())
            elif mode == "all":
                results.append(cursor.fetchall())
            else:
                raise ValueError("fetch_many mode must be 'one' or 'all'.")

        return results
    finally:
        conn.close()


def get_current_app_user_id() -> str:
    if not uses_postgres():
        scope = get_user_scope()

        if scope is None:
            raise RuntimeError("An authenticated user scope is required.")

        return scope.storage_key

    conn = get_connection()

    try:
        row = conn.execute(
            "SELECT public.ensure_current_app_user() AS id"
        ).fetchone()

        if not row or row["id"] is None:
            raise RuntimeError("Supabase could not resolve the authenticated user.")

        resolved = str(row["id"])
        conn.commit()
        return resolved
    finally:
        conn.close()


def init_db_once(session_state) -> bool:
    """Initialize the active user's database once per browser session.

    The marker is keyed by the authenticated identity for PostgreSQL and by the
    fully scoped path for SQLite, so switching users cannot reuse another
    user's initialization state. A missing SQLite workspace is initialized
    again; PostgreSQL workspace deletion ends the authenticated session.
    """
    if uses_postgres():
        scope = get_user_scope()

        if scope is None:
            raise RuntimeError("An authenticated user scope is required.")

        state_key = "_initialized_postgres_users"
        initialized_users = set(session_state.get(state_key, ()))

        if scope.storage_key in initialized_users:
            return False

        get_current_app_user_id()
        initialized_users.add(scope.storage_key)
        session_state[state_key] = tuple(sorted(initialized_users))
        return True

    db_path = get_db_path()
    state_key = "_initialized_database_paths"
    initialized_paths = set(session_state.get(state_key, ()))

    if db_path in initialized_paths and Path(db_path).is_file():
        return False

    init_db()
    initialized_paths.add(db_path)
    session_state[state_key] = tuple(sorted(initialized_paths))
    return True


def init_db():
    if uses_postgres():
        get_current_app_user_id()
        return

    conn = get_connection()
    cur = conn.cursor() # Cursorul este obiectul prin care trimiți comenzi SQL către baza de date.

    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            domain TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            objective TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (project_id)
            REFERENCES projects(id)
            ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL, 
            type TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (chat_id)
            REFERENCES chats(id)
            ON DELETE CASCADE
        )
    """)
    #role - cine a scris mesajul, user sau assistant(AI)
    #type - tipul mesajului, text sau audio_transcript sau ai_summary

    cur.execute("""
        CREATE TABLE IF NOT EXISTS experiment_ai_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (chat_id)
            REFERENCES chats(id)
            ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS audio_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            message_id INTEGER,
            file_path TEXT NOT NULL,
            transcript TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (chat_id)
            REFERENCES chats(id)
            ON DELETE CASCADE,

            FOREIGN KEY (message_id)
            REFERENCES messages(id)
            ON DELETE CASCADE
        )
    """)
    columns = cur.execute("PRAGMA table_info(audio_records)").fetchall()
    column_names = [column["name"] for column in columns]

    if "message_id" not in column_names:
        cur.execute("ALTER TABLE audio_records ADD COLUMN message_id INTEGER")


    cur.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            project_id INTEGER,
            chat_id INTEGER,
            summary_style TEXT NOT NULL DEFAULT 'Standard cercetare',
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (project_id)
            REFERENCES projects(id)
            ON DELETE CASCADE,

            FOREIGN KEY (chat_id)
            REFERENCES chats(id)
            ON DELETE CASCADE
        )
    """)

    summary_columns = cur.execute("PRAGMA table_info(summaries)").fetchall()
    summary_column_names = [column["name"] for column in summary_columns]

    if "summary_style" not in summary_column_names:
        cur.execute(
            """
            ALTER TABLE summaries
            ADD COLUMN summary_style TEXT NOT NULL DEFAULT 'Standard cercetare'
            """
        )

    # Rezumatele create înainte de introducerea structurii sunt considerate
    # rezumate standard. Dacă există duplicate istorice, păstrăm versiunea
    # cea mai nouă înainte de a activa unicitatea per structură.
    cur.execute(
        """
        DELETE FROM summaries
        WHERE scope = 'project'
          AND id NOT IN (
              SELECT MAX(id)
              FROM summaries
              WHERE scope = 'project'
              GROUP BY project_id, summary_style
          )
        """
    )
    cur.execute(
        """
        DELETE FROM summaries
        WHERE scope = 'chat'
          AND id NOT IN (
              SELECT MAX(id)
              FROM summaries
              WHERE scope = 'chat'
              GROUP BY chat_id, summary_style
          )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_summaries_project_style
        ON summaries(project_id, summary_style)
        WHERE scope = 'project'
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_summaries_chat_style
        ON summaries(chat_id, summary_style)
        WHERE scope = 'chat'
        """
    )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS project_ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            evidence TEXT,
            importance TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (project_id)
            REFERENCES projects(id)
            ON DELETE CASCADE
        )
    """)


    cur.execute("""
        CREATE TABLE IF NOT EXISTS mindmap_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            node_key TEXT NOT NULL,
            label TEXT NOT NULL,
            description TEXT,
            importance TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (project_id)
            REFERENCES projects(id)
            ON DELETE CASCADE,

            UNIQUE(project_id, node_key)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS mindmap_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            source_key TEXT NOT NULL,
            target_key TEXT NOT NULL,
            relation TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (project_id)
            REFERENCES projects(id)
            ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS mindmap_source_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_id INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (project_id)
            REFERENCES projects(id)
            ON DELETE CASCADE,

            UNIQUE(project_id, source_type, source_id)
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_mindmap_source_state_project
        ON mindmap_source_state(project_id)
    """)

    # =========================
    # RESEARCH LIBRARY
    # =========================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS library_folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER,
            name TEXT NOT NULL COLLATE NOCASE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (parent_id)
            REFERENCES library_folders(id)
            ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_library_folders_root_name
        ON library_folders(name)
        WHERE parent_id IS NULL
    """)

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_library_folders_parent_name
        ON library_folders(parent_id, name)
        WHERE parent_id IS NOT NULL
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS library_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_id INTEGER,
            item_type TEXT NOT NULL DEFAULT 'paper',
            title TEXT NOT NULL,
            authors TEXT,
            publication_year INTEGER,
            source_name TEXT,
            doi TEXT COLLATE NOCASE,
            openalex_id TEXT COLLATE NOCASE,
            url TEXT,
            abstract TEXT,
            original_filename TEXT,
            file_path TEXT,
            mime_type TEXT,
            file_size INTEGER,
            status TEXT NOT NULL DEFAULT 'To read',
            personal_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (folder_id)
            REFERENCES library_folders(id)
            ON DELETE SET NULL
        )
    """)

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_library_items_doi
        ON library_items(doi)
        WHERE doi IS NOT NULL AND doi != ''
    """)

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_library_items_openalex
        ON library_items(openalex_id)
        WHERE openalex_id IS NOT NULL AND openalex_id != ''
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_library_items_folder
        ON library_items(folder_id)
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS library_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS library_item_tags (
            item_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,

            PRIMARY KEY (item_id, tag_id),

            FOREIGN KEY (item_id)
            REFERENCES library_items(id)
            ON DELETE CASCADE,

            FOREIGN KEY (tag_id)
            REFERENCES library_tags(id)
            ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS library_item_projects (
            item_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,

            PRIMARY KEY (item_id, project_id),

            FOREIGN KEY (item_id)
            REFERENCES library_items(id)
            ON DELETE CASCADE,

            FOREIGN KEY (project_id)
            REFERENCES projects(id)
            ON DELETE CASCADE
        )
    """)

    # =========================
    # PROJECT RESEARCH CASES
    # =========================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS research_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            library_item_id INTEGER NOT NULL,
            schema_version TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            semantic_json TEXT NOT NULL DEFAULT '{}',
            embedding_json TEXT NOT NULL DEFAULT '[]',
            embedding_model TEXT NOT NULL,
            generation_model TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'processing',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (project_id)
            REFERENCES projects(id)
            ON DELETE CASCADE,

            FOREIGN KEY (library_item_id)
            REFERENCES library_items(id)
            ON DELETE CASCADE,

            FOREIGN KEY (library_item_id, project_id)
            REFERENCES library_item_projects(item_id, project_id)
            ON DELETE CASCADE,

            UNIQUE(project_id, library_item_id),

            CHECK (status IN ('processing', 'ready', 'failed'))
        )
    """)

    research_case_columns = cur.execute(
        "PRAGMA table_info(research_cases)"
    ).fetchall()
    research_case_column_names = {
        column["name"] for column in research_case_columns
    }

    if "generation_model" not in research_case_column_names:
        cur.execute(
            """
            ALTER TABLE research_cases
            ADD COLUMN generation_model TEXT NOT NULL DEFAULT 'unknown'
            """
        )

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_research_cases_project_status
        ON research_cases(project_id, status, updated_at DESC)
    """)

    # =========================
    # DATA ANALYSIS
    # =========================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS analysis_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            library_item_id INTEGER,
            source_kind TEXT NOT NULL,
            source_name TEXT NOT NULL,
            objective TEXT NOT NULL,
            algorithm_key TEXT NOT NULL,
            algorithm_label TEXT NOT NULL,
            target_column TEXT,
            feature_columns_json TEXT NOT NULL DEFAULT '[]',
            parameters_json TEXT NOT NULL DEFAULT '{}',
            preprocessing_json TEXT NOT NULL DEFAULT '{}',
            row_count INTEGER NOT NULL DEFAULT 0,
            column_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'running',
            metrics_json TEXT NOT NULL DEFAULT '{}',
            results_json TEXT NOT NULL DEFAULT '{}',
            predictions_file_path TEXT,
            report_file_path TEXT,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,

            FOREIGN KEY (library_item_id)
            REFERENCES library_items(id)
            ON DELETE SET NULL,

            CHECK (source_kind IN ('upload', 'library')),
            CHECK (status IN ('running', 'completed', 'failed'))
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_analysis_runs_created
        ON analysis_runs(created_at DESC, id DESC)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_analysis_runs_library_item
        ON analysis_runs(library_item_id)
    """)

    # =========================
    # PROJECT PAPER DISCOVERY
    # =========================

    # Manual Search and AI Recommendations each keep one independent current
    # result set per project.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS project_discovery_sets (
            project_id INTEGER NOT NULL,
            source_mode TEXT NOT NULL,
            profile_json TEXT NOT NULL DEFAULT '{}',
            queries_json TEXT NOT NULL DEFAULT '[]',
            search_options_json TEXT NOT NULL DEFAULT '{}',
            ai_error TEXT,
            result_count INTEGER NOT NULL DEFAULT 0,
            openalex_page INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (project_id, source_mode),

            FOREIGN KEY (project_id)
            REFERENCES projects(id)
            ON DELETE CASCADE,

            CHECK (source_mode IN ('Manual Search', 'AI Recommendations'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS project_discovery_set_papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            source_mode TEXT NOT NULL,
            ranking_id TEXT NOT NULL,
            rank_position INTEGER NOT NULL,
            openalex_id TEXT COLLATE NOCASE,
            doi TEXT COLLATE NOCASE,
            title TEXT NOT NULL,
            final_score REAL,
            paper_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (project_id, source_mode)
            REFERENCES project_discovery_sets(project_id, source_mode)
            ON DELETE CASCADE,

            UNIQUE(project_id, source_mode, ranking_id),
            UNIQUE(project_id, source_mode, rank_position)
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_project_discovery_set_papers_project
        ON project_discovery_set_papers(project_id, source_mode, rank_position)
    """)

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_project_discovery_set_papers_openalex
        ON project_discovery_set_papers(project_id, source_mode, openalex_id)
        WHERE openalex_id IS NOT NULL AND openalex_id != ''
    """)

    # Migrate result sets created by the earlier one-set-per-project schema.
    legacy_runs = cur.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'project_discovery_runs'
        """
    ).fetchone()
    legacy_papers = cur.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'project_discovery_papers'
        """
    ).fetchone()

    if legacy_runs:
        cur.execute("""
            INSERT OR IGNORE INTO project_discovery_sets (
                project_id,
                source_mode,
                profile_json,
                queries_json,
                search_options_json,
                ai_error,
                result_count,
                openalex_page,
                created_at,
                updated_at
            )
            SELECT
                project_id,
                CASE
                    WHEN source_mode = 'Manual Search' THEN 'Manual Search'
                    ELSE 'AI Recommendations'
                END,
                profile_json,
                queries_json,
                search_options_json,
                ai_error,
                result_count,
                openalex_page,
                created_at,
                updated_at
            FROM project_discovery_runs
        """)

    if legacy_runs and legacy_papers:
        cur.execute("""
            INSERT OR IGNORE INTO project_discovery_set_papers (
                project_id,
                source_mode,
                ranking_id,
                rank_position,
                openalex_id,
                doi,
                title,
                final_score,
                paper_json,
                created_at
            )
            SELECT
                paper.project_id,
                CASE
                    WHEN run.source_mode = 'Manual Search' THEN 'Manual Search'
                    ELSE 'AI Recommendations'
                END,
                paper.ranking_id,
                paper.rank_position,
                paper.openalex_id,
                paper.doi,
                paper.title,
                paper.final_score,
                paper.paper_json,
                paper.created_at
            FROM project_discovery_papers paper
            JOIN project_discovery_runs run
              ON run.project_id = paper.project_id
        """)

    # =========================
    # PAPER WRITING
    # =========================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS manuscripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Draft',
            citation_style TEXT NOT NULL DEFAULT 'APA 7',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (project_id)
            REFERENCES projects(id)
            ON DELETE CASCADE,

            CHECK (status IN ('Draft', 'In review', 'Final')),
            CHECK (citation_style IN ('APA 7', 'Vancouver'))
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_manuscripts_project
        ON manuscripts(project_id, updated_at DESC)
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS manuscript_sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manuscript_id INTEGER NOT NULL,
            parent_section_id INTEGER,
            section_type TEXT NOT NULL DEFAULT 'custom',
            title TEXT NOT NULL,
            content_md TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (manuscript_id)
            REFERENCES manuscripts(id)
            ON DELETE CASCADE,

            FOREIGN KEY (parent_section_id)
            REFERENCES manuscript_sections(id)
            ON DELETE SET NULL
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_manuscript_sections_order
        ON manuscript_sections(manuscript_id, sort_order, id)
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS manuscript_sources (
            manuscript_id INTEGER NOT NULL,
            library_item_id INTEGER NOT NULL,
            citation_key TEXT NOT NULL COLLATE NOCASE,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (manuscript_id, library_item_id),
            UNIQUE (manuscript_id, citation_key),

            FOREIGN KEY (manuscript_id)
            REFERENCES manuscripts(id)
            ON DELETE CASCADE,

            FOREIGN KEY (library_item_id)
            REFERENCES library_items(id)
            ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS manuscript_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manuscript_id INTEGER NOT NULL,
            evidence_type TEXT NOT NULL,
            evidence_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            excerpt TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (manuscript_id)
            REFERENCES manuscripts(id)
            ON DELETE CASCADE,

            UNIQUE (manuscript_id, evidence_type, evidence_id),
            CHECK (evidence_type IN ('experiment', 'summary', 'key_idea'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS manuscript_citations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manuscript_id INTEGER NOT NULL,
            section_id INTEGER NOT NULL,
            library_item_id INTEGER NOT NULL,
            citation_key TEXT NOT NULL COLLATE NOCASE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (manuscript_id)
            REFERENCES manuscripts(id)
            ON DELETE CASCADE,

            FOREIGN KEY (section_id)
            REFERENCES manuscript_sections(id)
            ON DELETE CASCADE,

            FOREIGN KEY (manuscript_id, library_item_id)
            REFERENCES manuscript_sources(manuscript_id, library_item_id)
            ON DELETE CASCADE,

            UNIQUE (section_id, library_item_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS manuscript_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manuscript_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            trigger_type TEXT NOT NULL DEFAULT 'manual',
            note TEXT,
            snapshot_json TEXT NOT NULL,
            word_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (manuscript_id)
            REFERENCES manuscripts(id)
            ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_manuscript_versions_created
        ON manuscript_versions(manuscript_id, created_at DESC, id DESC)
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS manuscript_version_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            author_name TEXT NOT NULL DEFAULT 'Researcher',
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (version_id)
            REFERENCES manuscript_versions(id)
            ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_manuscript_version_comments
        ON manuscript_version_comments(version_id, created_at, id)
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS manuscript_submission_profiles (
            manuscript_id INTEGER PRIMARY KEY,
            target_journal TEXT,
            journal_template TEXT NOT NULL DEFAULT 'General IMRaD',
            short_title TEXT,
            authors_json TEXT NOT NULL DEFAULT '[]',
            affiliations_json TEXT NOT NULL DEFAULT '[]',
            corresponding_author_json TEXT NOT NULL DEFAULT '{}',
            keywords_json TEXT NOT NULL DEFAULT '[]',
            word_limit INTEGER NOT NULL DEFAULT 5000,
            abstract_word_limit INTEGER NOT NULL DEFAULT 250,
            checklist_json TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (manuscript_id)
            REFERENCES manuscripts(id)
            ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS manuscript_ai_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manuscript_id INTEGER NOT NULL,
            section_id INTEGER,
            role TEXT NOT NULL,
            mode TEXT NOT NULL,
            content TEXT NOT NULL,
            payload_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (manuscript_id)
            REFERENCES manuscripts(id)
            ON DELETE CASCADE,

            FOREIGN KEY (section_id)
            REFERENCES manuscript_sections(id)
            ON DELETE SET NULL,

            CHECK (role IN ('user', 'assistant'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS manuscript_ai_contexts (
            manuscript_id INTEGER PRIMARY KEY,
            context_mode TEXT NOT NULL DEFAULT 'Current section',
            section_ids_json TEXT NOT NULL DEFAULT '[]',
            source_ids_json TEXT NOT NULL DEFAULT '[]',
            evidence_keys_json TEXT NOT NULL DEFAULT '[]',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (manuscript_id)
            REFERENCES manuscripts(id)
            ON DELETE CASCADE,

            CHECK (context_mode IN ('Current section', 'Whole manuscript', 'Custom'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS manuscript_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manuscript_id INTEGER NOT NULL,
            section_id INTEGER NOT NULL,
            asset_type TEXT NOT NULL,
            caption TEXT NOT NULL,
            alt_text TEXT,
            original_filename TEXT,
            storage_path TEXT,
            mime_type TEXT,
            content_json TEXT NOT NULL DEFAULT '{}',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (manuscript_id)
            REFERENCES manuscripts(id)
            ON DELETE CASCADE,

            FOREIGN KEY (section_id)
            REFERENCES manuscript_sections(id)
            ON DELETE CASCADE,

            CHECK (asset_type IN ('figure', 'table', 'equation'))
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_manuscript_assets_order
        ON manuscript_assets(manuscript_id, section_id, sort_order, id)
    """)

    conn.commit()
    conn.close()
