import json

from ai.factory import get_ai_provider


WRITING_MODES = ("Draft", "Rewrite", "Cite", "Check claims")


def _row_dict(row) -> dict:
    return dict(row) if row is not None else {}


def _source_payload(sources) -> list[dict]:
    return [
        {
            "library_item_id": source["library_item_id"],
            "citation_key": source["citation_key"],
            "title": source["title"],
            "authors": source["authors"] or "",
            "year": source["publication_year"],
            "journal": source["source_name"] or "",
            "doi": source["doi"] or "",
            "abstract": str(source["abstract"] or "")[:2200],
            "researcher_notes": str(source["source_notes"] or "")[:800],
        }
        for source in list(sources)[:16]
    ]


def _evidence_payload(evidence) -> list[dict]:
    return [
        {
            "evidence_type": row["evidence_type"],
            "evidence_id": row["evidence_id"],
            "label": row["label"],
            "excerpt": str(row["excerpt"] or "")[:2200],
        }
        for row in list(evidence)[:20]
    ]


def build_writing_prompt(
    *,
    mode: str,
    instruction: str,
    manuscript,
    section,
    sections,
    sources,
    evidence,
    context_mode: str = "Current section",
    context_sections=None,
) -> str:
    outline = [
        {
            "section_id": row["id"],
            "title": row["title"],
            "section_type": row["section_type"],
        }
        for row in sections
    ]
    selected_context_sections = list(
        context_sections if context_sections is not None else sections
    )[:16]
    context_section_payload = [
        {
            "section_id": row["id"],
            "title": row["title"],
            "section_type": row["section_type"],
            "content": str(row["content_md"] or "")[:6000],
        }
        for row in selected_context_sections
    ]
    return f"""
PAPER_WRITING_REQUEST

You are Research Journal AI, a careful scientific writing assistant. Work only
with the supplied manuscript text, project evidence, and bibliographic source
metadata/abstracts. You do not have access to full papers unless their content
is explicitly included below.

MODE: {mode}
USER_INSTRUCTION: {instruction.strip() or "Improve the selected section."}
CONTEXT_SCOPE: {context_mode}

MANUSCRIPT_JSON:
{json.dumps(_row_dict(manuscript), ensure_ascii=False, default=str)}

SELECTED_SECTION_JSON:
{json.dumps(_row_dict(section), ensure_ascii=False, default=str)}

OUTLINE_JSON:
{json.dumps(outline, ensure_ascii=False)}

SELECTED_CONTEXT_SECTIONS_JSON:
{json.dumps(context_section_payload, ensure_ascii=False)}

ATTACHED_BIBLIOGRAPHIC_SOURCES_JSON:
{json.dumps(_source_payload(sources), ensure_ascii=False, default=str)}

PINNED_PROJECT_EVIDENCE_JSON:
{json.dumps(_evidence_payload(evidence), ensure_ascii=False, default=str)}

Return STRICT JSON with this structure:
{{
  "suggested_text": "Markdown text for the selected section",
  "explanation": "Short explanation of the changes or analysis",
  "evidence_used": [
    {{
      "source_type": "library|experiment|summary|key_idea",
      "source_id": 1,
      "label": "Evidence label",
      "support": "What this evidence supports"
    }}
  ],
  "claims": [
    {{
      "claim": "Claim from the text",
      "status": "supported|weak|unsupported",
      "reason": "Why",
      "citation_keys": ["smith2025"]
    }}
  ]
}}

Rules:
- Match the language and scientific tone of the selected section.
- Use only the sections listed in SELECTED_CONTEXT_SECTIONS_JSON as additional
  manuscript context. The outline titles are structural orientation, not evidence.
- Never invent measurements, methods, findings, authors, citations, or DOI data.
- Use citation tokens only in the exact form [@citation_key] and only with keys
  listed in ATTACHED_BIBLIOGRAPHIC_SOURCES_JSON.
- A title/abstract alone is limited evidence; say so in the explanation or claim
  reason when relevant.
- For Draft, produce a coherent section draft grounded in supplied evidence.
- For Rewrite, preserve factual meaning and existing citation tokens.
- For Cite, retain the text and add only citations that are directly supported.
- For Check claims, keep suggested_text equal to the current section and return
  a claim-by-claim assessment. Mark unsupported claims explicitly.
- Do not output anything outside the JSON object.
"""


def _normalize_result(result: dict, current_text: str) -> dict:
    raw_evidence = result.get("evidence_used")
    raw_claims = result.get("claims")
    evidence_used = raw_evidence if isinstance(raw_evidence, list) else []
    claims = raw_claims if isinstance(raw_claims, list) else []
    normalized_claims = []

    for row in claims[:30]:
        if not isinstance(row, dict):
            continue

        status = str(row.get("status") or "unsupported").strip().lower()

        if status not in ("supported", "weak", "unsupported"):
            status = "unsupported"

        keys = row.get("citation_keys")
        normalized_claims.append({
            "claim": str(row.get("claim") or "").strip(),
            "status": status,
            "reason": str(row.get("reason") or "").strip(),
            "citation_keys": [
                str(key).strip()
                for key in (keys if isinstance(keys, list) else [])
                if str(key).strip()
            ],
        })

    normalized_evidence = []

    for row in evidence_used[:20]:
        if not isinstance(row, dict):
            continue

        normalized_evidence.append({
            "source_type": str(row.get("source_type") or "").strip(),
            "source_id": row.get("source_id"),
            "label": str(row.get("label") or "Evidence").strip(),
            "support": str(row.get("support") or "").strip(),
        })

    return {
        "suggested_text": str(result.get("suggested_text") or current_text),
        "explanation": str(result.get("explanation") or "").strip(),
        "evidence_used": normalized_evidence,
        "claims": normalized_claims,
    }


def generate_writing_suggestion(
    *,
    mode: str,
    instruction: str,
    manuscript,
    section,
    sections,
    sources,
    evidence,
    context_mode: str = "Current section",
    context_sections=None,
    ai_provider=None,
) -> dict:
    if mode not in WRITING_MODES:
        raise ValueError("Unsupported writing assistant mode.")

    if not section:
        raise ValueError("Select a manuscript section first.")

    if mode == "Cite" and not sources:
        raise ValueError("Attach at least one bibliographic source before citing.")

    ai = ai_provider or get_ai_provider()
    result = ai.generate_json(
        build_writing_prompt(
            mode=mode,
            instruction=instruction,
            manuscript=manuscript,
            section=section,
            sections=sections,
            sources=sources,
            evidence=evidence,
            context_mode=context_mode,
            context_sections=context_sections,
        )
    )

    if not isinstance(result, dict):
        raise ValueError("AI returned an invalid writing response.")

    normalized = _normalize_result(result, str(section["content_md"] or ""))
    normalized["context_used"] = {
        "mode": context_mode,
        "section_ids": [
            row["id"]
            for row in list(context_sections if context_sections is not None else sections)
        ],
        "source_ids": [row["library_item_id"] for row in sources],
        "evidence_keys": [
            f"{row['evidence_type']}:{row['evidence_id']}" for row in evidence
        ],
    }
    return normalized
