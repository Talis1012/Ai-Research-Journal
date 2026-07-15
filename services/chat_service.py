from ai.factory import get_ai_provider
from services.summary_service import format_messages_for_ai


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
    history_text = ""

    if chat_history:
        history_parts = []

        for message in chat_history[-12:]:
            history_parts.append(
                f"{message['role']}: {message['content']}"
            )

        history_text = "\n".join(history_parts)

    prompt = f"""
Ești Research Journal AI, un asistent pentru jurnal de cercetare.

Utilizatorul discută cu tine despre un singur experiment, iar sursa ta de adevăr este
setul de notițe al acelui experiment.

Proiect:
{project_name}

Experiment:
{chat_title}

Obiectiv experiment:
{chat_objective or "Nu este menționat."}

Notițe disponibile în experiment:
{notes_text or "Nu există încă notițe pentru acest experiment."}

Istoric conversație AI:
{history_text or "Nu există istoric."}

Întrebarea utilizatorului:
{user_question}

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

    history_text = ""

    if chat_history:
        parts = []

        for message in chat_history:
            role = message.get("role", "user")
            content = message.get("content", "")

            parts.append(f"{role}: {content}")

        history_text = "\n".join(parts)

    prompt = f"""
Ești un asistent AI pentru un cercetător.

Utilizatorul a dat click pe un nod din mindmap și vrea să discute DOAR despre acel nod.

Proiect:
{project_name}

Nod selectat:
{node_label}

Descriere nod:
{node_description}

Istoric conversație pe acest nod:
{history_text}

Notițe disponibile din proiect:
{notes_text}

Întrebarea utilizatorului:
{user_question}

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
