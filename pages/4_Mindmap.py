import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config

from db.database import init_db
from db.queries import (
    get_projects,
    get_project_messages,
    get_project_ideas,
    clear_project_mindmap,
    save_project_mindmap,
    get_mindmap_nodes,
    get_mindmap_edges,
    get_mindmap_node_by_key
)
from services.mindmap_service import generate_mindmap_for_project
from services.chat_service import answer_question_about_node


init_db()

st.title("🧠 Interactive Mindmap")

st.write("""
Aici poți genera un mindmap interactiv pentru proiect.
După ce dai click pe un nod, se deschide un chat contextual despre acel nod.
""")

projects = get_projects()

if not projects:
    st.warning("Nu există proiecte. Creează mai întâi un proiect.")
    st.stop()

project_options = {
    f"{project['name']} — {project['domain']}": project
    for project in projects
}

selected_project_label = st.selectbox(
    "Alege proiectul",
    list(project_options.keys())
)

selected_project = project_options[selected_project_label]
selected_project_id = selected_project["id"]

project_messages = get_project_messages(selected_project_id)
project_ideas = get_project_ideas(selected_project_id)

st.divider()

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Date proiect")
    st.write(f"**Proiect:** {selected_project['name']}")
    st.write(f"**Domeniu:** {selected_project['domain']}")
    st.write(f"**Mesaje în proiect:** {len(project_messages)}")
    st.write(f"**Idei principale salvate:** {len(project_ideas)}")

with col2:
    st.subheader("Generare mindmap")

    st.write("""
    Mindmap-ul va fi generat pe baza notițelor din toate chat-urile proiectului
    și, dacă există, pe baza ideilor principale extrase anterior.
    """)

    if not project_messages:
        st.warning("Proiectul nu are încă notițe. Adaugă notițe înainte să generezi mindmap-ul.")
    else:
        if st.button("Generează / regenerează mindmap"):
            with st.spinner("Gemini generează mindmap-ul..."):
                mindmap_data = generate_mindmap_for_project(
                    project_name=selected_project["name"],
                    messages=project_messages,
                    ideas=project_ideas
                )

            clear_project_mindmap(selected_project_id)
            save_project_mindmap(selected_project_id, mindmap_data)

            if "selected_mindmap_node" in st.session_state:
                del st.session_state["selected_mindmap_node"]

            st.success("Mindmap-ul a fost generat și salvat.")
            st.rerun()

st.divider()

nodes_from_db = get_mindmap_nodes(selected_project_id)
edges_from_db = get_mindmap_edges(selected_project_id)

if not nodes_from_db:
    st.info("Nu există mindmap salvat pentru acest proiect. Apasă pe butonul de generare.")
    st.stop()

st.subheader("Mindmap interactiv")

graph_nodes = []

for node in nodes_from_db:
    importance = node["importance"] or "medium"

    size = 25

    if importance == "high":
        size = 40
    elif importance == "medium":
        size = 30
    elif importance == "low":
        size = 22

    graph_nodes.append(
        Node(
            id=node["node_key"],
            label=node["label"],
            title=node["description"] or "",
            size=size,
            font={
            "size": 18,
            "face": "Arial",
            "color": "#ffffff",
            "strokeWidth": 3,
            "strokeColor": "#000000"
            }
        )
    )

graph_edges = []

for edge in edges_from_db:
    graph_edges.append(
        Edge(
            source=edge["source_key"],
            target=edge["target_key"]
        )
    )

config = Config(
    width="100%",
    height=600,
    directed=True,
    physics=True,
    hierarchical=False
)

selected_node = agraph(
    nodes=graph_nodes,
    edges=graph_edges,
    config=config
)

selected_node_key = None

if selected_node:
    if isinstance(selected_node, str):
        selected_node_key = selected_node
    elif isinstance(selected_node, dict):
        selected_node_key = selected_node.get("id")

if selected_node_key:
    st.session_state["selected_mindmap_node"] = selected_node_key

st.divider()

if "selected_mindmap_node" not in st.session_state:
    st.info("Dă click pe un nod din mindmap ca să deschizi chat-ul contextual.")
    st.stop()

selected_node_key = st.session_state["selected_mindmap_node"]

selected_node_data = get_mindmap_node_by_key(
    project_id=selected_project_id,
    node_key=selected_node_key
)

if not selected_node_data:
    st.warning("Nodul selectat nu mai există. Regenerează mindmap-ul.")
    st.stop()

st.subheader(f"💬 Chat contextual: {selected_node_data['label']}")

if selected_node_data["description"]:
    st.write("**Descriere nod:**")
    st.write(selected_node_data["description"])

chat_session_key = f"node_chat_{selected_project_id}_{selected_node_key}"

if chat_session_key not in st.session_state:
    st.session_state[chat_session_key] = []

node_chat_history = st.session_state[chat_session_key]

if not node_chat_history:
    st.caption("Nu există încă întrebări pentru acest nod.")
else:
    for message in node_chat_history:
        with st.chat_message(message["role"]):
            st.write(message["content"])

with st.form(f"node_question_form_{selected_project_id}_{selected_node_key}"):
    user_question = st.text_area(
        "Întreabă ceva despre acest nod",
        placeholder="Ex: Ce observații avem despre acest compus? Ce probleme au apărut?",
        height=100
    )

    submitted_question = st.form_submit_button("Trimite întrebarea")

    if submitted_question:
        if not user_question.strip():
            st.error("Întrebarea nu poate fi goală.")
        else:
            st.session_state[chat_session_key].append({
                "role": "user",
                "content": user_question.strip()
            })

            with st.spinner("Gemini răspunde pe baza notițelor proiectului..."):
                answer = answer_question_about_node(
                    project_name=selected_project["name"],
                    node_label=selected_node_data["label"],
                    node_description=selected_node_data["description"] or "",
                    messages=project_messages,
                    user_question=user_question.strip(),
                    chat_history=st.session_state[chat_session_key]
                )

            st.session_state[chat_session_key].append({
                "role": "assistant",
                "content": answer
            })

            st.rerun()

if st.button("Șterge conversația pentru acest nod"):
    st.session_state[chat_session_key] = []
    st.rerun()