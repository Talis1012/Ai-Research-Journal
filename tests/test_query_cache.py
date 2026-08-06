import unittest
from uuid import uuid4

from utils.query_cache import (
    current_user_data_revision,
    invalidate_user_data_cache,
)
from utils.user_scope import activate_user_scope, clear_user_scope


class QueryCacheRevisionTests(unittest.TestCase):
    def setUp(self):
        activate_user_scope(
            "https://example.auth0.com/",
            str(uuid4()),
            claims={"role": "authenticated"},
        )

    def tearDown(self):
        clear_user_scope()

    def test_unrelated_table_does_not_invalidate_known_reader_revision(self):
        before = current_user_data_revision(("projects",))

        invalidate_user_data_cache({"messages"})

        self.assertEqual(current_user_data_revision(("projects",)), before)

    def test_related_table_invalidates_known_reader_revision(self):
        before = current_user_data_revision(("messages",))

        invalidate_user_data_cache({"messages"})

        self.assertNotEqual(current_user_data_revision(("messages",)), before)

    def test_unknown_reader_revision_changes_after_any_mutation(self):
        before = current_user_data_revision()

        invalidate_user_data_cache({"messages"})

        self.assertNotEqual(current_user_data_revision(), before)

    def test_forced_invalidation_changes_every_reader_revision(self):
        projects_before = current_user_data_revision(("projects",))
        messages_before = current_user_data_revision(("messages",))

        invalidate_user_data_cache()

        self.assertNotEqual(
            current_user_data_revision(("projects",)),
            projects_before,
        )
        self.assertNotEqual(
            current_user_data_revision(("messages",)),
            messages_before,
        )


if __name__ == "__main__":
    unittest.main()
