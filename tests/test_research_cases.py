import os
import tempfile
import unittest
from pathlib import Path

from ai.mock_provider import MockProvider
from db.database import init_db
from db.library_queries import (
    create_library_item,
    get_library_item,
    get_library_items,
    update_library_item,
)
from db.queries import add_message, create_chat, create_project
from db.research_case_queries import (
    get_project_research_cases,
    get_research_case,
)
from services.research_case_service import (
    generate_project_research_cases,
    generate_research_case_for_item,
    get_research_case_coverage,
    is_research_case_current,
    normalize_template_type,
    recommend_relevant_experiments,
    research_case_to_mindmap,
)
from utils.user_scope import activate_user_scope, clear_user_scope


class UntraceableSynthesisProvider(MockProvider):
    def generate_json(self, prompt, **kwargs):
        result = super().generate_json(prompt, **kwargs)

        if "FINAL_EXPERIMENT_SYNTHESIS_REQUEST" in prompt:
            result["evidence_basis"] = [{
                "library_item_id": 999_999,
                "supported_choice": "Unsupported source reference.",
            }]

        return result


class ResearchCaseTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_database_path = os.environ.get("DATABASE_PATH")
        self.previous_ai_provider = os.environ.get("AI_PROVIDER")
        os.environ["DATABASE_PATH"] = str(Path(self.temp_dir.name) / "cases.db")
        os.environ["AI_PROVIDER"] = "mock"
        activate_user_scope("https://tests.local", "research-cases")
        init_db()
        self.project_id = create_project(
            "Tumor segmentation",
            "Medical imaging",
            "Compare segmentation approaches for MRI scans.",
        )
        chat_id = create_chat(
            self.project_id,
            "Segmentation experiment",
            "Evaluate segmentation quality.",
        )
        add_message(
            chat_id,
            "user",
            "text",
            "Compare a new model with a baseline on the same MRI split using Dice score.",
        )

    def tearDown(self):
        clear_user_scope()

        if self.previous_database_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = self.previous_database_path

        if self.previous_ai_provider is None:
            os.environ.pop("AI_PROVIDER", None)
        else:
            os.environ["AI_PROVIDER"] = self.previous_ai_provider

        self.temp_dir.cleanup()

    def _paper(self, title: str, abstract: str) -> int:
        return create_library_item(
            title=title,
            item_type="paper",
            abstract=abstract,
            url="https://example.org/paper",
            project_ids=[self.project_id],
        )

    def test_case_generation_persists_semantics_embedding_and_traceability(self):
        item_id = self._paper(
            "Transformer versus convolutional baseline",
            "We compare two segmentation methods under the same evaluation protocol.",
        )

        semantic = generate_research_case_for_item(
            self.project_id,
            item_id,
            ai_provider=MockProvider(),
        )
        stored = get_research_case(self.project_id, item_id)

        self.assertEqual(stored["status"], "ready")
        self.assertTrue(stored["embedding"])
        self.assertEqual(stored["semantic"], semantic)
        self.assertEqual(
            semantic["experimental_strategy"][0]["template_type"],
            "comparative_evaluation",
        )
        self.assertEqual(
            semantic["experimental_strategy"][0]["evidence"]["section"],
            "",
        )
        self.assertEqual(
            semantic["experimental_strategy"][0]["evidence"]["excerpt"],
            "",
        )
        self.assertEqual(
            semantic["traceability"]["sections"],
            [{"name": "Abstract", "page_range": ""}],
        )
        self.assertTrue(is_research_case_current(stored, get_library_item(item_id)))

        mindmap = research_case_to_mindmap(semantic)
        self.assertIn(
            "Experimental strategy",
            [node["label"] for node in mindmap["nodes"]],
        )

    def test_batch_generation_and_retrieval_group_template_frequency(self):
        self._paper(
            "Comparison A",
            "Two methods are compared using a controlled dataset and accuracy.",
        )
        self._paper(
            "Comparison B",
            "A baseline and candidate method are evaluated under one protocol.",
        )

        report = generate_project_research_cases(
            self.project_id,
            ai_provider=MockProvider(),
        )
        result = recommend_relevant_experiments(
            self.project_id,
            top_k=8,
            ai_provider=MockProvider(),
        )

        self.assertEqual(len(report["generated"]), 2)
        self.assertEqual(result["retrieved_case_count"], 2)
        self.assertEqual(len(result["recommendations"]), 1)
        recommendation = result["recommendations"][0]
        self.assertEqual(recommendation["template_type"], "comparative_evaluation")
        self.assertEqual(recommendation["template_frequency"], 2)
        self.assertEqual(len(recommendation["examples"]), 2)
        self.assertIn("similarity_score", recommendation["examples"][0])
        self.assertIn("top_k_rank", recommendation["examples"][0])
        final_experiment = result["final_experiment"]
        self.assertEqual(result["synthesis_error"], "")
        self.assertEqual(
            final_experiment["template_type"],
            "comparative_evaluation",
        )
        self.assertTrue(final_experiment["hypothesis"])
        self.assertEqual(final_experiment["experimental_units"]["total_units"], 10)
        self.assertTrue(final_experiment["procedure_steps"])
        self.assertTrue(final_experiment["measurements"])
        self.assertEqual(len(final_experiment["evidence_basis"]), 2)
        self.assertEqual(
            {
                evidence["library_item_id"]
                for evidence in final_experiment["evidence_basis"]
            },
            {
                case["library_item_id"]
                for case in get_project_research_cases(self.project_id)
            },
        )

    def test_coverage_marks_case_outdated_after_source_changes(self):
        item_id = self._paper(
            "Mutable paper",
            "Initial abstract comparing two approaches.",
        )
        generate_research_case_for_item(
            self.project_id,
            item_id,
            ai_provider=MockProvider(),
        )
        item = get_library_item(item_id)
        stored = get_research_case(self.project_id, item_id)
        self.assertTrue(is_research_case_current(stored, item))

        update_library_item(
            item_id,
            title=item["title"],
            item_type=item["item_type"],
            folder_id=item["folder_id"],
            authors=item["authors"] or "",
            publication_year=item["publication_year"],
            source_name=item["source_name"] or "",
            doi=item["doi"] or "",
            url=item["url"] or "",
            abstract="Updated abstract with a robustness evaluation.",
            status=item["status"],
            personal_notes=item["personal_notes"] or "",
            tags=[],
            project_ids=[self.project_id],
        )
        items = get_library_items(
            project_id=self.project_id,
            item_types=("paper", "pdf"),
        )
        cases = get_project_research_cases(self.project_id)
        coverage = get_research_case_coverage(items, cases)

        self.assertEqual(coverage["ready"], 0)
        self.assertEqual(coverage["outdated"], 1)
        self.assertEqual(coverage["to_process"], 1)

    def test_final_synthesis_rejects_unretrieved_source_references(self):
        self._paper(
            "Comparison source",
            "Two methods are compared using one controlled evaluation protocol.",
        )
        provider = UntraceableSynthesisProvider()
        generate_project_research_cases(
            self.project_id,
            ai_provider=provider,
        )
        result = recommend_relevant_experiments(
            self.project_id,
            ai_provider=provider,
        )

        self.assertIsNone(result["final_experiment"])
        self.assertIn("valid retrieved Research Case", result["synthesis_error"])

    def test_missing_article_evidence_is_recorded_as_failed(self):
        item_id = self._paper("Metadata-only paper", "")

        with self.assertRaisesRegex(ValueError, "no extractable article text"):
            generate_research_case_for_item(
                self.project_id,
                item_id,
                ai_provider=MockProvider(),
            )

        stored = get_research_case(self.project_id, item_id)
        self.assertEqual(stored["status"], "failed")
        self.assertIn("no extractable article text", stored["error_message"])

    def test_template_aliases_are_domain_independent(self):
        self.assertEqual(
            normalize_template_type("Model Comparison"),
            "comparative_evaluation",
        )
        self.assertEqual(
            normalize_template_type("Catalyst Comparison"),
            "comparative_evaluation",
        )


if __name__ == "__main__":
    unittest.main()
