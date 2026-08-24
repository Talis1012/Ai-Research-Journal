import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from db.calendar_queries import (
    create_calendar_reminder,
    delete_calendar_reminder,
    get_calendar_reminder,
    get_calendar_reminders,
    get_due_calendar_reminders,
    get_upcoming_calendar_reminders,
    mark_calendar_reminder_notified,
    set_calendar_reminder_completed,
)
from db.database import init_db
from utils.user_scope import activate_user_scope, clear_user_scope


class CalendarTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_database_path = os.environ.get("DATABASE_PATH")
        os.environ["DATABASE_PATH"] = str(Path(self.temp_dir.name) / "app.db")
        activate_user_scope("https://tests.local", "calendar-user")
        init_db()

    def tearDown(self):
        clear_user_scope()

        if self.previous_database_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = self.previous_database_path

        self.temp_dir.cleanup()

    def test_reminders_are_created_filtered_and_deleted(self):
        first_id = create_calendar_reminder(
            "Review experiment results",
            datetime(2026, 8, 24, 14, 30),
            "Compare the control group.",
        )
        create_calendar_reminder(
            "September reminder",
            datetime(2026, 9, 2, 9, 0),
        )

        august = get_calendar_reminders(
            datetime(2026, 8, 1),
            datetime(2026, 9, 1),
        )

        self.assertEqual([row["id"] for row in august], [first_id])
        self.assertEqual(august[0]["notes"], "Compare the control group.")
        self.assertTrue(delete_calendar_reminder(first_id))
        self.assertIsNone(get_calendar_reminder(first_id))

    def test_due_reminder_notifies_once_and_can_be_reopened(self):
        now = datetime(2026, 8, 24, 14, 30)
        reminder_id = create_calendar_reminder(
            "Prepare weekly summary",
            now - timedelta(minutes=2),
        )

        due = get_due_calendar_reminders(
            now,
            since=now - timedelta(days=1),
        )
        self.assertEqual([row["id"] for row in due], [reminder_id])
        self.assertTrue(mark_calendar_reminder_notified(reminder_id))
        self.assertEqual(get_due_calendar_reminders(now), [])

        self.assertTrue(set_calendar_reminder_completed(reminder_id, True))
        self.assertEqual(get_upcoming_calendar_reminders(now - timedelta(days=1)), [])
        self.assertTrue(set_calendar_reminder_completed(reminder_id, False))
        self.assertEqual(
            [row["id"] for row in get_due_calendar_reminders(now)],
            [reminder_id],
        )

    def test_reminder_content_and_ranges_are_validated(self):
        with self.assertRaises(ValueError):
            create_calendar_reminder("  ", datetime(2026, 8, 24, 14, 30))

        with self.assertRaises(ValueError):
            create_calendar_reminder("x" * 161, datetime(2026, 8, 24, 14, 30))

        with self.assertRaises(ValueError):
            get_calendar_reminders(
                datetime(2026, 9, 1),
                datetime(2026, 8, 1),
            )


if __name__ == "__main__":
    unittest.main()
