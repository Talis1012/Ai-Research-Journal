import re
from collections import Counter, defaultdict

from db.writing_queries import manuscript_word_count, validate_section_citations


JOURNAL_TEMPLATES = {
    "General IMRaD": {
        "description": "Standard original-research structure with a concise abstract.",
        "word_limit": 5000,
        "abstract_word_limit": 250,
        "required_sections": (
            "abstract",
            "introduction",
            "methods",
            "results",
            "discussion",
            "conclusion",
            "references",
        ),
    },
    "Concise journal article": {
        "description": "Short-format article with tightly limited main text.",
        "word_limit": 3000,
        "abstract_word_limit": 200,
        "required_sections": (
            "abstract",
            "introduction",
            "methods",
            "results",
            "discussion",
            "references",
        ),
    },
    "Full research article": {
        "description": "Full-length original article with room for detailed methods and discussion.",
        "word_limit": 8000,
        "abstract_word_limit": 300,
        "required_sections": (
            "abstract",
            "introduction",
            "methods",
            "results",
            "discussion",
            "conclusion",
            "references",
        ),
    },
    "Methods-focused article": {
        "description": "Method-development structure emphasizing reproducibility and validation.",
        "word_limit": 6000,
        "abstract_word_limit": 250,
        "required_sections": (
            "abstract",
            "introduction",
            "methods",
            "results",
            "discussion",
            "references",
        ),
    },
    "Custom journal": {
        "description": "User-defined limits while retaining section and submission checks.",
        "word_limit": 5000,
        "abstract_word_limit": 250,
        "required_sections": (
            "abstract",
            "introduction",
            "methods",
            "results",
            "discussion",
            "references",
        ),
    },
}

SECTION_MINIMUM_WORDS = {
    "abstract": 50,
    "introduction": 100,
    "methods": 100,
    "results": 100,
    "discussion": 100,
    "conclusion": 40,
}
CLAIM_PATTERN = re.compile(
    r"\b(?:significant(?:ly)?|increase[ds]?|decrease[ds]?|improve[ds]?|"
    r"reduce[ds]?|higher|lower|associated|correlat(?:e[ds]?|ion)|demonstrat(?:e[ds]?|ed)|"
    r"show(?:s|ed)?|confirm(?:s|ed)?|result(?:s|ed)?|observ(?:e[ds]?|ed)|"
    r"effect(?:ive|iveness)?|difference|superior|inferior)\b|\b\d+(?:\.\d+)?\s*%",
    re.IGNORECASE,
)
ABBREVIATION_PATTERN = re.compile(r"\b[A-Z][A-Z0-9-]{1,9}\b")
ABBREVIATION_WHITELIST = {
    "DOI",
    "ORCID",
    "PDF",
    "DOCX",
    "SI",
    "SD",
    "CI",
    "USA",
    "UK",
}
STOP_WORDS = {
    "about", "after", "again", "against", "also", "among", "because",
    "before", "between", "could", "during", "from", "have", "into", "more",
    "most", "other", "over", "same", "showed", "shows", "that", "their",
    "there", "these", "this", "those", "through", "under", "using", "were",
    "which", "while", "with", "would", "result", "results", "discussion",
}


def template_rules(template_name: str) -> dict:
    return dict(JOURNAL_TEMPLATES.get(template_name) or JOURNAL_TEMPLATES["General IMRaD"])


def _plain_text(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"\[\[@?[^\]]+\]\]|\[@[^\]]+\]", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^\s{0,3}(?:#{1,6}|[-*+]|\d+\.|>)\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_`]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _word_count(value: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", _plain_text(value)))


def _sentences(value: str) -> list[str]:
    text = _plain_text(value)
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _content_tokens(value: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"\b[A-Za-z][A-Za-z-]{3,}\b", _plain_text(value))
        if token.casefold() not in STOP_WORDS
    }


def _overlap(left: str, right: str) -> float:
    left_tokens = _content_tokens(left)
    right_tokens = _content_tokens(right)

    if not left_tokens or not right_tokens:
        return 0.0

    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def _issue(category, severity, title, detail, *, section=None, suggestion="") -> dict:
    return {
        "category": category,
        "severity": severity,
        "title": title,
        "detail": detail,
        "section_id": section["id"] if section else None,
        "section_title": section["title"] if section else None,
        "suggestion": suggestion,
    }


def run_manuscript_checks(manuscript, sections, sources, profile=None) -> dict:
    profile = profile or {}
    rules = template_rules(profile.get("journal_template", "General IMRaD"))
    word_limit = max(1, int(profile.get("word_limit") or rules["word_limit"]))
    abstract_limit = max(
        1,
        int(profile.get("abstract_word_limit") or rules["abstract_word_limit"]),
    )
    issues = []
    sections = [dict(section) for section in sections]
    by_type = defaultdict(list)

    for section in sections:
        by_type[str(section.get("section_type") or "custom").casefold()].append(section)

    for section_type in rules["required_sections"]:
        if not by_type.get(section_type):
            issues.append(_issue(
                "Incomplete sections",
                "error",
                f"Missing {section_type.title()} section",
                "The selected journal structure requires this section.",
                suggestion="Add the missing section to the outline.",
            ))

    for section in sections:
        section_type = str(section.get("section_type") or "custom").casefold()
        count = _word_count(section.get("content_md", ""))
        minimum = SECTION_MINIMUM_WORDS.get(section_type)

        if minimum and count < minimum:
            issues.append(_issue(
                "Incomplete sections",
                "error" if count == 0 else "warning",
                f"{section['title']} is incomplete",
                f"{count} words; the working completeness threshold is {minimum}.",
                section=section,
                suggestion="Add the missing objective, methods, findings, or interpretation.",
            ))

    all_text = "\n".join(str(section.get("content_md") or "") for section in sections)
    all_plain = _plain_text(all_text)
    defined_abbreviations = set()

    for abbreviation in set(ABBREVIATION_PATTERN.findall(all_plain)):
        definition_after = re.search(
            rf"\b[A-Za-z][A-Za-z][A-Za-z\s/-]{{3,}}\s+\({re.escape(abbreviation)}\)",
            all_plain,
        )
        definition_before = re.search(
            rf"\b{re.escape(abbreviation)}\s+\([A-Za-z][^)]{{3,}}\)",
            all_plain,
        )

        if definition_after or definition_before:
            defined_abbreviations.add(abbreviation)

    for abbreviation in sorted(set(ABBREVIATION_PATTERN.findall(all_plain))):
        if (
            abbreviation in ABBREVIATION_WHITELIST
            or abbreviation in defined_abbreviations
            or ("-" in abbreviation and any(character.isdigit() for character in abbreviation))
        ):
            continue

        section = next(
            (row for row in sections if re.search(rf"\b{re.escape(abbreviation)}\b", _plain_text(row.get("content_md", "")))),
            None,
        )
        issues.append(_issue(
            "Undefined abbreviations",
            "warning",
            f"{abbreviation} is not defined",
            "The abbreviation appears without an expanded form on first use.",
            section=section,
            suggestion=f"Write the full term followed by ({abbreviation}) at first mention.",
        ))

    attached_keys = {str(source["citation_key"]).casefold(): source for source in sources}
    cited_keys = []

    for section in sections:
        validation = validate_section_citations(section.get("content_md", ""), sources)
        cited_keys.extend(key.casefold() for key in validation["valid_keys"])

        for key in validation["unknown_keys"]:
            issues.append(_issue(
                "Citations",
                "error",
                f"Citation [@{key}] is not attached",
                "The citation token does not match an attached source.",
                section=section,
                suggestion="Attach the source or replace the citation key.",
            ))

    cited_folds = set(cited_keys)

    for key, source in attached_keys.items():
        if key not in cited_folds:
            issues.append(_issue(
                "Citations",
                "warning",
                f"Attached source [@{source['citation_key']}] is unused",
                str(source["title"] or "Untitled source"),
                suggestion="Cite the source in the manuscript or detach it.",
            ))

    for section in sections:
        if section.get("section_type") not in {"introduction", "results", "discussion", "conclusion"}:
            continue

        raw_content = str(section.get("content_md") or "")
        raw_sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", raw_content) if part.strip()]
        unsupported = [
            _plain_text(sentence)
            for sentence in raw_sentences
            if CLAIM_PATTERN.search(_plain_text(sentence))
            and not re.search(r"\[@[^\]]+\]|\[\[(?:figure|table|equation):\d+\]\]", sentence)
        ]

        if unsupported:
            excerpt = " ".join(unsupported[:2])
            issues.append(_issue(
                "Claims without evidence",
                "warning",
                f"{len(unsupported)} claim(s) may need evidence",
                excerpt[:300],
                section=section,
                suggestion="Add a citation, data-object reference, or soften the claim.",
            ))

    sentence_locations = defaultdict(list)

    for section in sections:
        for sentence in _sentences(section.get("content_md", "")):
            normalized = re.sub(r"\W+", " ", sentence.casefold()).strip()

            if len(normalized.split()) >= 7:
                sentence_locations[normalized].append(section)

    for sentence, locations in sentence_locations.items():
        if len(locations) > 1:
            distinct = []

            for location in locations:
                if location["id"] not in [row["id"] for row in distinct]:
                    distinct.append(location)

            issues.append(_issue(
                "Repetition and consistency",
                "warning",
                "Repeated sentence detected",
                f"Appears {len(locations)} times: {sentence[:220]}",
                section=distinct[0],
                suggestion="Keep the strongest occurrence and rewrite or remove the others.",
            ))

    unit_variants = {
        "microgram per millilitre": (r"\b(?:ug|µg)/m[lL]\b", r"\bmcg/m[lL]\b"),
        "degree Celsius": (r"\b°\s*C\b", r"\bdegrees?\s+C(?:elsius)?\b"),
        "p-value": (r"\bp\s*-\s*value\b", r"\bp\s+value\b"),
    }

    for label, variants in unit_variants.items():
        matched = [variant for variant in variants if re.search(variant, all_plain, re.IGNORECASE)]

        if len(matched) > 1:
            issues.append(_issue(
                "Repetition and consistency",
                "warning",
                f"Inconsistent {label} notation",
                "More than one notation is used across the manuscript.",
                suggestion="Choose one notation and apply it consistently.",
            ))

    result_sections = by_type.get("results", [])
    discussion_sections = by_type.get("discussion", [])
    result_claims = [sentence for row in result_sections for sentence in _sentences(row.get("content_md", "")) if CLAIM_PATTERN.search(sentence)]
    discussion_claims = [sentence for row in discussion_sections for sentence in _sentences(row.get("content_md", "")) if CLAIM_PATTERN.search(sentence)]

    if result_claims and discussion_sections:
        unmatched_results = [
            claim for claim in result_claims
            if not any(_overlap(claim, discussion) >= 0.3 for discussion in discussion_claims)
        ]

        if unmatched_results:
            issues.append(_issue(
                "Results vs Discussion",
                "warning",
                f"{len(unmatched_results)} result claim(s) are not discussed",
                " ".join(unmatched_results[:2])[:300],
                section=discussion_sections[0],
                suggestion="Interpret the result in Discussion or explain why it is not central.",
            ))

    if discussion_claims and result_sections:
        unmatched_discussion = [
            claim for claim in discussion_claims
            if not any(_overlap(claim, result) >= 0.3 for result in result_claims)
        ]

        if unmatched_discussion:
            issues.append(_issue(
                "Results vs Discussion",
                "warning",
                f"{len(unmatched_discussion)} discussion claim(s) lack a Results counterpart",
                " ".join(unmatched_discussion[:2])[:300],
                section=result_sections[0],
                suggestion="Add the supporting result or remove unsupported interpretation.",
            ))

    total_words = manuscript_word_count(sections)
    abstract_section = by_type.get("abstract", [None])[0]
    abstract_words = _word_count(abstract_section.get("content_md", "")) if abstract_section else 0

    if total_words > word_limit:
        issues.append(_issue(
            "Word limits",
            "error",
            "Main manuscript exceeds the word limit",
            f"{total_words:,} words against a {word_limit:,}-word limit.",
            suggestion=f"Reduce the manuscript by at least {total_words - word_limit:,} words.",
        ))

    if abstract_words > abstract_limit:
        issues.append(_issue(
            "Word limits",
            "error",
            "Abstract exceeds the word limit",
            f"{abstract_words:,} words against a {abstract_limit:,}-word limit.",
            section=abstract_section,
            suggestion=f"Reduce the abstract by at least {abstract_words - abstract_limit:,} words.",
        ))

    counts = Counter(issue["severity"] for issue in issues)
    score = max(0, 100 - counts["error"] * 12 - counts["warning"] * 5 - counts["info"] * 2)
    return {
        "issues": issues,
        "counts": dict(counts),
        "score": score,
        "word_count": total_words,
        "word_limit": word_limit,
        "abstract_word_count": abstract_words,
        "abstract_word_limit": abstract_limit,
        "template": profile.get("journal_template") or "General IMRaD",
    }


def publication_readiness(manuscript, sections, sources, assets, profile, checks=None) -> dict:
    checks = checks or run_manuscript_checks(manuscript, sections, sources, profile)
    sections = [dict(section) for section in sections]
    by_type = {str(section.get("section_type") or "").casefold(): section for section in sections}
    corresponding = profile.get("corresponding_author") or {}
    keywords = profile.get("keywords") or []
    authors = profile.get("authors") or []
    affiliations = profile.get("affiliations") or []
    automated = [
        ("Title completed", bool(str(manuscript["title"] or "").strip()), "Add a manuscript title."),
        ("Authors completed", bool(authors), "Add at least one author."),
        ("Affiliations completed", bool(affiliations), "Add institutional affiliations."),
        (
            "Corresponding author completed",
            bool(str(corresponding.get("name", "")).strip() and str(corresponding.get("email", "")).strip()),
            "Add the corresponding author name and email.",
        ),
        (
            "Abstract completed",
            _word_count(by_type.get("abstract", {}).get("content_md", "")) >= SECTION_MINIMUM_WORDS["abstract"],
            "Complete the Abstract section.",
        ),
        ("At least 3 keywords", len(keywords) >= 3, "Add at least three keywords."),
        (
            "Within word limits",
            checks["word_count"] <= checks["word_limit"] and checks["abstract_word_count"] <= checks["abstract_word_limit"],
            "Revise the manuscript or its configured limits.",
        ),
        (
            "Citations resolved",
            not any(issue["severity"] == "error" and issue["category"] == "Citations" for issue in checks["issues"]),
            "Resolve missing citation keys.",
        ),
        (
            "Figures have alt text",
            all(asset.get("asset_type") != "figure" or str(asset.get("alt_text") or "").strip() for asset in assets),
            "Add alt text to every figure.",
        ),
        (
            "No blocking manuscript checks",
            checks["counts"].get("error", 0) == 0,
            "Resolve every error-level manuscript check.",
        ),
    ]
    manual_labels = {
        "author_approval": "All authors approved the final manuscript",
        "cover_letter": "Cover letter prepared",
        "conflicts_disclosed": "Conflicts of interest disclosed",
        "ethics_statement": "Ethics statement verified",
        "data_availability": "Data availability statement verified",
        "figures_verified": "Figure resolution and legends verified",
        "supplementary_files": "Supplementary files attached or marked not applicable",
    }
    checklist = profile.get("checklist") or {}
    items = [
        {"label": label, "complete": complete, "detail": "Ready" if complete else detail, "kind": "automatic"}
        for label, complete, detail in automated
    ]
    items.extend({
        "label": label,
        "complete": bool(checklist.get(key)),
        "detail": "Confirmed" if checklist.get(key) else "Requires confirmation",
        "kind": "manual",
    } for key, label in manual_labels.items())
    complete_count = sum(1 for item in items if item["complete"])
    return {
        "items": items,
        "complete": complete_count,
        "total": len(items),
        "percent": round(100 * complete_count / max(1, len(items))),
        "ready": complete_count == len(items),
    }
