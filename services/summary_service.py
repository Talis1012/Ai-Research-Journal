from ai.factory import get_ai_provider
from utils.prompts import UNTRUSTED_CONTENT_RULES, untrusted_data, user_request


SUMMARY_STYLE_STANDARD = "Standard cercetare"
SUMMARY_STYLE_ACADEMIC = "Raport academic"
SUMMARY_STYLE_ACTIONS = "Rezumat rapid cu acțiuni"
SUMMARY_STYLE_CUSTOM = "Prompt personalizat"


SUMMARY_STYLE_OPTIONS = [
    SUMMARY_STYLE_STANDARD,
    SUMMARY_STYLE_ACADEMIC,
    SUMMARY_STYLE_ACTIONS,
    SUMMARY_STYLE_CUSTOM
]

CHAT_SUMMARY_STYLE_DESCRIPTIONS = {
    SUMMARY_STYLE_STANDARD: """
**Structură:**
1. Scopul experimentului, dacă apare în notițe
2. Observațiile importante
3. Rezultatele sau concluziile menționate
4. Probleme, incertitudini sau lucruri care trebuie verificate
5. Pași următori posibili, dar doar dacă pot fi deduși din notițe
""",

    SUMMARY_STYLE_ACADEMIC: """
**Structură:**
1. Contextul experimentului
2. Obiectivul experimentului
3. Materiale / compuși / elemente menționate
4. Metodă sau pași observați, doar dacă apar în notițe
5. Observații experimentale
6. Rezultate preliminare
7. Limitări și incertitudini
8. Concluzie
""",

    SUMMARY_STYLE_ACTIONS: """
**Structură:**
1. Ideea principală în 2-3 fraze
2. Cele mai importante observații, în bullet points
3. Ce pare promițător
4. Ce probleme trebuie verificate
5. Întrebări deschise
6. Următoarele acțiuni recomandate, doar dacă pot fi deduse din notițe
""",

    SUMMARY_STYLE_CUSTOM: """
**Structură personalizată:**

Vei scrie tu structura dorită în câmpul de prompt personalizat.
Gemini va primi notițele reale ale chat-ului și va încerca să respecte structura scrisă de tine.
"""
}


PROJECT_SUMMARY_STYLE_DESCRIPTIONS = {
    SUMMARY_STYLE_STANDARD: """
**Structură:**
1. Scopul general al proiectului
2. Experimentele principale
3. Observațiile importante
4. Rezultatele obținute până acum
5. Probleme sau neclarități
6. Conexiuni între experimente
7. Pași următori posibili, fără să inventeze date noi
""",

    SUMMARY_STYLE_ACADEMIC: """
**Structură:**
1. Titlu propus pentru raport
2. Contextul cercetării
3. Obiectivul general
4. Experimente / chat-uri analizate
5. Observații importante grupate pe teme
6. Rezultate preliminare
7. Corelații între experimente
8. Limitări ale datelor disponibile
9. Concluzii
10. Direcții viitoare de cercetare, doar dacă pot fi deduse din notițe
""",

    SUMMARY_STYLE_ACTIONS: """
**Structură:**
1. Rezumat foarte scurt al proiectului
2. Cele mai importante 5 idei
3. Ce rezultate par relevante
4. Ce probleme trebuie investigate
5. Ce experimente par conectate între ele
6. Listă de acțiuni următoare
7. Întrebări importante rămase deschise
""",

    SUMMARY_STYLE_CUSTOM: """
**Structură personalizată:**

Vei scrie tu structura dorită în câmpul de prompt personalizat.
Gemini va primi notițele reale ale proiectului și va încerca să respecte structura scrisă de tine.
"""
}


def format_messages_for_ai(messages) -> str:
    payload = []

    for message in messages:
        keys = message.keys() if hasattr(message, "keys") else ()
        payload.append({
            "experiment": message["chat_title"] if "chat_title" in keys else "",
            "message_type": message["type"],
            "created_at": message["created_at"],
            "content": message["content"],
        })

    return untrusted_data(payload, "research notes and transcripts")


def build_chat_summary_prompt(
    chat_title: str,
    messages,
    summary_style: str,
    custom_prompt: str = ""
) -> str:
    text = format_messages_for_ai(messages)

    base_context = f"""
Ești un asistent AI pentru cercetare științifică.

Ai primit notițele dintr-un singur experiment/chat.

Titlu experiment:
{untrusted_data(chat_title, "experiment title")}

Notițe:
{text}
"""

    safety_rules = """
Reguli obligatorii:
- Răspunde în limba română.
- Nu inventa informații.
- Folosește doar notițele date.
- Dacă ceva nu apare în notițe, spune că nu este menționat.
- Nu oferi proceduri chimice periculoase.
"""

    if summary_style == SUMMARY_STYLE_STANDARD:
        structure = """
Realizează un rezumat clar și structurat.

Structură:
1. Scopul experimentului, dacă apare în notițe
2. Observațiile importante
3. Rezultatele sau concluziile menționate
4. Probleme, incertitudini sau lucruri care trebuie verificate
5. Pași următori posibili, dar doar dacă pot fi deduși din notițe
"""

    elif summary_style == SUMMARY_STYLE_ACADEMIC:
        structure = """
Realizează un rezumat în stil academic, potrivit pentru un jurnal de laborator.

Structură:
1. Contextul experimentului
2. Obiectivul experimentului
3. Materiale / compuși / elemente menționate
4. Metodă sau pași observați, doar dacă apar în notițe
5. Observații experimentale
6. Rezultate preliminare
7. Limitări și incertitudini
8. Concluzie
"""

    elif summary_style == SUMMARY_STYLE_ACTIONS:
        structure = """
Realizează un rezumat scurt, practic și orientat spre acțiune.

Structură:
1. Ideea principală în 2-3 fraze
2. Cele mai importante observații, în bullet points
3. Ce pare promițător
4. Ce probleme trebuie verificate
5. Întrebări deschise
6. Următoarele acțiuni recomandate, doar dacă pot fi deduse din notițe
"""

    elif summary_style == SUMMARY_STYLE_CUSTOM:
        structure = f"""
Respectă următorul prompt personalizat scris de utilizator:

{user_request(custom_prompt, "requested summary structure")}

Dacă promptul personalizat cere informații care nu există în notițe, spune clar că nu sunt menționate.
"""

    else:
        structure = """
Realizează un rezumat clar și structurat al experimentului.
"""

    return f"""
{base_context}

{structure}

{safety_rules}

{UNTRUSTED_CONTENT_RULES}
"""


def build_project_summary_prompt(
    project_name: str,
    messages,
    summary_style: str,
    custom_prompt: str = ""
) -> str:
    text = format_messages_for_ai(messages)

    base_context = f"""
Ești un asistent AI pentru cercetare științifică.

Ai primit toate notițele dintr-un proiect de cercetare.

Nume proiect:
{untrusted_data(project_name, "project name")}

Notițe din toate experimentele:
{text}
"""

    safety_rules = """
Reguli obligatorii:
- Răspunde în limba română.
- Nu inventa informații.
- Folosește doar notițele date.
- Dacă nu există suficiente informații, spune clar.
- Nu oferi proceduri chimice periculoase.
"""

    if summary_style == SUMMARY_STYLE_STANDARD:
        structure = """
Realizează un rezumat complet al proiectului.

Structură:
1. Scopul general al proiectului
2. Experimentele principale
3. Observațiile importante
4. Rezultatele obținute până acum
5. Probleme sau neclarități
6. Conexiuni între experimente
7. Pași următori posibili, fără să inventezi date noi
"""

    elif summary_style == SUMMARY_STYLE_ACADEMIC:
        structure = """
Realizează un raport academic al proiectului.

Structură:
1. Titlu propus pentru raport
2. Contextul cercetării
3. Obiectivul general
4. Experimente / chat-uri analizate
5. Observații importante grupate pe teme
6. Rezultate preliminare
7. Corelații între experimente
8. Limitări ale datelor disponibile
9. Concluzii
10. Direcții viitoare de cercetare, doar dacă pot fi deduse din notițe
"""

    elif summary_style == SUMMARY_STYLE_ACTIONS:
        structure = """
Realizează un rezumat executiv, scurt și orientat spre decizii.

Structură:
1. Rezumat foarte scurt al proiectului
2. Cele mai importante 5 idei
3. Ce rezultate par relevante
4. Ce probleme trebuie investigate
5. Ce experimente par conectate între ele
6. Listă de acțiuni următoare
7. Întrebări importante rămase deschise
"""

    elif summary_style == SUMMARY_STYLE_CUSTOM:
        structure = f"""
Respectă următorul prompt personalizat scris de utilizator:

{user_request(custom_prompt, "requested summary structure")}

Dacă promptul personalizat cere informații care nu există în notițe, spune clar că nu sunt menționate.
"""

    else:
        structure = """
Realizează un rezumat clar și structurat al proiectului.
"""

    return f"""
{base_context}

{structure}

{safety_rules}

{UNTRUSTED_CONTENT_RULES}
"""


def generate_chat_summary(
    chat_title: str,
    messages,
    summary_style: str = SUMMARY_STYLE_STANDARD,
    custom_prompt: str = ""
) -> str:
    ai = get_ai_provider()

    prompt = build_chat_summary_prompt(
        chat_title=chat_title,
        messages=messages,
        summary_style=summary_style,
        custom_prompt=custom_prompt
    )

    return ai.generate_text(prompt)


def generate_project_summary(
    project_name: str,
    messages,
    summary_style: str = SUMMARY_STYLE_STANDARD,
    custom_prompt: str = ""
) -> str:
    ai = get_ai_provider()

    prompt = build_project_summary_prompt(
        project_name=project_name,
        messages=messages,
        summary_style=summary_style,
        custom_prompt=custom_prompt
    )

    return ai.generate_text(prompt)


def extract_project_ideas(project_name: str, messages) -> list[dict]:
    ai = get_ai_provider()

    text = format_messages_for_ai(messages)

    prompt = f"""
Ești un asistent AI pentru organizarea cercetării științifice.

Ai primit toate notițele dintr-un proiect.

Nume proiect:
{untrusted_data(project_name, "project name")}

Notițe:
{text}

{UNTRUSTED_CONTENT_RULES}

Extrage ideile principale ale proiectului.

Returnează STRICT JSON valid, fără markdown, fără explicații extra.

Format obligatoriu:

{{
  "ideas": [
    {{
      "title": "Titlu scurt al ideii",
      "description": "Descriere clară a ideii",
      "evidence": "Ce notiță sau observație susține această idee",
      "importance": "high/medium/low"
    }}
  ]
}}

Reguli:
- Nu inventa idei care nu apar în notițe.
- Dacă nu există suficiente informații, returnează:
{{
  "ideas": []
}}
- Titlurile trebuie să fie scurte.
- Description trebuie să fie clară și utilă pentru un cercetător.
- Nu oferi proceduri chimice periculoase.
"""

    data = ai.generate_json(prompt)

    raw_ideas = data.get("ideas", []) if isinstance(data, dict) else data

    if not isinstance(raw_ideas, list):
        return []

    ideas = []

    for row in raw_ideas[:20]:
        if not isinstance(row, dict):
            continue

        importance = str(row.get("importance") or "medium").strip().lower()
        ideas.append({
            "title": str(row.get("title") or "").strip()[:160],
            "description": str(row.get("description") or "").strip()[:1200],
            "evidence": str(row.get("evidence") or "").strip()[:1200],
            "importance": (
                importance if importance in ("high", "medium", "low") else "medium"
            ),
        })

    return [idea for idea in ideas if idea["title"]]
