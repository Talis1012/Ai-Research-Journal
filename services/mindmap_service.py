from ai.factory import get_ai_provider
from services.summary_service import format_messages_for_ai


def normalize_node_id(text: str) -> str:
    text = text.lower().strip()
    text = text.replace(" ", "_")
    text = text.replace("-", "_")

    allowed_chars = []

    for ch in text:
        if ch.isalnum() or ch == "_":
            allowed_chars.append(ch)

    result = "".join(allowed_chars)

    if not result:
        return "node"

    return result


def normalize_mindmap_data(data: dict) -> dict:
    raw_nodes = data.get("nodes", [])
    raw_edges = data.get("edges", [])

    nodes = []
    used_ids = set()

    for index, node in enumerate(raw_nodes):
        raw_id = node.get("id") or node.get("label") or f"node_{index}"
        node_id = normalize_node_id(str(raw_id))

        if node_id in used_ids:
            node_id = f"{node_id}_{index}"

        used_ids.add(node_id)

        nodes.append({
            "id": node_id,
            "label": node.get("label", node_id),
            "description": node.get("description", ""),
            "importance": node.get("importance", "medium")
        })

    valid_ids = {node["id"] for node in nodes}

    edges = []

    for edge in raw_edges:
        source = normalize_node_id(str(edge.get("source", "")))
        target = normalize_node_id(str(edge.get("target", "")))

        if source in valid_ids and target in valid_ids and source != target:
            edges.append({
                "source": source,
                "target": target,
                "relation": edge.get("relation", "")
            })

    return {
        "nodes": nodes,
        "edges": edges
    }


def generate_mindmap_for_project(project_name: str, messages, ideas=None) -> dict:
    ai = get_ai_provider()

    notes_text = format_messages_for_ai(messages)

    ideas_text = ""

    if ideas:
        idea_parts = []

        for idea in ideas:
            idea_parts.append(
                f"""
Titlu idee: {idea['title']}
Descriere: {idea['description']}
Dovadă: {idea['evidence']}
Importanță: {idea['importance']}
"""
            )

        ideas_text = "\n---\n".join(idea_parts)

    prompt = f"""
Ești un asistent AI care construiește un mindmap pentru un proiect de cercetare.

Nume proiect:
{project_name}

Idei principale deja extrase:
{ideas_text}

Notițe din proiect:
{notes_text}

Generează un mindmap în format JSON strict.

Format obligatoriu:

{{
  "nodes": [
    {{
      "id": "id_scurt_fara_spatii",
      "label": "Nume nod",
      "description": "Descriere scurtă a nodului",
      "importance": "high/medium/low"
    }}
  ],
  "edges": [
    {{
      "source": "id_nod_sursa",
      "target": "id_nod_destinatie",
      "relation": "relația dintre noduri"
    }}
  ]
}}

Reguli:
- Folosește doar informațiile din notițe.
- Nu inventa experimente, compuși sau rezultate.
- Nodurile trebuie să fie concepte importante, nu propoziții lungi.
- Creează maximum 12 noduri.
- Creează relații logice între noduri.
- Returnează doar JSON valid, fără markdown.
"""

    data = ai.generate_json(prompt)

    return normalize_mindmap_data(data)