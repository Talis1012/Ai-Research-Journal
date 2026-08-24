import unittest
from datetime import datetime, timezone

from utils.timezone import (
    local_datetime_to_utc,
    parse_utc_datetime,
    timezone_from_name,
    to_named_timezone,
)


class TimezoneTestCase(unittest.TestCase):
    def test_naive_database_timestamp_is_treated_as_utc(self):
        parsed = parse_utc_datetime("2026-08-24 12:30:00")

        self.assertEqual(parsed.tzinfo, timezone.utc)
        self.assertEqual(parsed.hour, 12)

    def test_browser_wall_time_is_converted_to_utc_with_dst(self):
        summer = local_datetime_to_utc(
            datetime(2026, 8, 24, 15, 0),
            "Europe/Bucharest",
        )
        winter = local_datetime_to_utc(
            datetime(2026, 1, 24, 15, 0),
            "Europe/Bucharest",
        )

        self.assertEqual(summer, datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(winter, datetime(2026, 1, 24, 13, 0, tzinfo=timezone.utc))

    def test_utc_timestamp_is_displayed_in_requested_timezone(self):
        local = to_named_timezone(
            "2026-08-24T12:00:00+00:00",
            "America/New_York",
        )

        self.assertEqual(local.strftime("%Y-%m-%d %H:%M"), "2026-08-24 08:00")

    def test_nonexistent_dst_wall_time_is_rejected(self):
        with self.assertRaises(ValueError):
            local_datetime_to_utc(
                datetime(2026, 3, 29, 3, 30),
                "Europe/Bucharest",
            )

    def test_invalid_timezone_falls_back_to_utc(self):
        self.assertEqual(timezone_from_name("Mars/Olympus").key, "UTC")


if __name__ == "__main__":
    unittest.main()
