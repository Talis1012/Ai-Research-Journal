import os
import tempfile
import unittest
from pathlib import Path

from db.database import get_db_path, init_db
from db.library_queries import create_library_item, get_library_items
from db.queries import create_project, get_projects
from services.library_service import read_library_file, save_library_upload
from services.manuscript_asset_service import get_manuscript_asset_storage_path
from services.transcription_service import get_audio_storage_path
from utils.user_scope import activate_user_scope, clear_user_scope


class FakeUpload:
    name = "private-notes.txt"
    type = "text/plain"

    def __init__(self, content: bytes):
        self._content = content

    def getvalue(self):
        return self._content


class UserIsolationTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_names = (
            "DATABASE_PATH",
            "LIBRARY_STORAGE_PATH",
            "AUDIO_STORAGE_PATH",
            "MANUSCRIPT_ASSET_STORAGE_PATH",
            "AUTH0_LEGACY_OWNER_SUB",
            "AUTH0_LEGACY_OWNER_ISSUER",
        )
        self.previous_env = {
            name: os.environ.get(name)
            for name in self.env_names
        }
        root = Path(self.temp_dir.name)
        os.environ["DATABASE_PATH"] = str(root / "app.db")
        os.environ["LIBRARY_STORAGE_PATH"] = str(root / "library")
        os.environ["AUDIO_STORAGE_PATH"] = str(root / "audio")
        os.environ["MANUSCRIPT_ASSET_STORAGE_PATH"] = str(root / "assets")
        os.environ.pop("AUTH0_LEGACY_OWNER_SUB", None)
        os.environ.pop("AUTH0_LEGACY_OWNER_ISSUER", None)
        clear_user_scope()

    def tearDown(self):
        clear_user_scope()

        for name, value in self.previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

        self.temp_dir.cleanup()

    def test_database_and_files_are_private_per_oidc_identity(self):
        activate_user_scope("https://tenant.auth0.com/", "auth0|alice")
        init_db()
        alice_db = get_db_path()
        alice_project = create_project("Alice project", "Chemistry")
        create_library_item(title="Alice paper", project_ids=[alice_project])
        alice_upload = save_library_upload(FakeUpload(b"alice-private"))
        alice_audio = get_audio_storage_path()
        alice_assets = get_manuscript_asset_storage_path()

        activate_user_scope("https://tenant.auth0.com/", "auth0|bob")
        init_db()
        bob_db = get_db_path()

        self.assertNotEqual(alice_db, bob_db)
        self.assertEqual(get_projects(), [])
        self.assertEqual(get_library_items(), [])
        self.assertNotEqual(alice_audio, get_audio_storage_path())
        self.assertNotEqual(alice_assets, get_manuscript_asset_storage_path())

        with self.assertRaises(ValueError):
            read_library_file(alice_upload["file_path"])

        activate_user_scope("https://tenant.auth0.com/", "auth0|alice")
        self.assertEqual([row["name"] for row in get_projects()], ["Alice project"])
        self.assertEqual([row["title"] for row in get_library_items()], ["Alice paper"])
        self.assertEqual(read_library_file(alice_upload["file_path"]), b"alice-private")

    def test_explicit_legacy_owner_keeps_pre_authentication_workspace(self):
        init_db()
        create_project("Legacy project", "Biology")
        legacy_db = get_db_path()
        os.environ["AUTH0_LEGACY_OWNER_SUB"] = "auth0|owner"
        os.environ["AUTH0_LEGACY_OWNER_ISSUER"] = "https://tenant.auth0.com/"

        activate_user_scope("https://tenant.auth0.com/", "auth0|owner")

        self.assertEqual(get_db_path(), legacy_db)
        self.assertEqual([row["name"] for row in get_projects()], ["Legacy project"])

        activate_user_scope("https://tenant.auth0.com/", "auth0|someone-else")
        init_db()
        self.assertNotEqual(get_db_path(), legacy_db)
        self.assertEqual(get_projects(), [])


if __name__ == "__main__":
    unittest.main()
