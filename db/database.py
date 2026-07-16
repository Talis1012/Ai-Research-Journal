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

    conn.commit()
    conn.close()
