import os

import requests
from dotenv import load_dotenv

from db.library_queries import normalize_doi, normalize_openalex_id
from services.resource_limits import (
    concurrency_slot,
    consume_rate_limit,
    env_int,
)


load_dotenv()


OPENALEX_BASE_URL = "https://api.openalex.org"
OPENALEX_SORT_OPTIONS = {
    "relevance": "relevance_score:desc",
    "citations": "cited_by_count:desc",
    "newest": "publication_date:desc",
}


def reconstruct_abstract(abstract_inverted_index):
    if not abstract_inverted_index:
        return ""

    words_with_positions = []

    for word, positions in abstract_inverted_index.items():
        for position in positions:
            words_with_positions.append((position, word))

    words_with_positions.sort()
    return " ".join(word for _, word in words_with_positions)


def get_auth_params():
    api_key = os.getenv("OPENALEX_API_KEY", "").strip()

    if not api_key:
        return {}

    return {"api_key": api_key}


def format_authors(authorships, max_authors=5):
    authors = []

    for authorship in authorships[:max_authors]:
        author = authorship.get("author", {})
        display_name = author.get("display_name")

        if display_name:
            authors.append(display_name)

    if len(authorships) > max_authors:
        authors.append("et al.")

    return ", ".join(authors)


def normalize_work(work):
    primary_location = work.get("primary_location") or {}
    best_oa_location = work.get("best_oa_location") or {}
    source = primary_location.get("source") or {}
    open_access = work.get("open_access") or {}
    doi = normalize_doi(work.get("doi"))
    openalex_id = normalize_openalex_id(work.get("id"))
    landing_page_url = (
        best_oa_location.get("landing_page_url")
        or primary_location.get("landing_page_url")
        or (f"https://doi.org/{doi}" if doi else "")
        or (f"https://openalex.org/{openalex_id}" if openalex_id else "")
    )

    return {
        "openalex_id": openalex_id,
        "title": work.get("title") or work.get("display_name") or "Untitled paper",
        "authors": format_authors(work.get("authorships", [])),
        "publication_year": work.get("publication_year"),
        "publication_date": work.get("publication_date") or "",
        "source_name": source.get("display_name", ""),
        "doi": doi,
        "url": landing_page_url,
        "pdf_url": best_oa_location.get("pdf_url") or "",
        "cited_by_count": int(work.get("cited_by_count") or 0),
        "is_open_access": bool(open_access.get("is_oa", False)),
        "oa_status": open_access.get("oa_status") or "",
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "relevance_score": float(work.get("relevance_score") or 0),
        "work_type": work.get("type") or "",
        "language": work.get("language") or "",
    }


def _build_filters(
    *,
    from_year: int | None,
    to_year: int | None,
    open_access_only: bool,
) -> str:
    filters = []

    if from_year:
        filters.append(f"from_publication_date:{int(from_year)}-01-01")

    if to_year:
        filters.append(f"to_publication_date:{int(to_year)}-12-31")

    if open_access_only:
        filters.append("open_access.is_oa:true")

    return ",".join(filters)


def _raise_openalex_error(response):
    if response.status_code == 401:
        raise RuntimeError("OpenAlex rejected the API key.")

    if response.status_code == 403:
        raise RuntimeError("OpenAlex access is not permitted for this request.")

    if response.status_code == 429:
        raise RuntimeError(
            "OpenAlex request limit reached. Please wait and try again."
        )

    try:
        detail = response.json().get("message") or response.json().get("error")
    except (ValueError, AttributeError):
        detail = ""

    suffix = f": {detail}" if detail else ""
    raise RuntimeError(f"OpenAlex returned HTTP {response.status_code}{suffix}")


def search_works(
    query: str,
    per_page: int = 10,
    *,
    from_year: int | None = None,
    to_year: int | None = None,
    open_access_only: bool = False,
    sort: str = "relevance",
    page: int = 1,
):
    normalized_query = str(query or "").strip()

    if not normalized_query:
        raise ValueError("Search query cannot be empty.")

    if len(normalized_query) > env_int(
        "OPENALEX_MAX_QUERY_CHARS",
        300,
        maximum=1000,
    ):
        raise ValueError("Search query is too long for OpenAlex.")

    per_page = max(1, min(int(per_page), 25))
    page = max(1, min(int(page), 100))
    params = {
        "search": normalized_query,
        "per_page": per_page,
        "page": page,
        "select": ",".join([
            "id",
            "doi",
            "title",
            "display_name",
            "publication_year",
            "publication_date",
            "authorships",
            "primary_location",
            "best_oa_location",
            "open_access",
            "cited_by_count",
            "abstract_inverted_index",
            "relevance_score",
            "type",
            "language",
        ]),
        "sort": OPENALEX_SORT_OPTIONS.get(
            sort,
            OPENALEX_SORT_OPTIONS["relevance"],
        ),
    }
    filters = _build_filters(
        from_year=from_year,
        to_year=to_year,
        open_access_only=open_access_only,
    )

    if filters:
        params["filter"] = filters

    params.update(get_auth_params())

    consume_rate_limit(
        "OpenAlex",
        per_user_hour=env_int(
            "OPENALEX_REQUESTS_PER_USER_HOUR",
            120,
            maximum=5000,
        ),
        per_user_day=env_int(
            "OPENALEX_REQUESTS_PER_USER_DAY",
            500,
            maximum=50000,
        ),
        global_per_minute=env_int(
            "OPENALEX_GLOBAL_REQUESTS_PER_MINUTE",
            120,
            maximum=10000,
        ),
        global_per_day=env_int(
            "OPENALEX_GLOBAL_REQUESTS_PER_DAY",
            5000,
            maximum=500000,
        ),
    )

    with concurrency_slot(
        "OpenAlex",
        global_limit=env_int(
            "OPENALEX_MAX_CONCURRENT_REQUESTS",
            8,
            maximum=100,
        ),
        lease_seconds=40,
    ):
        try:
            response = requests.get(
                f"{OPENALEX_BASE_URL}/works",
                params=params,
                timeout=15,
            )
        except requests.Timeout as exc:
            raise RuntimeError("OpenAlex took too long to respond.") from exc
        except requests.RequestException as exc:
            raise RuntimeError("Could not connect to OpenAlex.") from exc

    if not response.ok:
        _raise_openalex_error(response)

    data = response.json()
    return {
        "meta": data.get("meta", {}),
        "results": [normalize_work(work) for work in data.get("results", [])],
    }


def _work_unique_key(work: dict) -> str:
    return (
        normalize_doi(work.get("doi"))
        or normalize_openalex_id(work.get("openalex_id"))
        or f"{work.get('title', '').casefold().strip()}::{work.get('publication_year') or ''}"
    )


def _merge_duplicate_work(existing: dict, candidate: dict, query: str):
    matched_queries = list(existing.get("matched_queries") or [])

    if query not in matched_queries:
        matched_queries.append(query)

    existing["matched_queries"] = matched_queries
    existing["matched_query"] = matched_queries[0] if matched_queries else query
    existing["relevance_score"] = max(
        float(existing.get("relevance_score") or 0),
        float(candidate.get("relevance_score") or 0),
    )

    for field in ("abstract", "url", "pdf_url", "source_name", "authors"):
        if not existing.get(field) and candidate.get(field):
            existing[field] = candidate[field]


def search_works_for_queries(
    queries: list[str],
    per_page: int = 5,
    *,
    from_year: int | None = None,
    to_year: int | None = None,
    open_access_only: bool = False,
    sort: str = "relevance",
    exclude_terms: list[str] | None = None,
    page: int = 1,
):
    results_by_key = {}
    normalized_queries = []
    max_queries = env_int("OPENALEX_MAX_QUERIES_PER_SEARCH", 5, maximum=20)

    for raw_query in queries:
        query = str(raw_query or "").strip()

        if not query or query in normalized_queries:
            continue

        normalized_queries.append(query)

        if len(normalized_queries) > max_queries:
            raise ValueError(
                f"A single search can contain at most {max_queries} unique queries."
            )

    for query in normalized_queries:
        data = search_works(
            query=query,
            per_page=per_page,
            from_year=from_year,
            to_year=to_year,
            open_access_only=open_access_only,
            sort=sort,
            page=page,
        )

        for work in data.get("results", []):
            unique_key = _work_unique_key(work)

            if not unique_key:
                continue

            if unique_key in results_by_key:
                _merge_duplicate_work(results_by_key[unique_key], work, query)
                continue

            work["matched_queries"] = [query]
            work["matched_query"] = query
            results_by_key[unique_key] = work

    excluded = [
        str(term).casefold().strip()[:100]
        for term in list(exclude_terms or [])[:20]
        if str(term).strip()
    ]
    results = []

    for work in results_by_key.values():
        haystack = f"{work.get('title', '')} {work.get('abstract', '')}".casefold()

        if excluded and any(term in haystack for term in excluded):
            continue

        results.append(work)

    return results
