import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def get_db_path() -> str:
    return os.getenv("DATABASE_PATH", "data/app.db")


def get_connection():
    db_path = get_db_path()

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row #project[0] -> project["name"]
    conn.execute("PRAGMA foreign_keys = ON") #Activează relațiile dintre tabele în SQLite

    return conn


def init_db():
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
