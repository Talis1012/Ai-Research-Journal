import os
from datetime import datetime, timedelta

import streamlit as st

from db.database import init_db
from db.queries import (
    add_message,
    add_experiment_ai_message,
    clear_experiment_ai_messages,
    create_audio_record,
    create_chat,
    delete_chat,
    delete_audio_record_by_message_id,
    delete_project_ideas,
    delete_message,
    get_audio_record_by_message_id,
    get_audio_records,
    get_audio_file_paths_by_chat,
    get_chats,
    get_chat_summaries,
    get_experiment_ai_messages,
    get_mindmap_edges,
    get_mindmap_last_sync,
    get_mindmap_nodes,
    get_messages,
    get_project_messages,
    get_projects,
    get_project_summaries,
    save_project_ideas,
    save_summary,
    update_audio_transcript_by_message_id,
    update_message_content,
)
from services.transcription_service import (
    delete_audio_file,
    save_audio_file,
    transcribe_audio,
)
from services.bibliography_service import generate_bibliography_search_profile
from services.chat_service import answer_question_about_experiment
from services.mindmap_service import (
    get_pending_mindmap_signature,
    sync_project_mindmap,
)
from services.openalex_service import search_works_for_queries
from services.summary_service import (
    SUMMARY_STYLE_STANDARD,
    generate_chat_summary,
    generate_project_summary,
    extract_project_ideas,
)
from utils.ui import (
    audio_visual_card,
    chat_message,
    compact_date,
    experiment_card,
    header_icons,
    load_css,
    render_html,
    render_mindmap_preview,
    safe_html,
    sidebar_nav,
    stat_card,
    top_brand,
)


st.set_page_config(
    page_title="Experiment Chat",
    page_icon="💬",
    layout="wide",
)

init_db()
load_css()


def safe_get_project_ideas(project_id: int):
    try:
        from db.queries import get_project_ideas

        return get_project_ideas(project_id)
    except Exception:
        return []


def date_group_label(value: str | None) -> str:
    if not value:
        return "Earlier"

    try:
        created = datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return "Earlier"

    today = datetime.now().date()

    if created == today:
        return "Today"

    if created == today - timedelta(days=1):
        return "Yesterday"

    return created.strftime("%b %-d, %Y")


def parse_created_at(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def chat_has_audio(chat_id: int, audio_counts_by_chat: dict[int, int]) -> bool:
    return audio_counts_by_chat.get(chat_id, 0) > 0


def chat_haystack(chat, messages_by_chat: dict[int, list]) -> str:
    parts = [
        chat["title"],
        chat["objective"] or "",
    ]

    for message in messages_by_chat.get(chat["id"], []):
        parts.append(message["content"])
        parts.append(message["type"])

    return " ".join(parts).lower()


def initials_for(message_type: str) -> str:
    if message_type == "audio_transcript":
        return "AU"
    return "AM"


projects = get_projects()

if not projects:
    st.warning("Nu exista proiecte. Creeaza mai intai un proiect in pagina Projects.")
    st.stop()


# =========================
# TOP HEADER
# =========================

top_brand_col, top_project_col, top_search_col, top_user_col = st.columns(
    [0.95, 1.55, 2.75, 1.65],
    gap="large",
)

with top_brand_col:
    top_brand()

project_options = {
    f"{project['name']}": project
    for project in projects
}

with top_project_col:
    render_html('<div class="top-project-scope"></div>')
    selected_project_label = st.selectbox(
        "Project",
        list(project_options.keys()),
        label_visibility="visible",
    )

with top_search_col:
    render_html('<div class="top-search-scope"></div>')
    search_across_project = st.text_input(
        "Search",
        placeholder="Search across your project...",
        key="project_global_search",
        label_visibility="collapsed",
    )

with top_user_col:
    render_html('<div class="top-user-scope"></div>')
    header_icons()


selected_project = project_options[selected_project_label]
selected_project_id = selected_project["id"]

chats = get_chats(selected_project_id)
project_messages = get_project_messages(selected_project_id)
project_ideas = safe_get_project_ideas(selected_project_id)
mindmap_sync_failure_signature_key = (
    f"mindmap_sync_failure_signature_{selected_project_id}"
)
mindmap_sync_failure_message_key = (
    f"mindmap_sync_failure_message_{selected_project_id}"
)
mindmap_sync_notice_key = f"mindmap_sync_notice_{selected_project_id}"

try:
    mindmap_sync_signature = get_pending_mindmap_signature(
        selected_project_id,
        project_messages,
        project_ideas,
    )
except Exception as exc:
    mindmap_sync_signature = ""
    st.session_state[mindmap_sync_failure_message_key] = str(exc)

chat_ids = [chat["id"] for chat in chats]
messages_by_chat: dict[int, list] = {}

for project_message in project_messages:
    messages_by_chat.setdefault(project_message["chat_id"], []).append(project_message)

audio_counts_by_chat = {
    chat_id: sum(1 for message in chat_messages if message["type"] == "audio_transcript")
    for chat_id, chat_messages in messages_by_chat.items()
}

requested_chat_id = None
requested_chat_value = st.query_params.get("chat_id")

if requested_chat_value:
    try:
        requested_chat_id = int(requested_chat_value)
    except ValueError:
        requested_chat_id = None

if "selected_chat_id" not in st.session_state:
    st.session_state["selected_chat_id"] = chats[0]["id"] if chats else None

if "show_new_chat_form" not in st.session_state:
    st.session_state["show_new_chat_form"] = False

if "experiment_date_filter" not in st.session_state:
    st.session_state["experiment_date_filter"] = "All"

if "experiment_type_filter" not in st.session_state:
    st.session_state["experiment_type_filter"] = "All"

if "experiment_sort_filter" not in st.session_state:
    st.session_state["experiment_sort_filter"] = "Newest first"

if requested_chat_id in chat_ids:
    st.session_state["selected_chat_id"] = requested_chat_id
elif chats and st.session_state["selected_chat_id"] not in chat_ids:
    st.session_state["selected_chat_id"] = chats[0]["id"]


# =========================
# MAIN DASHBOARD LAYOUT
# =========================

nav_col, experiments_col, chat_col, insight_col = st.columns(
    [1.05, 1.58, 2.58, 2.32],
    gap="small",
)

with nav_col:
    render_html('<div class="nav-panel-scope"></div>')
    sidebar_nav()

with experiments_col:
    render_html('<div class="work-panel-scope"></div>')
    title_col, new_col = st.columns([1, 0.36], gap="small")

    with title_col:
        render_html(
            '<div class="section-title" style="padding-top:8px;">Experiments / Chats</div>'
    )

    with new_col:
        if st.button("+ New", key="new_experiment_button", use_container_width=True):
            st.session_state["show_new_chat_form"] = not st.session_state["show_new_chat_form"]

    if st.session_state["show_new_chat_form"]:
        with st.form("create_chat_form_ui", clear_on_submit=True):
            new_title = st.text_input(
                "Titlu experiment",
                placeholder="Thiazole Derivative SAR Study",
            )
            new_objective = st.text_area(
                "Obiectiv experiment",
                placeholder="Descrie scopul experimentului...",
            )

            create_submitted = st.form_submit_button("Creeaza experiment")

            if create_submitted:
                if not new_title.strip():
                    st.error("Titlul experimentului este obligatoriu.")
                else:
                    chat_id = create_chat(
                        project_id=selected_project_id,
                        title=new_title.strip(),
                        objective=new_objective.strip(),
                    )
                    st.session_state["selected_chat_id"] = chat_id
                    st.session_state["show_new_chat_form"] = False
                    st.success("Experiment creat.")
                    st.rerun()

    search_col, filter_col = st.columns([1, 0.17], gap="small")

    with search_col:
        experiment_search = st.text_input(
            "Search experiments",
            placeholder="Search experiments...",
            key="experiment_search_input",
            label_visibility="collapsed",
        )

    with filter_col:
        active_filters = (
            st.session_state["experiment_date_filter"] != "All"
            or st.session_state["experiment_type_filter"] != "All"
            or st.session_state["experiment_sort_filter"] != "Newest first"
        )

        with st.container(key="experiment_filter_control"):
            with st.popover("⌯", use_container_width=True):
                st.selectbox(
                    "Date",
                    ["All", "Today", "Last 7 days", "Last 30 days"],
                    key="experiment_date_filter",
                )
                st.selectbox(
                    "Content",
                    ["All", "Has notes", "Has audio"],
                    key="experiment_type_filter",
                )
                st.selectbox(
                    "Sort",
                    ["Newest first", "Oldest first", "A-Z"],
                    key="experiment_sort_filter",
                )

        if active_filters:
            render_html('<div class="filter-status">Filters active</div>')

    filtered_chats = []
    now = datetime.now()

    for chat in chats:
        haystack = chat_haystack(chat, messages_by_chat)
        project_query = search_across_project.lower().strip()
        experiment_query = experiment_search.lower().strip()
        created_at = parse_created_at(chat["created_at"])

        if experiment_query and experiment_query not in haystack:
            continue

        if project_query and project_query not in haystack:
            continue

        date_filter = st.session_state["experiment_date_filter"]

        if date_filter == "Today" and (not created_at or created_at.date() != now.date()):
            continue

        if date_filter == "Last 7 days" and (not created_at or created_at < now - timedelta(days=7)):
            continue

        if date_filter == "Last 30 days" and (not created_at or created_at < now - timedelta(days=30)):
            continue

        type_filter = st.session_state["experiment_type_filter"]

        if type_filter == "Has notes" and not messages_by_chat.get(chat["id"]):
            continue

        if type_filter == "Has audio" and not chat_has_audio(chat["id"], audio_counts_by_chat):
            continue

        filtered_chats.append(chat)

    sort_filter = st.session_state["experiment_sort_filter"]

    if sort_filter == "Oldest first":
        filtered_chats = sorted(filtered_chats, key=lambda item: item["created_at"])
    elif sort_filter == "A-Z":
        filtered_chats = sorted(filtered_chats, key=lambda item: item["title"].lower())

    if not chats:
        st.info("Nu exista experimente pentru acest proiect.")
    elif not filtered_chats:
        st.info("Nu exista experimente care se potrivesc cautarii.")
    else:
        if search_across_project.strip():
            render_html(
                f'<div class="filter-status">{len(filtered_chats)} experiments match project search.</div>'
            )

        current_group = None

        for chat in filtered_chats:
            group_label = date_group_label(chat["created_at"])

            if group_label != current_group:
                current_group = group_label
                render_html(
                    f'<div class="date-label">{safe_html(group_label)}</div>'
    )

            is_selected = chat["id"] == st.session_state["selected_chat_id"]

            with st.container(key=f"experiment_item_{chat['id']}"):
                experiment_card(
                    title=chat["title"],
                    snippet=chat["objective"] or "No objective added yet.",
                    created_at=chat["created_at"],
                    selected=is_selected,
                    chat_id=chat["id"],
                )
                with st.popover("⋮"):
                    st.caption(chat["title"])
                    confirm_delete_experiment = st.checkbox(
                        "Confirm ștergerea",
                        key=f"confirm_delete_experiment_sidebar_{chat['id']}",
                    )

                    if st.button(
                        "Șterge experimentul",
                        key=f"delete_experiment_sidebar_{chat['id']}",
                        disabled=not confirm_delete_experiment,
                        use_container_width=True,
                    ):
                        audio_paths = get_audio_file_paths_by_chat(chat["id"])

                        for audio_path in audio_paths:
                            delete_audio_file(audio_path)

                        delete_chat(chat["id"])

                        if st.session_state.get("selected_chat_id") == chat["id"]:
                            remaining_chat_ids = [
                                candidate["id"]
                                for candidate in chats
                                if candidate["id"] != chat["id"]
                            ]
                            st.session_state["selected_chat_id"] = (
                                remaining_chat_ids[0]
                                if remaining_chat_ids
                                else None
                            )

                        st.success("Experimentul a fost șters.")
                        st.rerun()


if not chats:
    st.stop()

selected_chat_id = st.session_state["selected_chat_id"]
selected_chat = next((chat for chat in chats if chat["id"] == selected_chat_id), chats[0])

messages = get_messages(selected_chat["id"])
audio_records = get_audio_records(selected_chat["id"])
ai_messages = get_experiment_ai_messages(selected_chat["id"])
ai_response_count = sum(
    1
    for ai_message in ai_messages
    if ai_message["role"] == "assistant"
)
chat_summaries = get_chat_summaries(selected_chat["id"])
project_summaries = get_project_summaries(selected_project_id)
mindmap_nodes = get_mindmap_nodes(selected_project_id)
mindmap_edges = get_mindmap_edges(selected_project_id)

latest_update = compact_date(messages[-1]["created_at"]) if messages else "No notes yet"
latest_project_update = compact_date(project_messages[-1]["created_at"]) if project_messages else "No notes yet"
latest_ideas_update = compact_date(project_ideas[0]["created_at"]) if project_ideas else "No ideas yet"
latest_transcript = ""

for message in reversed(messages):
    if message["type"] == "audio_transcript":
        latest_transcript = message["content"]
        break


with chat_col:
    render_html('<div class="center-panel-scope"></div>')
    render_html(
        f"""
        <div class="chat-header">
            <div class="chat-title-row">
                <div class="chat-title">{safe_html(selected_chat['title'])}</div>
            </div>
        </div>
        """
    )

    notes_tab, chat_tab = st.tabs(["Notes", "Chat"])

    with chat_tab:
        st.caption("Discută cu Gemini despre notițele existente în acest experiment.")

        with st.container(height=460, border=True):
            if not ai_messages:
                st.info("Nu există încă o conversație AI pentru acest experiment.")
            else:
                for ai_message in ai_messages:
                    with st.chat_message(ai_message["role"]):
                        st.markdown(ai_message["content"])
                        st.caption(compact_date(ai_message["created_at"]))

        with st.form("experiment_ai_chat_form", clear_on_submit=True):
            user_question = st.text_area(
                "Întreabă Gemini despre notițele experimentului",
                placeholder="Ex: Ce concluzii pot trage din notițele actuale? Ce lipsește?",
                height=90,
                label_visibility="collapsed",
            )

            ask_submitted = st.form_submit_button("Trimite către Gemini")

            if ask_submitted:
                if not user_question.strip():
                    st.error("Întrebarea nu poate fi goală.")
                elif not messages:
                    st.error("Adaugă mai întâi notițe în tabul Notes. Chat-ul AI răspunde doar pe baza lor.")
                else:
                    question = user_question.strip()
                    add_experiment_ai_message(
                        chat_id=selected_chat["id"],
                        role="user",
                        content=question,
                    )

                    history_for_ai = [
                        {
                            "role": row["role"],
                            "content": row["content"],
                        }
                        for row in ai_messages
                    ]
                    history_for_ai.append({"role": "user", "content": question})

                    with st.spinner("Gemini analizează notițele experimentului..."):
                        try:
                            answer = answer_question_about_experiment(
                                project_name=selected_project["name"],
                                chat_title=selected_chat["title"],
                                chat_objective=selected_chat["objective"] or "",
                                notes=messages,
                                user_question=question,
                                chat_history=history_for_ai,
                            )
                        except Exception as exc:
                            answer = f"Nu am putut obține răspuns de la AI: {exc}"

                    add_experiment_ai_message(
                        chat_id=selected_chat["id"],
                        role="assistant",
                        content=answer,
                    )
                    st.rerun()

        if ai_messages:
            if st.button("Șterge conversația AI pentru experiment", use_container_width=True):
                clear_experiment_ai_messages(selected_chat["id"])
                st.rerun()

    with notes_tab:
        st.caption("Notițele experimentului: text, transcrieri audio și observații salvate.")

        with st.container(height=460, border=True):
            if not messages:
                st.info("Nu există încă notițe pentru acest experiment.")
            else:
                for message in messages:
                    label = "Transcriere audio" if message["type"] == "audio_transcript" else "Notiță"
                    chat_message(
                        author=label,
                        initials=initials_for(message["type"]),
                        created_at=message["created_at"],
                        content=message["content"],
                    )

                    if message["type"] == "text":
                        with st.expander("Modifică / șterge notița"):
                            with st.form(f"edit_text_note_form_{message['id']}"):
                                edited_note = st.text_area(
                                    "Notiță modificată",
                                    value=message["content"],
                                    height=120,
                                    key=f"edited_note_{message['id']}",
                                )

                                save_edit = st.form_submit_button("Salvează modificarea")

                                if save_edit:
                                    if not edited_note.strip():
                                        st.error("Notița nu poate fi goală.")
                                    else:
                                        update_message_content(
                                            message_id=message["id"],
                                            new_content=edited_note.strip(),
                                        )
                                        st.success("Notița a fost actualizată.")
                                        st.rerun()

                            confirm_delete_note = st.checkbox(
                                "Confirm ștergerea acestei notițe",
                                key=f"confirm_delete_note_{message['id']}",
                            )

                            if st.button(
                                "Șterge notița",
                                key=f"delete_text_note_{message['id']}",
                                disabled=not confirm_delete_note,
                            ):
                                delete_message(message["id"])
                                st.success("Notița a fost ștearsă.")
                                st.rerun()

                    if message["type"] == "audio_transcript":
                        with st.expander("Corectează / șterge transcrierea"):
                            with st.form(f"edit_audio_transcript_form_{message['id']}"):
                                edited_transcript = st.text_area(
                                    "Transcriere corectată",
                                    value=message["content"],
                                    height=120,
                                    key=f"edited_transcript_{message['id']}",
                                )

                                save_audio_edit = st.form_submit_button("Salvează corectarea")

                                if save_audio_edit:
                                    if not edited_transcript.strip():
                                        st.error("Transcrierea nu poate fi goală.")
                                    else:
                                        update_message_content(
                                            message_id=message["id"],
                                            new_content=edited_transcript.strip(),
                                        )

                                        update_audio_transcript_by_message_id(
                                            message_id=message["id"],
                                            new_transcript=edited_transcript.strip(),
                                        )

                                        st.success("Transcrierea a fost actualizată.")
                                        st.rerun()

                            confirm_delete_audio = st.checkbox(
                                "Confirm ștergerea acestei transcrieri audio",
                                key=f"confirm_delete_audio_{message['id']}",
                            )

                            if st.button(
                                "Șterge transcrierea audio",
                                key=f"delete_audio_{message['id']}",
                                disabled=not confirm_delete_audio,
                            ):
                                audio_record = get_audio_record_by_message_id(message["id"])

                                if audio_record:
                                    delete_audio_file(audio_record["file_path"])
                                    delete_audio_record_by_message_id(message["id"])

                                delete_message(message["id"])
                                st.success("Transcrierea audio a fost ștearsă.")
                                st.rerun()

        with st.form("add_text_note_form", clear_on_submit=True):
            note = st.text_area(
                "Scrie o notiță nouă",
                placeholder="Ex: Am observat că soluția și-a schimbat culoarea după încălzire...",
                height=90,
                label_visibility="collapsed",
            )

            submitted_note = st.form_submit_button("Salvează notița")

            if submitted_note:
                if not note.strip():
                    st.error("Notița nu poate fi goală.")
                else:
                    add_message(
                        chat_id=selected_chat["id"],
                        role="user",
                        message_type="text",
                        content=note.strip(),
                    )
                    st.success("Notița a fost salvată.")
                    st.rerun()

        if latest_transcript:
            audio_visual_card(latest_transcript)

        with st.container(border=True):
            if not latest_transcript:
                render_html(
                    """
                    <div class="audio-card" style="margin-top:0;">
                        <div class="audio-head">
                            <div class="audio-title">Audio Recording &amp; Transcription <span style="color:#8a95a8;">ⓘ</span></div>
                            <div class="audio-clock">Ready</div>
                        </div>
                        <div class="wave-wrap">
                            <div class="stop-circle">■</div>
                            <div class="waveform"></div>
                        </div>
                        <div class="transcript-preview">Înregistrează o observație audio, apoi salveaz-o ca transcriere în Notes.</div>
                    </div>
                    """
                )

            language_option = st.selectbox(
                "Limba transcrierii",
                ["auto", "ro", "en"],
                help="Alege auto pentru detectare automată, ro pentru română, en pentru engleză.",
            )

            audio_file = st.audio_input("Înregistrează observația audio")

            if audio_file is not None:
                st.audio(audio_file)

                if st.button("Salvează audio și transcrie"):
                    with st.spinner("Se salvează fișierul audio..."):
                        audio_path = save_audio_file(audio_file, selected_chat["id"])

                    selected_language = None if language_option == "auto" else language_option

                    with st.spinner("Se transcrie audio-ul local..."):
                        transcript = transcribe_audio(
                            audio_path=audio_path,
                            language=selected_language,
                        )

                    if not transcript:
                        st.error("Nu s-a putut obține o transcriere.")
                    else:
                        message_id = add_message(
                            chat_id=selected_chat["id"],
                            role="user",
                            message_type="audio_transcript",
                            content=transcript,
                        )

                        create_audio_record(
                            chat_id=selected_chat["id"],
                            message_id=message_id,
                            file_path=audio_path,
                            transcript=transcript,
                        )

                        st.success("Audio-ul a fost salvat, transcris și adăugat în notițe.")
                        st.rerun()

        if audio_records:
            with st.expander("Fișiere audio salvate"):
                for record in audio_records[-3:]:
                    st.caption(record["created_at"])

                    if os.path.exists(record["file_path"]):
                        st.audio(record["file_path"])
                    else:
                        st.warning("Fișierul audio nu mai există pe disc.")

                    if record["transcript"]:
                        st.write(record["transcript"])


with insight_col:
    render_html('<div class="right-panel-scope"></div>')
    metric_a, metric_b, metric_c = st.columns(3, gap="small")

    with metric_a:
        stat_card(
            title="Chat Summary",
            value=str(ai_response_count),
            subtitle="AI responses",
            icon="▣",
            tone="blue",
            updated=f"Last updated {latest_update}",
        )

    with metric_b:
        stat_card(
            title="Project Summary",
            value=str(len(chats)),
            subtitle="Experiments",
            icon="▥",
            tone="green",
            updated=f"Last note {latest_project_update}",
        )

    with metric_c:
        stat_card(
            title="Key Ideas",
            value=str(len(project_ideas)),
            subtitle="Insights",
            icon="♙",
            tone="purple",
            updated=f"Last updated {latest_ideas_update}",
        )

    with st.container(border=True):
        st.subheader("Chat Summary")

        if chat_summaries:
            st.caption(f"Ultimul rezumat salvat: {chat_summaries[0]['created_at']}")
            with st.expander("Vezi rezumatul chat-ului", expanded=False):
                st.markdown(chat_summaries[0]["content"])
        else:
            st.caption("Nu există încă rezumat salvat pentru acest experiment.")

        if st.button("Generează rezumat chat", use_container_width=True):
            if not messages:
                st.error("Nu există notițe de rezumat.")
            else:
                with st.spinner("Gemini generează rezumatul experimentului..."):
                    try:
                        summary = generate_chat_summary(
                            chat_title=selected_chat["title"],
                            messages=messages,
                            summary_style=SUMMARY_STYLE_STANDARD,
                        )
                        save_summary(
                            scope="chat",
                            project_id=selected_project_id,
                            chat_id=selected_chat["id"],
                            content=summary,
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Nu am putut genera rezumatul: {exc}")

    with st.container(border=True):
        st.subheader("Project Summary")

        if project_summaries:
            st.caption(f"Ultimul rezumat salvat: {project_summaries[0]['created_at']}")
            with st.expander("Vezi rezumatul proiectului", expanded=False):
                st.markdown(project_summaries[0]["content"])
        else:
            st.caption("Nu există încă rezumat salvat pentru proiect.")

        if st.button("Generează rezumat proiect", use_container_width=True):
            if not project_messages:
                st.error("Proiectul nu are încă notițe.")
            else:
                with st.spinner("Gemini generează rezumatul proiectului..."):
                    try:
                        summary = generate_project_summary(
                            project_name=selected_project["name"],
                            messages=project_messages,
                            summary_style=SUMMARY_STYLE_STANDARD,
                        )
                        save_summary(
                            scope="project",
                            project_id=selected_project_id,
                            chat_id=None,
                            content=summary,
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Nu am putut genera rezumatul proiectului: {exc}")

    with st.container(border=True):
        st.subheader("Key Ideas")

        if project_ideas:
            for idea in project_ideas[:4]:
                st.markdown(f"**{idea['title']}**")
                st.caption(idea["description"])
        else:
            st.caption("Nu există încă idei extrase pentru proiect.")

        if st.button("Extrage idei principale", use_container_width=True):
            if not project_messages:
                st.error("Proiectul nu are încă notițe.")
            else:
                with st.spinner("Gemini extrage ideile principale..."):
                    try:
                        ideas = extract_project_ideas(
                            project_name=selected_project["name"],
                            messages=project_messages,
                        )
                        delete_project_ideas(selected_project_id)
                        save_project_ideas(selected_project_id, ideas)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Nu am putut extrage ideile: {exc}")

    with st.container(border=True):
        head_left, head_right = st.columns([1, 0.56], gap="small")

        with head_left:
            st.subheader("Mindmap Preview")

        with head_right:
            st.page_link("pages/4_Mindmap.py", label="Open Mindmap")

        if mindmap_nodes:
            render_mindmap_preview(mindmap_nodes, mindmap_edges)
            last_mindmap_sync = get_mindmap_last_sync(selected_project_id)
            sync_meta = "actualizare incrementală automată"

            if last_mindmap_sync:
                sync_meta = f"actualizat {compact_date(last_mindmap_sync)}"

            st.caption(
                f"{len(mindmap_nodes)} noduri · {len(mindmap_edges)} legături · "
                f"{sync_meta}"
            )
        else:
            st.info(
                "Mindmap-ul va fi creat automat după ce adaugi prima notiță."
            )

        mindmap_sync_notice = st.session_state.pop(mindmap_sync_notice_key, None)

        if mindmap_sync_notice:
            st.success(
                "Mindmap actualizat automat din "
                f"{mindmap_sync_notice['sources_processed']} informații noi; "
                "nodurile existente au fost păstrate."
            )

        mindmap_sync_error = st.session_state.get(
            mindmap_sync_failure_message_key
        )

        if mindmap_sync_error:
            st.warning(
                "Actualizarea automată a mindmap-ului nu a reușit: "
                f"{mindmap_sync_error}"
            )

            if st.button(
                "Reîncearcă actualizarea incrementală",
                key=f"retry_mindmap_sync_{selected_project_id}",
                use_container_width=True,
            ):
                st.session_state.pop(mindmap_sync_failure_signature_key, None)
                st.session_state.pop(mindmap_sync_failure_message_key, None)
                st.rerun()

    with st.container(border=True):
        top_lit, top_link = st.columns([1, 0.4], gap="small")

        with top_lit:
            st.subheader("Literature Recommendations")

        with top_link:
            st.page_link("pages/5_Bibliography_Search.py", label="View all")

        literature_key = f"literature_recommendations_{selected_project_id}"
        literature_results = st.session_state.get(literature_key, [])

        if literature_results:
            for work in literature_results[:2]:
                with st.container(border=True):
                    title = work.get("title") or "Untitled work"
                    st.markdown(f"**{title}**")
                    meta = []

                    if work.get("source_name"):
                        meta.append(work["source_name"])

                    if work.get("publication_year"):
                        meta.append(str(work["publication_year"]))

                    if meta:
                        st.caption(" · ".join(meta))

                    if work.get("authors"):
                        st.caption(work["authors"])

                    if work.get("url"):
                        st.link_button("Deschide lucrarea", work["url"])
        else:
            st.caption("Nu există recomandări generate în această sesiune.")

        if st.button("Generează recomandări literatură", use_container_width=True):
            if not project_messages:
                st.error("Proiectul nu are încă notițe.")
            else:
                with st.spinner("Gemini generează query-uri și caută în OpenAlex..."):
                    try:
                        profile = generate_bibliography_search_profile(
                            project_name=selected_project["name"],
                            project_domain=selected_project["domain"],
                            messages=project_messages,
                            ideas=project_ideas,
                        )
                        queries = profile.get("search_queries", [])[:3]
                        results = search_works_for_queries(
                            queries=queries,
                            per_page=3,
                        )
                        st.session_state[literature_key] = results
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Nu am putut genera recomandări: {exc}")


# Rulează sincronizarea costisitoare numai după ce întreaga pagină a fost
# randată. Astfel, un răspuns lent sau o eroare Gemini nu mai poate lăsa
# Experiment Chat blocat după antet.
if (
    mindmap_sync_signature
    and st.session_state.get(mindmap_sync_failure_signature_key)
    != mindmap_sync_signature
):
    try:
        sync_result = sync_project_mindmap(
            project_id=selected_project_id,
            project_name=selected_project["name"],
            messages=project_messages,
            ideas=project_ideas,
        )
        st.session_state.pop(mindmap_sync_failure_signature_key, None)
        st.session_state.pop(mindmap_sync_failure_message_key, None)

        if sync_result["status"] == "updated":
            st.session_state[mindmap_sync_notice_key] = sync_result
    except Exception as exc:
        st.session_state[mindmap_sync_failure_signature_key] = (
            mindmap_sync_signature
        )
        st.session_state[mindmap_sync_failure_message_key] = str(exc)

    st.rerun()
