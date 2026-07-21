import unittest
from unittest.mock import Mock, patch

from services.discovery_service import rank_discovery_results
from services.openalex_service import (
    normalize_work,
    search_works,
    search_works_for_queries,
)


class FixedRankingProvider:
    def generate_json(self, prompt):
        return {
            "papers": [
                {
                    "ranking_id": "candidate-1",
                    "rubric": {
                        "direct_topic_relevance": 35,
                        "method_compatibility": 20,
                        "outcome_relevance": 16,
                        "research_gap_contribution": 9,
                    },
                    "reason": "Directly examines the requested scaffold and activity.",
                    "matched_concepts": ["thiazole", "antibacterial activity"],
                    "limitations": "Only the abstract was assessed.",
                    "confidence": "High",
                },
                {
                    "ranking_id": "candidate-2",
                    "rubric": {
                        "direct_topic_relevance": 15,
                        "method_compatibility": 10,
                        "outcome_relevance": 8,
                        "research_gap_contribution": 5,
                    },
                    "reason": "Provides secondary methodological context.",
                    "matched_concepts": ["screening"],
                    "limitations": "No abstract is available.",
                    "confidence": "Low",
                },
            ]
        }


class DiscoveryRankingTestCase(unittest.TestCase):
    def setUp(self):
        self.results = [
            {
                "openalex_id": "W1",
                "title": "Thiazole derivatives with antibacterial activity",
                "authors": "A. Researcher",
                "publication_year": 2025,
                "source_name": "Medicinal Chemistry",
                "abstract": (
                    "This study evaluates thiazole derivatives, antibacterial "
                    "activity, and structure activity relationships."
                ),
                "cited_by_count": 20,
                "is_open_access": True,
                "matched_queries": ["thiazole antibacterial", "thiazole SAR"],
                "relevance_score": 12,
            },
            {
                "openalex_id": "W2",
                "title": "General compound screening methods",
                "authors": "B. Researcher",
                "publication_year": 2018,
                "source_name": "Methods",
                "abstract": "",
                "cited_by_count": 5,
                "is_open_access": False,
                "matched_queries": ["thiazole SAR"],
                "relevance_score": 4,
            },
        ]
        self.profile = {
            "research_topic": "Thiazole antibacterial structure activity relationships",
            "short_description": "Medicinal chemistry optimization project",
            "keywords": ["thiazole", "antibacterial", "SAR"],
            "search_queries": ["thiazole antibacterial", "thiazole SAR"],
            "exclude_terms": [],
        }
        self.ideas = [
            {
                "title": "Antibacterial activity",
                "description": "Optimize thiazole structure activity relationships",
                "importance": "high",
            }
        ]

    def test_hybrid_score_uses_exact_weights(self):
        ranked, ai_error = rank_discovery_results(
            self.results,
            profile=self.profile,
            ideas=self.ideas,
            queries=self.profile["search_queries"],
            ai_provider=FixedRankingProvider(),
        )

        self.assertEqual(ai_error, "")
        strongest = next(work for work in ranked if work["openalex_id"] == "W1")
        self.assertEqual(strongest["ai_score"], 80)
        expected_final = round(0.55 * strongest["base_score"] + 0.45 * 80, 1)
        self.assertEqual(strongest["final_score"], expected_final)
        self.assertEqual(strongest["query_coverage_score"], 100)
        self.assertEqual(strongest["ai_confidence"], "High")

    def test_ai_failure_keeps_calculated_ranking(self):
        provider = Mock()
        provider.generate_json.side_effect = RuntimeError("temporary AI failure")
        ranked, ai_error = rank_discovery_results(
            self.results,
            profile=self.profile,
            ideas=self.ideas,
            queries=self.profile["search_queries"],
            ai_provider=provider,
        )

        self.assertEqual(ai_error, "temporary AI failure")
        self.assertTrue(all(work["ai_score"] is None for work in ranked))
        self.assertTrue(
            all(work["final_score"] == work["base_score"] for work in ranked)
        )


class OpenAlexServiceTestCase(unittest.TestCase):
    def test_normalize_work_canonicalizes_external_ids(self):
        work = normalize_work({
            "id": "https://openalex.org/W123",
            "doi": "https://doi.org/10.1000/TEST",
            "title": "Example",
            "publication_year": 2026,
            "authorships": [],
            "primary_location": {"source": {"display_name": "Journal"}},
            "open_access": {"is_oa": True},
            "cited_by_count": 3,
        })

        self.assertEqual(work["openalex_id"], "W123")
        self.assertEqual(work["doi"], "10.1000/test")
        self.assertEqual(work["url"], "https://doi.org/10.1000/test")

    @patch("services.openalex_service.requests.get")
    def test_search_sends_filters_sort_and_paging(self, mocked_get):
        response = Mock()
        response.ok = True
        response.json.return_value = {"meta": {"count": 1}, "results": []}
        mocked_get.return_value = response

        search_works(
            "thiazole SAR",
            per_page=12,
            from_year=2020,
            to_year=2026,
            open_access_only=True,
            sort="citations",
            page=2,
        )
        params = mocked_get.call_args.kwargs["params"]
        self.assertEqual(params["per_page"], 12)
        self.assertEqual(params["page"], 2)
        self.assertEqual(params["sort"], "cited_by_count:desc")
        self.assertIn("from_publication_date:2020-01-01", params["filter"])
        self.assertIn("to_publication_date:2026-12-31", params["filter"])
        self.assertIn("open_access.is_oa:true", params["filter"])

    @patch("services.openalex_service.search_works")
    def test_multi_query_search_deduplicates_and_tracks_matches(self, mocked_search):
        shared = {
            "openalex_id": "W1",
            "doi": "10.1000/shared",
            "title": "Shared paper",
            "publication_year": 2025,
            "abstract": "Relevant abstract",
            "relevance_score": 5,
        }
        mocked_search.side_effect = [
            {"meta": {}, "results": [dict(shared)]},
            {"meta": {}, "results": [{**shared, "relevance_score": 8}]},
        ]

        results = search_works_for_queries(["query one", "query two"])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["matched_queries"], ["query one", "query two"])
        self.assertEqual(results[0]["relevance_score"], 8)


if __name__ == "__main__":
    unittest.main()
