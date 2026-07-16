from db.database import get_connection


def create_project(name: str, domain: str, description: str = "") -> int:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO projects (name, domain, description)
        VALUES (?, ?, ?)
        """,
        (name, domain, description)
    )

    project_id = cur.lastrowid

    conn.commit()
    conn.close()

    return project_id


def get_projects():
    conn = get_connection()

    projects = conn.execute(
        """
        SELECT *
        FROM projects
        ORDER BY created_at DESC
        """
    ).fetchall()

    conn.close()

    return projects


def get_project_by_id(project_id: int):
    conn = get_connection()

    project = conn.execute(
        """
        SELECT *
        FROM projects
        WHERE id = ?
        """,
        (project_id,)
    ).fetchone()

    conn.close()

    return project


def create_chat(project_id: int, title: str, objective: str = "") -> int:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO chats (project_id, title, objective)
        VALUES (?, ?, ?)
        """,
        (project_id, title, objective)
    )

    chat_id = cur.lastrowid

    conn.commit()
    conn.close()

    return chat_id


def get_chats(project_id: int):
    conn = get_connection()

    chats = conn.execute(
        """
        SELECT *
        FROM chats
        WHERE project_id = ?
        ORDER BY created_at DESC
        """,
        (project_id,)
    ).fetchall()

    conn.close()

    return chats


def get_chat_by_id(chat_id: int):
    conn = get_connection()

    chat = conn.execute(
        """
        SELECT *
        FROM chats
        WHERE id = ?
        """,
        (chat_id,)
    ).fetchone()

    conn.close()

    return chat


def add_message(chat_id: int, role: str, message_type: str, content: str) -> int:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO messages (chat_id, role, type, content)
        VALUES (?, ?, ?, ?)
        """,
        (chat_id, role, message_type, content)
    )

    message_id = cur.lastrowid

    conn.commit()
    conn.close()

    return message_id


def get_messages(chat_id: int):
    conn = get_connection()

    messages = conn.execute(
        """
        SELECT *
        FROM messages
        WHERE chat_id = ?
        ORDER BY created_at ASC
        """,
        (chat_id,)
    ).fetchall()

    conn.close()

    return messages

def create_audio_record(
    chat_id: int,
    file_path: str,
    transcript: str = "",
    message_id: int | None = None
) -> int:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO audio_records (chat_id, message_id, file_path, transcript)
        VALUES (?, ?, ?, ?)
        """,
        (chat_id, message_id, file_path, transcript)
    )

    audio_record_id = cur.lastrowid

    conn.commit()
    conn.close()

    return audio_record_id


def get_audio_records(chat_id: int):
    conn = get_connection()

    audio_records = conn.execute(
        """
        SELECT *
        FROM audio_records
        WHERE chat_id = ?
        ORDER BY created_at ASC
        """,
        (chat_id,)
    ).fetchall()

    conn.close()

    return audio_records

def update_message_content(message_id: int, new_content: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE messages
        SET content = ?
        WHERE id = ?
        """,
        (new_content, message_id)
    )

    conn.commit()
    conn.close()


def update_audio_transcript_by_message_id(message_id: int, new_transcript: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE audio_records
        SET transcript = ?
        WHERE message_id = ?
        """,
        (new_transcript, message_id)
    )

    conn.commit()
    conn.close()

def get_audio_record_by_message_id(message_id: int):
    conn = get_connection()

    audio_record = conn.execute(
        """
        SELECT *
        FROM audio_records
        WHERE message_id = ?
        """,
        (message_id,)
    ).fetchone()

    conn.close()

    return audio_record


def delete_audio_record_by_message_id(message_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        DELETE FROM audio_records
        WHERE message_id = ?
        """,
        (message_id,)
    )

    conn.commit()
    conn.close()


def delete_message(message_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        DELETE FROM messages
        WHERE id = ?
        """,
        (message_id,)
    )

    conn.commit()
    conn.close()


#----------------------- EXPERIMENT AI CHAT ----------------------------

def add_experiment_ai_message(chat_id: int, role: str, content: str) -> int:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO experiment_ai_messages (chat_id, role, content)
        VALUES (?, ?, ?)
        """,
        (chat_id, role, content)
    )

    message_id = cur.lastrowid

    conn.commit()
    conn.close()

    return message_id


def get_experiment_ai_messages(chat_id: int):
    conn = get_connection()

    messages = conn.execute(
        """
        SELECT *
        FROM experiment_ai_messages
        WHERE chat_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (chat_id,)
    ).fetchall()

    conn.close()

    return messages


def clear_experiment_ai_messages(chat_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        DELETE FROM experiment_ai_messages
        WHERE chat_id = ?
        """,
        (chat_id,)
    )

    conn.commit()
    conn.close()


#----------------------- AI ----------------------------

def get_project_messages(project_id: int):
    conn = get_connection()

    messages = conn.execute(
        """
        SELECT
            messages.*,
            chats.title AS chat_title
        FROM messages
        JOIN chats ON messages.chat_id = chats.id
        WHERE chats.project_id = ?
        ORDER BY chats.created_at ASC, messages.created_at ASC
        """,
        (project_id,)
    ).fetchall()

    conn.close()

    return messages


def save_summary(
    scope: str,
    content: str,
    project_id: int | None = None,
    chat_id: int | None = None,
    summary_style: str = "Standard cercetare",
) -> int:
    if scope not in {"project", "chat"}:
        raise ValueError("Summary scope must be 'project' or 'chat'.")

    if scope == "project" and project_id is None:
        raise ValueError("project_id is required for a project summary.")

    if scope == "chat" and chat_id is None:
        raise ValueError("chat_id is required for an experiment summary.")

    summary_style = summary_style.strip() or "Standard cercetare"
    conn = get_connection()
    cur = conn.cursor()

    if scope == "project":
        existing = cur.execute(
            """
            SELECT id
            FROM summaries
            WHERE scope = 'project'
              AND project_id = ?
              AND summary_style = ?
            """,
            (project_id, summary_style),
        ).fetchone()

        if existing:
            summary_id = existing["id"]
            cur.execute(
                """
                UPDATE summaries
                SET content = ?,
                    chat_id = NULL,
                    created_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (content, summary_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO summaries (
                    scope,
                    project_id,
                    chat_id,
                    summary_style,
                    content
                )
                VALUES ('project', ?, NULL, ?, ?)
                """,
                (project_id, summary_style, content),
            )
            summary_id = cur.lastrowid
    else:
        existing = cur.execute(
            """
            SELECT id
            FROM summaries
            WHERE scope = 'chat'
              AND chat_id = ?
              AND summary_style = ?
            """,
            (chat_id, summary_style),
        ).fetchone()

        if existing:
            summary_id = existing["id"]
            cur.execute(
                """
                UPDATE summaries
                SET content = ?,
                    project_id = ?,
                    created_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (content, project_id, summary_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO summaries (
                    scope,
                    project_id,
                    chat_id,
                    summary_style,
                    content
                )
                VALUES ('chat', ?, ?, ?, ?)
                """,
                (project_id, chat_id, summary_style, content),
            )
            summary_id = cur.lastrowid

    conn.commit()
    conn.close()

    return summary_id


def get_chat_summaries(chat_id: int, summary_style: str | None = None):
    conn = get_connection()
    params = [chat_id]
    style_filter = ""

    if summary_style is not None:
        style_filter = " AND summary_style = ?"
        params.append(summary_style)

    summaries = conn.execute(
        f"""
        SELECT *
        FROM summaries
        WHERE scope = 'chat' AND chat_id = ?{style_filter}
        ORDER BY created_at DESC, id DESC
        """,
        params,
    ).fetchall()

    conn.close()

    return summaries


def get_chat_summary(chat_id: int, summary_style: str):
    conn = get_connection()
    summary = conn.execute(
        """
        SELECT *
        FROM summaries
        WHERE scope = 'chat'
          AND chat_id = ?
          AND summary_style = ?
        LIMIT 1
        """,
        (chat_id, summary_style),
    ).fetchone()
    conn.close()

    return summary


def get_project_summaries(project_id: int, summary_style: str | None = None):
    conn = get_connection()
    params = [project_id]
    style_filter = ""

    if summary_style is not None:
        style_filter = " AND summary_style = ?"
        params.append(summary_style)

    summaries = conn.execute(
        f"""
        SELECT *
        FROM summaries
        WHERE scope = 'project' AND project_id = ?{style_filter}
        ORDER BY created_at DESC, id DESC
        """,
        params,
    ).fetchall()

    conn.close()

    return summaries


def get_project_summary(project_id: int, summary_style: str):
    conn = get_connection()
    summary = conn.execute(
        """
        SELECT *
        FROM summaries
        WHERE scope = 'project'
          AND project_id = ?
          AND summary_style = ?
        LIMIT 1
        """,
        (project_id, summary_style),
    ).fetchone()
    conn.close()

    return summary


def delete_project_ideas(project_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        DELETE FROM project_ideas
        WHERE project_id = ?
        """,
        (project_id,)
    )

    conn.commit()
    conn.close()


def save_project_ideas(project_id: int, ideas: list[dict]):
    conn = get_connection()
    cur = conn.cursor()

    for idea in ideas:
        cur.execute(
            """
            INSERT INTO project_ideas (
                project_id,
                title,
                description,
                evidence,
                importance
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                project_id,
                idea.get("title", ""),
                idea.get("description", ""),
                idea.get("evidence", ""),
                idea.get("importance", "medium")
            )
        )

    conn.commit()
    conn.close()


def get_project_ideas(project_id: int):
    conn = get_connection()

    ideas = conn.execute(
        """
        SELECT *
        FROM project_ideas
        WHERE project_id = ?
        ORDER BY created_at DESC
        """,
        (project_id,)
    ).fetchall()

    conn.close()

    return ideas

#---------------------------------------------

#----------------- MINDMAP -------------------

def clear_project_mindmap(project_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        DELETE FROM mindmap_edges
        WHERE project_id = ?
        """,
        (project_id,)
    )

    cur.execute(
        """
        DELETE FROM mindmap_nodes
        WHERE project_id = ?
        """,
        (project_id,)
    )

    cur.execute(
        """
        DELETE FROM mindmap_source_state
        WHERE project_id = ?
        """,
        (project_id,)
    )

    conn.commit()
    conn.close()


def save_project_mindmap(project_id: int, mindmap_data: dict):
    merge_project_mindmap(project_id, mindmap_data)


def merge_project_mindmap(
    project_id: int,
    mindmap_data: dict,
    processed_sources: list[dict] | None = None,
):
    conn = get_connection()
    cur = conn.cursor()

    nodes = mindmap_data.get("nodes", [])
    edges = mindmap_data.get("edges", [])

    for node in nodes:
        node_key = str(node.get("id") or "").strip()

        if not node_key:
            continue

        cur.execute(
            """
            INSERT INTO mindmap_nodes (
                project_id,
                node_key,
                label,
                description,
                importance
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id, node_key) DO UPDATE SET
                label = excluded.label,
                description = excluded.description,
                importance = excluded.importance
            """,
            (
                project_id,
                node_key,
                node.get("label", ""),
                node.get("description", ""),
                node.get("importance", "medium")
            )
        )

    for edge in edges:
        source_key = str(edge.get("source") or "").strip()
        target_key = str(edge.get("target") or "").strip()
        relation = str(edge.get("relation") or "").strip()

        if not source_key or not target_key or source_key == target_key:
            continue

        cur.execute(
            """
            INSERT INTO mindmap_edges (
                project_id,
                source_key,
                target_key,
                relation
            )
            SELECT ?, ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1
                FROM mindmap_edges
                WHERE project_id = ?
                  AND source_key = ?
                  AND target_key = ?
                  AND COALESCE(relation, '') = ?
            )
            """,
            (
                project_id,
                source_key,
                target_key,
                relation,
                project_id,
                source_key,
                target_key,
                relation,
            )
        )

    for source in processed_sources or []:
        cur.execute(
            """
            INSERT INTO mindmap_source_state (
                project_id,
                source_type,
                source_id,
                content_hash,
                processed_at
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(project_id, source_type, source_id) DO UPDATE SET
                content_hash = excluded.content_hash,
                processed_at = CURRENT_TIMESTAMP
            """,
            (
                project_id,
                source["source_type"],
                source["source_id"],
                source["content_hash"],
            )
        )

    conn.commit()
    conn.close()


def get_mindmap_source_states(project_id: int):
    conn = get_connection()

    states = conn.execute(
        """
        SELECT *
        FROM mindmap_source_state
        WHERE project_id = ?
        ORDER BY processed_at ASC, id ASC
        """,
        (project_id,)
    ).fetchall()

    conn.close()

    return states


def get_mindmap_last_sync(project_id: int):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT MAX(processed_at) AS processed_at
        FROM mindmap_source_state
        WHERE project_id = ?
        """,
        (project_id,)
    ).fetchone()

    conn.close()

    return row["processed_at"] if row else None


def get_mindmap_nodes(project_id: int):
    conn = get_connection()

    nodes = conn.execute(
        """
        SELECT *
        FROM mindmap_nodes
        WHERE project_id = ?
        ORDER BY created_at ASC
        """,
        (project_id,)
    ).fetchall()

    conn.close()

    return nodes


def get_mindmap_edges(project_id: int):
    conn = get_connection()

    edges = conn.execute(
        """
        SELECT *
        FROM mindmap_edges
        WHERE project_id = ?
        ORDER BY created_at ASC
        """,
        (project_id,)
    ).fetchall()

    conn.close()

    return edges


def get_mindmap_node_by_key(project_id: int, node_key: str):
    conn = get_connection()

    node = conn.execute(
        """
        SELECT *
        FROM mindmap_nodes
        WHERE project_id = ? AND node_key = ?
        """,
        (project_id, node_key)
    ).fetchone()

    conn.close()

    return node


def update_summary(summary_id: int, new_content: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE summaries
        SET content = ?
        WHERE id = ?
        """,
        (new_content, summary_id)
    )

    conn.commit()
    conn.close()


def update_project_idea(
    idea_id: int,
    title: str,
    description: str,
    evidence: str,
    importance: str
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE project_ideas
        SET title = ?,
            description = ?,
            evidence = ?,
            importance = ?
        WHERE id = ?
        """,
        (
            title,
            description,
            evidence,
            importance,
            idea_id
        )
    )

    conn.commit()
    conn.close()


def delete_project_idea(idea_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        DELETE FROM project_ideas
        WHERE id = ?
        """,
        (idea_id,)
    )

    conn.commit()
    conn.close()

#--------------------------------------------

def get_audio_file_paths_by_chat(chat_id: int):
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT file_path
        FROM audio_records
        WHERE chat_id = ?
        """,
        (chat_id,)
    ).fetchall()

    conn.close()

    return [row["file_path"] for row in rows]


def get_audio_file_paths_by_project(project_id: int):
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT audio_records.file_path
        FROM audio_records
        JOIN chats ON audio_records.chat_id = chats.id
        WHERE chats.project_id = ?
        """,
        (project_id,)
    ).fetchall()

    conn.close()

    return [row["file_path"] for row in rows]


def delete_chat(chat_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        DELETE FROM chats
        WHERE id = ?
        """,
        (chat_id,)
    )

    conn.commit()
    conn.close()


def delete_project(project_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        DELETE FROM projects
        WHERE id = ?
        """,
        (project_id,)
    )

    conn.commit()
    conn.close()


def delete_summary(summary_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        DELETE FROM summaries
        WHERE id = ?
        """,
        (summary_id,)
    )

    conn.commit()
    conn.close()
