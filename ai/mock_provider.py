import json
import hashlib
import math
import re
import unicodedata
from typing import Any

from ai.base import AIProvider


class MockProvider(AIProvider):
    def generate_text(self, prompt: str) -> str:
        return """
Acesta este un rezumat de test.

Experimentul conține observații importante, iar cercetătorul a notat rezultate care pot fi analizate ulterior.
"""

    def generate_json(
        self,
        prompt: str,
        *,
        json_schema: dict | None = None,
        max_output_tokens: int | None = None,
    ) -> Any:
        del json_schema, max_output_tokens

        if "FINAL_EXPERIMENT_SYNTHESIS_REQUEST" in prompt:
            source_ids = list(dict.fromkeys(
                int(value)
                for value in re.findall(
                    r'"library_item_id":\s*(\d+)',
                    prompt,
                )
            ))
            return {
                "title": "Controlled comparison of the candidate method",
                "objective": (
                    "Determine whether the candidate method improves the primary "
                    "outcome under the same evaluation protocol as the baseline."
                ),
                "hypothesis": (
                    "The candidate method will improve the primary outcome over "
                    "the baseline while all other conditions remain fixed."
                ),
                "template_type": "comparative_evaluation",
                "rationale": (
                    "The closest Research Cases repeatedly use controlled comparisons."
                ),
                "independent_variables": [{
                    "name": "Method",
                    "levels": ["Baseline", "Candidate method"],
                    "rationale": "Isolate the effect of the proposed method.",
                }],
                "control_condition": "Baseline method under the shared protocol.",
                "controlled_variables": ["Dataset", "Evaluation protocol"],
                "experimental_units": {
                    "unit": "Independent evaluation run",
                    "groups": 2,
                    "replicates_per_group": 5,
                    "total_units": 10,
                },
                "materials_and_setup": [
                    "Fixed dataset split",
                    "Baseline and candidate implementations",
                ],
                "randomization": "Randomize run order with a recorded seed.",
                "blinding": "Blind outcome aggregation to method labels where feasible.",
                "procedure_steps": [
                    "Freeze the dataset split and evaluation protocol.",
                    "Run the baseline and candidate under identical conditions.",
                    "Collect the predefined primary and secondary outcomes.",
                    "Compare groups using the prespecified analysis.",
                ],
                "measurements": [{
                    "name": "Primary outcome",
                    "unit": "score",
                    "timing": "After every evaluation run",
                    "role": "Primary",
                }],
                "duration": "One complete evaluation cycle per replicate.",
                "analysis_plan": [
                    "Report group means, dispersion, effect size, and uncertainty.",
                ],
                "success_criteria": [
                    "The candidate improves the prespecified primary outcome.",
                ],
                "stop_conditions": [
                    "Stop if data integrity or protocol consistency cannot be verified.",
                ],
                "assumptions": [
                    "Five replicates per group is an operational default requiring review.",
                ],
                "evidence_basis": [
                    {
                        "library_item_id": source_id,
                        "supported_choice": (
                            "Supports a controlled comparative evaluation design."
                        ),
                    }
                    for source_id in source_ids[:2]
                ],
                "confidence": "Medium",
            }

        if "PROJECT_CASE_EXTRACTION_REQUEST" in prompt:
            return {
                "metadata": {
                    "title": "Current research project",
                    "domain": "research",
                    "keywords": ["research", "experimental evaluation"],
                },
                "research_context": {
                    "problem": "Evaluate the current research question.",
                    "motivation": "Use project evidence to identify relevant precedents.",
                    "limitations": [],
                },
                "proposed_solution": {
                    "main_idea": "Test the project hypothesis with controlled experiments.",
                    "novelty": "",
                    "components": [],
                },
                "experimental_strategy": [],
                "findings": {
                    "main_results": [],
                    "negative_results": [],
                    "future_work": [],
                },
                "traceability": {"sections": []},
            }

        if "RESEARCH_CASE_EXTRACTION_REQUEST" in prompt:
            return {
                "metadata": {
                    "title": "Research article",
                    "domain": "research",
                    "keywords": ["experiment", "comparison", "evaluation"],
                },
                "research_context": {
                    "problem": "Compare alternative research methods.",
                    "motivation": "Identify which method performs better.",
                    "limitations": ["Only the supplied source was available."],
                },
                "proposed_solution": {
                    "main_idea": "Evaluate alternatives under a shared protocol.",
                    "novelty": "",
                    "components": ["baseline", "candidate method"],
                },
                "experimental_strategy": [
                    {
                        "template_type": "comparative_evaluation",
                        "goal": "Compare two methods under the same protocol.",
                        "changed_variable": "Method",
                        "controlled_variables": ["dataset", "protocol"],
                        "evaluation_metric": "Primary outcome metric",
                        "motivation": "Validate the main contribution.",
                        "concrete_example": "Baseline versus candidate method.",
                        "evidence": {
                            "section": "Abstract",
                            "page": "",
                            "excerpt": "Comparison reported in the supplied abstract.",
                        },
                    }
                ],
                "findings": {
                    "main_results": [],
                    "negative_results": [],
                    "future_work": [],
                },
                "traceability": {
                    "sections": [{"name": "Abstract", "page_range": ""}]
                },
            }

        if "PAPER_WRITING_REQUEST" in prompt:
            section_match = re.search(
                r"SELECTED_SECTION_JSON:\s*(.*?)\s*OUTLINE_JSON:",
                prompt,
                flags=re.DOTALL,
            )
            section = json.loads(section_match.group(1)) if section_match else {}
            current_text = str(section.get("content_md") or "").strip()
            suggested_text = current_text or (
                "The selected project evidence supports a cautious scientific "
                "draft. Add verified measurements and citations before final review."
            )

            return {
                "suggested_text": suggested_text,
                "explanation": (
                    "Mock writing suggestion generated from the selected section "
                    "and attached project context."
                ),
                "evidence_used": [],
                "claims": [
                    {
                        "claim": suggested_text[:140],
                        "status": "weak",
                        "reason": "Mock mode cannot verify source content.",
                        "citation_keys": [],
                    }
                ],
            }

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

    def generate_embedding(
        self,
        text: str,
        *,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> list[float]:
        del task_type
        dimensions = 256
        vector = [0.0] * dimensions
        normalized = unicodedata.normalize("NFKD", str(text or "").casefold())
        tokens = re.findall(r"[a-z0-9]+", normalized)
        features = [*tokens, *[
            f"{tokens[index]} {tokens[index + 1]}"
            for index in range(len(tokens) - 1)
        ]]

        for feature in features:
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % dimensions
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))

        if not norm:
            return vector

        return [round(value / norm, 8) for value in vector]
