import math
import re
from collections import Counter

from ai.factory import get_ai_provider
from services.resource_limits import env_int
from services.summary_service import format_messages_for_ai
from utils.prompts import UNTRUSTED_CONTENT_RULES, untrusted_data, user_request
from utils.timezone import user_today


DISCOVERY_BASE_WEIGHTS = {
    "topic_match_score": 0.40,
    "query_coverage_score": 0.20,
    "key_ideas_score": 0.15,
    "citation_score": 0.10,
    "recency_score": 0.10,
    "open_access_score": 0.05,
}

DISCOVERY_AI_WEIGHT = 0.45
DISCOVERY_BASE_WEIGHT = 0.55


def _discovery_ranking_json_schema(candidate_count: int) -> dict:
    return {
        "type": "object",
        "properties": {
            "papers": {
                "type": "array",
                "minItems": candidate_count,
                "maxItems": candidate_count,
                "items": {
                    "type": "object",
                    "properties": {
                        "ranking_id": {"type": "string"},
                        "rubric": {
                            "type": "object",
                            "properties": {
                                "direct_topic_relevance": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": 40,
                                },
                                "method_compatibility": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": 25,
                                },
                                "outcome_relevance": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": 20,
                                },
                                "research_gap_contribution": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": 15,
                                },
                            },
                            "required": [
                                "direct_topic_relevance",
                                "method_compatibility",
                                "outcome_relevance",
                                "research_gap_contribution",
                            ],
                        },
                        "reason": {"type": "string"},
                        "matched_concepts": {
                            "type": "array",
                            "maxItems": 4,
                            "items": {"type": "string"},
                        },
                        "limitations": {"type": "string"},
                        "confidence": {
                            "type": "string",
                            "enum": ["High", "Medium", "Low"],
                        },
                    },
                    "required": [
                        "ranking_id",
                        "rubric",
                        "reason",
                        "matched_concepts",
                        "limitations",
                        "confidence",
                    ],
                },
            },
        },
        "required": ["papers"],
    }


_STOP_WORDS = {
    "a", "about", "after", "all", "also", "an", "and", "are", "as", "at",
    "be", "been", "between", "by", "can", "could", "for", "from", "has",
    "have", "how", "in", "into", "is", "it", "its", "may", "more", "of",
    "on", "or", "our", "paper", "research", "study", "than", "that", "the",
    "their", "these", "this", "those", "to", "using", "was", "were", "what",
    "when", "which", "with", "within", "would",
}


def _row_value(row, key: str, default=""):
    try:
        value = row[key]
    except (KeyError, TypeError, IndexError):
        value = default

    return default if value is None else value


def _tokens(text: str) -> list[str]:
    words = [
        token
        for token in re.findall(r"[a-z0-9α-ω]+", str(text or "").casefold())
        if len(token) > 1 and token not in _STOP_WORDS
    ]
    bigrams = [f"{words[index]} {words[index + 1]}" for index in range(len(words) - 1)]
    return [*words, *bigrams]


def _weighted_counts(parts: list[tuple[str, float]]) -> Counter:
    counts = Counter()

    for text, weight in parts:
        for token, frequency in Counter(_tokens(text)).items():
            counts[token] += frequency * weight

    return counts


def _idf_for_documents(documents: list[Counter]) -> dict[str, float]:
    document_count = max(1, len(documents))
    document_frequency = Counter()

    for document in documents:
        document_frequency.update(document.keys())

    return {
        token: math.log((document_count + 1) / (frequency + 1)) + 1
        for token, frequency in document_frequency.items()
    }


def _tfidf_vector(counts: Counter, idf: dict[str, float]) -> dict[str, float]:
    return {
        token: (1 + math.log(frequency)) * idf.get(token, 1)
        for token, frequency in counts.items()
        if frequency > 0
    }


def _cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0

    common_tokens = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in common_tokens)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))

    if not left_norm or not right_norm:
        return 0.0

    return numerator / (left_norm * right_norm)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return float(ordered[lower])

    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _idea_counts(idea) -> Counter:
    return _weighted_counts([
        (str(_row_value(idea, "title")), 2.0),
        (str(_row_value(idea, "description")), 1.0),
    ])


def _importance_weight(idea) -> float:
    return {
        "high": 3.0,
        "medium": 2.0,
        "low": 1.0,
    }.get(str(_row_value(idea, "importance", "medium")).casefold(), 2.0)


def _score_candidates(
    results: list[dict],
    *,
    profile: dict,
    ideas,
    queries: list[str],
) -> list[dict]:
    if not results:
        return []

    project_counts = _weighted_counts([
        (str(profile.get("research_topic", "")), 3.0),
        (" ".join(profile.get("keywords", []) or []), 2.0),
        (str(profile.get("short_description", "")), 1.0),
    ])
    paper_counts = [
        _weighted_counts([
            (str(work.get("title", "")), 3.0),
            (str(work.get("abstract", "")), 1.0),
        ])
        for work in results
    ]
    idea_count_rows = [(_idea_counts(idea), _importance_weight(idea)) for idea in ideas or []]
    all_counts = [project_counts, *paper_counts, *[counts for counts, _ in idea_count_rows]]
    idf = _idf_for_documents(all_counts)
    project_vector = _tfidf_vector(project_counts, idf)
    paper_vectors = [_tfidf_vector(counts, idf) for counts in paper_counts]
    idea_vectors = [(_tfidf_vector(counts, idf), weight) for counts, weight in idea_count_rows]
    current_year = user_today().year
    citation_rates = []

    for work in results:
        publication_year = int(work.get("publication_year") or 0)
        age_denominator = max(1, current_year - publication_year + 1) if publication_year else 1
        citation_rates.append(int(work.get("cited_by_count") or 0) / age_denominator)

    citation_p95 = _percentile(citation_rates, 0.95)
    total_queries = max(1, len({query.strip() for query in queries if query.strip()}))
    scored = []

    for index, work in enumerate(results):
        paper_vector = paper_vectors[index]
        topic_score = 100 * _cosine_similarity(project_vector, paper_vector)
        matched_queries = {
            query.strip()
            for query in work.get("matched_queries", [])
            if query.strip()
        }
        query_coverage_score = 100 * min(1.0, len(matched_queries) / total_queries)

        if idea_vectors:
            weighted_similarity = sum(
                _cosine_similarity(idea_vector, paper_vector) * weight
                for idea_vector, weight in idea_vectors
            )
            total_idea_weight = sum(weight for _, weight in idea_vectors)
            key_ideas_score = 100 * weighted_similarity / total_idea_weight
        else:
            key_ideas_score = topic_score

        citation_rate = citation_rates[index]

        if citation_p95 > 0:
            citation_score = min(
                100.0,
                100 * math.log1p(citation_rate) / math.log1p(citation_p95),
            )
        else:
            citation_score = 0.0

        publication_year = int(work.get("publication_year") or 0)
        age = max(0, current_year - publication_year) if publication_year else 50
        recency_score = 100 * (2 ** (-age / 7))
        open_access_score = 100.0 if work.get("is_open_access") else 0.0
        components = {
            "topic_match_score": topic_score,
            "query_coverage_score": query_coverage_score,
            "key_ideas_score": key_ideas_score,
            "citation_score": citation_score,
            "recency_score": recency_score,
            "open_access_score": open_access_score,
        }
        base_score = sum(
            DISCOVERY_BASE_WEIGHTS[name] * value
            for name, value in components.items()
        )
        enriched = dict(work)
        enriched.update({name: round(value, 1) for name, value in components.items()})
        enriched.update({
            "base_score": round(base_score, 1),
            "ai_score": None,
            "final_score": round(base_score, 1),
            "ai_reason": "AI ranking has not been generated.",
            "matched_concepts": [],
            "ai_limitations": "",
            "ai_confidence": "Unavailable",
            "ai_rubric": {},
            "ranking_id": f"candidate-{index + 1}",
        })
        scored.append(enriched)

    return scored


def _ranking_payload(scored_results: list[dict]) -> list[dict]:
    return [
        {
            "ranking_id": work["ranking_id"],
            "openalex_id": work.get("openalex_id", ""),
            "title": work.get("title", ""),
            "authors": work.get("authors", ""),
            "publication_year": work.get("publication_year"),
            "source_name": work.get("source_name", ""),
            "abstract": str(work.get("abstract", ""))[:1800],
            "matched_queries": work.get("matched_queries", []),
            "base_score": work["base_score"],
            "topic_match_score": work["topic_match_score"],
            "key_ideas_score": work["key_ideas_score"],
        }
        for work in scored_results
    ]


def _ai_ranking_prompt(
    *,
    profile: dict,
    ideas,
    scored_results: list[dict],
) -> str:
    idea_payload = [
        {
            "title": _row_value(idea, "title"),
            "description": _row_value(idea, "description"),
            "importance": _row_value(idea, "importance", "medium"),
        }
        for idea in ideas or []
    ]
    expected_ranking_ids = [work["ranking_id"] for work in scored_results]
    example_ranking_id = (
        expected_ranking_ids[0]
        if expected_ranking_ids
        else "candidate-id"
    )
    return f"""
DISCOVER_RANKING_REQUEST

You are ranking scientific papers for a research project. Use only the supplied
project profile, key ideas, paper titles, metadata, and abstracts. Do not assume
access to the full papers.

Score every candidate with this exact rubric:
- direct_topic_relevance: integer 0-40
- method_compatibility: integer 0-25
- outcome_relevance: integer 0-20
- research_gap_contribution: integer 0-15

The AI score is the sum of these four fields. If the abstract is missing, be
conservative and state that limitation. Give a short evidence-based reason and
up to four matched concepts. Return exactly one entry for every supplied
ranking_id. Keep reason under 45 words and limitations under 25 words.

Expected ranking_id values for this batch:
{untrusted_data(expected_ranking_ids, "required ranking identifiers")}

Return STRICT JSON in this format:
{{
  "papers": [
    {{
      "ranking_id": "{example_ranking_id}",
      "rubric": {{
        "direct_topic_relevance": 0,
        "method_compatibility": 0,
        "outcome_relevance": 0,
        "research_gap_contribution": 0
      }},
      "reason": "Why the paper is relevant",
      "matched_concepts": ["concept"],
      "limitations": "Evidence limitation or empty string",
      "confidence": "High|Medium|Low"
    }}
  ]
}}

PROJECT_PROFILE_JSON:
{untrusted_data(profile, "AI-generated search profile")}

KEY_IDEAS_JSON:
{untrusted_data(idea_payload, "saved project ideas")}

CANDIDATES_JSON_START
{untrusted_data(_ranking_payload(scored_results), "external OpenAlex candidates")}
CANDIDATES_JSON_END

{UNTRUSTED_CONTENT_RULES}
"""


def _bounded_number(value, maximum: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0

    return min(max(numeric, 0.0), maximum)


def _apply_ai_ranking(scored_results: list[dict], response: dict):
    response_rows = {
        str(row.get("ranking_id", "")): row
        for row in response.get("papers", [])
        if isinstance(row, dict) and row.get("ranking_id")
    }

    for work in scored_results:
        row = response_rows.get(work["ranking_id"])

        if not row:
            continue

        rubric = row.get("rubric") if isinstance(row.get("rubric"), dict) else {}
        normalized_rubric = {
            "direct_topic_relevance": _bounded_number(
                rubric.get("direct_topic_relevance"), 40
            ),
            "method_compatibility": _bounded_number(
                rubric.get("method_compatibility"), 25
            ),
            "outcome_relevance": _bounded_number(
                rubric.get("outcome_relevance"), 20
            ),
            "research_gap_contribution": _bounded_number(
                rubric.get("research_gap_contribution"), 15
            ),
        }
        ai_score = sum(normalized_rubric.values())

        if not work.get("abstract"):
            ai_score = min(ai_score, 70.0)

        final_score = (
            DISCOVERY_BASE_WEIGHT * work["base_score"]
            + DISCOVERY_AI_WEIGHT * ai_score
        )
        raw_concepts = row.get("matched_concepts")
        concepts = raw_concepts if isinstance(raw_concepts, list) else []
        confidence = str(row.get("confidence") or "Medium").strip().title()

        if confidence not in ("High", "Medium", "Low"):
            confidence = "Medium"

        work.update({
            "ai_score": round(ai_score, 1),
            "final_score": round(final_score, 1),
            "ai_reason": str(row.get("reason") or "No AI explanation returned.").strip(),
            "matched_concepts": [
                str(concept).strip()
                for concept in concepts[:4]
                if str(concept).strip()
            ],
            "ai_limitations": str(row.get("limitations") or "").strip(),
            "ai_confidence": confidence,
            "ai_rubric": {name: round(value, 1) for name, value in normalized_rubric.items()},
        })


def _ranking_batches(scored_results: list[dict]) -> list[list[dict]]:
    batch_size = env_int(
        "DISCOVERY_AI_RANKING_BATCH_SIZE",
        5,
        minimum=1,
        maximum=10,
    )
    return [
        scored_results[index:index + batch_size]
        for index in range(0, len(scored_results), batch_size)
    ]


def _validate_ranking_response(batch: list[dict], response) -> None:
    if not isinstance(response, dict) or not isinstance(
        response.get("papers"),
        list,
    ):
        raise ValueError("AI ranking response has an invalid structure.")

    expected_ids = {str(work["ranking_id"]) for work in batch}
    returned_ids = {
        str(row.get("ranking_id") or "")
        for row in response["papers"]
        if isinstance(row, dict)
    }
    missing_ids = expected_ids - returned_ids
    unexpected_ids = returned_ids - expected_ids

    if (
        len(response["papers"]) != len(batch)
        or missing_ids
        or unexpected_ids
    ):
        raise ValueError(
            "AI ranking did not return exactly one result for every paper in "
            "the batch."
        )


def rank_discovery_results(
    results: list[dict],
    *,
    profile: dict,
    ideas=None,
    queries: list[str] | None = None,
    ai_provider=None,
) -> tuple[list[dict], str]:
    scored_results = _score_candidates(
        results,
        profile=profile,
        ideas=ideas or [],
        queries=queries or profile.get("search_queries", []) or [],
    )

    if not scored_results:
        return [], ""

    ai = ai_provider or get_ai_provider()
    batches = _ranking_batches(scored_results)
    batch_errors = []

    for batch_index, batch in enumerate(batches, start=1):
        try:
            response = ai.generate_json(
                _ai_ranking_prompt(
                    profile=profile,
                    ideas=ideas or [],
                    scored_results=batch,
                ),
                json_schema=_discovery_ranking_json_schema(len(batch)),
                max_output_tokens=env_int(
                    "DISCOVERY_RANKING_MAX_OUTPUT_TOKENS",
                    6144,
                    minimum=1024,
                    maximum=16_384,
                ),
            )
            _validate_ranking_response(batch, response)
            _apply_ai_ranking(batch, response)
        except Exception as exc:
            if len(batches) == 1:
                batch_errors.append(str(exc))
            else:
                batch_errors.append(
                    f"Batch {batch_index}/{len(batches)}: {exc}"
                )

    ai_error = " · ".join(batch_errors)

    scored_results.sort(
        key=lambda work: (
            -float(work.get("final_score") or 0),
            -float(work.get("base_score") or 0),
            -int(work.get("cited_by_count") or 0),
            str(work.get("title") or "").casefold(),
        )
    )
    return scored_results, ai_error


def answer_question_about_discovery(
    *,
    user_question: str,
    profile: dict,
    results: list[dict],
    selected_work: dict | None,
    project=None,
    project_messages=None,
    project_ideas=None,
    chat_history=None,
) -> str:
    ai = get_ai_provider()
    project_context = {
        "name": _row_value(project, "name") if project else "No project selected",
        "domain": _row_value(project, "domain") if project else "",
        "description": _row_value(project, "description") if project else "",
    }
    idea_payload = [
        {
            "title": _row_value(idea, "title"),
            "description": _row_value(idea, "description"),
            "importance": _row_value(idea, "importance", "medium"),
        }
        for idea in (project_ideas or [])
    ]
    result_payload = [
        {
            "title": work.get("title", ""),
            "authors": work.get("authors", ""),
            "year": work.get("publication_year"),
            "source": work.get("source_name", ""),
            "abstract": str(work.get("abstract", ""))[:1800],
            "final_score": work.get("final_score"),
            "ai_reason": work.get("ai_reason", ""),
        }
        for work in results[:10]
    ]
    selected_payload = None

    if selected_work:
        selected_payload = {
            "title": selected_work.get("title", ""),
            "authors": selected_work.get("authors", ""),
            "year": selected_work.get("publication_year"),
            "source": selected_work.get("source_name", ""),
            "doi": selected_work.get("doi", ""),
            "abstract": selected_work.get("abstract", ""),
            "score_components": {
                "base": selected_work.get("base_score"),
                "ai": selected_work.get("ai_score"),
                "final": selected_work.get("final_score"),
            },
            "ai_reason": selected_work.get("ai_reason", ""),
        }

    history_text = untrusted_data(
        list(chat_history or [])[-10:],
        "discovery chat history",
    )
    notes_text = format_messages_for_ai(list(project_messages or [])[-30:])
    prompt = f"""
You are Research Journal AI. Help the researcher understand scientific search
results and their relevance. Respond in Romanian.

PROJECT_JSON:
{untrusted_data(project_context, "project metadata")}

PROJECT_NOTES:
{notes_text or "No project notes were supplied."}

PROJECT_KEY_IDEAS_JSON:
{untrusted_data(idea_payload, "saved project ideas")}

SEARCH_PROFILE_JSON:
{untrusted_data(profile, "AI-generated search profile")}

TOP_SEARCH_RESULTS_JSON:
{untrusted_data(result_payload, "external OpenAlex search results")}

SELECTED_PAPER_JSON:
{untrusted_data(selected_payload, "selected external paper metadata")}

CHAT_HISTORY:
{history_text}

USER_QUESTION:
{user_request(user_question, "current user question")}

{UNTRUSTED_CONTENT_RULES}

Rules:
- Use only the supplied metadata, abstracts, project data, and score explanations.
- Never imply that you read the full paper when only an abstract is available.
- Clearly distinguish source-supported statements from cautious inference.
- If evidence is missing, say exactly what is missing.
- Do not invent findings, methods, numerical results, or citations.
- Keep the answer structured and useful for a researcher.
"""
    return ai.generate_text(prompt)
