"""
ia notițele proiectului
↓
le trimite la Gemini
↓
primește keywords + query-uri în engleză
"""

from ai.factory import get_ai_provider
from services.summary_service import format_messages_for_ai
from utils.prompts import UNTRUSTED_CONTENT_RULES, untrusted_data


def _string_list(value, *, maximum: int = 20, item_chars: int = 200) -> list[str]:
    if not isinstance(value, list):
        return []

    return [
        str(item).strip()[:item_chars]
        for item in value[:maximum]
        if str(item).strip()
    ]


def format_ideas_for_ai(ideas) -> str:
    if not ideas:
        return untrusted_data([], "saved project ideas")

    return untrusted_data(
        [
            {
                "title": idea["title"],
                "description": idea["description"],
                "evidence": idea["evidence"],
                "importance": idea["importance"],
            }
            for idea in list(ideas)[:30]
        ],
        "saved project ideas",
    )


def generate_bibliography_search_profile(
    project_name: str,
    project_domain: str,
    messages,
    ideas=None
) -> dict:
    ai = get_ai_provider()

    notes_text = format_messages_for_ai(messages)
    ideas_text = format_ideas_for_ai(ideas)

    prompt = f"""
Ești un asistent AI pentru cercetare științifică.

Scopul tău este să înțelegi proiectul cercetătorului și să generezi query-uri bune
pentru căutarea de literatură științifică în OpenAlex.

Proiect:
{untrusted_data(project_name, "project name")}

Domeniu:
{untrusted_data(project_domain, "project domain")}

Idei principale deja extrase:
{ideas_text}

Notițe din proiect:
{notes_text}

{UNTRUSTED_CONTENT_RULES}

Generează un profil de căutare bibliografică.

Returnează STRICT JSON valid, fără markdown, fără explicații extra.

Format obligatoriu:

{{
  "research_topic": "Tema principală a cercetării, în engleză",
  "short_description": "Descriere scurtă a proiectului, în engleză",
  "keywords": [
    "keyword 1",
    "keyword 2",
    "keyword 3"
  ],
  "search_queries": [
    "query 1 in English",
    "query 2 in English",
    "query 3 in English"
  ],
  "exclude_terms": [
    "term that should be avoided"
  ]
}}

Reguli:
- Toate query-urile trebuie să fie în engleză.
- Query-urile trebuie să fie potrivite pentru articole științifice.
- Nu inventa compuși, rezultate sau metode care nu apar în notițe.
- Generează între 3 și 5 query-uri.
- Fiecare query trebuie să fie scurt, clar și util pentru OpenAlex.
- Nu folosi propoziții lungi; folosește termeni de căutare.
- Dacă notițele sunt prea puține, generează query-uri generale, dar spune asta în short_description.
"""

    data = ai.generate_json(prompt)

    if not isinstance(data, dict):
        return {
            "research_topic": "",
            "short_description": "",
            "keywords": [],
            "search_queries": [],
            "exclude_terms": []
        }

    return {
        "research_topic": str(data.get("research_topic") or "").strip()[:300],
        "short_description": str(data.get("short_description") or "").strip()[:1000],
        "keywords": _string_list(data.get("keywords"), maximum=12, item_chars=80),
        "search_queries": _string_list(
            data.get("search_queries"),
            maximum=5,
            item_chars=300,
        ),
        "exclude_terms": _string_list(
            data.get("exclude_terms"),
            maximum=20,
            item_chars=100,
        ),
    }
