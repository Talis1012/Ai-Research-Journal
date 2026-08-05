import json

from db.database import get_connection


DISCOVERY_MODES = ("Manual Search", "AI Recommendations")


def _normalize_source_mode(source_mode: str) -> str:
    normalized = str(source_mode or "").strip()

    if normalized not in DISCOVERY_MODES:
        raise ValueError("Unknown Discover search mode.")

    return normalized


def _json_dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_load(value: str | None, fallback):
    if isinstance(value, (dict, list)):
        return value

    try:
        loaded = json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback

    return loaded


def replace_project_discovery_results(
    project_id: int,
    *,
    results: list[dict],
    profile: dict,
    queries: list[str],
    search_options: dict,
    ai_error: str = "",
    source_mode: str = "AI Recommendations",
    page: int = 1,
):
    """Atomically replace the current Discover result set for a project."""
    if not project_id:
        raise ValueError("A project is required to persist Discover results.")

    source_mode = _normalize_source_mode(source_mode)
    normalized_results = [dict(work) for work in results]
    serialized_papers = []

    for position, work in enumerate(normalized_results, start=1):
        ranking_id = str(work.get("ranking_id") or f"candidate-{position}").strip()
        work["ranking_id"] = ranking_id
        serialized_papers.append((
            int(project_id),
            source_mode,
            ranking_id,
            position,
            str(work.get("openalex_id") or "").strip() or None,
            str(work.get("doi") or "").strip().lower() or None,
            str(work.get("title") or "Untitled paper").strip(),
            float(work.get("final_score") or 0),
            _json_dump(work),
        ))

    profile_json = _json_dump(profile or {})
    queries_json = _json_dump([
        str(query).strip()
        for query in queries
        if str(query).strip()
    ])
    search_options_json = _json_dump(search_options or {})
    conn = get_connection()

    try:
        project = conn.execute(
            "SELECT id FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()

        if not project:
            raise ValueError("The selected project no longer exists.")

        with conn:
            conn.execute(
                """
                INSERT INTO project_discovery_sets (
                    project_id,
                    source_mode,
                    profile_json,
                    queries_json,
                    search_options_json,
                    ai_error,
                    result_count,
                    openalex_page
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, source_mode) DO UPDATE SET
                    profile_json = excluded.profile_json,
                    queries_json = excluded.queries_json,
                    search_options_json = excluded.search_options_json,
                    ai_error = excluded.ai_error,
                    result_count = excluded.result_count,
                    openalex_page = excluded.openalex_page,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    project_id,
                    source_mode,
                    profile_json,
                    queries_json,
                    search_options_json,
                    str(ai_error or ""),
                    len(serialized_papers),
                    max(1, int(page)),
                ),
            )
            conn.execute(
                """
                DELETE FROM project_discovery_set_papers
                WHERE project_id = ? AND source_mode = ?
                """,
                (project_id, source_mode),
            )

            if serialized_papers:
                conn.executemany(
                    """
                    INSERT INTO project_discovery_set_papers (
                        project_id,
                        source_mode,
                        ranking_id,
                        rank_position,
                        openalex_id,
                        doi,
                        title,
                        final_score,
                        paper_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    serialized_papers,
                )
    finally:
        conn.close()


def _discovery_snapshot(conn, run_row) -> dict | None:
    if not run_row:
        return None

    paper_rows = conn.execute(
        """
        SELECT paper_json
        FROM project_discovery_set_papers
        WHERE project_id = ? AND source_mode = ?
        ORDER BY rank_position ASC
        """,
        (run_row["project_id"], run_row["source_mode"]),
    ).fetchall()
    results = []

    for paper_row in paper_rows:
        work = _json_load(paper_row["paper_json"], {})

        if isinstance(work, dict):
            results.append(work)

    profile = _json_load(run_row["profile_json"], {})
    queries = _json_load(run_row["queries_json"], [])
    search_options = _json_load(run_row["search_options_json"], {})

    return {
        "project_id": run_row["project_id"],
        "source_mode": run_row["source_mode"],
        "profile": profile if isinstance(profile, dict) else {},
        "queries": queries if isinstance(queries, list) else [],
        "search_options": (
            search_options if isinstance(search_options, dict) else {}
        ),
        "ai_error": run_row["ai_error"] or "",
        "page": max(1, int(run_row["openalex_page"] or 1)),
        "results": results,
        "created_at": run_row["created_at"],
        "updated_at": run_row["updated_at"],
    }


def get_project_discovery_results(
    project_id: int,
    source_mode: str = "AI Recommendations",
) -> dict | None:
    source_mode = _normalize_source_mode(source_mode)
    conn = get_connection()

    try:
        run_row = conn.execute(
            """
            SELECT *
            FROM project_discovery_sets
            WHERE project_id = ? AND source_mode = ?
            """,
            (project_id, source_mode),
        ).fetchone()
        return _discovery_snapshot(conn, run_row)
    finally:
        conn.close()


def get_latest_project_discovery_results() -> dict | None:
    conn = get_connection()

    try:
        run_row = conn.execute(
            """
            SELECT *
            FROM project_discovery_sets
            ORDER BY updated_at DESC, project_id DESC, source_mode ASC
            LIMIT 1
            """
        ).fetchone()
        return _discovery_snapshot(conn, run_row)
    finally:
        conn.close()
