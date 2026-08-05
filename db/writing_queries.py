import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from db.database import fetch_many, get_connection
from services.manuscript_asset_service import (
    delete_manuscript_asset_directory,
    delete_manuscript_asset_file,
)


MANUSCRIPT_STATUSES = ("Draft", "In review", "Final")
CITATION_STYLES = ("APA 7", "Vancouver")
AI_CONTEXT_MODES = ("Current section", "Whole manuscript", "Custom")
MANUSCRIPT_ASSET_TYPES = ("figure", "table", "equation")
DEFAULT_SECTIONS = (
    ("abstract", "Abstract"),
    ("introduction", "Introduction"),
    ("methods", "Methods"),
    ("results", "Results"),
    ("discussion", "Discussion"),
    ("conclusion", "Conclusion"),
    ("references", "References"),
)
DEFAULT_SUBMISSION_CHECKLIST = {
    "author_approval": False,
    "cover_letter": False,
    "conflicts_disclosed": False,
    "ethics_statement": False,
    "data_availability": False,
    "figures_verified": False,
    "supplementary_files": False,
}


class StoredFileCleanupError(RuntimeError):
    pass


def _delete_manuscript_files(paths):
    failures = []

    for storage_path in sorted({str(path) for path in paths if path}):
        try:
            delete_manuscript_asset_file(storage_path)
        except (OSError, ValueError):
            failures.append(storage_path)

    if failures:
        raise StoredFileCleanupError(
            "The database records were deleted, but one or more figure files "
            "could not be removed."
        )


def manuscript_word_count(sections) -> int:
    total = 0

    for section in sections:
        try:
            content = section["content_md"]
        except (KeyError, TypeError, IndexError):
            content = ""

        total += len(re.findall(r"\b[\w'-]+\b", str(content or "")))

    return total


def _require_text(value: str, label: str) -> str:
    normalized = str(value or "").strip()

    if not normalized:
        raise ValueError(f"{label} is required.")

    return normalized


def create_manuscript(
    project_id: int,
    title: str,
    *,
    status: str = "Draft",
    citation_style: str = "APA 7",
    create_default_sections: bool = True,
) -> int:
    title = _require_text(title, "Manuscript title")

    if status not in MANUSCRIPT_STATUSES:
        raise ValueError("Unsupported manuscript status.")

    if citation_style not in CITATION_STYLES:
        raise ValueError("Unsupported citation style.")

    conn = get_connection()

    try:
        project = conn.execute(
            "SELECT id FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()

        if not project:
            raise ValueError("The selected project no longer exists.")

        with conn:
            cur = conn.execute(
                """
                INSERT INTO manuscripts (project_id, title, status, citation_style)
                VALUES (?, ?, ?, ?)
                """,
                (project_id, title, status, citation_style),
            )
            manuscript_id = cur.lastrowid

            if create_default_sections:
                conn.executemany(
                    """
                    INSERT INTO manuscript_sections (
                        manuscript_id,
                        section_type,
                        title,
                        sort_order
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (manuscript_id, section_type, section_title, index)
                        for index, (section_type, section_title)
                        in enumerate(DEFAULT_SECTIONS, start=1)
                    ],
                )

        return manuscript_id
    finally:
        conn.close()


def get_manuscripts(project_id: int):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT
            manuscript.*,
            (SELECT COUNT(*) FROM manuscript_sections section
             WHERE section.manuscript_id = manuscript.id) AS section_count,
            (SELECT COUNT(*) FROM manuscript_sources source
             WHERE source.manuscript_id = manuscript.id) AS source_count,
            (SELECT COUNT(*) FROM manuscript_versions version
             WHERE version.manuscript_id = manuscript.id) AS version_count
        FROM manuscripts manuscript
        WHERE manuscript.project_id = ?
        ORDER BY manuscript.updated_at DESC, manuscript.id DESC
        """,
        (project_id,),
    ).fetchall()
    conn.close()
    return rows


def get_manuscript(manuscript_id: int):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT
            manuscript.*,
            project.name AS project_name,
            project.domain AS project_domain,
            project.description AS project_description
        FROM manuscripts manuscript
        JOIN projects project ON project.id = manuscript.project_id
        WHERE manuscript.id = ?
        """,
        (manuscript_id,),
    ).fetchone()
    conn.close()
    return row


def update_manuscript(
    manuscript_id: int,
    *,
    title: str,
    status: str,
    citation_style: str,
):
    title = _require_text(title, "Manuscript title")

    if status not in MANUSCRIPT_STATUSES:
        raise ValueError("Unsupported manuscript status.")

    if citation_style not in CITATION_STYLES:
        raise ValueError("Unsupported citation style.")

    conn = get_connection()
    cur = conn.execute(
        """
        UPDATE manuscripts
        SET title = ?, status = ?, citation_style = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (title, status, citation_style, manuscript_id),
    )

    if cur.rowcount == 0:
        conn.close()
        raise ValueError("The manuscript no longer exists.")

    conn.commit()
    conn.close()


def _json_list(value: str | None) -> list:
    if isinstance(value, list):
        return value

    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []

    return parsed if isinstance(parsed, list) else []


def _submission_profile_from_row(manuscript_id: int, row) -> dict:
    profile = {
        "manuscript_id": manuscript_id,
        "target_journal": "",
        "journal_template": "General IMRaD",
        "short_title": "",
        "authors": [],
        "affiliations": [],
        "corresponding_author": {},
        "keywords": [],
        "word_limit": 5000,
        "abstract_word_limit": 250,
        "checklist": dict(DEFAULT_SUBMISSION_CHECKLIST),
    }

    if not row:
        return profile

    profile.update({
        "target_journal": row["target_journal"] or "",
        "journal_template": row["journal_template"] or "General IMRaD",
        "short_title": row["short_title"] or "",
        "authors": _json_list(row["authors_json"]),
        "affiliations": _json_list(row["affiliations_json"]),
        "keywords": [str(value) for value in _json_list(row["keywords_json"]) if str(value).strip()],
        "word_limit": max(1, int(row["word_limit"] or 5000)),
        "abstract_word_limit": max(1, int(row["abstract_word_limit"] or 250)),
    })

    try:
        corresponding = row["corresponding_author_json"] or {}
        if not isinstance(corresponding, dict):
            corresponding = json.loads(corresponding)
    except (TypeError, json.JSONDecodeError):
        corresponding = {}

    try:
        checklist = row["checklist_json"] or {}
        if not isinstance(checklist, dict):
            checklist = json.loads(checklist)
    except (TypeError, json.JSONDecodeError):
        checklist = {}

    profile["corresponding_author"] = corresponding if isinstance(corresponding, dict) else {}
    profile["checklist"].update(checklist if isinstance(checklist, dict) else {})
    return profile


def get_manuscript_submission_profile(manuscript_id: int) -> dict:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM manuscript_submission_profiles WHERE manuscript_id = ?",
        (manuscript_id,),
    ).fetchone()
    conn.close()
    return _submission_profile_from_row(manuscript_id, row)


def update_manuscript_submission_profile(
    manuscript_id: int,
    *,
    target_journal: str = "",
    journal_template: str = "General IMRaD",
    short_title: str = "",
    authors=None,
    affiliations=None,
    corresponding_author=None,
    keywords=None,
    word_limit: int = 5000,
    abstract_word_limit: int = 250,
    checklist=None,
) -> dict:
    if not get_manuscript(manuscript_id):
        raise ValueError("The manuscript no longer exists.")

    journal_template = _require_text(journal_template, "Journal template")
    word_limit = max(1, int(word_limit))
    abstract_word_limit = max(1, int(abstract_word_limit))
    clean_authors = [dict(row) for row in (authors or []) if isinstance(row, dict) and str(row.get("name", "")).strip()]
    clean_affiliations = [
        dict(row)
        for row in (affiliations or [])
        if isinstance(row, dict) and str(row.get("institution", "")).strip()
    ]
    clean_keywords = []

    for value in keywords or []:
        keyword = str(value or "").strip()

        if keyword and keyword.casefold() not in {item.casefold() for item in clean_keywords}:
            clean_keywords.append(keyword)

    clean_checklist = dict(DEFAULT_SUBMISSION_CHECKLIST)
    clean_checklist.update({
        key: bool(value)
        for key, value in (checklist or {}).items()
        if key in clean_checklist
    })
    conn = get_connection()

    with conn:
        conn.execute(
            """
            INSERT INTO manuscript_submission_profiles (
                manuscript_id,
                target_journal,
                journal_template,
                short_title,
                authors_json,
                affiliations_json,
                corresponding_author_json,
                keywords_json,
                word_limit,
                abstract_word_limit,
                checklist_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(manuscript_id) DO UPDATE SET
                target_journal = excluded.target_journal,
                journal_template = excluded.journal_template,
                short_title = excluded.short_title,
                authors_json = excluded.authors_json,
                affiliations_json = excluded.affiliations_json,
                corresponding_author_json = excluded.corresponding_author_json,
                keywords_json = excluded.keywords_json,
                word_limit = excluded.word_limit,
                abstract_word_limit = excluded.abstract_word_limit,
                checklist_json = excluded.checklist_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                manuscript_id,
                target_journal.strip() or None,
                journal_template,
                short_title.strip() or None,
                json.dumps(clean_authors, ensure_ascii=False),
                json.dumps(clean_affiliations, ensure_ascii=False),
                json.dumps(corresponding_author or {}, ensure_ascii=False),
                json.dumps(clean_keywords, ensure_ascii=False),
                word_limit,
                abstract_word_limit,
                json.dumps(clean_checklist),
            ),
        )
        conn.execute(
            "UPDATE manuscripts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (manuscript_id,),
        )

    conn.close()
    return get_manuscript_submission_profile(manuscript_id)


def delete_manuscript(manuscript_id: int):
    conn = get_connection()
    files = conn.execute(
        """
        SELECT storage_path FROM manuscript_assets
        WHERE manuscript_id = ? AND storage_path IS NOT NULL
        """,
        (manuscript_id,),
    ).fetchall()
    conn.execute("DELETE FROM manuscripts WHERE id = ?", (manuscript_id,))
    conn.commit()
    conn.close()
    _delete_manuscript_files(row["storage_path"] for row in files)
    delete_manuscript_asset_directory(manuscript_id)


def get_manuscript_sections(manuscript_id: int):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT *
        FROM manuscript_sections
        WHERE manuscript_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (manuscript_id,),
    ).fetchall()
    conn.close()
    return rows


def get_manuscript_section(section_id: int):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM manuscript_sections WHERE id = ?",
        (section_id,),
    ).fetchone()
    conn.close()
    return row


def add_manuscript_section(
    manuscript_id: int,
    title: str,
    *,
    section_type: str = "custom",
    parent_section_id: int | None = None,
) -> int:
    title = _require_text(title, "Section title")
    conn = get_connection()
    maximum = conn.execute(
        """
        SELECT COALESCE(MAX(sort_order), 0) AS maximum
        FROM manuscript_sections
        WHERE manuscript_id = ?
        """,
        (manuscript_id,),
    ).fetchone()["maximum"]
    cur = conn.execute(
        """
        INSERT INTO manuscript_sections (
            manuscript_id,
            parent_section_id,
            section_type,
            title,
            sort_order
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (manuscript_id, parent_section_id, section_type, title, maximum + 1),
    )
    section_id = cur.lastrowid
    conn.execute(
        "UPDATE manuscripts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (manuscript_id,),
    )
    conn.commit()
    conn.close()
    return section_id


def update_manuscript_section(
    section_id: int,
    *,
    title: str | None = None,
    content_md: str | None = None,
):
    section = get_manuscript_section(section_id)

    if not section:
        raise ValueError("The section no longer exists.")

    new_title = section["title"] if title is None else _require_text(title, "Section title")
    new_content = section["content_md"] if content_md is None else str(content_md)
    conn = get_connection()

    with conn:
        conn.execute(
            """
            UPDATE manuscript_sections
            SET title = ?, content_md = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_title, new_content, section_id),
        )
        conn.execute(
            "UPDATE manuscripts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (section["manuscript_id"],),
        )
        _sync_section_citations(conn, section_id, section["manuscript_id"], new_content)

    conn.close()


def delete_manuscript_section(section_id: int):
    section = get_manuscript_section(section_id)

    if not section:
        return

    conn = get_connection()

    with conn:
        removed_assets = conn.execute(
            """
            SELECT id, asset_type, storage_path FROM manuscript_assets
            WHERE section_id = ?
            """,
            (section_id,),
        ).fetchall()

        if removed_assets:
            other_sections = conn.execute(
                """
                SELECT id, content_md FROM manuscript_sections
                WHERE manuscript_id = ? AND id != ?
                """,
                (section["manuscript_id"], section_id),
            ).fetchall()

            for other_section in other_sections:
                content = other_section["content_md"] or ""

                for asset in removed_assets:
                    token = manuscript_asset_reference_token(
                        asset["asset_type"],
                        asset["id"],
                    )
                    content = re.sub(
                        rf"\s*{re.escape(token)}\s*",
                        " ",
                        content,
                    ).strip()

                conn.execute(
                    """
                    UPDATE manuscript_sections
                    SET content_md = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (content, other_section["id"]),
                )

        conn.execute("DELETE FROM manuscript_sections WHERE id = ?", (section_id,))
        conn.execute(
            "UPDATE manuscripts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (section["manuscript_id"],),
        )

    conn.close()
    _delete_manuscript_files(asset["storage_path"] for asset in removed_assets)


def move_manuscript_section(section_id: int, direction: int):
    section = get_manuscript_section(section_id)

    if not section or direction not in (-1, 1):
        return

    sections = get_manuscript_sections(section["manuscript_id"])
    section_ids = [row["id"] for row in sections]
    index = section_ids.index(section_id)
    target = index + direction

    if target < 0 or target >= len(section_ids):
        return

    section_ids[index], section_ids[target] = section_ids[target], section_ids[index]
    conn = get_connection()

    with conn:
        for order, current_id in enumerate(section_ids, start=1):
            conn.execute(
                "UPDATE manuscript_sections SET sort_order = ? WHERE id = ?",
                (order, current_id),
            )
        conn.execute(
            "UPDATE manuscripts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (section["manuscript_id"],),
        )

    conn.close()


def _json_object(value: str | None) -> dict:
    if isinstance(value, dict):
        return value

    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}

    return parsed if isinstance(parsed, dict) else {}


def manuscript_asset_reference_token(asset_type: str, asset_id: int) -> str:
    if asset_type not in MANUSCRIPT_ASSET_TYPES:
        raise ValueError("Unsupported manuscript object type.")

    return f"[[{asset_type}:{int(asset_id)}]]"


def get_manuscript_assets(
    manuscript_id: int,
    *,
    section_id: int | None = None,
) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT asset.*, section.sort_order AS section_sort_order
        FROM manuscript_assets asset
        JOIN manuscript_sections section ON section.id = asset.section_id
        WHERE asset.manuscript_id = ?
        ORDER BY section.sort_order ASC, asset.sort_order ASC, asset.id ASC
        """,
        (manuscript_id,),
    ).fetchall()
    conn.close()
    return _manuscript_assets_from_rows(rows, section_id=section_id)


def _manuscript_assets_from_rows(rows, *, section_id: int | None = None):
    counters = {asset_type: 0 for asset_type in MANUSCRIPT_ASSET_TYPES}
    assets = []

    for row in rows:
        asset = dict(row)
        asset_type = asset["asset_type"]
        counters[asset_type] = counters.get(asset_type, 0) + 1
        asset["number"] = counters[asset_type]
        asset["label"] = f"{asset_type.title()} {asset['number']}"
        asset["reference_token"] = manuscript_asset_reference_token(
            asset_type,
            asset["id"],
        )
        asset["content"] = _json_object(asset.pop("content_json", "{}"))

        if section_id is None or asset["section_id"] == section_id:
            assets.append(asset)

    return assets


def get_manuscript_asset(asset_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT manuscript_id FROM manuscript_assets WHERE id = ?",
        (asset_id,),
    ).fetchone()
    conn.close()

    if not row:
        return None

    return next(
        (
            asset
            for asset in get_manuscript_assets(row["manuscript_id"])
            if asset["id"] == asset_id
        ),
        None,
    )


def create_manuscript_asset(
    manuscript_id: int,
    section_id: int,
    asset_type: str,
    caption: str,
    *,
    alt_text: str = "",
    original_filename: str | None = None,
    storage_path: str | None = None,
    mime_type: str | None = None,
    content: dict | None = None,
) -> int:
    if asset_type not in MANUSCRIPT_ASSET_TYPES:
        raise ValueError("Unsupported manuscript object type.")

    caption = _require_text(caption, "Caption")
    conn = get_connection()
    section = conn.execute(
        """
        SELECT id FROM manuscript_sections
        WHERE id = ? AND manuscript_id = ?
        """,
        (section_id, manuscript_id),
    ).fetchone()

    if not section:
        conn.close()
        raise ValueError("The selected manuscript section no longer exists.")

    maximum = conn.execute(
        """
        SELECT COALESCE(MAX(sort_order), 0) AS maximum
        FROM manuscript_assets
        WHERE manuscript_id = ? AND section_id = ?
        """,
        (manuscript_id, section_id),
    ).fetchone()["maximum"]

    with conn:
        cur = conn.execute(
            """
            INSERT INTO manuscript_assets (
                manuscript_id,
                section_id,
                asset_type,
                caption,
                alt_text,
                original_filename,
                storage_path,
                mime_type,
                content_json,
                sort_order
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                manuscript_id,
                section_id,
                asset_type,
                caption,
                str(alt_text or "").strip() or None,
                original_filename,
                storage_path,
                mime_type,
                json.dumps(content or {}, ensure_ascii=False),
                maximum + 1,
            ),
        )
        conn.execute(
            "UPDATE manuscripts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (manuscript_id,),
        )

    asset_id = cur.lastrowid
    conn.close()
    return asset_id


def update_manuscript_asset(
    asset_id: int,
    *,
    caption: str,
    alt_text: str = "",
    original_filename: str | None = None,
    storage_path: str | None = None,
    mime_type: str | None = None,
    content: dict | None = None,
):
    asset = get_manuscript_asset(asset_id)

    if not asset:
        raise ValueError("The manuscript object no longer exists.")

    caption = _require_text(caption, "Caption")
    conn = get_connection()

    with conn:
        conn.execute(
            """
            UPDATE manuscript_assets
            SET caption = ?,
                alt_text = ?,
                original_filename = ?,
                storage_path = ?,
                mime_type = ?,
                content_json = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                caption,
                str(alt_text or "").strip() or None,
                original_filename,
                storage_path,
                mime_type,
                json.dumps(content or {}, ensure_ascii=False),
                asset_id,
            ),
        )
        conn.execute(
            "UPDATE manuscripts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (asset["manuscript_id"],),
        )

    conn.close()

    if asset.get("storage_path") and asset.get("storage_path") != storage_path:
        _delete_manuscript_files([asset["storage_path"]])


def move_manuscript_asset(asset_id: int, direction: int):
    asset = get_manuscript_asset(asset_id)

    if not asset or direction not in (-1, 1):
        return

    section_assets = get_manuscript_assets(
        asset["manuscript_id"],
        section_id=asset["section_id"],
    )
    asset_ids = [item["id"] for item in section_assets]
    index = asset_ids.index(asset_id)
    target = index + direction

    if target < 0 or target >= len(asset_ids):
        return

    asset_ids[index], asset_ids[target] = asset_ids[target], asset_ids[index]
    conn = get_connection()

    with conn:
        for order, current_id in enumerate(asset_ids, start=1):
            conn.execute(
                "UPDATE manuscript_assets SET sort_order = ? WHERE id = ?",
                (order, current_id),
            )
        conn.execute(
            "UPDATE manuscripts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (asset["manuscript_id"],),
        )

    conn.close()


def delete_manuscript_asset(asset_id: int):
    asset = get_manuscript_asset(asset_id)

    if not asset:
        return

    token = asset["reference_token"]
    conn = get_connection()

    with conn:
        sections = conn.execute(
            """
            SELECT id, content_md FROM manuscript_sections
            WHERE manuscript_id = ? AND content_md LIKE ?
            """,
            (asset["manuscript_id"], f"%{token}%"),
        ).fetchall()

        for section in sections:
            content = re.sub(
                rf"\s*{re.escape(token)}\s*",
                " ",
                section["content_md"] or "",
            ).strip()
            conn.execute(
                """
                UPDATE manuscript_sections
                SET content_md = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (content, section["id"]),
            )

        conn.execute("DELETE FROM manuscript_assets WHERE id = ?", (asset_id,))
        conn.execute(
            "UPDATE manuscripts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (asset["manuscript_id"],),
        )

    conn.close()
    _delete_manuscript_files([asset.get("storage_path")])


def insert_manuscript_asset_reference(
    section_id: int,
    asset_id: int,
    *,
    placement: str = "end",
    after_paragraph: int | None = None,
) -> str:
    section = get_manuscript_section(section_id)
    asset = get_manuscript_asset(asset_id)

    if not section or not asset:
        raise ValueError("Select an existing section and manuscript object.")

    if section["manuscript_id"] != asset["manuscript_id"]:
        raise ValueError("The object belongs to another manuscript.")

    token = asset["reference_token"]
    content = str(section["content_md"] or "").strip()

    if token in content:
        return token

    if placement == "beginning":
        updated = f"{token}\n\n{content}".strip()
    elif placement == "after_paragraph" and content:
        paragraphs = re.split(r"\n\s*\n", content)
        position = max(0, min(int(after_paragraph or 0) + 1, len(paragraphs)))
        paragraphs.insert(position, token)
        updated = "\n\n".join(paragraphs).strip()
    else:
        updated = f"{content} {token}".strip() if content else token

    update_manuscript_section(section_id, content_md=updated)
    return token


def _ascii_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", ascii_text.casefold())


def _base_citation_key(item) -> str:
    authors = str(item["authors"] or "")
    first_author = re.split(r"[;,]", authors, maxsplit=1)[0].strip()
    author_parts = re.findall(r"[A-Za-zÀ-ž'-]+", first_author)
    surname = author_parts[-1] if author_parts else "source"
    year = str(item["publication_year"] or "nd")
    return (_ascii_slug(surname) or "source") + year


def get_project_library_sources(project_id: int, search: str = ""):
    clauses = [
        "EXISTS (SELECT 1 FROM library_item_projects link "
        "WHERE link.item_id = item.id AND link.project_id = ?)"
    ]
    params: list = [project_id]

    if search.strip():
        pattern = f"%{search.strip()}%"
        clauses.append(
            "(item.title LIKE ? OR COALESCE(item.authors, '') LIKE ? "
            "OR COALESCE(item.doi, '') LIKE ?)"
        )
        params.extend([pattern, pattern, pattern])

    conn = get_connection()
    rows = conn.execute(
        f"""
        SELECT item.*
        FROM library_items item
        WHERE {' AND '.join(clauses)}
        ORDER BY item.title COLLATE NOCASE ASC
        """,
        params,
    ).fetchall()
    conn.close()
    return rows


def get_manuscript_sources(manuscript_id: int):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT
            source.manuscript_id,
            source.library_item_id,
            source.citation_key,
            source.notes AS source_notes,
            source.created_at AS attached_at,
            item.*
        FROM manuscript_sources source
        JOIN library_items item ON item.id = source.library_item_id
        WHERE source.manuscript_id = ?
        ORDER BY item.title COLLATE NOCASE ASC
        """,
        (manuscript_id,),
    ).fetchall()
    conn.close()
    return rows


def get_manuscript_workspace(manuscript_id: int):
    manuscript, sections, sources, asset_rows, profile_row = fetch_many(
        [
            (
                """
                SELECT manuscript.*, project.name AS project_name,
                       project.domain AS project_domain,
                       project.description AS project_description
                FROM manuscripts manuscript
                JOIN projects project ON project.id = manuscript.project_id
                WHERE manuscript.id = ?
                """,
                (manuscript_id,),
                "one",
            ),
            (
                """
                SELECT * FROM manuscript_sections
                WHERE manuscript_id = ?
                ORDER BY sort_order ASC, id ASC
                """,
                (manuscript_id,),
                "all",
            ),
            (
                """
                SELECT source.manuscript_id, source.library_item_id,
                       source.citation_key, source.notes AS source_notes,
                       source.created_at AS attached_at, item.*
                FROM manuscript_sources source
                JOIN library_items item ON item.id = source.library_item_id
                WHERE source.manuscript_id = ?
                ORDER BY item.title COLLATE NOCASE ASC
                """,
                (manuscript_id,),
                "all",
            ),
            (
                """
                SELECT asset.*, section.sort_order AS section_sort_order
                FROM manuscript_assets asset
                JOIN manuscript_sections section ON section.id = asset.section_id
                WHERE asset.manuscript_id = ?
                ORDER BY section.sort_order ASC, asset.sort_order ASC, asset.id ASC
                """,
                (manuscript_id,),
                "all",
            ),
            (
                "SELECT * FROM manuscript_submission_profiles WHERE manuscript_id = ?",
                (manuscript_id,),
                "one",
            ),
        ]
    )
    return {
        "manuscript": manuscript,
        "sections": sections,
        "sources": sources,
        "assets": _manuscript_assets_from_rows(asset_rows),
        "submission_profile": _submission_profile_from_row(
            manuscript_id,
            profile_row,
        ),
    }


def attach_manuscript_source(manuscript_id: int, library_item_id: int) -> str:
    conn = get_connection()
    item = conn.execute(
        "SELECT * FROM library_items WHERE id = ?",
        (library_item_id,),
    ).fetchone()

    if not item:
        conn.close()
        raise ValueError("The selected library source no longer exists.")

    existing = conn.execute(
        """
        SELECT citation_key
        FROM manuscript_sources
        WHERE manuscript_id = ? AND library_item_id = ?
        """,
        (manuscript_id, library_item_id),
    ).fetchone()

    if existing:
        conn.close()
        return existing["citation_key"]

    base_key = _base_citation_key(item)
    citation_key = base_key
    suffix = 2

    while conn.execute(
        """
        SELECT 1 FROM manuscript_sources
        WHERE manuscript_id = ? AND citation_key = ? COLLATE NOCASE
        """,
        (manuscript_id, citation_key),
    ).fetchone():
        citation_key = f"{base_key}{suffix}"
        suffix += 1

    with conn:
        conn.execute(
            """
            INSERT INTO manuscript_sources (
                manuscript_id,
                library_item_id,
                citation_key
            )
            VALUES (?, ?, ?)
            """,
            (manuscript_id, library_item_id, citation_key),
        )
        conn.execute(
            "UPDATE manuscripts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (manuscript_id,),
        )

    conn.close()
    return citation_key


def update_manuscript_source(
    manuscript_id: int,
    library_item_id: int,
    *,
    citation_key: str,
    notes: str = "",
):
    citation_key = _require_text(citation_key, "Citation key")

    if not re.fullmatch(r"[A-Za-z0-9_-]+", citation_key):
        raise ValueError("Citation keys may contain letters, numbers, _ and - only.")

    conn = get_connection()
    existing = conn.execute(
        """
        SELECT citation_key
        FROM manuscript_sources
        WHERE manuscript_id = ? AND library_item_id = ?
        """,
        (manuscript_id, library_item_id),
    ).fetchone()

    if not existing:
        conn.close()
        raise ValueError("The source is no longer attached to this manuscript.")

    old_key = existing["citation_key"]

    with conn:
        conn.execute(
            """
            UPDATE manuscript_sources
            SET citation_key = ?, notes = ?
            WHERE manuscript_id = ? AND library_item_id = ?
            """,
            (citation_key, notes.strip() or None, manuscript_id, library_item_id),
        )
        conn.execute(
            """
            UPDATE manuscript_citations
            SET citation_key = ?
            WHERE manuscript_id = ? AND library_item_id = ?
            """,
            (citation_key, manuscript_id, library_item_id),
        )

        if old_key.casefold() != citation_key.casefold():
            section_rows = conn.execute(
                """
                SELECT id, content_md
                FROM manuscript_sections
                WHERE manuscript_id = ? AND content_md LIKE ?
                """,
                (manuscript_id, f"%[@{old_key}]%"),
            ).fetchall()

            for section in section_rows:
                updated_content = re.sub(
                    rf"\[@{re.escape(old_key)}\]",
                    f"[@{citation_key}]",
                    section["content_md"],
                    flags=re.IGNORECASE,
                )
                conn.execute(
                    """
                    UPDATE manuscript_sections
                    SET content_md = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (updated_content, section["id"]),
                )
                _sync_section_citations(
                    conn,
                    section["id"],
                    manuscript_id,
                    updated_content,
                )

    conn.close()


def detach_manuscript_source(manuscript_id: int, library_item_id: int):
    conn = get_connection()
    conn.execute(
        """
        DELETE FROM manuscript_sources
        WHERE manuscript_id = ? AND library_item_id = ?
        """,
        (manuscript_id, library_item_id),
    )
    conn.commit()
    conn.close()


def _sync_section_citations(conn, section_id: int, manuscript_id: int, content: str):
    keys = {
        key.strip()
        for key in re.findall(r"\[@([^\]]+)\]", content or "")
        if key.strip()
    }
    conn.execute("DELETE FROM manuscript_citations WHERE section_id = ?", (section_id,))

    for key in keys:
        source = conn.execute(
            """
            SELECT library_item_id, citation_key
            FROM manuscript_sources
            WHERE manuscript_id = ? AND citation_key = ? COLLATE NOCASE
            """,
            (manuscript_id, key),
        ).fetchone()

        if source:
            conn.execute(
                """
                INSERT INTO manuscript_citations (
                    manuscript_id,
                    section_id,
                    library_item_id,
                    citation_key
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    manuscript_id,
                    section_id,
                    source["library_item_id"],
                    source["citation_key"],
                ),
            )


def validate_section_citations(content: str, sources) -> dict:
    tokens = [
        key.strip()
        for key in re.findall(r"\[@([^\]]+)\]", content or "")
        if key.strip()
    ]
    attached_by_fold = {
        str(source["citation_key"]).casefold(): str(source["citation_key"])
        for source in sources
    }
    valid_keys = []
    unknown_keys = []

    for key in tokens:
        canonical = attached_by_fold.get(key.casefold())
        target = valid_keys if canonical else unknown_keys
        value = canonical or key

        if value not in target:
            target.append(value)

    used_folds = {key.casefold() for key in valid_keys}
    unused_keys = [
        str(source["citation_key"])
        for source in sources
        if str(source["citation_key"]).casefold() not in used_folds
    ]
    return {
        "tokens": tokens,
        "valid_keys": valid_keys,
        "unknown_keys": unknown_keys,
        "unused_keys": unused_keys,
    }


def insert_section_citations(
    section_id: int,
    library_item_ids,
    *,
    placement: str = "end",
    after_paragraph: int | None = None,
) -> list[str]:
    section = get_manuscript_section(section_id)

    if not section:
        raise ValueError("Select a manuscript section first.")

    item_ids = []

    for value in library_item_ids or []:
        item_id = int(value)

        if item_id not in item_ids:
            item_ids.append(item_id)

    if not item_ids:
        raise ValueError("Select at least one attached source.")

    conn = get_connection()
    placeholders = ",".join("?" for _ in item_ids)
    rows = conn.execute(
        f"""
        SELECT library_item_id, citation_key
        FROM manuscript_sources
        WHERE manuscript_id = ? AND library_item_id IN ({placeholders})
        """,
        (section["manuscript_id"], *item_ids),
    ).fetchall()
    conn.close()
    sources_by_id = {row["library_item_id"]: row for row in rows}
    missing_ids = [item_id for item_id in item_ids if item_id not in sources_by_id]

    if missing_ids:
        raise ValueError("Attach every selected source to the manuscript first.")

    tokens = [f"[@{sources_by_id[item_id]['citation_key']}]" for item_id in item_ids]
    citation_text = " ".join(tokens)
    content = str(section["content_md"] or "").strip()

    if placement == "beginning":
        new_content = f"{citation_text}\n\n{content}".strip()
    elif placement == "after_paragraph" and content:
        paragraphs = re.split(r"\n\s*\n", content)
        position = max(0, min(int(after_paragraph or 0) + 1, len(paragraphs)))
        paragraphs.insert(position, citation_text)
        new_content = "\n\n".join(paragraphs).strip()
    else:
        new_content = f"{content} {citation_text}".strip() if content else citation_text

    update_manuscript_section(section_id, content_md=new_content)
    return tokens


def insert_section_citation(section_id: int, library_item_id: int):
    return insert_section_citations(section_id, [library_item_id])[0]


def get_project_evidence_candidates(project_id: int) -> list[dict]:
    experiments, summaries, ideas = fetch_many(
        [
            (
                """
                SELECT id, title, objective FROM chats
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (project_id,),
                "all",
            ),
            (
                """
                SELECT summary.id, summary.scope, summary.summary_style,
                       summary.content, chat.title AS chat_title
                FROM summaries summary
                LEFT JOIN chats chat ON chat.id = summary.chat_id
                WHERE summary.project_id = ?
                ORDER BY summary.created_at DESC, summary.id DESC
                """,
                (project_id,),
                "all",
            ),
            (
                """
                SELECT id, title, description, evidence, importance
                FROM project_ideas
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (project_id,),
                "all",
            ),
        ]
    )
    candidates = []

    for row in experiments:
        candidates.append({
            "evidence_type": "experiment",
            "evidence_id": row["id"],
            "label": row["title"],
            "excerpt": row["objective"] or "",
        })

    for row in summaries:
        scope_label = row["chat_title"] or "Project summary"
        candidates.append({
            "evidence_type": "summary",
            "evidence_id": row["id"],
            "label": f"{scope_label} · {row['summary_style']}",
            "excerpt": row["content"] or "",
        })

    for row in ideas:
        candidates.append({
            "evidence_type": "key_idea",
            "evidence_id": row["id"],
            "label": row["title"],
            "excerpt": "\n".join(
                value
                for value in (row["description"], row["evidence"])
                if value
            ),
        })

    return candidates


def get_manuscript_evidence(manuscript_id: int):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT *
        FROM manuscript_evidence
        WHERE manuscript_id = ?
        ORDER BY evidence_type ASC, label COLLATE NOCASE ASC
        """,
        (manuscript_id,),
    ).fetchall()
    conn.close()
    return rows


def _json_list(value: str | None) -> list:
    if isinstance(value, list):
        return value

    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []

    return parsed if isinstance(parsed, list) else []


def get_manuscript_ai_context(manuscript_id: int) -> dict:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM manuscript_ai_contexts WHERE manuscript_id = ?",
        (manuscript_id,),
    ).fetchone()
    conn.close()

    if not row:
        return {
            "manuscript_id": manuscript_id,
            "context_mode": "Current section",
            "section_ids": [],
            "source_ids": [],
            "evidence_keys": [],
        }

    return {
        "manuscript_id": manuscript_id,
        "context_mode": (
            row["context_mode"]
            if row["context_mode"] in AI_CONTEXT_MODES
            else "Current section"
        ),
        "section_ids": [
            int(value)
            for value in _json_list(row["section_ids_json"])
            if str(value).isdigit()
        ],
        "source_ids": [
            int(value)
            for value in _json_list(row["source_ids_json"])
            if str(value).isdigit()
        ],
        "evidence_keys": [
            str(value)
            for value in _json_list(row["evidence_keys_json"])
            if re.fullmatch(r"(?:experiment|summary|key_idea):\d+", str(value))
        ],
    }


def update_manuscript_ai_context(
    manuscript_id: int,
    *,
    context_mode: str,
    section_ids=None,
    source_ids=None,
    evidence_keys=None,
) -> dict:
    if context_mode not in AI_CONTEXT_MODES:
        raise ValueError("Unsupported AI context mode.")

    requested_sections = {
        int(value) for value in (section_ids or []) if str(value).isdigit()
    }
    requested_sources = {
        int(value) for value in (source_ids or []) if str(value).isdigit()
    }
    requested_evidence = {
        str(value)
        for value in (evidence_keys or [])
        if re.fullmatch(r"(?:experiment|summary|key_idea):\d+", str(value))
    }
    conn = get_connection()
    manuscript_exists = conn.execute(
        "SELECT 1 FROM manuscripts WHERE id = ?",
        (manuscript_id,),
    ).fetchone()

    if not manuscript_exists:
        conn.close()
        raise ValueError("The manuscript no longer exists.")

    allowed_sections = {
        row["id"]
        for row in conn.execute(
            "SELECT id FROM manuscript_sections WHERE manuscript_id = ?",
            (manuscript_id,),
        ).fetchall()
    }
    allowed_sources = {
        row["library_item_id"]
        for row in conn.execute(
            "SELECT library_item_id FROM manuscript_sources WHERE manuscript_id = ?",
            (manuscript_id,),
        ).fetchall()
    }
    allowed_evidence = {
        f"{row['evidence_type']}:{row['evidence_id']}"
        for row in conn.execute(
            """
            SELECT evidence_type, evidence_id
            FROM manuscript_evidence
            WHERE manuscript_id = ?
            """,
            (manuscript_id,),
        ).fetchall()
    }
    normalized_sections = sorted(requested_sections & allowed_sections)
    normalized_sources = sorted(requested_sources & allowed_sources)
    normalized_evidence = sorted(requested_evidence & allowed_evidence)

    with conn:
        conn.execute(
            """
            INSERT INTO manuscript_ai_contexts (
                manuscript_id,
                context_mode,
                section_ids_json,
                source_ids_json,
                evidence_keys_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(manuscript_id) DO UPDATE SET
                context_mode = excluded.context_mode,
                section_ids_json = excluded.section_ids_json,
                source_ids_json = excluded.source_ids_json,
                evidence_keys_json = excluded.evidence_keys_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                manuscript_id,
                context_mode,
                json.dumps(normalized_sections),
                json.dumps(normalized_sources),
                json.dumps(normalized_evidence),
            ),
        )

    conn.close()
    return get_manuscript_ai_context(manuscript_id)


def attach_manuscript_evidence(
    manuscript_id: int,
    evidence_type: str,
    evidence_id: int,
    label: str,
    excerpt: str = "",
):
    if evidence_type not in ("experiment", "summary", "key_idea"):
        raise ValueError("Unsupported evidence type.")

    conn = get_connection()
    conn.execute(
        """
        INSERT OR IGNORE INTO manuscript_evidence (
            manuscript_id,
            evidence_type,
            evidence_id,
            label,
            excerpt
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (manuscript_id, evidence_type, evidence_id, label, excerpt or None),
    )
    conn.commit()
    conn.close()


def detach_manuscript_evidence(manuscript_id: int, evidence_type: str, evidence_id: int):
    conn = get_connection()
    conn.execute(
        """
        DELETE FROM manuscript_evidence
        WHERE manuscript_id = ? AND evidence_type = ? AND evidence_id = ?
        """,
        (manuscript_id, evidence_type, evidence_id),
    )
    conn.commit()
    conn.close()


def _snapshot_for_manuscript(conn, manuscript_id: int) -> dict:
    manuscript = conn.execute(
        "SELECT * FROM manuscripts WHERE id = ?",
        (manuscript_id,),
    ).fetchone()

    if not manuscript:
        raise ValueError("The manuscript no longer exists.")

    sections = conn.execute(
        """
        SELECT * FROM manuscript_sections
        WHERE manuscript_id = ? ORDER BY sort_order, id
        """,
        (manuscript_id,),
    ).fetchall()
    sources = conn.execute(
        """
        SELECT * FROM manuscript_sources
        WHERE manuscript_id = ? ORDER BY citation_key
        """,
        (manuscript_id,),
    ).fetchall()
    evidence = conn.execute(
        """
        SELECT * FROM manuscript_evidence
        WHERE manuscript_id = ? ORDER BY id
        """,
        (manuscript_id,),
    ).fetchall()
    citations = conn.execute(
        """
        SELECT * FROM manuscript_citations
        WHERE manuscript_id = ? ORDER BY id
        """,
        (manuscript_id,),
    ).fetchall()
    assets = conn.execute(
        """
        SELECT * FROM manuscript_assets
        WHERE manuscript_id = ? ORDER BY section_id, sort_order, id
        """,
        (manuscript_id,),
    ).fetchall()
    submission_profile = conn.execute(
        "SELECT * FROM manuscript_submission_profiles WHERE manuscript_id = ?",
        (manuscript_id,),
    ).fetchone()
    return {
        "manuscript": {
            "title": manuscript["title"],
            "status": manuscript["status"],
            "citation_style": manuscript["citation_style"],
        },
        "sections": [dict(row) for row in sections],
        "sources": [dict(row) for row in sources],
        "evidence": [dict(row) for row in evidence],
        "citations": [dict(row) for row in citations],
        "assets": [dict(row) for row in assets],
        "submission_profile": dict(submission_profile) if submission_profile else None,
    }


def create_manuscript_version(
    manuscript_id: int,
    label: str,
    *,
    trigger_type: str = "manual",
    note: str = "",
) -> int:
    label = _require_text(label, "Version label")
    conn = get_connection()
    snapshot = _snapshot_for_manuscript(conn, manuscript_id)
    word_count = manuscript_word_count(snapshot["sections"])
    cur = conn.execute(
        """
        INSERT INTO manuscript_versions (
            manuscript_id,
            label,
            trigger_type,
            note,
            snapshot_json,
            word_count
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            manuscript_id,
            label,
            trigger_type,
            note.strip() or None,
            json.dumps(snapshot, ensure_ascii=False, default=str),
            word_count,
        ),
    )
    version_id = cur.lastrowid
    conn.commit()
    conn.close()
    return version_id


def get_manuscript_versions(
    manuscript_id: int,
    *,
    limit: int = 20,
    offset: int = 0,
):
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT
            version.id,
            version.manuscript_id,
            version.label,
            version.trigger_type,
            version.note,
            version.word_count,
            version.created_at,
            version.snapshot_json,
            (SELECT COUNT(*) FROM manuscript_version_comments comment
             WHERE comment.version_id = version.id) AS comment_count
        FROM manuscript_versions version
        WHERE version.manuscript_id = ?
        ORDER BY version.created_at DESC, version.id DESC
        LIMIT ? OFFSET ?
        """,
        (manuscript_id, limit, offset),
    ).fetchall()
    conn.close()
    return _normalize_manuscript_versions(rows)


def _normalize_manuscript_versions(rows):
    results = []

    for row in rows:
        result = dict(row)
        snapshot = result.pop("snapshot_json", None)

        if isinstance(snapshot, dict):
            result["snapshot"] = snapshot
        else:
            try:
                result["snapshot"] = json.loads(snapshot)
            except (TypeError, json.JSONDecodeError):
                result["snapshot"] = {}

        results.append(result)

    return results


def get_manuscript_versions_page(
    manuscript_id: int,
    *,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    page = max(1, int(page))
    page_size = max(5, min(int(page_size), 50))
    count_row, rows = fetch_many(
        [
            (
                "SELECT COUNT(*) AS count FROM manuscript_versions WHERE manuscript_id = ?",
                (manuscript_id,),
                "one",
            ),
            (
                """
                SELECT version.id, version.manuscript_id, version.label,
                       version.trigger_type, version.note, version.word_count,
                       version.created_at, version.snapshot_json,
                       (SELECT COUNT(*) FROM manuscript_version_comments comment
                        WHERE comment.version_id = version.id) AS comment_count
                FROM manuscript_versions version
                WHERE version.manuscript_id = ?
                ORDER BY version.created_at DESC, version.id DESC
                LIMIT ? OFFSET ?
                """,
                (manuscript_id, page_size, (page - 1) * page_size),
                "all",
            ),
        ]
    )
    return {
        "count": int(count_row["count"] if count_row else 0),
        "page": page,
        "page_size": page_size,
        "versions": _normalize_manuscript_versions(rows),
    }


def get_manuscript_version(version_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM manuscript_versions WHERE id = ?",
        (version_id,),
    ).fetchone()
    conn.close()

    if not row:
        return None

    result = dict(row)

    snapshot = row["snapshot_json"]

    if isinstance(snapshot, dict):
        result["snapshot"] = snapshot
    else:
        try:
            result["snapshot"] = json.loads(snapshot)
        except (TypeError, json.JSONDecodeError):
            result["snapshot"] = {}

    return result


def update_manuscript_version(
    version_id: int,
    *,
    label: str,
    note: str = "",
):
    label = _require_text(label, "Version label")
    conn = get_connection()
    cur = conn.execute(
        """
        UPDATE manuscript_versions
        SET label = ?, note = ?
        WHERE id = ?
        """,
        (label, note.strip() or None, version_id),
    )

    if cur.rowcount == 0:
        conn.close()
        raise ValueError("The selected version no longer exists.")

    conn.commit()
    conn.close()


def add_manuscript_version_comment(
    version_id: int,
    content: str,
    *,
    author_name: str = "Researcher",
) -> int:
    content = _require_text(content, "Comment")
    author_name = _require_text(author_name, "Comment author")
    conn = get_connection()
    version = conn.execute(
        "SELECT id FROM manuscript_versions WHERE id = ?",
        (version_id,),
    ).fetchone()

    if not version:
        conn.close()
        raise ValueError("The selected version no longer exists.")

    cur = conn.execute(
        """
        INSERT INTO manuscript_version_comments (version_id, author_name, content)
        VALUES (?, ?, ?)
        """,
        (version_id, author_name, content),
    )
    comment_id = cur.lastrowid
    conn.commit()
    conn.close()
    return comment_id


def get_manuscript_version_comments(version_id: int):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT * FROM manuscript_version_comments
        WHERE version_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (version_id,),
    ).fetchall()
    conn.close()
    return rows


def get_manuscript_version_comments_for_versions(version_ids) -> dict:
    normalized_ids = tuple(
        dict.fromkeys(int(value) for value in version_ids if int(value) > 0)
    )

    if not normalized_ids:
        return {}

    placeholders = ", ".join("?" for _ in normalized_ids)
    conn = get_connection()
    rows = conn.execute(
        f"""
        SELECT * FROM manuscript_version_comments
        WHERE version_id IN ({placeholders})
        ORDER BY version_id, created_at ASC, id ASC
        """,
        normalized_ids,
    ).fetchall()
    conn.close()
    comments_by_version = {}

    for row in rows:
        comments_by_version.setdefault(row["version_id"], []).append(row)

    return comments_by_version


def _apply_snapshot(conn, manuscript_id: int, snapshot: dict, *, title_override=None):
    current_paths = {
        row["storage_path"]
        for row in conn.execute(
            """
            SELECT storage_path FROM manuscript_assets
            WHERE manuscript_id = ? AND storage_path IS NOT NULL
            """,
            (manuscript_id,),
        ).fetchall()
        if row["storage_path"]
    }
    restored_paths = {
        str(asset.get("storage_path"))
        for asset in snapshot.get("assets", [])
        if asset.get("storage_path")
    }
    metadata = snapshot.get("manuscript", {})
    title = title_override or metadata.get("title") or "Untitled manuscript"
    status = metadata.get("status") if metadata.get("status") in MANUSCRIPT_STATUSES else "Draft"
    style = metadata.get("citation_style") if metadata.get("citation_style") in CITATION_STYLES else "APA 7"
    conn.execute(
        """
        UPDATE manuscripts
        SET title = ?, status = ?, citation_style = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (title, status, style, manuscript_id),
    )
    conn.execute("DELETE FROM manuscript_sections WHERE manuscript_id = ?", (manuscript_id,))
    conn.execute("DELETE FROM manuscript_sources WHERE manuscript_id = ?", (manuscript_id,))
    conn.execute("DELETE FROM manuscript_evidence WHERE manuscript_id = ?", (manuscript_id,))
    section_id_map = {}

    for position, section in enumerate(snapshot.get("sections", []), start=1):
        cur = conn.execute(
            """
            INSERT INTO manuscript_sections (
                manuscript_id,
                section_type,
                title,
                content_md,
                sort_order
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                manuscript_id,
                section.get("section_type") or "custom",
                section.get("title") or "Untitled section",
                section.get("content_md") or "",
                position,
            ),
        )
        section_id_map[section.get("id")] = cur.lastrowid

    for section in snapshot.get("sections", []):
        old_parent = section.get("parent_section_id")

        if old_parent in section_id_map:
            conn.execute(
                "UPDATE manuscript_sections SET parent_section_id = ? WHERE id = ?",
                (section_id_map[old_parent], section_id_map.get(section.get("id"))),
            )

    for source in snapshot.get("sources", []):
        item_exists = conn.execute(
            "SELECT 1 FROM library_items WHERE id = ?",
            (source.get("library_item_id"),),
        ).fetchone()

        if item_exists:
            conn.execute(
                """
                INSERT OR IGNORE INTO manuscript_sources (
                    manuscript_id,
                    library_item_id,
                    citation_key,
                    notes
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    manuscript_id,
                    source.get("library_item_id"),
                    source.get("citation_key") or "source",
                    source.get("notes"),
                ),
            )

    asset_id_map = {}
    skipped_asset_ids = set()

    for asset in snapshot.get("assets", []):
        new_section_id = section_id_map.get(asset.get("section_id"))

        if not new_section_id or asset.get("asset_type") not in MANUSCRIPT_ASSET_TYPES:
            continue

        if asset.get("asset_type") == "figure" and not Path(
            str(asset.get("storage_path") or "")
        ).is_file():
            if asset.get("id") is not None:
                skipped_asset_ids.add(asset.get("id"))
            continue

        cur = conn.execute(
            """
            INSERT INTO manuscript_assets (
                manuscript_id,
                section_id,
                asset_type,
                caption,
                alt_text,
                original_filename,
                storage_path,
                mime_type,
                content_json,
                sort_order
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                manuscript_id,
                new_section_id,
                asset.get("asset_type"),
                asset.get("caption") or "Untitled object",
                asset.get("alt_text"),
                asset.get("original_filename"),
                asset.get("storage_path"),
                asset.get("mime_type"),
                asset.get("content_json") or "{}",
                asset.get("sort_order") or 0,
            ),
        )
        asset_id_map[asset.get("id")] = cur.lastrowid

    if asset_id_map or skipped_asset_ids:
        restored_sections = conn.execute(
            """
            SELECT id, content_md FROM manuscript_sections
            WHERE manuscript_id = ?
            """,
            (manuscript_id,),
        ).fetchall()

        for section in restored_sections:
            content = section["content_md"] or ""

            for old_id, new_id in asset_id_map.items():
                content = re.sub(
                    rf"\[\[(figure|table|equation):{int(old_id)}\]\]",
                    lambda match: manuscript_asset_reference_token(
                        match.group(1),
                        new_id,
                    ),
                    content,
                )

            for old_id in skipped_asset_ids:
                content = re.sub(
                    rf"\s*\[\[figure:{int(old_id)}\]\]\s*",
                    " ",
                    content,
                ).strip()

            conn.execute(
                "UPDATE manuscript_sections SET content_md = ? WHERE id = ?",
                (content, section["id"]),
            )

    for evidence in snapshot.get("evidence", []):
        conn.execute(
            """
            INSERT OR IGNORE INTO manuscript_evidence (
                manuscript_id,
                evidence_type,
                evidence_id,
                label,
                excerpt
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                manuscript_id,
                evidence.get("evidence_type"),
                evidence.get("evidence_id"),
                evidence.get("label") or "Evidence",
                evidence.get("excerpt"),
            ),
        )

    for citation in snapshot.get("citations", []):
        new_section_id = section_id_map.get(citation.get("section_id"))

        if not new_section_id:
            continue

        source_exists = conn.execute(
            """
            SELECT 1 FROM manuscript_sources
            WHERE manuscript_id = ? AND library_item_id = ?
            """,
            (manuscript_id, citation.get("library_item_id")),
        ).fetchone()

        if source_exists:
            conn.execute(
                """
                INSERT OR IGNORE INTO manuscript_citations (
                    manuscript_id,
                    section_id,
                    library_item_id,
                    citation_key
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    manuscript_id,
                    new_section_id,
                    citation.get("library_item_id"),
                    citation.get("citation_key") or "source",
                ),
            )

    submission_profile = snapshot.get("submission_profile")

    if isinstance(submission_profile, dict):
        conn.execute(
            """
            INSERT INTO manuscript_submission_profiles (
                manuscript_id,
                target_journal,
                journal_template,
                short_title,
                authors_json,
                affiliations_json,
                corresponding_author_json,
                keywords_json,
                word_limit,
                abstract_word_limit,
                checklist_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(manuscript_id) DO UPDATE SET
                target_journal = excluded.target_journal,
                journal_template = excluded.journal_template,
                short_title = excluded.short_title,
                authors_json = excluded.authors_json,
                affiliations_json = excluded.affiliations_json,
                corresponding_author_json = excluded.corresponding_author_json,
                keywords_json = excluded.keywords_json,
                word_limit = excluded.word_limit,
                abstract_word_limit = excluded.abstract_word_limit,
                checklist_json = excluded.checklist_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                manuscript_id,
                submission_profile.get("target_journal"),
                submission_profile.get("journal_template") or "General IMRaD",
                submission_profile.get("short_title"),
                submission_profile.get("authors_json") or "[]",
                submission_profile.get("affiliations_json") or "[]",
                submission_profile.get("corresponding_author_json") or "{}",
                submission_profile.get("keywords_json") or "[]",
                max(1, int(submission_profile.get("word_limit") or 5000)),
                max(1, int(submission_profile.get("abstract_word_limit") or 250)),
                submission_profile.get("checklist_json") or "{}",
            ),
        )

    return current_paths - restored_paths


def restore_manuscript_version(version_id: int):
    version = get_manuscript_version(version_id)

    if not version:
        raise ValueError("The selected version no longer exists.")

    conn = get_connection()

    with conn:
        obsolete_paths = _apply_snapshot(
            conn,
            version["manuscript_id"],
            version["snapshot"],
        )

    conn.close()
    _delete_manuscript_files(obsolete_paths)


def restore_manuscript_section_from_version(
    version_id: int,
    snapshot_section_id: int,
    target_section_id: int,
    *,
    restore_title: bool = False,
) -> int:
    version = get_manuscript_version(version_id)

    if not version:
        raise ValueError("The selected version no longer exists.")

    snapshot_section = next(
        (
            row
            for row in version["snapshot"].get("sections", [])
            if int(row.get("id") or 0) == int(snapshot_section_id)
        ),
        None,
    )
    target_section = get_manuscript_section(target_section_id)

    if not snapshot_section or not target_section:
        raise ValueError("Select an existing section from the version and the current manuscript.")

    if int(target_section["manuscript_id"]) != int(version["manuscript_id"]):
        raise ValueError("The target section belongs to another manuscript.")

    content = str(snapshot_section.get("content_md") or "")
    snapshot_assets = {
        int(asset.get("id")): asset
        for asset in version["snapshot"].get("assets", [])
        if int(asset.get("section_id") or 0) == int(snapshot_section_id)
        and asset.get("id") is not None
    }
    current_assets = get_manuscript_assets(version["manuscript_id"])
    current_by_id = {int(asset["id"]): asset for asset in current_assets}

    for old_id, old_asset in snapshot_assets.items():
        if old_id in current_by_id:
            continue

        replacement = next(
            (
                asset
                for asset in current_assets
                if asset["asset_type"] == old_asset.get("asset_type")
                and str(asset.get("caption") or "").casefold()
                == str(old_asset.get("caption") or "").casefold()
            ),
            None,
        )
        old_token = manuscript_asset_reference_token(
            old_asset.get("asset_type"),
            old_id,
        )

        if replacement:
            content = content.replace(old_token, replacement["reference_token"])
        else:
            content = re.sub(rf"\s*{re.escape(old_token)}\s*", " ", content).strip()

    title = (
        _require_text(snapshot_section.get("title"), "Section title")
        if restore_title
        else target_section["title"]
    )
    conn = get_connection()

    with conn:
        conn.execute(
            """
            UPDATE manuscript_sections
            SET title = ?, content_md = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (title, content, target_section_id),
        )
        _sync_section_citations(
            conn,
            target_section_id,
            version["manuscript_id"],
            content,
        )
        conn.execute(
            "UPDATE manuscripts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (version["manuscript_id"],),
        )

    conn.close()
    return target_section_id


def duplicate_manuscript_version(version_id: int, title: str | None = None) -> int:
    version = get_manuscript_version(version_id)

    if not version:
        raise ValueError("The selected version no longer exists.")

    source = get_manuscript(version["manuscript_id"])
    duplicate_title = title or f"{version['snapshot'].get('manuscript', {}).get('title', 'Manuscript')} copy"
    manuscript_id = create_manuscript(
        source["project_id"],
        duplicate_title,
        create_default_sections=False,
    )
    conn = get_connection()

    with conn:
        _apply_snapshot(
            conn,
            manuscript_id,
            version["snapshot"],
            title_override=duplicate_title,
        )

    conn.close()
    return manuscript_id


def snapshot_to_text(snapshot: dict) -> str:
    parts = [f"# {snapshot.get('manuscript', {}).get('title', 'Manuscript')}"]

    for section in snapshot.get("sections", []):
        parts.append(f"\n## {section.get('title', 'Untitled section')}\n")
        parts.append(section.get("content_md", ""))

    return "\n".join(parts).strip()


def add_manuscript_ai_message(
    manuscript_id: int,
    *,
    section_id: int | None,
    role: str,
    mode: str,
    content: str,
    payload: dict | None = None,
) -> int:
    if role not in ("user", "assistant"):
        raise ValueError("Unsupported AI message role.")

    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO manuscript_ai_messages (
            manuscript_id,
            section_id,
            role,
            mode,
            content,
            payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            manuscript_id,
            section_id,
            role,
            mode,
            content,
            json.dumps(payload, ensure_ascii=False, default=str) if payload else None,
        ),
    )
    message_id = cur.lastrowid
    conn.commit()
    conn.close()
    return message_id


def get_manuscript_ai_messages(manuscript_id: int, limit: int = 20) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT *
        FROM manuscript_ai_messages
        WHERE manuscript_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (manuscript_id, max(1, min(int(limit), 100))),
    ).fetchall()
    conn.close()
    messages = []

    for row in reversed(rows):
        message = dict(row)

        payload = row["payload_json"] or {}

        if isinstance(payload, dict):
            message["payload"] = payload
        else:
            try:
                message["payload"] = json.loads(payload)
            except (TypeError, json.JSONDecodeError):
                message["payload"] = {}

        messages.append(message)

    return messages


def clear_manuscript_ai_messages(manuscript_id: int):
    conn = get_connection()
    conn.execute(
        "DELETE FROM manuscript_ai_messages WHERE manuscript_id = ?",
        (manuscript_id,),
    )
    conn.commit()
    conn.close()
