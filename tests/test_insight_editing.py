import os
import tempfile
import unittest
from pathlib import Path

from db.database import init_db
from utils.user_scope import activate_user_scope, clear_user_scope
from db.queries import (
    create_chat,
    create_project,
    get_chat_summary,
    get_project_ideas,
    get_project_workspace,
    get_project_summary,
    save_project_ideas,
    save_summary,
    update_project_idea,
    update_summary,
)


class InsightEditingTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db_path = os.environ.get("DATABASE_PATH")
        os.environ["DATABASE_PATH"] = str(
            Path(self.temp_dir.name) / "insights.db"
        )
        activate_user_scope("https://tests.local", "insight-editing")
        init_db()
        self.project_id = create_project(
            "Insight editing",
            "Medicinal chemistry",
        )
        self.chat_id = create_chat(
            self.project_id,
            "Stability experiment",
        )

    def tearDown(self):
        clear_user_scope()

        if self.previous_db_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = self.previous_db_path

        self.temp_dir.cleanup()

    def test_summary_edit_updates_only_selected_scope_and_structure(self):
        project_summary_id = save_summary(
            scope="project",
            project_id=self.project_id,
            summary_style="Standard cercetare",
            content="Original project summary.",
        )
        save_summary(
            scope="project",
            project_id=self.project_id,
            summary_style="Raport detaliat",
            content="Detailed project summary.",
        )
        chat_summary_id = save_summary(
            scope="chat",
            project_id=self.project_id,
            chat_id=self.chat_id,
            summary_style="Standard cercetare",
            content="Original experiment summary.",
        )

        update_summary(project_summary_id, "Edited project summary.")
        update_summary(chat_summary_id, "Edited experiment summary.")

        self.assertEqual(
            get_project_summary(
                self.project_id,
                "Standard cercetare",
            )["content"],
            "Edited project summary.",
        )
        self.assertEqual(
            get_project_summary(
                self.project_id,
                "Raport detaliat",
            )["content"],
            "Detailed project summary.",
        )
        self.assertEqual(
            get_chat_summary(
                self.chat_id,
                "Standard cercetare",
            )["content"],
            "Edited experiment summary.",
        )

    def test_key_ideas_can_be_edited_individually(self):
        save_project_ideas(
            self.project_id,
            [
                {
                    "title": "Stability window",
                    "description": "Original description.",
                    "evidence": "Original evidence.",
                    "importance": "medium",
                },
                {
                    "title": "Control",
                    "description": "Unchanged idea.",
                    "evidence": "",
                    "importance": "low",
                },
            ],
        )
        ideas = get_project_ideas(self.project_id)
        selected = next(idea for idea in ideas if idea["title"] == "Stability window")

        update_project_idea(
            selected["id"],
            title="Defined stability window",
            description="Edited description.",
            evidence="Edited evidence.",
            importance="high",
        )

        updated = get_project_ideas(self.project_id)
        edited = next(idea for idea in updated if idea["id"] == selected["id"])
        untouched = next(idea for idea in updated if idea["title"] == "Control")
        self.assertEqual(edited["title"], "Defined stability window")
        self.assertEqual(edited["description"], "Edited description.")
        self.assertEqual(edited["evidence"], "Edited evidence.")
        self.assertEqual(edited["importance"], "high")
        self.assertEqual(untouched["description"], "Unchanged idea.")

    def test_project_workspace_batches_experiments_messages_and_ideas(self):
        chats, messages, ideas = get_project_workspace(self.project_id)

        self.assertEqual([row["id"] for row in chats], [self.chat_id])
        self.assertEqual(messages, [])
        self.assertEqual(ideas, [])


if __name__ == "__main__":
    unittest.main()
