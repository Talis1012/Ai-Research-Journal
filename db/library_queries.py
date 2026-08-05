from db.database import get_connection
from utils.runtime_config import uses_postgres


LIBRARY_ITEM_TYPES = (
    "paper",
    "pdf",
    "dataset",
    "audio",
    "document",
    "other",
)

LIBRARY_STATUSES = (
    "To read",
    "Reading",
    "Reviewed",
)


def normalize_doi(value: str | None) -> str:
    normalized = str(value or "").strip().lower()

    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    ):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):].strip()
            break

    return normalized.rstrip(" .")


def normalize_openalex_id(value: str | None) -> str:
    normalized = str(value or "").strip().rstrip("/")

    if not normalized:
        return ""

    normalized = normalized.rsplit("/", 1)[-1]
    return normalized.upper()


def _optional_text(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def create_library_folder(name: str, parent_id: int | None = None) -> int:
    name = name.strip()

    if not name:
        raise ValueError("Folder name is required.")

    conn = get_connection()

    if parent_id is not None:
        parent = conn.execute(
            "SELECT id FROM library_folders WHERE id = ?",
            (parent_id,),
        ).fetchone()

        if not parent:
            conn.close()
            raise ValueError("The selected parent folder no longer exists.")

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO library_folders (parent_id, name)
        VALUES (?, ?)
        """,
        (parent_id, name),
    )
    folder_id = cur.lastrowid
    conn.commit()
    conn.close()

    return folder_id


def get_library_folders():
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT
            folder.*,
            (
                SELECT COUNT(*)
                FROM library_items item
                WHERE item.folder_id = folder.id
            ) AS item_count
        FROM library_folders folder
        ORDER BY folder.name COLLATE NOCASE ASC, folder.id ASC
        """
    ).fetchall()
    conn.close()

    return rows


def get_library_folder(folder_id: int):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT *
        FROM library_folders
        WHERE id = ?
        """,
        (folder_id,),
    ).fetchone()
    conn.close()

    return row


def rename_library_folder(folder_id: int, name: str):
    name = name.strip()

    if not name:
        raise ValueError("Folder name is required.")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE library_folders
        SET name = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (name, folder_id),
    )

    if cur.rowcount == 0:
        conn.close()
        raise ValueError("The folder no longer exists.")

    conn.commit()
    conn.close()


def delete_library_folder(
    folder_id: int,
    *,
    delete_items: bool = False,
) -> list[str]:
    conn = get_connection()
    file_rows = conn.execute(
        """
        WITH RECURSIVE subtree(id) AS (
            SELECT id
            FROM library_folders
            WHERE id = ?

            UNION ALL

            SELECT folder.id
            FROM library_folders folder
            JOIN subtree ON folder.parent_id = subtree.id
        )
        SELECT item.file_path
        FROM library_items item
        WHERE item.folder_id IN (SELECT id FROM subtree)
          AND item.file_path IS NOT NULL
        """,
        (folder_id,),
    ).fetchall()

    if delete_items:
        conn.execute(
            """
            WITH RECURSIVE subtree(id) AS (
                SELECT id
                FROM library_folders
                WHERE id = ?

                UNION ALL

                SELECT folder.id
                FROM library_folders folder
                JOIN subtree ON folder.parent_id = subtree.id
            )
            DELETE FROM library_items
            WHERE folder_id IN (SELECT id FROM subtree)
            """,
            (folder_id,),
        )

    cur = conn.cursor()
    cur.execute("DELETE FROM library_folders WHERE id = ?", (folder_id,))

    if cur.rowcount == 0:
        conn.close()
        raise ValueError("The folder no longer exists.")

    conn.commit()
    conn.close()

    if not delete_items:
        return []

    return [row["file_path"] for row in file_rows]


def create_library_item(
    *,
    title: str,
    item_type: str = "paper",
    folder_id: int | None = None,
    authors: str = "",
    publication_year: int | None = None,
    source_name: str = "",
    doi: str = "",
    openalex_id: str = "",
    url: str = "",
    abstract: str = "",
    original_filename: str = "",
    file_path: str = "",
    mime_type: str = "",
    file_size: int | None = None,
    status: str = "To read",
    personal_notes: str = "",
    tags: list[str] | None = None,
    project_ids: list[int] | None = None,
) -> int:
    title = title.strip()

    if not title:
        raise ValueError("Item title is required.")

    if item_type not in LIBRARY_ITEM_TYPES:
        raise ValueError(f"Unsupported library item type: {item_type}")

    if status not in LIBRARY_STATUSES:
        raise ValueError(f"Unsupported library status: {status}")

    doi = normalize_doi(doi)
    openalex_id = normalize_openalex_id(openalex_id)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO library_items (
            folder_id,
            item_type,
            title,
            authors,
            publication_year,
            source_name,
            doi,
            openalex_id,
            url,
            abstract,
            original_filename,
            file_path,
            mime_type,
            file_size,
            status,
            personal_notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            folder_id,
            item_type,
            title,
            _optional_text(authors),
            publication_year,
            _optional_text(source_name),
            _optional_text(doi),
            _optional_text(openalex_id),
            _optional_text(url),
            _optional_text(abstract),
            _optional_text(original_filename),
            _optional_text(file_path),
            _optional_text(mime_type),
            file_size,
            status,
            _optional_text(personal_notes),
        ),
    )
    item_id = cur.lastrowid
    _replace_library_item_tags(conn, item_id, tags or [])
    _replace_library_item_projects(conn, item_id, project_ids or [])
    conn.commit()
    conn.close()

    return item_id


def _library_item_select() -> str:
    if uses_postgres():
        return """
            SELECT
                item.*,
                folder.name AS folder_name,
                COALESCE((
                    SELECT STRING_AGG(
                        tag.name::text,
                        ', ' ORDER BY LOWER(tag.name::text)
                    )
                    FROM library_tags tag
                    JOIN library_item_tags item_tag
                      ON item_tag.tag_id = tag.id
                    WHERE item_tag.item_id = item.id
                ), '') AS tags,
                COALESCE((
                    SELECT STRING_AGG(
                        item_project.project_id::text,
                        ',' ORDER BY item_project.project_id
                    )
                    FROM library_item_projects item_project
                    WHERE item_project.item_id = item.id
                ), '') AS project_ids,
                COALESCE((
                    SELECT STRING_AGG(
                        project.name,
                        ', ' ORDER BY LOWER(project.name)
                    )
                    FROM projects project
                    JOIN library_item_projects item_project
                      ON item_project.project_id = project.id
                    WHERE item_project.item_id = item.id
                ), '') AS project_names
            FROM library_items item
            LEFT JOIN library_folders folder ON folder.id = item.folder_id
        """

    return """
        SELECT
            item.*,
            folder.name AS folder_name,
            COALESCE((
                SELECT GROUP_CONCAT(tag_name, ', ')
                FROM (
                    SELECT tag.name AS tag_name
                    FROM library_tags tag
                    JOIN library_item_tags item_tag ON item_tag.tag_id = tag.id
                    WHERE item_tag.item_id = item.id
                    ORDER BY tag.name COLLATE NOCASE
                )
            ), '') AS tags,
            COALESCE((
                SELECT GROUP_CONCAT(project_id, ',')
                FROM (
                    SELECT item_project.project_id AS project_id
                    FROM library_item_projects item_project
                    WHERE item_project.item_id = item.id
                    ORDER BY item_project.project_id
                )
            ), '') AS project_ids,
            COALESCE((
                SELECT GROUP_CONCAT(project_name, ', ')
                FROM (
                    SELECT project.name AS project_name
                    FROM projects project
                    JOIN library_item_projects item_project
                        ON item_project.project_id = project.id
                    WHERE item_project.item_id = item.id
                    ORDER BY project.name COLLATE NOCASE
                )
            ), '') AS project_names
        FROM library_items item
        LEFT JOIN library_folders folder ON folder.id = item.folder_id
    """


def get_library_item(item_id: int):
    conn = get_connection()
    row = conn.execute(
        _library_item_select() + " WHERE item.id = ?",
        (item_id,),
    ).fetchone()
    conn.close()

    return row


def _library_item_filters(
    *,
    folder_id: int | None = None,
    only_unfiled: bool = False,
    item_type: str | None = None,
    item_types: tuple[str, ...] | list[str] | None = None,
    status: str | None = None,
    project_id: int | None = None,
    search: str = "",
) -> tuple[str, list]:
    clauses = []
    params: list = []

    if only_unfiled:
        clauses.append("item.folder_id IS NULL")
    elif folder_id is not None:
        clauses.append("item.folder_id = ?")
        params.append(folder_id)

    normalized_types = []

    if item_type and item_type != "All types":
        normalized_types.append(item_type)

    for value in item_types or ():
        if value and value != "All types" and value not in normalized_types:
            normalized_types.append(value)

    if normalized_types:
        placeholders = ",".join("?" for _ in normalized_types)
        clauses.append(f"item.item_type IN ({placeholders})")
        params.extend(normalized_types)

    if status and status != "All statuses":
        clauses.append("item.status = ?")
        params.append(status)

    if project_id is not None:
        clauses.append(
            """
            EXISTS (
                SELECT 1
                FROM library_item_projects item_project
                WHERE item_project.item_id = item.id
                  AND item_project.project_id = ?
            )
            """
        )
        params.append(project_id)

    normalized_search = search.strip()

    if normalized_search:
        pattern = f"%{normalized_search}%"
        clauses.append(
            """
            (
                item.title LIKE ?
                OR COALESCE(item.authors, '') LIKE ?
                OR COALESCE(item.doi, '') LIKE ?
                OR COALESCE(item.source_name, '') LIKE ?
                OR EXISTS (
                    SELECT 1
                    FROM library_tags tag
                    JOIN library_item_tags item_tag ON item_tag.tag_id = tag.id
                    WHERE item_tag.item_id = item.id
                      AND tag.name LIKE ?
                )
            )
            """
        )
        params.extend([pattern] * 5)

    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, params


def get_library_item_count(
    *,
    folder_id: int | None = None,
    only_unfiled: bool = False,
    item_type: str | None = None,
    item_types: tuple[str, ...] | list[str] | None = None,
    status: str | None = None,
    project_id: int | None = None,
    search: str = "",
) -> int:
    where_sql, params = _library_item_filters(
        folder_id=folder_id,
        only_unfiled=only_unfiled,
        item_type=item_type,
        item_types=item_types,
        status=status,
        project_id=project_id,
        search=search,
    )
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) AS item_count FROM library_items item" + where_sql,
        params,
    ).fetchone()
    conn.close()
    return int(row["item_count"] or 0)


def get_library_items(
    *,
    folder_id: int | None = None,
    only_unfiled: bool = False,
    item_type: str | None = None,
    item_types: tuple[str, ...] | list[str] | None = None,
    status: str | None = None,
    project_id: int | None = None,
    search: str = "",
    sort: str = "newest",
    limit: int | None = None,
    offset: int = 0,
):
    where_sql, params = _library_item_filters(
        folder_id=folder_id,
        only_unfiled=only_unfiled,
        item_type=item_type,
        item_types=item_types,
        status=status,
        project_id=project_id,
        search=search,
    )
    sort_sql = {
        "newest": "item.created_at DESC, item.id DESC",
        "oldest": "item.created_at ASC, item.id ASC",
        "title": "item.title COLLATE NOCASE ASC, item.id ASC",
        "year_desc": "item.publication_year DESC, item.title COLLATE NOCASE ASC",
        "year_asc": "item.publication_year ASC, item.title COLLATE NOCASE ASC",
    }.get(sort, "item.created_at DESC, item.id DESC")
    pagination_sql = ""

    if limit is not None:
        pagination_sql = " LIMIT ? OFFSET ?"
        params.extend([max(1, int(limit)), max(0, int(offset))])

    conn = get_connection()
    rows = conn.execute(
        _library_item_select()
        + where_sql
        + f" ORDER BY {sort_sql}"
        + pagination_sql,
        params,
    ).fetchall()
    conn.close()

    return rows


def update_library_item(
    item_id: int,
    *,
    title: str,
    item_type: str,
    folder_id: int | None,
    authors: str,
    publication_year: int | None,
    source_name: str,
    doi: str,
    url: str,
    abstract: str,
    status: str,
    personal_notes: str,
    tags: list[str],
    project_ids: list[int],
):
    title = title.strip()

    if not title:
        raise ValueError("Item title is required.")

    if item_type not in LIBRARY_ITEM_TYPES:
        raise ValueError(f"Unsupported library item type: {item_type}")

    if status not in LIBRARY_STATUSES:
        raise ValueError(f"Unsupported library status: {status}")

    doi = normalize_doi(doi)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE library_items
        SET folder_id = ?,
            item_type = ?,
            title = ?,
            authors = ?,
            publication_year = ?,
            source_name = ?,
            doi = ?,
            url = ?,
            abstract = ?,
            status = ?,
            personal_notes = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            folder_id,
            item_type,
            title,
            _optional_text(authors),
            publication_year,
            _optional_text(source_name),
            _optional_text(doi),
            _optional_text(url),
            _optional_text(abstract),
            status,
            _optional_text(personal_notes),
            item_id,
        ),
    )

    if cur.rowcount == 0:
        conn.close()
        raise ValueError("The library item no longer exists.")

    _replace_library_item_tags(conn, item_id, tags)
    _replace_library_item_projects(conn, item_id, project_ids)
    conn.commit()
    conn.close()


def _replace_library_item_tags(conn, item_id: int, tag_names: list[str]):
    normalized_names = []
    seen = set()

    for raw_name in tag_names:
        name = raw_name.strip()
        normalized = name.casefold()

        if not name or normalized in seen:
            continue

        seen.add(normalized)
        normalized_names.append(name)

    conn.execute("DELETE FROM library_item_tags WHERE item_id = ?", (item_id,))

    for name in normalized_names:
        conn.execute(
            "INSERT OR IGNORE INTO library_tags (name) VALUES (?)",
            (name,),
        )
        tag = conn.execute(
            "SELECT id FROM library_tags WHERE name = ? COLLATE NOCASE",
            (name,),
        ).fetchone()
        conn.execute(
            """
            INSERT OR IGNORE INTO library_item_tags (item_id, tag_id)
            VALUES (?, ?)
            """,
            (item_id, tag["id"]),
        )


def _replace_library_item_projects(conn, item_id: int, project_ids: list[int]):
    conn.execute(
        "DELETE FROM library_item_projects WHERE item_id = ?",
        (item_id,),
    )

    for project_id in sorted(set(project_ids)):
        conn.execute(
            """
            INSERT OR IGNORE INTO library_item_projects (item_id, project_id)
            SELECT ?, id
            FROM projects
            WHERE id = ?
            """,
            (item_id, project_id),
        )


def move_library_items(item_ids: list[int], folder_id: int | None):
    normalized_ids = sorted(set(int(item_id) for item_id in item_ids))

    if not normalized_ids:
        return

    placeholders = ",".join("?" for _ in normalized_ids)
    conn = get_connection()
    conn.execute(
        f"""
        UPDATE library_items
        SET folder_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id IN ({placeholders})
        """,
        [folder_id, *normalized_ids],
    )
    conn.commit()
    conn.close()


def delete_library_item(item_id: int) -> str | None:
    conn = get_connection()
    item = conn.execute(
        "SELECT file_path FROM library_items WHERE id = ?",
        (item_id,),
    ).fetchone()

    if not item:
        conn.close()
        return None

    conn.execute("DELETE FROM library_items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()

    return item["file_path"]


def get_library_stats() -> dict:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN item_type = 'paper' THEN 1 ELSE 0 END) AS papers,
            SUM(CASE WHEN item_type = 'pdf' THEN 1 ELSE 0 END) AS pdfs,
            SUM(CASE WHEN item_type = 'dataset' THEN 1 ELSE 0 END) AS datasets,
            SUM(CASE WHEN item_type = 'audio' THEN 1 ELSE 0 END) AS audio,
            SUM(CASE WHEN folder_id IS NULL THEN 1 ELSE 0 END) AS unfiled,
            SUM(CASE WHEN status = 'To read' THEN 1 ELSE 0 END) AS to_read
        FROM library_items
        """
    ).fetchone()
    conn.close()

    return {
        key: int(row[key] or 0)
        for key in (
            "total",
            "papers",
            "pdfs",
            "datasets",
            "audio",
            "unfiled",
            "to_read",
        )
    }


def get_library_external_keys() -> dict[str, set[str]]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT doi, openalex_id
        FROM library_items
        WHERE doi IS NOT NULL OR openalex_id IS NOT NULL
        """
    ).fetchall()
    conn.close()

    return {
        "dois": {
            normalize_doi(row["doi"])
            for row in rows
            if normalize_doi(row["doi"])
        },
        "openalex_ids": {
            normalize_openalex_id(row["openalex_id"])
            for row in rows
            if normalize_openalex_id(row["openalex_id"])
        },
    }


def find_library_item_by_external_ids(
    *,
    doi: str = "",
    openalex_id: str = "",
):
    normalized_doi = normalize_doi(doi)
    normalized_openalex_id = normalize_openalex_id(openalex_id)

    if not normalized_doi and not normalized_openalex_id:
        return None

    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, doi, openalex_id, title
        FROM library_items
        WHERE doi IS NOT NULL OR openalex_id IS NOT NULL
        """
    ).fetchall()
    conn.close()

    for row in rows:
        if normalized_openalex_id and (
            normalize_openalex_id(row["openalex_id"]) == normalized_openalex_id
        ):
            return row

        if normalized_doi and normalize_doi(row["doi"]) == normalized_doi:
            return row

    return None
