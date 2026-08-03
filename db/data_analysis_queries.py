import json

from db.database import get_connection


ANALYSIS_RUN_STATUSES = ("running", "completed", "failed")
ANALYSIS_SOURCE_KINDS = ("upload", "library")


def _json_dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads(value: str | None, default):
    if not value:
        return default

    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _decoded_run(row):
    if row is None:
        return None

    decoded = dict(row)
    decoded["feature_columns"] = _json_loads(
        decoded.pop("feature_columns_json", None),
        [],
    )
    decoded["parameters"] = _json_loads(
        decoded.pop("parameters_json", None),
        {},
    )
    decoded["preprocessing"] = _json_loads(
        decoded.pop("preprocessing_json", None),
        {},
    )
    decoded["metrics"] = _json_loads(decoded.pop("metrics_json", None), {})
    decoded["results"] = _json_loads(decoded.pop("results_json", None), {})
    return decoded


def create_analysis_run(
    *,
    library_item_id: int | None,
    source_kind: str,
    source_name: str,
    objective: str,
    algorithm_key: str,
    algorithm_label: str,
    target_column: str | None,
    feature_columns: list[str],
    parameters: dict,
    preprocessing: dict,
    row_count: int,
    column_count: int,
) -> int:
    source_name = str(source_name or "").strip()

    if source_kind not in ANALYSIS_SOURCE_KINDS:
        raise ValueError("Unsupported analysis source kind.")

    if not source_name:
        raise ValueError("The analysis source must have a name.")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO analysis_runs (
            library_item_id,
            source_kind,
            source_name,
            objective,
            algorithm_key,
            algorithm_label,
            target_column,
            feature_columns_json,
            parameters_json,
            preprocessing_json,
            row_count,
            column_count,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'running')
        """,
        (
            library_item_id,
            source_kind,
            source_name,
            objective,
            algorithm_key,
            algorithm_label,
            target_column or None,
            _json_dumps(feature_columns),
            _json_dumps(parameters),
            _json_dumps(preprocessing),
            max(0, int(row_count)),
            max(0, int(column_count)),
        ),
    )
    run_id = cur.lastrowid
    conn.commit()
    conn.close()
    return run_id


def complete_analysis_run(
    run_id: int,
    *,
    metrics: dict,
    results: dict,
    predictions_file_path: str | None,
    report_file_path: str | None,
):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE analysis_runs
        SET status = 'completed',
            metrics_json = ?,
            results_json = ?,
            predictions_file_path = ?,
            report_file_path = ?,
            error_message = NULL,
            completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            _json_dumps(metrics),
            _json_dumps(results),
            predictions_file_path or None,
            report_file_path or None,
            run_id,
        ),
    )

    if cur.rowcount == 0:
        conn.close()
        raise ValueError("The analysis run no longer exists.")

    conn.commit()
    conn.close()


def fail_analysis_run(run_id: int, error_message: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE analysis_runs
        SET status = 'failed',
            error_message = ?,
            completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (str(error_message or "Analysis failed.")[:2000], run_id),
    )

    if cur.rowcount == 0:
        conn.close()
        raise ValueError("The analysis run no longer exists.")

    conn.commit()
    conn.close()


def get_analysis_run(run_id: int):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM analysis_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    conn.close()
    return _decoded_run(row)


def get_analysis_runs(*, limit: int = 50, offset: int = 0):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT *
        FROM analysis_runs
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        (max(1, min(int(limit), 200)), max(0, int(offset))),
    ).fetchall()
    conn.close()
    return [_decoded_run(row) for row in rows]


def get_analysis_run_count() -> int:
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) AS run_count FROM analysis_runs").fetchone()
    conn.close()
    return int(row["run_count"] or 0)
