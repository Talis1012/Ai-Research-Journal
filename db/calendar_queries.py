from datetime import datetime

from db.database import get_connection
from utils.timezone import parse_utc_datetime, timezone_from_name


MAX_REMINDER_TITLE_LENGTH = 160
MAX_REMINDER_NOTES_LENGTH = 2000


def _normalized_datetime(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise ValueError("Reminder time must be a valid date and time.")

    return parse_utc_datetime(value).isoformat(
        sep=" ",
        timespec="seconds",
    )


def _validated_content(title: str, notes: str | None) -> tuple[str, str | None]:
    normalized_title = str(title or "").strip()
    normalized_notes = str(notes or "").strip() or None

    if not normalized_title:
        raise ValueError("Reminder title is required.")

    if len(normalized_title) > MAX_REMINDER_TITLE_LENGTH:
        raise ValueError(
            f"Reminder title must have at most {MAX_REMINDER_TITLE_LENGTH} characters."
        )

    if normalized_notes and len(normalized_notes) > MAX_REMINDER_NOTES_LENGTH:
        raise ValueError(
            f"Reminder notes must have at most {MAX_REMINDER_NOTES_LENGTH} characters."
        )

    return normalized_title, normalized_notes


def create_calendar_reminder(
    title: str,
    reminder_at: datetime,
    notes: str | None = None,
    timezone_name: str = "UTC",
) -> int:
    normalized_title, normalized_notes = _validated_content(title, notes)
    normalized_timezone = timezone_from_name(timezone_name).key
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO calendar_reminders (
            title,
            reminder_at,
            notes,
            timezone_name
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            normalized_title,
            _normalized_datetime(reminder_at),
            normalized_notes,
            normalized_timezone,
        ),
    )
    reminder_id = cur.lastrowid
    conn.commit()
    conn.close()
    return reminder_id


def get_calendar_reminder(reminder_id: int):
    conn = get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM calendar_reminders WHERE id = ?",
            (int(reminder_id),),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row is not None else None


def get_calendar_reminders(start_at: datetime, end_at: datetime):
    start_value = _normalized_datetime(start_at)
    end_value = _normalized_datetime(end_at)

    if start_value >= end_value:
        raise ValueError("Calendar range end must be after its start.")

    conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM calendar_reminders
            WHERE reminder_at >= ? AND reminder_at < ?
            ORDER BY reminder_at ASC, id ASC
            """,
            (start_value, end_value),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def get_upcoming_calendar_reminders(now: datetime, limit: int = 8):
    conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM calendar_reminders
            WHERE completed = 0 AND reminder_at >= ?
            ORDER BY reminder_at ASC, id ASC
            LIMIT ?
            """,
            (_normalized_datetime(now), max(1, min(int(limit), 50))),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def get_due_calendar_reminders(
    now: datetime,
    *,
    since: datetime | None = None,
    limit: int = 3,
):
    params: list[object] = [_normalized_datetime(now)]
    since_clause = ""

    if since is not None:
        since_clause = "AND reminder_at >= ?"
        params.append(_normalized_datetime(since))

    params.append(max(1, min(int(limit), 20)))
    conn = get_connection()

    try:
        rows = conn.execute(
            f"""
            SELECT *
            FROM calendar_reminders
            WHERE completed = 0
              AND notified_at IS NULL
              AND reminder_at <= ?
              {since_clause}
            ORDER BY reminder_at ASC, id ASC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def get_recent_calendar_reminder_notifications(
    since: datetime,
    *,
    limit: int = 3,
):
    conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM calendar_reminders
            WHERE completed = 0
              AND notified_at IS NOT NULL
              AND notified_at >= ?
            ORDER BY notified_at DESC, id DESC
            LIMIT ?
            """,
            (
                _normalized_datetime(since),
                max(1, min(int(limit), 20)),
            ),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in reversed(rows)]


def set_calendar_reminder_completed(reminder_id: int, completed: bool) -> bool:
    completed_value = 1 if completed else 0
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE calendar_reminders
        SET completed = ?,
            notified_at = CASE WHEN ? = 0 THEN NULL ELSE notified_at END,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (completed_value, completed_value, int(reminder_id)),
    )
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def mark_calendar_reminder_notified(reminder_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE calendar_reminders
        SET notified_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND notified_at IS NULL
        """,
        (int(reminder_id),),
    )
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def delete_calendar_reminder(reminder_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM calendar_reminders WHERE id = ?",
        (int(reminder_id),),
    )
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted
