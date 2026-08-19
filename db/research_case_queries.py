import json

from db.database import get_connection
from utils.runtime_config import uses_postgres


def _json_value(value, fallback):
    if value is None:
        return fallback

    if isinstance(value, (dict, list)):
        return value

    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _case_from_row(row) -> dict | None:
    if row is None:
        return None

    case = dict(row)
    case["semantic"] = _json_value(case.pop("semantic_json", None), {})
    case["embedding"] = _json_value(case.pop("embedding_json", None), [])
    return case


def _conflict_columns() -> str:
    if uses_postgres():
        return "user_id, project_id, library_item_id"

    return "project_id, library_item_id"


def mark_research_case_processing(
    *,
    project_id: int,
    library_item_id: int,
    schema_version: str,
    prompt_version: str,
    source_hash: str,
    embedding_model: str,
    generation_model: str,
) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        f"""
        INSERT INTO research_cases (
            project_id,
            library_item_id,
            schema_version,
            prompt_version,
            source_hash,
            semantic_json,
            embedding_json,
            embedding_model,
            generation_model,
            status,
            error_message
        )
        SELECT ?, ?, ?, ?, ?, '{{}}', '[]', ?, ?, 'processing', NULL
        FROM library_item_projects
        WHERE item_id = ? AND project_id = ?
        ON CONFLICT({_conflict_columns()}) DO UPDATE SET
            schema_version = excluded.schema_version,
            prompt_version = excluded.prompt_version,
            source_hash = excluded.source_hash,
            embedding_model = excluded.embedding_model,
            generation_model = excluded.generation_model,
            status = 'processing',
            error_message = NULL,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            project_id,
            library_item_id,
            schema_version,
            prompt_version,
            source_hash,
            embedding_model,
            generation_model,
            library_item_id,
            project_id,
        ),
    )

    if cur.rowcount == 0:
        conn.close()
        raise ValueError("The paper is not linked to the selected project.")

    row = conn.execute(
        """
        SELECT id
        FROM research_cases
        WHERE project_id = ? AND library_item_id = ?
        """,
        (project_id, library_item_id),
    ).fetchone()
    conn.commit()
    conn.close()
    return int(row["id"])


def save_research_case(
    *,
    project_id: int,
    library_item_id: int,
    schema_version: str,
    prompt_version: str,
    source_hash: str,
    semantic: dict,
    embedding: list[float],
    embedding_model: str,
    generation_model: str,
):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE research_cases
        SET schema_version = ?,
            prompt_version = ?,
            source_hash = ?,
            semantic_json = ?,
            embedding_json = ?,
            embedding_model = ?,
            generation_model = ?,
            status = 'ready',
            error_message = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE project_id = ? AND library_item_id = ?
        """,
        (
            schema_version,
            prompt_version,
            source_hash,
            json.dumps(semantic, ensure_ascii=False),
            json.dumps(embedding, separators=(",", ":")),
            embedding_model,
            generation_model,
            project_id,
            library_item_id,
        ),
    )

    if cur.rowcount == 0:
        conn.close()
        raise ValueError("The Research Case could not be saved.")

    conn.commit()
    conn.close()


def fail_research_case(
    *,
    project_id: int,
    library_item_id: int,
    error_message: str,
):
    conn = get_connection()
    conn.execute(
        """
        UPDATE research_cases
        SET status = 'failed',
            error_message = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE project_id = ? AND library_item_id = ?
        """,
        (str(error_message or "")[:1000], project_id, library_item_id),
    )
    conn.commit()
    conn.close()


def get_research_case(project_id: int, library_item_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT
            research_case.*,
            item.title AS article_title,
            item.authors AS article_authors,
            item.publication_year,
            item.doi,
            item.url,
            item.abstract,
            item.file_path,
            item.original_filename,
            item.item_type,
            item.personal_notes,
            item.mime_type,
            item.file_size,
            item.updated_at AS item_updated_at
        FROM research_cases research_case
        JOIN library_items item ON item.id = research_case.library_item_id
        WHERE research_case.project_id = ?
          AND research_case.library_item_id = ?
        """,
        (project_id, library_item_id),
    ).fetchone()
    conn.close()
    return _case_from_row(row)


def get_project_research_cases(
    project_id: int,
    *,
    status: str | None = None,
) -> list[dict]:
    params: list = [project_id]
    status_sql = ""

    if status is not None:
        status_sql = " AND research_case.status = ?"
        params.append(status)

    conn = get_connection()
    rows = conn.execute(
        """
        SELECT
            research_case.*,
            item.title AS article_title,
            item.authors AS article_authors,
            item.publication_year,
            item.doi,
            item.url,
            item.abstract,
            item.file_path,
            item.original_filename,
            item.item_type,
            item.personal_notes,
            item.mime_type,
            item.file_size,
            item.updated_at AS item_updated_at
        FROM research_cases research_case
        JOIN library_items item ON item.id = research_case.library_item_id
        WHERE research_case.project_id = ?
        """
        + status_sql
        + " ORDER BY research_case.updated_at DESC, research_case.id DESC",
        params,
    ).fetchall()
    conn.close()
    return [_case_from_row(row) for row in rows]
