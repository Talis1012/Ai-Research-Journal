import os
from datetime import datetime, timedelta

import streamlit as st
from streamlit_agraph import agraph, Config, Edge, Node

from db.database import init_db_once
from db.queries import (
    add_experiment_ai_message,
    add_message,
    clear_experiment_ai_messages,
    create_audio_record,
    create_chat,
    create_project,
    delete_audio_record_by_message_id,
    delete_chat,
    delete_message,
    delete_project,
    delete_project_ideas,
    get_audio_record_by_message_id,
    get_audio_records,
    get_all_project_summaries,
    get_chat_summary,
    get_experiment_ai_messages,
    get_messages,
    get_mindmap_edges,
    get_mindmap_last_sync,
    get_mindmap_node_by_key,
    get_mindmap_nodes,
    get_project_workspace,
    get_project_summary,
    get_projects,
    save_project_ideas,
    save_summary,
    update_audio_transcript_by_message_id,
    update_message_content,
    update_project_idea,
    update_summary,
)
from services.chat_service import (
    answer_question_about_experiment,
    answer_question_about_node,
    answer_question_about_project,
)
from services.mindmap_service import (
    get_pending_mindmap_signature,
    sync_project_mindmap,
)
from services.summary_service import (
    SUMMARY_STYLE_CUSTOM,
    SUMMARY_STYLE_OPTIONS,
    SUMMARY_STYLE_STANDARD,
    extract_project_ideas,
    generate_chat_summary,
    generate_project_summary,
)
from services.transcription_service import (
    audio_preview_source,
    delete_audio_file,
    save_audio_file,
    transcribe_audio,
)
from utils.auth import authenticated_callback, require_auth
from utils.query_cache import cached_read
from utils.ui import (
    chat_message,
    compact_date,
    experiment_card,
    header_icons,
    load_css,
    render_html,
    render_due_reminder_notifications,
    render_untrusted_caption,
    render_untrusted_markdown,
    safe_html,
    sidebar_nav,
    top_brand,
)


st.set_page_config(
    page_title="Experiments · Research Journal AI",
    page_icon="🧪",
    layout="wide",
)

require_auth()
init_db_once(st.session_state)
load_css()
render_due_reminder_notifications()


def parse_created_at(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def date_group_label(value: str | None) -> str:
    created_at = parse_created_at(value)

    if not created_at:
        return "Earlier"

    today = datetime.now().date()

    if created_at.date() == today:
        return "Today"

    if created_at.date() == today - timedelta(days=1):
        return "Yesterday"

    return created_at.strftime("%b %-d, %Y")


def message_initials(message_type: str) -> str:
    return "AU" if message_type == "audio_transcript" else "AM"


def chat_haystack(chat, messages_by_chat: dict[int, list]) -> str:
    values = [chat["title"], chat["objective"] or ""]
    values.extend(
        message["content"]
        for message in messages_by_chat.get(chat["id"], [])
    )
    return " ".join(values).lower()


def render_page_css():
    render_html(
        """
        <style>
        .experiments-page-scope,
        .experiments-list-scope,
        .experiment-content-scope,
        .experiment-ai-chat-scope,
        .insight-main-scope,
        .insight-side-scope {
            display: none;
        }

        div[data-testid="column"]:has(.experiments-page-scope) {
            min-height: calc(100vh - var(--topbar-h));
            padding: 24px 28px 36px !important;
            background: #ffffff;
        }

        div[data-testid="column"]:has(.experiments-page-scope)
        > div[data-testid="stVerticalBlock"] {
            gap: 0.72rem;
        }

        .experiments-heading {
            font-size: 1.85rem;
            font-weight: 880;
            color: #101828;
            line-height: 1.08;
            padding-top: 13px;
        }

        .experiments-subtitle {
            margin-top: 7px;
            color: #667085;
            font-size: 0.94rem;
        }

        .eyebrow {
            color: #1769d2;
            font-size: 0.72rem;
            font-weight: 850;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 5px;
        }

        .panel-title {
            color: #101828;
            font-size: 1rem;
            font-weight: 850;
            line-height: 1.25;
        }

        .panel-subtitle {
            color: #667085;
            font-size: 0.78rem;
            line-height: 1.45;
            margin-top: 4px;
        }

        div[data-testid="column"]:has(.experiments-list-scope),
        div[data-testid="column"]:has(.experiment-content-scope),
        div[data-testid="column"]:has(.experiment-ai-chat-scope),
        div[data-testid="column"]:has(.insight-main-scope),
        div[data-testid="column"]:has(.insight-side-scope) {
            border: 1px solid #dfe6ef;
            border-radius: 9px;
            background: #ffffff;
            box-shadow: var(--shadow);
            padding: 18px !important;
        }

        div[data-testid="column"]:has(.experiments-list-scope),
        div[data-testid="column"]:has(.experiment-content-scope),
        div[data-testid="column"]:has(.experiment-ai-chat-scope) {
            min-height: 760px;
        }

        div[data-testid="column"]:has(.experiments-list-scope)
        > div[data-testid="stVerticalBlock"],
        div[data-testid="column"]:has(.experiment-content-scope)
        > div[data-testid="stVerticalBlock"],
        div[data-testid="column"]:has(.experiment-ai-chat-scope)
        > div[data-testid="stVerticalBlock"],
        div[data-testid="column"]:has(.insight-main-scope)
        > div[data-testid="stVerticalBlock"],
        div[data-testid="column"]:has(.insight-side-scope)
        > div[data-testid="stVerticalBlock"] {
            gap: 0.72rem;
        }

        .empty-state {
            border: 1px dashed #cbd7e6;
            border-radius: 9px;
            background: #f8fbff;
            padding: 32px 22px;
            text-align: center;
            color: #667085;
            font-size: 0.86rem;
            line-height: 1.55;
        }

        .empty-state strong {
            display: block;
            color: #101828;
            font-size: 1rem;
            margin-bottom: 6px;
        }

        .insights-info-banner {
            border: 1px solid #cfe0f7;
            border-radius: 8px;
            background: #f5f9ff;
            color: #526078;
            padding: 12px 15px;
            font-size: 0.78rem;
            font-weight: 690;
            line-height: 1.45;
            margin-bottom: 4px;
        }

        .insight-reader-heading {
            color: #101828;
            font-size: 1rem;
            font-weight: 850;
            line-height: 1.25;
        }

        .insight-reader-context {
            color: #667085;
            font-size: 0.72rem;
            margin: 4px 0 9px;
        }

        div[class*="st-key-insight_selector_"] button {
            height: 96px !important;
            min-height: 96px !important;
            border-radius: 9px !important;
            padding: 10px 7px !important;
            font-size: 0.77rem !important;
            line-height: 1.3 !important;
        }

        div[class*="st-key-insight_selector_"] button p {
            white-space: pre-line !important;
            text-align: center !important;
        }

        div[class*="st-key-compact_mindmap_"] button,
        div[class*="st-key-expand_mindmap_"] button {
            min-height: 36px !important;
            height: 36px !important;
            padding: 0 !important;
            font-size: 1rem !important;
        }

        .project-ai-title {
            color: #101828;
            font-size: 1.08rem;
            font-weight: 870;
            line-height: 1.2;
        }

        .project-ai-subtitle {
            color: #667085;
            font-size: 0.75rem;
            line-height: 1.5;
            margin: 6px 0 10px;
        }

        div[class*="st-key-project_delete_control"],
        div[class*="st-key-new_project_control"] {
            margin-top: 15px !important;
        }

        div[class*="st-key-project_delete_control"] div[data-testid="stPopover"] > button,
        div[class*="st-key-new_project_control"] div[data-testid="stPopover"] > button {
            min-height: 40px !important;
            height: 40px !important;
            padding: 0 10px !important;
            border-radius: 7px !important;
            font-size: 0.76rem !important;
            font-weight: 820 !important;
            white-space: nowrap !important;
        }

        div[class*="st-key-project_delete_control"] div[data-testid="stPopover"] > button {
            color: #b42318 !important;
            border-color: #f0c7c3 !important;
            background: #fffafa !important;
        }

        div[class*="st-key-new_project_control"] div[data-testid="stPopover"] > button {
            color: #0d65d9 !important;
            border-color: #bfd5f2 !important;
            background: #f7fbff !important;
        }

        div[class*="st-key-project_ai_suggestion_"] button {
            min-height: 54px !important;
            height: 54px !important;
            padding: 7px !important;
            font-size: 0.7rem !important;
            line-height: 1.3 !important;
            white-space: normal !important;
        }

        div[class*="st-key-experiment_new_note_"] textarea {
            height: 76px !important;
            min-height: 76px !important;
            max-height: 76px !important;
            overflow-y: auto !important;
            resize: none !important;
        }

        .audio-section-title {
            color: #101828;
            font-size: 0.92rem;
            font-weight: 850;
            line-height: 1.3;
        }

        .audio-section-subtitle {
            color: #667085;
            font-size: 0.75rem;
            line-height: 1.45;
            margin: 4px 0 8px;
        }

        div[data-testid="column"]:has(.experiments-page-scope)
        div[data-testid="stTabs"] button {
            font-weight: 780 !important;
            color: #526078 !important;
        }

        div[data-testid="column"]:has(.experiments-page-scope)
        div[data-testid="stTabs"] button[aria-selected="true"] {
            color: #0d65d9 !important;
        }

        @media (max-width: 1100px) {
            div[data-testid="column"]:has(.experiments-list-scope),
            div[data-testid="column"]:has(.experiment-content-scope),
            div[data-testid="column"]:has(.experiment-ai-chat-scope) {
                min-height: auto;
            }
        }
        </style>
        """
    )


def render_create_project_form(*, key: str):
    with st.form(key, clear_on_submit=True):
        name = st.text_input(
            "Project name",
            placeholder="CM-02 Formulation Study",
            key=f"{key}_name",
        )
        domain = st.text_input(
            "Domain",
            placeholder="Medicinal Chemistry",
            key=f"{key}_domain",
        )
        description = st.text_area(
            "Description",
            placeholder="What is the general research objective?",
            key=f"{key}_description",
        )
        submitted = st.form_submit_button("Create project", width="stretch")

        if submitted:
            if not name.strip() or not domain.strip():
                st.error("Project name and domain are required.")
            else:
                project_id = create_project(
                    name=name.strip(),
                    domain=domain.strip(),
                    description=description.strip(),
                )
                st.session_state["experiments_pending_project_id"] = project_id
                st.session_state["selected_chat_id"] = None
                st.success("Project created.")
                st.rerun()


def render_delete_project_control(selected_project, projects):
    with st.popover("🗑", width="stretch"):
        render_untrusted_markdown(f"**Delete {selected_project['name']}?**")
        st.caption(
            "This permanently deletes every experiment, note, AI conversation, "
            "summary, key idea, mind map node, and audio recording in the project."
        )
        confirm_delete = st.checkbox(
            "I understand and want to delete this project",
            key=f"confirm_delete_project_header_{selected_project['id']}",
        )

        if st.button(
            "Delete project",
            key=f"delete_project_header_{selected_project['id']}",
            disabled=not confirm_delete,
            type="primary",
            width="stretch",
        ):
            delete_project(selected_project["id"])
            remaining_project_ids = [
                project["id"]
                for project in projects
                if project["id"] != selected_project["id"]
            ]
            st.session_state["experiments_pending_project_id"] = (
                remaining_project_ids[0]
                if remaining_project_ids
                else None
            )
            st.session_state["selected_chat_id"] = None
            st.query_params.clear()
            st.rerun()


@st.fragment
@authenticated_callback
def render_experiment_list(
    selected_project,
    search_across_project: str,
):
    chats, project_messages, _ = cached_read(
        get_project_workspace,
        selected_project["id"],
    )
    render_html('<div class="experiments-list-scope"></div>')
    heading_col, action_col = st.columns([1, 0.48], gap="small")

    with heading_col:
        render_html(
            """
            <div class="panel-title">Experiments</div>
            <div class="panel-subtitle">Research runs in this project</div>
            """
        )

    with action_col:
        with st.popover("+ New", width="stretch"):
            with st.form("create_experiment_form", clear_on_submit=True):
                title = st.text_input(
                    "Experiment title",
                    placeholder="CM-01 stability at pH 7.4",
                )
                objective = st.text_area(
                    "Objective",
                    placeholder="What should this experiment determine?",
                )
                submitted = st.form_submit_button(
                    "Create experiment",
                    width="stretch",
                )

                if submitted:
                    if not title.strip():
                        st.error("Experiment title is required.")
                    else:
                        chat_id = create_chat(
                            project_id=selected_project["id"],
                            title=title.strip(),
                            objective=objective.strip(),
                        )
                        st.session_state["selected_chat_id"] = chat_id
                        st.success("Experiment created.")
                        st.rerun()

    experiment_search = st.text_input(
        "Search experiments",
        placeholder="Search experiments...",
        label_visibility="collapsed",
        key="experiments_local_search",
    )

    messages_by_chat: dict[int, list] = {}

    for message in project_messages:
        messages_by_chat.setdefault(message["chat_id"], []).append(message)

    query = " ".join([
        search_across_project.strip().lower(),
        experiment_search.strip().lower(),
    ]).strip()
    filtered_chats = [
        chat
        for chat in chats
        if not query or all(
            term in chat_haystack(chat, messages_by_chat)
            for term in query.split()
        )
    ]

    if not chats:
        render_html(
            """
            <div class="empty-state">
                <strong>No experiments yet</strong>
                Create the first experiment for this project using the New button.
            </div>
            """
        )
        return

    if not filtered_chats:
        st.info("No experiments match the current search.")
        return

    current_group = None

    for chat in filtered_chats:
        group_label = date_group_label(chat["created_at"])

        if group_label != current_group:
            current_group = group_label
            render_html(
                f'<div class="date-label">{safe_html(group_label)}</div>'
            )

        selected = chat["id"] == st.session_state.get("selected_chat_id")
        clicked = experiment_card(
            title=chat["title"],
            snippet=chat["objective"] or "No objective added yet.",
            created_at=chat["created_at"],
            selected=selected,
            chat_id=chat["id"],
        )

        if clicked and not selected:
            st.session_state["selected_chat_id"] = chat["id"]
            st.query_params["chat_id"] = str(chat["id"])
            st.rerun(scope="app")


@st.fragment
@authenticated_callback
def render_notes_tab(selected_chat):
    messages = cached_read(get_messages, selected_chat["id"])
    audio_records = cached_read(get_audio_records, selected_chat["id"])
    st.caption("Capture written observations and local audio transcriptions.")

    with st.container(height=380, border=True):
        if not messages:
            st.info("No notes have been added to this experiment yet.")

        for message in messages:
            label = (
                "Audio transcript"
                if message["type"] == "audio_transcript"
                else "Research note"
            )
            chat_message(
                author=label,
                initials=message_initials(message["type"]),
                created_at=message["created_at"],
                content=message["content"],
            )

            with st.expander(f"Edit or delete {label.lower()}"):
                with st.form(f"edit_message_{message['id']}"):
                    edited_content = st.text_area(
                        "Content",
                        value=message["content"],
                        height=120,
                    )
                    edit_submitted = st.form_submit_button("Save changes")

                    if edit_submitted:
                        if not edited_content.strip():
                            st.error("Content cannot be empty.")
                        else:
                            update_message_content(
                                message_id=message["id"],
                                new_content=edited_content.strip(),
                            )

                            if message["type"] == "audio_transcript":
                                update_audio_transcript_by_message_id(
                                    message_id=message["id"],
                                    new_transcript=edited_content.strip(),
                                )

                            st.success("Observation updated.")
                            st.rerun(scope="fragment")

                confirm_delete = st.checkbox(
                    "Confirm deletion",
                    key=f"confirm_delete_message_{message['id']}",
                )

                if st.button(
                    "Delete observation",
                    key=f"delete_message_{message['id']}",
                    disabled=not confirm_delete,
                ):
                    if message["type"] == "audio_transcript":
                        audio_record = cached_read(
                            get_audio_record_by_message_id,
                            message["id"],
                        )

                        if audio_record:
                            delete_audio_file(audio_record["file_path"])
                            delete_audio_record_by_message_id(message["id"])

                    delete_message(message["id"])
                    st.success("Observation deleted.")
                    st.rerun(scope="fragment")

    with st.form("add_experiment_note", clear_on_submit=True):
        note = st.text_area(
            "New note",
            placeholder="Write an observation, result, issue, or next step...",
            height=76,
            label_visibility="collapsed",
            key=f"experiment_new_note_{selected_chat['id']}",
        )
        submitted = st.form_submit_button("Save note", width="stretch")

        if submitted:
            if not note.strip():
                st.error("The note cannot be empty.")
            else:
                add_message(
                    chat_id=selected_chat["id"],
                    role="user",
                    message_type="text",
                    content=note.strip(),
                )
                st.success("Note saved.")
                st.rerun(scope="fragment")

    with st.container(border=True):
        render_html(
            """
            <div class="audio-section-title">Audio Recording &amp; Transcription</div>
            <div class="audio-section-subtitle">
                Record an observation and save its transcription directly in Notes.
            </div>
            """
        )
        language_option = st.selectbox(
            "Transcription language",
            ["auto", "ro", "en"],
            key=f"transcription_language_{selected_chat['id']}",
        )
        audio_file = st.audio_input(
            "Record an observation",
            key=f"experiment_audio_input_{selected_chat['id']}",
        )

        if audio_file is not None:
            st.audio(audio_file)

            if st.button("Save and transcribe audio", width="stretch"):
                audio_path = None

                try:
                    with st.spinner("Saving and transcribing locally..."):
                        audio_path = save_audio_file(audio_file, selected_chat["id"])
                        language = None if language_option == "auto" else language_option
                        transcript = transcribe_audio(audio_path, language=language)

                    if not transcript:
                        raise ValueError("The audio could not be transcribed.")

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
                    st.success("Audio saved and added to Notes.")
                    st.rerun(scope="fragment")
                except (ValueError, RuntimeError, OSError) as exc:
                    if audio_path:
                        delete_audio_file(audio_path)

                    st.error(str(exc))

        if audio_records:
            st.divider()
            st.caption("Latest saved recordings")

            for record in reversed(audio_records[-3:]):
                st.caption(compact_date(record["created_at"]))

                try:
                    st.audio(
                        audio_preview_source(record["file_path"]),
                        format="audio/wav",
                    )
                except (FileNotFoundError, OSError, ValueError, RuntimeError):
                    st.caption("Înregistrarea audio nu mai este disponibilă.")


@st.fragment
@authenticated_callback
def render_ai_chat_panel(selected_project, selected_chat):
    messages = cached_read(get_messages, selected_chat["id"])
    ai_messages = cached_read(
        get_experiment_ai_messages,
        selected_chat["id"],
    )
    st.caption("Ask AI questions grounded only in this experiment's notes.")

    with st.container(height=520, border=True):
        if not ai_messages:
            st.info("Start a contextual conversation about this experiment.")

        for message in ai_messages:
            with st.chat_message(message["role"]):
                render_untrusted_markdown(message["content"])
                st.caption(compact_date(message["created_at"]))

    with st.form("experiment_ai_chat", clear_on_submit=True):
        question = st.text_area(
            "Question",
            placeholder="What conclusions are supported by the current notes?",
            height=92,
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Ask AI", width="stretch")

        if submitted:
            if not question.strip():
                st.error("The question cannot be empty.")
            elif not messages:
                st.error("Add notes before asking AI about the experiment.")
            else:
                user_question = question.strip()
                add_experiment_ai_message(
                    selected_chat["id"],
                    "user",
                    user_question,
                )
                history = [
                    {"role": row["role"], "content": row["content"]}
                    for row in ai_messages
                ]
                history.append({"role": "user", "content": user_question})

                with st.spinner("AI is reviewing the experiment notes..."):
                    try:
                        answer = answer_question_about_experiment(
                            project_name=selected_project["name"],
                            chat_title=selected_chat["title"],
                            chat_objective=selected_chat["objective"] or "",
                            notes=messages,
                            user_question=user_question,
                            chat_history=history,
                        )
                    except Exception as exc:
                        answer = f"AI response could not be generated: {exc}"

                add_experiment_ai_message(
                    selected_chat["id"],
                    "assistant",
                    answer,
                )
                st.rerun(scope="fragment")

    if ai_messages and st.button(
        "Clear AI conversation",
        width="stretch",
    ):
        clear_experiment_ai_messages(selected_chat["id"])
        st.rerun(scope="fragment")


def render_experiment_settings(selected_chat, all_chats):
    st.caption(
        "Deleting an experiment also deletes its notes, AI conversation, "
        "summaries, and audio records."
    )
    confirm_delete = st.checkbox(
        "Confirm permanent deletion",
        key=f"confirm_delete_experiment_{selected_chat['id']}",
    )

    if st.button(
        "Delete experiment",
        disabled=not confirm_delete,
        width="stretch",
        key=f"delete_experiment_{selected_chat['id']}",
    ):
        delete_chat(selected_chat["id"])
        remaining = [
            chat["id"]
            for chat in all_chats
            if chat["id"] != selected_chat["id"]
        ]
        st.session_state["selected_chat_id"] = remaining[0] if remaining else None
        st.success("Experiment deleted.")
        st.rerun()


def generate_selected_insight(
    selection: str,
    selected_project,
    selected_chat,
    project_messages,
    summary_style: str = SUMMARY_STYLE_STANDARD,
    custom_prompt: str = "",
):
    project_id = selected_project["id"]

    if selection == "project":
        if not project_messages:
            st.error("Add project notes before generating a project summary.")
            return

        with st.spinner("Generating project summary..."):
            summary = generate_project_summary(
                project_name=selected_project["name"],
                messages=project_messages,
                summary_style=summary_style,
                custom_prompt=custom_prompt,
            )
            save_summary(
                scope="project",
                project_id=project_id,
                chat_id=None,
                summary_style=summary_style,
                content=summary,
            )
    elif selection == "chat":
        if not selected_chat:
            st.error("Select an experiment first.")
            return

        messages = cached_read(get_messages, selected_chat["id"])

        if not messages:
            st.error("Add experiment notes before generating its summary.")
            return

        with st.spinner("Generating experiment summary..."):
            summary = generate_chat_summary(
                chat_title=selected_chat["title"],
                messages=messages,
                summary_style=summary_style,
                custom_prompt=custom_prompt,
            )
            save_summary(
                scope="chat",
                project_id=project_id,
                chat_id=selected_chat["id"],
                summary_style=summary_style,
                content=summary,
            )
    else:
        if not project_messages:
            st.error("Add project notes before extracting key ideas.")
            return

        with st.spinner("Extracting key ideas..."):
            ideas = extract_project_ideas(
                selected_project["name"],
                project_messages,
            )
            delete_project_ideas(project_id)
            save_project_ideas(project_id, ideas)

    st.rerun()


def clear_insight_edit_state(edit_state_key: str):
    st.session_state.pop(edit_state_key, None)


def render_insight_reader(
    selected_project,
    selected_chat,
    chats,
    project_messages,
    project_ideas,
):
    project_id = selected_project["id"]
    selection_key = f"insight_reader_selection_{project_id}"
    edit_state_key = f"insight_reader_edit_target_{project_id}"

    if st.session_state.get(selection_key) not in {"chat", "project", "ideas"}:
        st.session_state[selection_key] = "project"

    selector_col, reader_col = st.columns([0.72, 3.4], gap="small")
    options = [
        ("chat", "🗂️\nChat Summary"),
        ("project", "🗃️\nProject Summary"),
        ("ideas", "🔑\nKey Ideas"),
    ]

    with selector_col:
        for option, label in options:
            if st.button(
                label,
                key=f"insight_selector_{option}_{project_id}",
                type=(
                    "primary"
                    if st.session_state[selection_key] == option
                    else "secondary"
                ),
                width="stretch",
            ):
                st.session_state[selection_key] = option
                st.session_state.pop(edit_state_key, None)
                st.rerun()

    selection = st.session_state[selection_key]

    with reader_col:
        headings = {
            "chat": "Chat Summary",
            "project": "Project Summary",
            "ideas": "Key Ideas",
        }
        summary_style = SUMMARY_STYLE_STANDARD
        custom_prompt = ""
        reader_selected_chat = selected_chat

        if selection == "chat":
            header_col, experiment_col, style_col = st.columns(
                [1.35, 1.25, 1.15],
                gap="small",
            )
            chats_by_id = {chat["id"]: chat for chat in chats}
            chat_ids = list(chats_by_id)
            reader_chat_key = f"insight_summary_chat_id_{project_id}"
            preferred_chat_id = (
                selected_chat["id"]
                if selected_chat
                else (chat_ids[0] if chat_ids else None)
            )

            if st.session_state.get(reader_chat_key) not in chat_ids:
                st.session_state[reader_chat_key] = preferred_chat_id

            with experiment_col:
                if chat_ids:
                    reader_chat_id = st.selectbox(
                        "Experiment",
                        chat_ids,
                        key=reader_chat_key,
                        format_func=lambda chat_id: chats_by_id[chat_id]["title"],
                        on_change=clear_insight_edit_state,
                        args=(edit_state_key,),
                    )
                    reader_selected_chat = chats_by_id[reader_chat_id]
                else:
                    st.text_input(
                        "Experiment",
                        value="No experiments available",
                        disabled=True,
                    )
                    reader_selected_chat = None

            with style_col:
                summary_style = st.selectbox(
                    "Summary structure",
                    SUMMARY_STYLE_OPTIONS,
                    key=f"chat_summary_style_reader_{project_id}",
                    on_change=clear_insight_edit_state,
                    args=(edit_state_key,),
                )

            with header_col:
                render_html(
                    f"""
                    <div class="insight-reader-heading">{headings[selection]}</div>
                    <div class="insight-reader-context">
                        {safe_html(reader_selected_chat['title']) if reader_selected_chat else 'Select an experiment'}
                    </div>
                    """
                )
        elif selection == "project":
            header_col, style_col = st.columns([2.55, 1.15], gap="small")

            with header_col:
                render_html(
                    f"""
                    <div class="insight-reader-heading">{headings[selection]}</div>
                    <div class="insight-reader-context">{safe_html(selected_project['name'])}</div>
                    """
                )

            with style_col:
                summary_style = st.selectbox(
                    "Summary structure",
                    SUMMARY_STYLE_OPTIONS,
                    key=f"project_summary_style_reader_{project_id}",
                    on_change=clear_insight_edit_state,
                    args=(edit_state_key,),
                )
        else:
            render_html(
                f"""
                <div class="insight-reader-heading">{headings[selection]}</div>
                <div class="insight-reader-context">{safe_html(selected_project['name'])}</div>
                """
            )

        if selection in {"chat", "project"} and summary_style == SUMMARY_STYLE_CUSTOM:
            custom_prompt = st.text_area(
                "Custom summary prompt",
                placeholder="Describe the structure and emphasis you want for this summary...",
                height=92,
                key=f"custom_{selection}_summary_prompt_reader_{project_id}",
            )

        active_summary = None

        if selection == "project":
            active_summary = cached_read(
                get_project_summary,
                project_id,
                summary_style,
            )
        elif selection == "chat" and reader_selected_chat:
            active_summary = cached_read(
                get_chat_summary,
                reader_selected_chat["id"],
                summary_style,
            )

        if selection in {"chat", "project"} and active_summary:
            edit_target = f"summary:{active_summary['id']}"
        elif selection == "ideas" and project_ideas:
            idea_ids = ":".join(str(idea["id"]) for idea in project_ideas)
            edit_target = f"ideas:{idea_ids}"
        else:
            edit_target = None

        is_editing = bool(
            edit_target
            and st.session_state.get(edit_state_key) == edit_target
        )

        with st.container(height=420, border=True):
            if selection in {"chat", "project"} and active_summary:
                st.caption(f"Structure: {active_summary['summary_style']}")

                if is_editing:
                    summary_editor_key = (
                        f"insight_summary_editor_{active_summary['id']}"
                    )
                    st.session_state.setdefault(
                        summary_editor_key,
                        active_summary["content"],
                    )
                    st.text_area(
                        "Edit summary",
                        height=322,
                        key=summary_editor_key,
                        label_visibility="collapsed",
                    )
                else:
                    render_untrusted_markdown(active_summary["content"])
                    st.caption(f"Updated {active_summary['created_at']}")
            elif selection == "project":
                st.info(
                    "No project summary has been generated for "
                    f"the structure “{summary_style}”."
                )
            elif selection == "chat" and reader_selected_chat:
                st.info(
                    "No summary exists for this experiment with "
                    f"the structure “{summary_style}”."
                )
            elif selection == "chat":
                st.info("Select an experiment to read its summary.")
            elif project_ideas and is_editing:
                for index, idea in enumerate(project_ideas, start=1):
                    title_key = f"insight_idea_title_{idea['id']}"
                    description_key = f"insight_idea_description_{idea['id']}"
                    evidence_key = f"insight_idea_evidence_{idea['id']}"
                    importance_key = f"insight_idea_importance_{idea['id']}"
                    importance = (idea["importance"] or "medium").lower()

                    st.session_state.setdefault(title_key, idea["title"])
                    st.session_state.setdefault(
                        description_key,
                        idea["description"],
                    )
                    st.session_state.setdefault(
                        evidence_key,
                        idea["evidence"] or "",
                    )
                    st.session_state.setdefault(
                        importance_key,
                        importance if importance in {"high", "medium", "low"}
                        else "medium",
                    )
                    st.text_input(f"Idea {index} title", key=title_key)
                    st.text_area(
                        f"Idea {index} description",
                        height=105,
                        key=description_key,
                    )
                    st.text_area(
                        f"Idea {index} evidence",
                        height=82,
                        key=evidence_key,
                    )
                    st.selectbox(
                        f"Idea {index} importance",
                        ["high", "medium", "low"],
                        key=importance_key,
                    )
                    st.divider()
            elif project_ideas:
                for idea in project_ideas:
                    importance = (idea["importance"] or "medium").title()
                    render_untrusted_markdown(
                        f"**{idea['title']}** · {importance}"
                    )
                    render_untrusted_markdown(idea["description"])

                    if idea["evidence"]:
                        render_untrusted_caption(f"Evidence: {idea['evidence']}")

                    st.divider()
            else:
                st.info("No key ideas have been extracted yet.")

        action_label = {
            "chat": "Generate chat summary",
            "project": "Generate project summary",
            "ideas": "Refresh key ideas",
        }[selection]

        generate_col, edit_col = st.columns([4.1, 1], gap="small")

        with generate_col:
            generate_clicked = st.button(
                action_label,
                key=f"generate_selected_insight_{project_id}",
                disabled=is_editing,
                width="stretch",
            )

        with edit_col:
            edit_clicked = st.button(
                "Save" if is_editing else "Edit",
                key=f"edit_selected_insight_{project_id}",
                disabled=edit_target is None,
                type="primary" if is_editing else "secondary",
                width="stretch",
            )

        if edit_clicked and not is_editing:
            st.session_state[edit_state_key] = edit_target

            if active_summary:
                st.session_state[
                    f"insight_summary_editor_{active_summary['id']}"
                ] = active_summary["content"]
            else:
                for idea in project_ideas:
                    importance = (idea["importance"] or "medium").lower()
                    st.session_state[f"insight_idea_title_{idea['id']}"] = (
                        idea["title"]
                    )
                    st.session_state[
                        f"insight_idea_description_{idea['id']}"
                    ] = idea["description"]
                    st.session_state[f"insight_idea_evidence_{idea['id']}"] = (
                        idea["evidence"] or ""
                    )
                    st.session_state[
                        f"insight_idea_importance_{idea['id']}"
                    ] = (
                        importance
                        if importance in {"high", "medium", "low"}
                        else "medium"
                    )

            st.rerun()

        if edit_clicked and is_editing:
            if active_summary:
                summary_editor_key = (
                    f"insight_summary_editor_{active_summary['id']}"
                )
                edited_content = st.session_state.get(
                    summary_editor_key,
                    "",
                ).strip()

                if not edited_content:
                    st.error("The summary cannot be empty.")
                else:
                    update_summary(active_summary["id"], edited_content)
                    st.session_state.pop(edit_state_key, None)
                    st.toast("Summary saved.")
                    st.rerun()
            else:
                edited_ideas = []

                for idea in project_ideas:
                    edited_ideas.append({
                        "id": idea["id"],
                        "title": st.session_state.get(
                            f"insight_idea_title_{idea['id']}",
                            "",
                        ).strip(),
                        "description": st.session_state.get(
                            f"insight_idea_description_{idea['id']}",
                            "",
                        ).strip(),
                        "evidence": st.session_state.get(
                            f"insight_idea_evidence_{idea['id']}",
                            "",
                        ).strip(),
                        "importance": st.session_state.get(
                            f"insight_idea_importance_{idea['id']}",
                            "medium",
                        ),
                    })

                if any(not idea["title"] for idea in edited_ideas):
                    st.error("Every key idea must have a title.")
                elif any(not idea["description"] for idea in edited_ideas):
                    st.error("Every key idea must have a description.")
                else:
                    for idea in edited_ideas:
                        update_project_idea(
                            idea_id=idea["id"],
                            title=idea["title"],
                            description=idea["description"],
                            evidence=idea["evidence"],
                            importance=idea["importance"],
                        )

                    st.session_state.pop(edit_state_key, None)
                    st.toast("Key ideas saved.")
                    st.rerun()

        if generate_clicked:
            st.session_state.pop(edit_state_key, None)

            if (
                selection in {"chat", "project"}
                and summary_style == SUMMARY_STYLE_CUSTOM
                and not custom_prompt.strip()
            ):
                st.error("Write a custom prompt before generating the summary.")
            else:
                try:
                    generate_selected_insight(
                        selection=selection,
                        selected_project=selected_project,
                        selected_chat=reader_selected_chat,
                        project_messages=project_messages,
                        summary_style=summary_style,
                        custom_prompt=custom_prompt.strip(),
                    )
                except Exception as exc:
                    st.error(f"The insight could not be generated: {exc}")


def render_node_context_chat(
    selected_project,
    project_messages,
    selected_node,
):
    project_id = selected_project["id"]
    node_key = selected_node["node_key"]
    history_key = f"insight_node_chat_{project_id}_{node_key}"
    st.session_state.setdefault(history_key, [])
    history = st.session_state[history_key]

    with st.container(border=True):
        render_untrusted_markdown(
            f"#### Contextual AI Chat · {selected_node['label']}"
        )

        if selected_node["description"]:
            render_untrusted_caption(selected_node["description"])

        with st.container(height=240, border=True):
            if not history:
                st.info("Ask a question grounded in this node and the project notes.")

            for message in history:
                with st.chat_message(message["role"]):
                    render_untrusted_markdown(message["content"])

        with st.form(
            f"insight_node_question_form_{project_id}_{node_key}",
            clear_on_submit=True,
        ):
            question = st.text_area(
                "Ask about this node",
                placeholder="What evidence supports this concept?",
                height=76,
                label_visibility="collapsed",
            )
            submitted = st.form_submit_button("Ask about node", width="stretch")

        if submitted:
            if not question.strip():
                st.error("The question cannot be empty.")
            else:
                user_question = question.strip()
                history.append({"role": "user", "content": user_question})

                with st.spinner("AI is reviewing this node in project context..."):
                    try:
                        answer = answer_question_about_node(
                            project_name=selected_project["name"],
                            node_label=selected_node["label"],
                            node_description=selected_node["description"] or "",
                            messages=project_messages,
                            user_question=user_question,
                            chat_history=history,
                        )
                    except Exception as exc:
                        answer = f"AI response could not be generated: {exc}"

                history.append({"role": "assistant", "content": answer})
                st.rerun()

        if history and st.button(
            "Clear node conversation",
            key=f"clear_insight_node_chat_{project_id}_{node_key}",
            width="stretch",
        ):
            st.session_state[history_key] = []
            st.rerun()


def render_interactive_mindmap(
    selected_project,
    project_messages,
    mindmap_nodes,
    mindmap_edges,
):
    project_id = selected_project["id"]
    expanded_key = f"insight_mindmap_expanded_{project_id}"
    st.session_state.setdefault(expanded_key, False)
    title_col, compact_col, expand_col = st.columns(
        [1, 0.13, 0.13],
        gap="small",
    )

    with title_col:
        st.markdown("### Interactive Mind Map")
        st.caption("Click a node to open its contextual AI chat.")

    with compact_col:
        if st.button(
            "−",
            key=f"compact_mindmap_{project_id}",
            help="Minimize mind map",
            width="stretch",
        ):
            st.session_state[expanded_key] = False
            st.rerun()

    with expand_col:
        if st.button(
            "⛶",
            key=f"expand_mindmap_{project_id}",
            help="Maximize mind map",
            width="stretch",
        ):
            st.session_state[expanded_key] = True
            st.rerun()

    if not mindmap_nodes:
        st.info("The mind map will appear after the first notes are processed.")
        return

    graph_nodes = []
    node_sizes = {"high": 38, "medium": 30, "low": 24}
    node_colors = {"high": "#1769d2", "medium": "#4d91d8", "low": "#7d4ad8"}

    for node in mindmap_nodes:
        importance = (node["importance"] or "medium").lower()
        graph_nodes.append(
            Node(
                id=node["node_key"],
                label=node["label"],
                title="Open contextual details",
                size=node_sizes.get(importance, 30),
                color=node_colors.get(importance, "#4d91d8"),
                font={
                    "size": 18,
                    "face": "Inter",
                    "color": "#111827",
                    "strokeWidth": 3,
                    "strokeColor": "#ffffff",
                },
            )
        )

    graph_edges = [
        Edge(
            source=edge["source_key"],
            target=edge["target_key"],
        )
        for edge in mindmap_edges
    ]
    graph_height = 700 if st.session_state[expanded_key] else 420
    selected_node_value = agraph(
        nodes=graph_nodes,
        edges=graph_edges,
        config=Config(
            width="100%",
            height=graph_height,
            directed=True,
            physics=True,
            hierarchical=False,
        ),
    )
    selected_node_key = None

    if isinstance(selected_node_value, str):
        selected_node_key = selected_node_value
    elif isinstance(selected_node_value, dict):
        selected_node_key = selected_node_value.get("id")

    state_key = f"insight_selected_mindmap_node_{project_id}"

    if selected_node_key:
        st.session_state[state_key] = selected_node_key

    last_sync = cached_read(get_mindmap_last_sync, project_id)
    st.caption(
        f"{len(mindmap_nodes)} nodes · {len(mindmap_edges)} connections"
        + (f" · updated {compact_date(last_sync)}" if last_sync else "")
    )
    stored_node_key = st.session_state.get(state_key)

    if not stored_node_key:
        st.info("Click a node to start a contextual conversation about it.")
        return

    selected_node = cached_read(
        get_mindmap_node_by_key,
        project_id,
        stored_node_key,
    )

    if selected_node:
        render_node_context_chat(
            selected_project=selected_project,
            project_messages=project_messages,
            selected_node=selected_node,
        )


def collect_project_summaries(project_id: int, chats) -> list:
    del chats
    return list(cached_read(get_all_project_summaries, project_id))


def render_project_ai_chat(
    selected_project,
    chats,
    project_messages,
    project_ideas,
    mindmap_nodes,
    mindmap_edges,
):
    project_id = selected_project["id"]
    history_key = f"project_insights_ai_chat_{project_id}"
    st.session_state.setdefault(history_key, [])
    history = st.session_state[history_key]
    render_html(
        """
        <div class="project-ai-title">✦ AI Chat</div>
        <div class="project-ai-subtitle">
            Uses notes, transcripts, summaries, key ideas, and the mind map from the entire project.
        </div>
        """
    )
    suggestions = [
        ("Summarize project", "Rezuma proiectul și evidențiază concluziile susținute de date."),
        ("Find patterns", "Ce tipare apar între experimentele proiectului?"),
        ("Identify gaps", "Ce goluri de informație și întrebări deschise există în proiect?"),
    ]
    suggestion_cols = st.columns(3, gap="small")
    suggested_question = None

    for column, (label, prompt) in zip(suggestion_cols, suggestions):
        with column:
            if st.button(
                label,
                key=f"project_ai_suggestion_{label}_{project_id}",
                width="stretch",
            ):
                suggested_question = prompt

    with st.container(height=540, border=True):
        if not history:
            st.info("Ask AI to synthesize findings or identify gaps across the project.")

        for message in history:
            with st.chat_message(message["role"]):
                render_untrusted_markdown(message["content"])

    with st.form(f"project_insights_ai_form_{project_id}", clear_on_submit=True):
        typed_question = st.text_area(
            "Ask AI about this project",
            placeholder="Ask AI about the entire project...",
            height=82,
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Ask AI", width="stretch")

    question = suggested_question or (typed_question.strip() if submitted else "")

    if question:
        if not any([project_messages, project_ideas, mindmap_nodes]):
            st.error("Add project data before starting the project AI chat.")
        else:
            history.append({"role": "user", "content": question})
            summaries = collect_project_summaries(project_id, chats)

            with st.spinner("AI is analyzing the complete project context..."):
                try:
                    answer = answer_question_about_project(
                        project_name=selected_project["name"],
                        project_domain=selected_project["domain"],
                        messages=project_messages,
                        summaries=summaries,
                        ideas=project_ideas,
                        mindmap_nodes=mindmap_nodes,
                        mindmap_edges=mindmap_edges,
                        user_question=question,
                        chat_history=history,
                    )
                except Exception as exc:
                    answer = f"AI response could not be generated: {exc}"

            history.append({"role": "assistant", "content": answer})
            st.rerun()

    if history and st.button(
        "Clear project conversation",
        key=f"clear_project_insights_chat_{project_id}",
        width="stretch",
    ):
        st.session_state[history_key] = []
        st.rerun()


def render_insights(
    selected_project,
    selected_chat,
    chats,
    project_messages,
    project_ideas,
    mindmap_nodes,
    mindmap_edges,
):
    main_col, chat_col = st.columns([2.2, 1], gap="small")

    with main_col:
        render_html('<div class="insight-main-scope"></div>')
        render_html(
            """
            <div class="insights-info-banner">
                AI reads project notes, transcripts, summaries, and key ideas to build a connected research view.
            </div>
            """
        )
        render_insight_reader(
            selected_project=selected_project,
            selected_chat=selected_chat,
            chats=chats,
            project_messages=project_messages,
            project_ideas=project_ideas,
        )
        st.divider()
        render_interactive_mindmap(
            selected_project=selected_project,
            project_messages=project_messages,
            mindmap_nodes=mindmap_nodes,
            mindmap_edges=mindmap_edges,
        )

    with chat_col:
        render_html('<div class="insight-side-scope"></div>')
        render_project_ai_chat(
            selected_project=selected_project,
            chats=chats,
            project_messages=project_messages,
            project_ideas=project_ideas,
            mindmap_nodes=mindmap_nodes,
            mindmap_edges=mindmap_edges,
        )


def render_workspace_tab_content(
    selected_project,
    selected_chat,
    chats,
    project_messages,
    search_across_project,
):
    list_col, content_col, chat_col = st.columns(
        [1.35, 2.7, 2.05],
        gap="small",
    )

    with list_col:
        render_experiment_list(
            selected_project=selected_project,
            search_across_project=search_across_project,
        )

    if not selected_chat:
        with content_col:
            render_html('<div class="experiment-content-scope"></div>')
            render_html(
                """
                <div class="empty-state">
                    <strong>Select or create an experiment</strong>
                    Notes and audio transcription will appear here.
                </div>
                """
            )

        with chat_col:
            render_html('<div class="experiment-ai-chat-scope"></div>')
            render_html(
                """
                <div class="panel-title">AI Chat</div>
                <div class="panel-subtitle">Select an experiment to start a contextual conversation.</div>
                """
            )
        return

    with content_col:
        render_html('<div class="experiment-content-scope"></div>')
        title_col, settings_col = st.columns([1, 0.15], gap="small")

        with title_col:
            render_html(
                f"""
                <div class="eyebrow">Selected experiment</div>
                <div class="panel-title">{safe_html(selected_chat['title'])}</div>
                <div class="panel-subtitle">{safe_html(selected_chat['objective'] or 'No objective added yet.')}</div>
                """
            )

        with settings_col:
            with st.popover("•••"):
                render_experiment_settings(selected_chat, chats)

        st.markdown("#### Notes")
        render_notes_tab(selected_chat)

    with chat_col:
        render_html('<div class="experiment-ai-chat-scope"></div>')
        render_html(
            f"""
            <div class="panel-title">AI Chat</div>
            <div class="panel-subtitle">Always connected to {safe_html(selected_chat['title'])}</div>
            """
        )
        render_ai_chat_panel(selected_project, selected_chat)


def render_insights_tab_content(
    selected_project,
    selected_chat,
    chats,
    project_messages,
    project_ideas,
):
    project_id = selected_project["id"]
    failure_signature_key = f"mindmap_sync_failure_signature_{project_id}"
    failure_message_key = f"mindmap_sync_failure_message_{project_id}"

    try:
        sync_signature = get_pending_mindmap_signature(
            project_id,
            project_messages,
            project_ideas,
        )
    except Exception as exc:
        sync_signature = ""
        st.session_state[failure_message_key] = str(exc)

    mindmap_nodes = cached_read(get_mindmap_nodes, project_id)
    mindmap_edges = cached_read(get_mindmap_edges, project_id)
    render_insights(
        selected_project=selected_project,
        selected_chat=selected_chat,
        chats=chats,
        project_messages=project_messages,
        project_ideas=project_ideas,
        mindmap_nodes=mindmap_nodes,
        mindmap_edges=mindmap_edges,
    )

    if sync_signature:
        st.info(
            "The mind map has unsynchronized notes or ideas. "
            "Updating it uses one AI request."
        )

        if st.button(
            "Synchronize mind map with AI",
            key=f"sync_mindmap_{project_id}",
            width="stretch",
        ):
            try:
                with st.spinner("Synchronizing the mind map..."):
                    sync_project_mindmap(
                        project_id=project_id,
                        project_name=selected_project["name"],
                        messages=project_messages,
                        ideas=project_ideas,
                    )
                st.session_state.pop(failure_signature_key, None)
                st.session_state.pop(failure_message_key, None)
                st.rerun()
            except Exception as exc:
                st.session_state[failure_signature_key] = sync_signature
                st.session_state[failure_message_key] = str(exc)

    mindmap_error = st.session_state.get(failure_message_key)

    if mindmap_error:
        st.warning(f"Mind map synchronization needs attention: {mindmap_error}")


render_page_css()

projects = cached_read(get_projects)

top_brand_col, top_project_col, top_search_col, top_user_col = st.columns(
    [1.05, 3.0, 1.9, 1.65],
    gap="large",
)

with top_brand_col:
    top_brand()

selected_project = None

with top_project_col:
    render_html('<div class="top-project-scope"></div>')

    if projects:
        project_ids = [project["id"] for project in projects]
        projects_by_id = {
            project["id"]: project
            for project in projects
        }

        pending_project_id = st.session_state.pop(
            "experiments_pending_project_id",
            None,
        )

        if pending_project_id in project_ids:
            st.session_state["experiments_project_id"] = pending_project_id

        if st.session_state.get("experiments_project_id") not in project_ids:
            st.session_state["experiments_project_id"] = project_ids[0]

        project_select_col, delete_col, new_col = st.columns(
            [1.75, 0.28, 0.52],
            gap="small",
        )

        with project_select_col:
            selected_project_id = st.selectbox(
                "Project",
                project_ids,
                key="experiments_project_id",
                format_func=lambda project_id: projects_by_id[project_id]["name"],
            )
            selected_project = projects_by_id[selected_project_id]

        with delete_col:
            with st.container(key="project_delete_control"):
                render_delete_project_control(selected_project, projects)

        with new_col:
            with st.container(key="new_project_control"):
                with st.popover("+ New", width="stretch"):
                    render_create_project_form(key="new_project_header_form")
    else:
        empty_project_col, new_col = st.columns([1.75, 0.52], gap="small")

        with empty_project_col:
            st.text_input(
                "Project",
                value="Create your first project",
                disabled=True,
            )

        with new_col:
            with st.container(key="new_project_control"):
                with st.popover("+ New", width="stretch"):
                    render_create_project_form(key="new_project_header_form")

with top_search_col:
    render_html('<div class="top-search-scope"></div>')

with top_user_col:
    render_html('<div class="top-user-scope"></div>')
    header_icons()


nav_col, page_col = st.columns([1.05, 6.48], gap="small")

with nav_col:
    render_html('<div class="nav-panel-scope"></div>')
    sidebar_nav("experiments")

with page_col:
    render_html('<div class="experiments-page-scope"></div>')
    title_col, search_col, spacer_col = st.columns(
        [0.72, 1.55, 0.58],
        gap="small",
    )

    with title_col:
        render_html(
            """
            <div class="experiments-heading">Experiments</div>
            """
        )

    with search_col:
        search_across_project = st.text_input(
            "Search",
            placeholder="Search experiments, notes, and insights...",
            key="project_global_search",
            label_visibility="collapsed",
        )

    if not selected_project:
        render_html(
            """
            <div class="empty-state" style="margin-top:28px;">
                <strong>Create your first research project</strong>
                A project groups experiments, notes, AI discussions, summaries, and insights.
            </div>
            """
        )
        render_create_project_form(key="first_project_form")
        st.stop()

    chats, project_messages, project_ideas = cached_read(
        get_project_workspace,
        selected_project["id"],
    )

    requested_chat_id = None
    requested_chat_value = st.query_params.get("chat_id")

    if requested_chat_value:
        try:
            requested_chat_id = int(requested_chat_value)
        except (TypeError, ValueError):
            requested_chat_id = None

    chat_ids = [chat["id"] for chat in chats]

    if requested_chat_id in chat_ids:
        st.session_state["selected_chat_id"] = requested_chat_id
    elif st.session_state.get("selected_chat_id") not in chat_ids:
        st.session_state["selected_chat_id"] = chat_ids[0] if chat_ids else None

    selected_chat = next(
        (
            chat
            for chat in chats
            if chat["id"] == st.session_state.get("selected_chat_id")
        ),
        None,
    )

    workspace_tab, insights_tab = st.tabs(
        ["Workspace", "Insights"],
        key="experiments_primary_tab",
        on_change="rerun",
    )

    if workspace_tab.open:
        with workspace_tab:
            render_workspace_tab_content(
                selected_project=selected_project,
                selected_chat=selected_chat,
                chats=chats,
                project_messages=project_messages,
                search_across_project=search_across_project,
            )

    if insights_tab.open:
        with insights_tab:
            render_insights_tab_content(
                selected_project=selected_project,
                selected_chat=selected_chat,
                chats=chats,
                project_messages=project_messages,
                project_ideas=project_ideas,
            )
