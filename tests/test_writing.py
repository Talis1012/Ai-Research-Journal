import os
import tempfile
import unittest
from pathlib import Path

from db.database import init_db
from db.library_queries import create_library_item
from db.queries import create_project
from db.writing_queries import (
    attach_manuscript_evidence,
    attach_manuscript_source,
    create_manuscript,
    create_manuscript_version,
    duplicate_manuscript_version,
    get_manuscript,
    get_manuscript_evidence,
    get_manuscript_section,
    get_manuscript_sections,
    get_manuscript_sources,
    get_manuscript_versions,
    get_project_library_sources,
    insert_section_citation,
    restore_manuscript_version,
    update_manuscript_section,
    update_manuscript_source,
)
from services.manuscript_export_service import (
    manuscript_docx,
    manuscript_markdown,
    manuscript_pdf,
)
from services.writing_service import generate_writing_suggestion


class FixedWritingProvider:
    def generate_json(self, prompt):
        return {
            "suggested_text": "Supported result [@smith2025].",
            "explanation": "Grounded in the attached abstract.",
            "evidence_used": [
                {
                    "source_type": "library",
                    "source_id": 1,
                    "label": "Attached paper",
                    "support": "Reports the selected outcome.",
                }
            ],
            "claims": [
                {
                    "claim": "Supported result",
                    "status": "supported",
                    "reason": "The abstract reports it.",
                    "citation_keys": ["smith2025"],
                }
            ],
        }


class WritingTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db_path = os.environ.get("DATABASE_PATH")
        os.environ["DATABASE_PATH"] = str(Path(self.temp_dir.name) / "writing.db")
        init_db()
        self.project_id = create_project(
            "Writing project",
            "Medicinal chemistry",
            "Evidence-grounded manuscript",
        )
        self.manuscript_id = create_manuscript(
            self.project_id,
            "Stability manuscript",
        )
        self.item_id = create_library_item(
            title="Stability of CM-01",
            authors="Jane Smith; Alex Researcher",
            publication_year=2025,
            source_name="Journal of Stability",
            doi="10.1000/stability",
            abstract="CM-01 remained stable under the selected conditions.",
            project_ids=[self.project_id],
        )

    def tearDown(self):
        if self.previous_db_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = self.previous_db_path

        self.temp_dir.cleanup()

    def _results_section(self):
        return next(
            section
            for section in get_manuscript_sections(self.manuscript_id)
            if section["section_type"] == "results"
        )

    def test_manuscript_outline_sources_and_citations(self):
        self.assertEqual(len(get_manuscript_sections(self.manuscript_id)), 7)
        self.assertEqual(len(get_project_library_sources(self.project_id)), 1)
        citation_key = attach_manuscript_source(self.manuscript_id, self.item_id)
        self.assertEqual(citation_key, "smith2025")

        section = self._results_section()
        update_manuscript_section(section["id"], content_md="A supported result.")
        token = insert_section_citation(section["id"], self.item_id)
        self.assertEqual(token, "[@smith2025]")
        self.assertIn(token, get_manuscript_section(section["id"])["content_md"])

        update_manuscript_source(
            self.manuscript_id,
            self.item_id,
            citation_key="stability2025",
            notes="Core reference",
        )
        updated = get_manuscript_section(section["id"])
        self.assertIn("[@stability2025]", updated["content_md"])
        self.assertNotIn("[@smith2025]", updated["content_md"])

    def test_versions_restore_and_duplicate_complete_snapshot(self):
        section = self._results_section()
        update_manuscript_section(section["id"], content_md="Original result.")
        attach_manuscript_source(self.manuscript_id, self.item_id)
        attach_manuscript_evidence(
            self.manuscript_id,
            "key_idea",
            999,
            "Stability window",
            "Near-neutral stability was strongest.",
        )
        version_id = create_manuscript_version(
            self.manuscript_id,
            "Original draft",
        )
        update_manuscript_section(section["id"], content_md="Changed result.")

        restore_manuscript_version(version_id)
        restored_section = next(
            row
            for row in get_manuscript_sections(self.manuscript_id)
            if row["section_type"] == "results"
        )
        self.assertEqual(restored_section["content_md"], "Original result.")
        self.assertEqual(len(get_manuscript_sources(self.manuscript_id)), 1)
        self.assertEqual(len(get_manuscript_evidence(self.manuscript_id)), 1)

        duplicate_id = duplicate_manuscript_version(version_id, "Duplicate draft")
        self.assertEqual(get_manuscript(duplicate_id)["title"], "Duplicate draft")
        self.assertEqual(len(get_manuscript_sections(duplicate_id)), 7)
        self.assertEqual(len(get_manuscript_versions(self.manuscript_id)), 1)

    def test_ai_response_and_all_export_formats(self):
        source_key = attach_manuscript_source(self.manuscript_id, self.item_id)
        self.assertEqual(source_key, "smith2025")
        section = self._results_section()
        update_manuscript_section(section["id"], content_md="Current result.")
        manuscript = get_manuscript(self.manuscript_id)
        sections = get_manuscript_sections(self.manuscript_id)
        sources = get_manuscript_sources(self.manuscript_id)
        result = generate_writing_suggestion(
            mode="Cite",
            instruction="Cite the result.",
            manuscript=manuscript,
            section=section,
            sections=sections,
            sources=sources,
            evidence=[],
            ai_provider=FixedWritingProvider(),
        )

        self.assertEqual(result["claims"][0]["status"], "supported")
        markdown = manuscript_markdown(manuscript, sections, sources)
        docx = manuscript_docx(manuscript, sections, sources)
        pdf = manuscript_pdf(manuscript, sections, sources)
        self.assertIn("# Stability manuscript", markdown)
        self.assertTrue(docx.startswith(b"PK"))
        self.assertTrue(pdf.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
