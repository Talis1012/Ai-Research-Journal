import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config

from db.database import init_db
from db.queries import (
    get_projects,
    get_project_messages,
    get_project_ideas,
    get_mindmap_nodes,
    get_mindmap_edges,
    get_mindmap_last_sync,
    get_mindmap_node_by_key
)
from services.mindmap_service import (
    get_pending_mindmap_signature,
    sync_project_mindmap,
)
from services.chat_service import answer_question_about_node
from utils.ui import load_css, page_brand_header, sidebar_nav



init_db()
load_css()
page_brand_header()

nav_col, main_col = st.columns([1.05, 5.3], gap="small")

with nav_col:
    sidebar_nav("mindmap")

with main_col:

    st.title("🧠 Interactive Mindmap")

    st.write("""
    Mindmap-ul proiectului se actualizează automat și incremental.
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
    mindmap_sync_failure_signature_key = (
        f"mindmap_sync_failure_signature_{selected_project_id}"
    )
    mindmap_sync_failure_message_key = (
        f"mindmap_sync_failure_message_{selected_project_id}"
    )

    try:
        mindmap_sync_signature = get_pending_mindmap_signature(
            selected_project_id,
            project_messages,
            project_ideas,
        )
    except Exception as exc:
        mindmap_sync_signature = ""
        st.session_state[mindmap_sync_failure_message_key] = str(exc)

    st.divider()

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Date proiect")
        st.write(f"**Proiect:** {selected_project['name']}")
        st.write(f"**Domeniu:** {selected_project['domain']}")
        st.write(f"**Mesaje în proiect:** {len(project_messages)}")
        st.write(f"**Idei principale salvate:** {len(project_ideas)}")

    with col2:
        st.subheader("Actualizare mindmap")

        st.write("""
        Mindmap-ul se actualizează automat din notițele și ideile noi.
        Nodurile și legăturile deja salvate sunt păstrate.
        """)

        if not project_messages:
            st.warning("Proiectul nu are încă notițe.")
        else:
            last_mindmap_sync = get_mindmap_last_sync(selected_project_id)

            if last_mindmap_sync:
                st.success(
                    f"Sincronizat automat: {last_mindmap_sync}."
                )
            else:
                st.caption("Prima sincronizare se face automat.")

        mindmap_sync_error = st.session_state.get(
            mindmap_sync_failure_message_key
        )

        if mindmap_sync_error:
            st.warning(
                "Actualizarea automată nu a reușit: "
                f"{mindmap_sync_error}"
            )

            if st.button(
                "Reîncearcă actualizarea incrementală",
                key=f"retry_full_mindmap_sync_{selected_project_id}",
            ):
                st.session_state.pop(mindmap_sync_failure_signature_key, None)
                st.session_state.pop(mindmap_sync_failure_message_key, None)
                st.rerun()

    st.divider()

    # Sincronizarea AI pornește după ce antetul și informațiile proiectului
    # sunt deja vizibile, ca un apel lent să nu lase pagina goală.
    if (
        mindmap_sync_signature
        and st.session_state.get(mindmap_sync_failure_signature_key)
        != mindmap_sync_signature
    ):
        try:
            sync_project_mindmap(
                project_id=selected_project_id,
                project_name=selected_project["name"],
                messages=project_messages,
                ideas=project_ideas,
            )
            st.session_state.pop(mindmap_sync_failure_signature_key, None)
            st.session_state.pop(mindmap_sync_failure_message_key, None)
        except Exception as exc:
            st.session_state[mindmap_sync_failure_signature_key] = (
                mindmap_sync_signature
            )
            st.session_state[mindmap_sync_failure_message_key] = str(exc)

        st.rerun()

    nodes_from_db = get_mindmap_nodes(selected_project_id)
    edges_from_db = get_mindmap_edges(selected_project_id)

    if not nodes_from_db:
        st.info("Mindmap-ul va apărea automat după procesarea primei notițe.")
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
                "size": 19,
                "face": "Inter",
                "color": "#111827",
                "strokeWidth": 3,
                "strokeColor": "#ffffff"
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
        st.warning("Nodul selectat nu mai există. Reîncearcă actualizarea mindmap-ului.")
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
