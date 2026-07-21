import json
import os
import tempfile
import unittest
from pathlib import Path

from db.database import get_connection, init_db
from db.discovery_queries import (
    get_project_discovery_results,
    replace_project_discovery_results,
)
from db.queries import create_project


def _paper(ranking_id: str, openalex_id: str, title: str, score: float) -> dict:
    return {
        "ranking_id": ranking_id,
        "openalex_id": openalex_id,
        "doi": f"10.1000/{openalex_id.lower()}",
        "title": title,
        "authors": "A. Researcher",
        "publication_year": 2026,
        "abstract": f"Abstract for {title}",
        "matched_queries": ["thiazole SAR"],
        "matched_concepts": ["thiazole"],
        "base_score": score - 5,
        "ai_score": score + 5,
        "final_score": score,
        "ai_rubric": {"direct_topic_relevance": 30},
    }


class DiscoveryPersistenceTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db_path = os.environ.get("DATABASE_PATH")
        os.environ["DATABASE_PATH"] = str(
            Path(self.temp_dir.name) / "discovery.db"
        )
        init_db()
        self.project_id = create_project(
            "Thiazole project",
            "Medicinal chemistry",
            "Antibacterial SAR",
        )

    def tearDown(self):
        if self.previous_db_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = self.previous_db_path

        self.temp_dir.cleanup()

    def test_result_set_is_restored_with_its_search_context(self):
        profile = {
            "research_topic": "Thiazole antibacterial SAR",
            "search_queries": ["thiazole SAR"],
        }
        results = [
            _paper("candidate-1", "W1", "First paper", 84.2),
            _paper("candidate-2", "W2", "Second paper", 76.5),
        ]
        options = {
            "from_year": 2020,
            "to_year": 2026,
            "open_access_only": True,
            "result_limit": 10,
            "order": "hybrid",
        }
        replace_project_discovery_results(
            self.project_id,
            results=results,
            profile=profile,
            queries=["thiazole SAR"],
            search_options=options,
            source_mode="AI Recommendations",
            page=2,
        )

        restored = get_project_discovery_results(self.project_id)

        self.assertEqual(restored["project_id"], self.project_id)
        self.assertEqual(restored["profile"], profile)
        self.assertEqual(restored["queries"], ["thiazole SAR"])
        self.assertEqual(restored["search_options"], options)
        self.assertEqual(restored["page"], 2)
        self.assertEqual(
            [paper["openalex_id"] for paper in restored["results"]],
            ["W1", "W2"],
        )
        self.assertEqual(restored["results"][0]["ai_rubric"], {
            "direct_topic_relevance": 30,
        })

    def test_manual_and_ai_sets_are_independent_and_replace_only_their_own_mode(self):
        second_project_id = create_project("Second project", "Biology")
        common = {
            "profile": {"research_topic": "test"},
            "queries": ["test"],
            "search_options": {"order": "hybrid"},
        }
        replace_project_discovery_results(
            self.project_id,
            results=[
                _paper("candidate-1", "W-OLD-1", "Old one", 70),
                _paper("candidate-2", "W-OLD-2", "Old two", 65),
            ],
            **common,
        )
        replace_project_discovery_results(
            self.project_id,
            results=[_paper("candidate-1", "W-MANUAL", "Manual result", 83)],
            source_mode="Manual Search",
            **common,
        )
        replace_project_discovery_results(
            second_project_id,
            results=[_paper("candidate-1", "W-OTHER", "Other project", 80)],
            **common,
        )
        replace_project_discovery_results(
            self.project_id,
            results=[_paper("candidate-1", "W-NEW", "New generation", 91)],
            **common,
        )

        ai_snapshot = get_project_discovery_results(
            self.project_id,
            "AI Recommendations",
        )
        manual_snapshot = get_project_discovery_results(
            self.project_id,
            "Manual Search",
        )
        second_snapshot = get_project_discovery_results(second_project_id)

        self.assertEqual(
            [paper["openalex_id"] for paper in ai_snapshot["results"]],
            ["W-NEW"],
        )
        self.assertEqual(
            [paper["openalex_id"] for paper in manual_snapshot["results"]],
            ["W-MANUAL"],
        )
        self.assertEqual(manual_snapshot["source_mode"], "Manual Search")
        self.assertEqual(ai_snapshot["source_mode"], "AI Recommendations")
        self.assertEqual(
            [paper["openalex_id"] for paper in second_snapshot["results"]],
            ["W-OTHER"],
        )

    def test_legacy_single_project_set_is_migrated(self):
        legacy_paper = _paper(
            "candidate-1",
            "W-LEGACY",
            "Previously generated paper",
            79,
        )
        conn = get_connection()
        conn.executescript("""
            CREATE TABLE project_discovery_runs (
                project_id INTEGER PRIMARY KEY,
                source_mode TEXT NOT NULL,
                profile_json TEXT NOT NULL,
                queries_json TEXT NOT NULL,
                search_options_json TEXT NOT NULL,
                ai_error TEXT,
                result_count INTEGER NOT NULL,
                openalex_page INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE project_discovery_papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                ranking_id TEXT NOT NULL,
                rank_position INTEGER NOT NULL,
                openalex_id TEXT,
                doi TEXT,
                title TEXT NOT NULL,
                final_score REAL,
                paper_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute(
            """
            INSERT INTO project_discovery_runs (
                project_id,
                source_mode,
                profile_json,
                queries_json,
                search_options_json,
                ai_error,
                result_count,
                openalex_page
            )
            VALUES (?, 'AI Recommendations', '{}', '["legacy query"]', '{}', '', 1, 1)
            """,
            (self.project_id,),
        )
        conn.execute(
            """
            INSERT INTO project_discovery_papers (
                project_id,
                ranking_id,
                rank_position,
                openalex_id,
                title,
                final_score,
                paper_json
            )
            VALUES (?, 'candidate-1', 1, 'W-LEGACY', ?, 79, ?)
            """,
            (
                self.project_id,
                legacy_paper["title"],
                json.dumps(legacy_paper),
            ),
        )
        conn.commit()
        conn.close()

        init_db()
        migrated = get_project_discovery_results(
            self.project_id,
            "AI Recommendations",
        )

        self.assertEqual(migrated["queries"], ["legacy query"])
        self.assertEqual(migrated["results"][0]["openalex_id"], "W-LEGACY")


if __name__ == "__main__":
    unittest.main()
