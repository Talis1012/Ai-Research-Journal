import unittest
from unittest.mock import patch

from db.database import _PostgresConnection, init_db_once
from utils.user_scope import activate_user_scope, clear_user_scope


class _RecordingContext:
    def __init__(self, events, name):
        self.events = events
        self.name = name

    def __enter__(self):
        self.events.append((f"{self.name}_enter",))
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.events.append((f"{self.name}_exit",))
        return False


class _RecordingCursor:
    def __init__(self, events, name):
        self.events = events
        self.name = name
        self.rowcount = 0

    def execute(self, statement, params=()):
        self.events.append(("execute", self.name, " ".join(statement.split()), params))
        return self

    def executemany(self, statement, params_seq):
        self.events.append(
            ("executemany", self.name, " ".join(statement.split()), tuple(params_seq))
        )
        return self

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self):
        self.events.append(("close", self.name))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False


class _RecordingRawConnection:
    def __init__(self):
        self.events = []
        self.cursor_count = 0

    def cursor(self):
        self.cursor_count += 1
        return _RecordingCursor(self.events, f"cursor-{self.cursor_count}")

    def pipeline(self):
        return _RecordingContext(self.events, "pipeline")

    def commit(self):
        self.events.append(("commit",))

    def rollback(self):
        self.events.append(("rollback",))


class PostgresDatabaseTestCase(unittest.TestCase):
    def setUp(self):
        activate_user_scope(
            "https://issuer.example/",
            "auth0|performance-user",
            claims={"email": "performance@example.com"},
        )

    def tearDown(self):
        clear_user_scope()

    def test_rls_context_and_query_share_one_pipeline(self):
        raw = _RecordingRawConnection()
        connection = _PostgresConnection(raw, pool=None)

        connection.execute("SELECT ? AS value", (7,))

        pipeline_events = [event for event in raw.events if event[0] == "pipeline_enter"]
        executions = [event for event in raw.events if event[0] == "execute"]
        self.assertEqual(len(pipeline_events), 1)
        self.assertEqual(len(executions), 2)
        self.assertIn("set_config('request.jwt.claims'", executions[0][2])
        self.assertIn("set_config('role', 'authenticated', true)", executions[0][2])
        self.assertEqual(executions[1][2], "SELECT %s AS value")
        self.assertNotIn("ensure_current_app_user", str(raw.events))

        connection.execute("SELECT 2")

        pipeline_events = [event for event in raw.events if event[0] == "pipeline_enter"]
        self.assertEqual(len(pipeline_events), 1)

        connection.commit()
        connection.execute("SELECT 3")

        pipeline_events = [event for event in raw.events if event[0] == "pipeline_enter"]
        self.assertEqual(len(pipeline_events), 2)

    def test_postgres_user_is_initialized_once_per_streamlit_session(self):
        session_state = {}

        with (
            patch("db.database.uses_postgres", return_value=True),
            patch(
                "db.database.get_current_app_user_id",
                return_value="00000000-0000-0000-0000-000000000001",
            ) as initialize_user,
        ):
            self.assertTrue(init_db_once(session_state))
            self.assertFalse(init_db_once(session_state))

        initialize_user.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
