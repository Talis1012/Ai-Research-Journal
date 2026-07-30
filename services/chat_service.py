from ai.factory import get_ai_provider
from services.summary_service import format_messages_for_ai
from utils.prompts import UNTRUSTED_CONTENT_RULES, untrusted_data, user_request


def _format_rows_for_project_ai(rows, fields: tuple[str, ...]) -> str:
    payload = []

    for row in rows or []:
        values = []

        for field in fields:
            try:
                value = row[field]
            except (KeyError, TypeError, IndexError):
                value = ""

            if value:
                values.append(f"{field}: {value}")

        if values:
            payload.append({
                field: row[field]
                for field in fields
                if field in row.keys() and row[field] is not None
            })

    return untrusted_data(payload, "saved project context")


def answer_question_about_project(
    project_name: str,
    project_domain: str,
    messages,
    summaries,
    ideas,
    mindmap_nodes,
    mindmap_edges,
    user_question: str,
    chat_history: list[dict] | None = None,
) -> str:
    ai = get_ai_provider()
    notes_text = format_messages_for_ai(messages)
    summaries_text = _format_rows_for_project_ai(
        summaries,
        ("scope", "content", "created_at"),
    )
    ideas_text = _format_rows_for_project_ai(
        ideas,
        ("title", "description", "evidence", "importance"),
    )
    nodes_text = _format_rows_for_project_ai(
        mindmap_nodes,
        ("node_key", "label", "description", "importance"),
    )
    edges_text = _format_rows_for_project_ai(
        mindmap_edges,
        ("source_key", "target_key", "relation"),
    )
    history_text = untrusted_data(
        list(chat_history or [])[-12:],
        "AI chat history",
    )

    prompt = f"""
Ești Research Journal AI, un asistent care ajută cercetătorul să înțeleagă
întregul proiect, nu doar un singur experiment.

Proiect:
{untrusted_data(project_name, "project name")}

Domeniu:
{untrusted_data(project_domain, "project domain")}

Notițe și transcrieri din toate experimentele:
{notes_text or "Nu există notițe."}

Rezumate salvate pentru proiect și experimente:
{summaries_text or "Nu există rezumate salvate."}

Idei principale:
{ideas_text or "Nu există idei principale salvate."}

Noduri mind map:
{nodes_text or "Nu există noduri în mind map."}

Relații mind map:
{edges_text or "Nu există relații în mind map."}

Istoric conversație:
{history_text}

Întrebarea utilizatorului:
{user_request(user_question, "current user question")}

{UNTRUSTED_CONTENT_RULES}

Răspunde în limba română.

Reguli stricte:
- Folosește numai datele proiectului furnizate mai sus.
- Poți sintetiza informații între experimente și poți identifica tipare sau goluri.
- Separă clar informațiile observate de inferențele prudente.
- Dacă datele nu susțin răspunsul, spune explicit ce informații lipsesc.
- Nu inventa rezultate, valori, surse, compuși sau concluzii.
- Nu oferi proceduri periculoase sau pași operaționali riscanți.
- Fii clar, structurat și util pentru un cercetător.
"""

    return ai.generate_text(prompt)


def answer_question_about_experiment(
    project_name: str,
    chat_title: str,
    chat_objective: str,
    notes,
    user_question: str,
    chat_history=None
) -> str:
    ai = get_ai_provider()

    notes_text = format_messages_for_ai(notes)
    history_text = untrusted_data(
        list(chat_history or [])[-12:],
        "AI chat history",
    )

    prompt = f"""
Ești Research Journal AI, un asistent pentru jurnal de cercetare.

Utilizatorul discută cu tine despre un singur experiment, iar sursa ta de adevăr este
setul de notițe al acelui experiment.

Proiect:
{untrusted_data(project_name, "project name")}

Experiment:
{untrusted_data(chat_title, "experiment title")}

Obiectiv experiment:
{untrusted_data(chat_objective or "Nu este menționat.", "experiment objective")}

Notițe disponibile în experiment:
{notes_text or "Nu există încă notițe pentru acest experiment."}

Istoric conversație AI:
{history_text}

Întrebarea utilizatorului:
{user_request(user_question, "current user question")}

{UNTRUSTED_CONTENT_RULES}

Răspunde în limba română.

Reguli stricte:
- Folosește doar notițele experimentului și istoricul conversației de mai sus.
- Dacă notițele nu conțin informația cerută, spune clar că nu există suficiente informații.
- Nu inventa rezultate, compuși, valori, proceduri sau concluzii.
- Poți ajuta cu rezumate, comparații, întrebări de follow-up, tabele conceptuale și interpretări prudente.
- Nu oferi instrucțiuni chimice periculoase sau pași operaționali riscanți.
- Fii concis, util și explicit când faci o inferență.
"""

    return ai.generate_text(prompt)


def answer_question_about_node(
    project_name: str,
    node_label: str,
    node_description: str,
    messages,
    user_question: str,
    chat_history: list[dict] | None = None
) -> str:
    ai = get_ai_provider()

    notes_text = format_messages_for_ai(messages)

    history_text = untrusted_data(
        list(chat_history or [])[-12:],
        "mind-map chat history",
    )

    prompt = f"""
Ești un asistent AI pentru un cercetător.

Utilizatorul a dat click pe un nod din mindmap și vrea să discute DOAR despre acel nod.

Proiect:
{untrusted_data(project_name, "project name")}

Nod selectat:
{untrusted_data(node_label, "selected node label")}

Descriere nod:
{untrusted_data(node_description, "selected node description")}

Istoric conversație pe acest nod:
{history_text}

Notițe disponibile din proiect:
{notes_text}

Întrebarea utilizatorului:
{user_request(user_question, "current user question")}

{UNTRUSTED_CONTENT_RULES}

Răspunde în limba română.

Reguli stricte:
- Răspunde doar pe baza notițelor disponibile.
- Concentrează-te pe nodul selectat.
- Dacă întrebarea cere ceva ce nu există în notițe, spune clar că nu ai suficiente informații.
- Nu inventa rezultate, compuși, observații sau concluzii.
- Nu oferi instrucțiuni chimice periculoase.
- Fii clar și util pentru un cercetător.
"""

    return ai.generate_text(prompt)
