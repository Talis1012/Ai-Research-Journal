import json
import re
import unicodedata
from datetime import datetime

from db.database import get_connection


MANUSCRIPT_STATUSES = ("Draft", "In review", "Final")
CITATION_STYLES = ("APA 7", "Vancouver")
DEFAULT_SECTIONS = (
    ("abstract", "Abstract"),
    ("introduction", "Introduction"),
    ("methods", "Methods"),
    ("results", "Results"),
    ("discussion", "Discussion"),
    ("conclusion", "Conclusion"),
    ("references", "References"),
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


def delete_manuscript(manuscript_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM manuscripts WHERE id = ?", (manuscript_id,))
    conn.commit()
    conn.close()


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
        conn.execute("DELETE FROM manuscript_sections WHERE id = ?", (section_id,))
        conn.execute(
            "UPDATE manuscripts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (section["manuscript_id"],),
        )

    conn.close()


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


def insert_section_citation(section_id: int, library_item_id: int):
    section = get_manuscript_section(section_id)

    if not section:
        raise ValueError("Select a manuscript section first.")

    conn = get_connection()
    source = conn.execute(
        """
        SELECT citation_key
        FROM manuscript_sources
        WHERE manuscript_id = ? AND library_item_id = ?
        """,
        (section["manuscript_id"], library_item_id),
    ).fetchone()
    conn.close()

    if not source:
        raise ValueError("Attach this source to the manuscript first.")

    token = f"[@{source['citation_key']}]"
    content = section["content_md"].rstrip()
    new_content = f"{content} {token}".strip() if content else token
    update_manuscript_section(section_id, content_md=new_content)
    return token


def get_project_evidence_candidates(project_id: int) -> list[dict]:
    conn = get_connection()
    experiments = conn.execute(
        """
        SELECT id, title, objective
        FROM chats
        WHERE project_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (project_id,),
    ).fetchall()
    summaries = conn.execute(
        """
        SELECT summary.id, summary.scope, summary.summary_style, summary.content,
               chat.title AS chat_title
        FROM summaries summary
        LEFT JOIN chats chat ON chat.id = summary.chat_id
        WHERE summary.project_id = ?
        ORDER BY summary.created_at DESC, summary.id DESC
        """,
        (project_id,),
    ).fetchall()
    ideas = conn.execute(
        """
        SELECT id, title, description, evidence, importance
        FROM project_ideas
        WHERE project_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (project_id,),
    ).fetchall()
    conn.close()
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


def get_manuscript_versions(manuscript_id: int):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, manuscript_id, label, trigger_type, note, word_count, created_at
        FROM manuscript_versions
        WHERE manuscript_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (manuscript_id,),
    ).fetchall()
    conn.close()
    return rows


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

    try:
        result["snapshot"] = json.loads(row["snapshot_json"])
    except json.JSONDecodeError:
        result["snapshot"] = {}

    return result


def _apply_snapshot(conn, manuscript_id: int, snapshot: dict, *, title_override=None):
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


def restore_manuscript_version(version_id: int):
    version = get_manuscript_version(version_id)

    if not version:
        raise ValueError("The selected version no longer exists.")

    conn = get_connection()

    with conn:
        _apply_snapshot(conn, version["manuscript_id"], version["snapshot"])

    conn.close()


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

        try:
            message["payload"] = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
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
