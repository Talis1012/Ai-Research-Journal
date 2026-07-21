import json
import re
from typing import Any

from ai.base import AIProvider


class MockProvider(AIProvider):
    def generate_text(self, prompt: str) -> str:
        return """
Acesta este un rezumat de test.

Experimentul conține observații importante, iar cercetătorul a notat rezultate care pot fi analizate ulterior.
"""

    def generate_json(self, prompt: str) -> Any:
        if "DISCOVER_RANKING_REQUEST" in prompt:
            match = re.search(
                r"CANDIDATES_JSON_START\s*(.*?)\s*CANDIDATES_JSON_END",
                prompt,
                flags=re.DOTALL,
            )
            candidates = json.loads(match.group(1)) if match else []
            papers = []

            for candidate in candidates:
                topic = float(candidate.get("topic_match_score") or 0)
                ideas = float(candidate.get("key_ideas_score") or 0)
                papers.append({
                    "ranking_id": candidate.get("ranking_id"),
                    "rubric": {
                        "direct_topic_relevance": round(min(40, topic * 0.4)),
                        "method_compatibility": round(min(25, ideas * 0.25)),
                        "outcome_relevance": round(min(20, topic * 0.2)),
                        "research_gap_contribution": 8,
                    },
                    "reason": (
                        "The paper overlaps with the generated research profile "
                        "and is suitable for contextual evaluation."
                    ),
                    "matched_concepts": ["research topic", "project context"],
                    "limitations": "Mock ranking used for local development.",
                    "confidence": "Medium",
                })

            return {"papers": papers}

        if "profil de căutare bibliografică" in prompt:
            return {
                "research_topic": "project research topic",
                "short_description": "Search profile generated for local development.",
                "keywords": ["research", "experimental results", "analysis"],
                "search_queries": [
                    "experimental research analysis",
                    "research methods project results",
                    "scientific evidence review",
                ],
                "exclude_terms": [],
            }

        return {
            "ideas": [
                {
                    "title": "Idee de test",
                    "description": "Aceasta este o idee principală generată pentru testare.",
                    "evidence": "Bazată pe notițele de test.",
                    "importance": "medium"
                }
            ]
        }
