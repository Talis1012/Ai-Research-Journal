import hashlib
import json

from ai.factory import get_ai_provider
from db.queries import (
    get_mindmap_edges,
    get_mindmap_nodes,
    get_mindmap_source_states,
    merge_project_mindmap,
)
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


def normalize_mindmap_data(data: dict, known_node_ids=None) -> dict:
    raw_nodes = data.get("nodes", [])
    raw_edges = data.get("edges", [])

    nodes = []
    used_ids = set()
    known_ids = {
        normalize_node_id(str(node_id))
        for node_id in (known_node_ids or [])
        if node_id
    }

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

    valid_ids = known_ids | {node["id"] for node in nodes}

    edges = []
    used_edges = set()

    for edge in raw_edges:
        source = normalize_node_id(str(edge.get("source", "")))
        target = normalize_node_id(str(edge.get("target", "")))

        relation = str(edge.get("relation", "")).strip()
        edge_key = (source, target, relation)

        if (
            source in valid_ids
            and target in valid_ids
            and source != target
            and edge_key not in used_edges
        ):
            used_edges.add(edge_key)
            edges.append({
                "source": source,
                "target": target,
                "relation": relation
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


def _row_value(row, key: str, default=""):
    try:
        value = row[key]
    except (KeyError, TypeError, IndexError):
        value = default

    return default if value is None else value


def _content_hash(payload: dict) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_mindmap_sources(messages, ideas=None) -> list[dict]:
    sources = []

    for message in messages or []:
        content = str(_row_value(message, "content", "")).strip()

        if not content:
            continue

        payload = {
            "chat_title": str(_row_value(message, "chat_title", "")).strip(),
            "message_type": str(_row_value(message, "type", "text")).strip(),
            "content": content,
        }
        sources.append({
            "source_type": "message",
            "source_id": int(_row_value(message, "id", 0)),
            "content_hash": _content_hash(payload),
            "payload": payload,
        })

    for idea in ideas or []:
        payload = {
            "title": str(_row_value(idea, "title", "")).strip(),
            "description": str(_row_value(idea, "description", "")).strip(),
            "evidence": str(_row_value(idea, "evidence", "")).strip(),
            "importance": str(_row_value(idea, "importance", "medium")).strip(),
        }

        if not any(payload[key] for key in ("title", "description", "evidence")):
            continue

        sources.append({
            "source_type": "idea",
            "source_id": int(_row_value(idea, "id", 0)),
            "content_hash": _content_hash(payload),
            "payload": payload,
        })

    return [source for source in sources if source["source_id"] > 0]


def get_pending_mindmap_sources(project_id: int, messages, ideas=None) -> list[dict]:
    states = {
        (state["source_type"], state["source_id"]): state["content_hash"]
        for state in get_mindmap_source_states(project_id)
    }

    return [
        source
        for source in build_mindmap_sources(messages, ideas)
        if states.get((source["source_type"], source["source_id"]))
        != source["content_hash"]
    ]


def get_pending_mindmap_signature(project_id: int, messages, ideas=None) -> str:
    pending_sources = get_pending_mindmap_sources(project_id, messages, ideas)

    if not pending_sources:
        return ""

    signature_parts = [
        f"{source['source_type']}:{source['source_id']}:{source['content_hash']}"
        for source in pending_sources
    ]
    return hashlib.sha256("|".join(signature_parts).encode("utf-8")).hexdigest()


def _format_incremental_sources(sources: list[dict]) -> str:
    formatted = []

    for source in sources:
        payload = source["payload"]

        if source["source_type"] == "message":
            formatted.append(
                "\n".join([
                    f"Sursă: notiță #{source['source_id']}",
                    f"Experiment: {payload['chat_title'] or 'Nespecificat'}",
                    f"Tip: {payload['message_type']}",
                    f"Conținut: {payload['content']}",
                ])
            )
        else:
            formatted.append(
                "\n".join([
                    f"Sursă: idee #{source['source_id']}",
                    f"Titlu: {payload['title']}",
                    f"Descriere: {payload['description']}",
                    f"Dovadă: {payload['evidence']}",
                    f"Importanță: {payload['importance']}",
                ])
            )

    return "\n\n---\n\n".join(formatted)


def _serialize_existing_mindmap(nodes, edges) -> dict:
    return {
        "nodes": [
            {
                "id": node["node_key"],
                "label": node["label"],
                "description": node["description"] or "",
                "importance": node["importance"] or "medium",
            }
            for node in nodes
        ],
        "edges": [
            {
                "source": edge["source_key"],
                "target": edge["target_key"],
                "relation": edge["relation"] or "",
            }
            for edge in edges
        ],
    }


def generate_mindmap_increment(
    project_name: str,
    new_sources: list[dict],
    existing_nodes,
    existing_edges,
) -> dict:
    ai = get_ai_provider()
    existing_mindmap = _serialize_existing_mindmap(
        existing_nodes,
        existing_edges,
    )
    existing_json = json.dumps(existing_mindmap, ensure_ascii=False, indent=2)
    new_information = _format_incremental_sources(new_sources)

    prompt = f"""
Ești un asistent AI care actualizează incremental un mindmap de cercetare.

Nume proiect:
{project_name}

Mindmap existent (trebuie păstrat):
{existing_json}

Informații noi sau modificate, încă neprocesate:
{new_information}

Returnează strict JSON cu DOAR diferența necesară:

{{
  "nodes": [
    {{
      "id": "id_scurt_fara_spatii",
      "label": "Nume nod",
      "description": "Descriere scurtă",
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

Reguli obligatorii:
- Nu returna din nou întregul mindmap.
- Nu șterge și nu redenumi nodurile existente.
- Refolosește exact ID-urile existente când informația aparține unui concept existent.
- Adaugă un nod nou numai pentru un concept cu adevărat nou.
- Poți returna un nod existent doar dacă descrierea sau importanța lui trebuie completată.
- Muchiile pot lega noduri noi de noduri existente.
- Nu duplica noduri sau relații deja prezente.
- Folosește numai informațiile noi furnizate; nu inventa date.
- Creează maximum 6 noduri noi pentru această actualizare.
- Dacă informația nouă este deja reprezentată complet, returnează liste goale.
- Returnează doar JSON valid, fără markdown.
"""

    data = ai.generate_json(prompt)
    known_ids = [node["node_key"] for node in existing_nodes]

    return normalize_mindmap_data(data, known_node_ids=known_ids)


def sync_project_mindmap(
    project_id: int,
    project_name: str,
    messages,
    ideas=None,
) -> dict:
    pending_sources = get_pending_mindmap_sources(project_id, messages, ideas)

    if not pending_sources:
        return {
            "status": "up_to_date",
            "sources_processed": 0,
            "nodes_changed": 0,
            "edges_changed": 0,
        }

    existing_nodes = get_mindmap_nodes(project_id)
    existing_edges = get_mindmap_edges(project_id)
    increment = generate_mindmap_increment(
        project_name=project_name,
        new_sources=pending_sources,
        existing_nodes=existing_nodes,
        existing_edges=existing_edges,
    )

    if not existing_nodes and not increment["nodes"]:
        raise ValueError("AI nu a generat niciun nod pentru informațiile proiectului.")

    merge_project_mindmap(
        project_id=project_id,
        mindmap_data=increment,
        processed_sources=pending_sources,
    )

    return {
        "status": "updated",
        "sources_processed": len(pending_sources),
        "nodes_changed": len(increment["nodes"]),
        "edges_changed": len(increment["edges"]),
    }
