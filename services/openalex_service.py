import os
import requests
from dotenv import load_dotenv


load_dotenv()


OPENALEX_BASE_URL = "https://api.openalex.org"


def reconstruct_abstract(abstract_inverted_index):
    if not abstract_inverted_index:
        return ""

    words_with_positions = []

    for word, positions in abstract_inverted_index.items():
        for position in positions:
            words_with_positions.append((position, word))

    words_with_positions.sort()

    words = [word for position, word in words_with_positions]

    return " ".join(words)


def get_auth_params():
    api_key = os.getenv("OPENALEX_API_KEY")

    if not api_key:
        return {}

    return {
        "api_key": api_key
    }


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
    source = primary_location.get("source") or {}

    open_access = work.get("open_access") or {}

    abstract = reconstruct_abstract(
        work.get("abstract_inverted_index")
    )

    return {
        "openalex_id": work.get("id", ""),
        "title": work.get("title") or work.get("display_name") or "Fără titlu",
        "authors": format_authors(work.get("authorships", [])),
        "publication_year": work.get("publication_year"),
        "source_name": source.get("display_name", ""),
        "doi": work.get("doi", ""),
        "url": work.get("doi") or work.get("id", ""),
        "cited_by_count": work.get("cited_by_count", 0),
        "is_open_access": open_access.get("is_oa", False),
        "abstract": abstract,
    }


def search_works(query: str, per_page: int = 10):
    params = {
        "search": query,
        "per_page": per_page,
        "select": ",".join([
            "id",
            "doi",
            "title",
            "display_name",
            "publication_year",
            "authorships",
            "primary_location",
            "open_access",
            "cited_by_count",
            "abstract_inverted_index"
        ])
    }

    params.update(get_auth_params())

    response = requests.get(
        f"{OPENALEX_BASE_URL}/works",
        params=params,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    results = data.get("results", [])

    normalized_results = []

    for work in results:
        normalized_results.append(normalize_work(work))

    return {
        "meta": data.get("meta", {}),
        "results": normalized_results
    }