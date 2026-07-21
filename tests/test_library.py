import os
import tempfile
import unittest
from pathlib import Path

from db.database import init_db
from db.library_queries import (
    create_library_folder,
    create_library_item,
    delete_library_folder,
    get_library_item,
    get_library_external_keys,
    get_library_items,
    get_library_stats,
    move_library_items,
    update_library_item,
)
from services.library_service import (
    delete_library_file,
    infer_library_item_type,
    read_library_file,
    save_library_upload,
)


class FakeUpload:
    def __init__(self, name: str, content: bytes, mime_type: str):
        self.name = name
        self._content = content
        self.type = mime_type

    def getvalue(self):
        return self._content


class LibraryTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db_path = os.environ.get("DATABASE_PATH")
        self.previous_storage_path = os.environ.get("LIBRARY_STORAGE_PATH")
        os.environ["DATABASE_PATH"] = str(
            Path(self.temp_dir.name) / "library.db"
        )
        os.environ["LIBRARY_STORAGE_PATH"] = str(
            Path(self.temp_dir.name) / "files"
        )
        init_db()

    def tearDown(self):
        if self.previous_db_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = self.previous_db_path

        if self.previous_storage_path is None:
            os.environ.pop("LIBRARY_STORAGE_PATH", None)
        else:
            os.environ["LIBRARY_STORAGE_PATH"] = self.previous_storage_path

        self.temp_dir.cleanup()

    def test_folder_item_lifecycle(self):
        root_id = create_library_folder("Reviews")
        child_id = create_library_folder("Medicinal chemistry", root_id)
        item_id = create_library_item(
            title="Thiazole review",
            item_type="paper",
            folder_id=child_id,
            authors="A. Scientist",
            publication_year=2025,
            doi="10.1000/test",
            tags=["SAR", "Review"],
            status="Reading",
        )

        self.assertEqual(get_library_stats()["total"], 1)
        self.assertEqual(len(get_library_items(folder_id=child_id)), 1)
        self.assertEqual(len(get_library_items(search="scientist")), 1)

        move_library_items([item_id], root_id)
        self.assertEqual(get_library_item(item_id)["folder_id"], root_id)

        update_library_item(
            item_id,
            title="Updated review",
            item_type="paper",
            folder_id=root_id,
            authors="A. Scientist",
            publication_year=2026,
            source_name="Research Journal",
            doi="10.1000/test",
            url="",
            abstract="Updated abstract",
            status="Reviewed",
            personal_notes="Important",
            tags=["SAR"],
            project_ids=[],
        )
        updated_item = get_library_item(item_id)
        self.assertEqual(updated_item["title"], "Updated review")
        self.assertEqual(updated_item["status"], "Reviewed")

        delete_library_folder(root_id, delete_items=False)
        self.assertIsNone(get_library_item(item_id)["folder_id"])

    def test_upload_storage_and_type_inference(self):
        upload = FakeUpload(
            "screening_results.csv",
            b"compound,activity\nCM-01,87\n",
            "text/csv",
        )
        saved = save_library_upload(upload)

        self.assertEqual(saved["item_type"], "dataset")
        self.assertEqual(saved["title"], "screening results")
        self.assertEqual(read_library_file(saved["file_path"]), upload.getvalue())
        self.assertEqual(infer_library_item_type("paper.pdf"), "pdf")

        delete_library_file(saved["file_path"])
        self.assertFalse(Path(saved["file_path"]).exists())

    def test_external_ids_are_normalized_for_duplicate_detection(self):
        create_library_item(
            title="External paper",
            doi="https://doi.org/10.1000/TEST",
            openalex_id="https://openalex.org/W123",
        )
        keys = get_library_external_keys()

        self.assertIn("10.1000/test", keys["dois"])
        self.assertIn("W123", keys["openalex_ids"])

    def test_storage_rejects_paths_outside_library(self):
        outside_path = Path(self.temp_dir.name) / "outside.txt"
        outside_path.write_text("private", encoding="utf-8")

        with self.assertRaises(ValueError):
            read_library_file(str(outside_path))

        with self.assertRaises(ValueError):
            delete_library_file(str(outside_path))


if __name__ == "__main__":
    unittest.main()
