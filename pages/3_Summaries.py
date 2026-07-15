import streamlit as st

from db.database import init_db
from db.queries import (
    get_projects,
    get_chats,
    get_messages,
    get_project_messages,
    save_summary,
    get_chat_summaries,
    get_project_summaries,
    delete_project_ideas,
    save_project_ideas,
    get_project_ideas,
    update_summary,
    update_project_idea,
    delete_summary,
    delete_project_idea
)
from services.summary_service import (
    generate_chat_summary,
    generate_project_summary,
    extract_project_ideas,
    SUMMARY_STYLE_OPTIONS,
    SUMMARY_STYLE_CUSTOM,
    CHAT_SUMMARY_STYLE_DESCRIPTIONS,
    PROJECT_SUMMARY_STYLE_DESCRIPTIONS
)
from utils.ui import load_css, page_brand_header, sidebar_nav



init_db()
load_css()
page_brand_header()

nav_col, main_col = st.columns([1.05, 5.3], gap="small")

with nav_col:
    sidebar_nav("summaries")

with main_col:

    st.title("🧾 AI Summaries")

    st.write("""
    Aici poți genera:
    - rezumat pentru un chat/experiment;
    - rezumat complet pentru un proiect;
    - idei principale extrase din proiect.
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

    tab_chat, tab_project, tab_ideas = st.tabs(
        [
            "Rezumat chat",
            "Rezumat proiect",
            "Idei principale"
        ]
    )


    with tab_chat:
        st.subheader("💬 Rezumat pentru un chat/experiment")

        chats = get_chats(selected_project_id)

        if not chats:
            st.info("Acest proiect nu are încă experimente/chat-uri.")
        else:
            chat_options = {
                chat["title"]: chat
                for chat in chats
            }

            selected_chat_title = st.selectbox(
                "Alege chat-ul/experimentul",
                list(chat_options.keys())
            )

            selected_chat = chat_options[selected_chat_title]
            selected_chat_id = selected_chat["id"]

            messages = get_messages(selected_chat_id)

            if not messages:
                st.warning("Acest chat nu are încă notițe.")
            else:
                st.write(f"Număr de mesaje în chat: **{len(messages)}**")

                summary_style = st.selectbox(
                    "Alege structura rezumatului",
                    SUMMARY_STYLE_OPTIONS,
                    key=f"chat_summary_style_{selected_chat_id}"
                )

                with st.expander("Vezi structura aleasă", expanded=True):
                    st.markdown(
                        CHAT_SUMMARY_STYLE_DESCRIPTIONS.get(
                            summary_style,
                            "Nu există descriere pentru această structură."
                        )
                    )

                custom_prompt = ""

                if summary_style == SUMMARY_STYLE_CUSTOM:
                    custom_prompt = st.text_area(
                        "Scrie promptul tău personalizat pentru rezumatul chat-ului",
                        placeholder=(
                            "Ex: Fă un rezumat foarte scurt, apoi separă observațiile în: "
                            "compuși, reacții, rezultate, probleme și concluzii."
                        ),
                        height=180,
                        key=f"custom_chat_prompt_{selected_chat_id}"
                    )

                if st.button("Generează rezumat pentru chat"):
                    if summary_style == SUMMARY_STYLE_CUSTOM and not custom_prompt.strip():
                        st.error("Ai ales prompt personalizat, dar nu ai scris niciun prompt.")
                    else:
                        with st.spinner("Gemini generează rezumatul chat-ului..."):
                            summary = generate_chat_summary(
                                chat_title=selected_chat["title"],
                                messages=messages,
                                summary_style=summary_style,
                                custom_prompt=custom_prompt.strip()
                            )

                        save_summary(
                            scope="chat",
                            project_id=selected_project_id,
                            chat_id=selected_chat_id,
                            content=summary
                        )

                        st.success("Rezumatul chat-ului a fost generat și salvat.")
                        st.markdown(summary)

            st.divider()

            st.subheader("Rezumate salvate pentru acest chat")

            saved_chat_summaries = get_chat_summaries(selected_chat_id)

            if not saved_chat_summaries:
                st.caption("Nu există rezumate salvate pentru acest chat.")
            else:
                for summary in saved_chat_summaries:
                    with st.expander(f"Rezumat generat la {summary['created_at']}"):
                        st.markdown(summary["content"])

                        st.divider()

                        with st.form(f"edit_chat_summary_form_{summary['id']}"):
                            edited_summary = st.text_area(
                                "Modifică rezumatul chat-ului",
                                value=summary["content"],
                                height=250,
                                key=f"edited_chat_summary_{summary['id']}"
                            )

                            submitted_summary_edit = st.form_submit_button("Salvează modificarea")

                            if submitted_summary_edit:
                                if not edited_summary.strip():
                                    st.error("Rezumatul nu poate fi gol.")
                                else:
                                    update_summary(
                                        summary_id=summary["id"],
                                        new_content=edited_summary.strip()
                                    )

                                    st.success("Rezumatul chat-ului a fost modificat.")
                                    st.rerun()

                        st.error("Zonă de ștergere")

                        confirm_delete_summary = st.checkbox(
                            "Confirm că vreau să șterg acest rezumat de chat",
                            key=f"confirm_delete_chat_summary_{summary['id']}"
                        )

                        if st.button(
                            "Șterge rezumatul de chat",
                            key=f"delete_chat_summary_{summary['id']}",
                            disabled=not confirm_delete_summary
                        ):
                            delete_summary(summary["id"])

                            st.success("Rezumatul de chat a fost șters.")
                            st.rerun()


    with tab_project:
        st.subheader("📁 Rezumat complet pentru proiect")

        project_messages = get_project_messages(selected_project_id)

        if not project_messages:
            st.warning("Acest proiect nu are încă notițe în experimente.")
        else:
            st.write(f"Număr total de mesaje în proiect: **{len(project_messages)}**")

            project_summary_style = st.selectbox(
                "Alege structura rezumatului de proiect",
                SUMMARY_STYLE_OPTIONS,
                key=f"project_summary_style_{selected_project_id}"
            )
            with st.expander("Vezi structura aleasă", expanded=True):
                st.markdown(
                    PROJECT_SUMMARY_STYLE_DESCRIPTIONS.get(
                        project_summary_style,
                        "Nu există descriere pentru această structură."
                    )
                )

            project_custom_prompt = ""

            if project_summary_style == SUMMARY_STYLE_CUSTOM:
                project_custom_prompt = st.text_area(
                    "Scrie promptul tău personalizat pentru rezumatul proiectului",
                    placeholder=(
                        "Ex: Fă un raport pe capitole: scop, experimente, rezultate, "
                        "conexiuni între experimente, probleme și pași următori."
                    ),
                    height=180,
                    key=f"custom_project_prompt_{selected_project_id}"
                )

            if st.button("Generează rezumat complet pentru proiect"):
                if project_summary_style == SUMMARY_STYLE_CUSTOM and not project_custom_prompt.strip():
                    st.error("Ai ales prompt personalizat, dar nu ai scris niciun prompt.")
                else:
                    with st.spinner("Gemini generează rezumatul proiectului..."):
                        summary = generate_project_summary(
                            project_name=selected_project["name"],
                            messages=project_messages,
                            summary_style=project_summary_style,
                            custom_prompt=project_custom_prompt.strip()
                        )

                    save_summary(
                        scope="project",
                        project_id=selected_project_id,
                        chat_id=None,
                        content=summary
                    )

                    st.success("Rezumatul proiectului a fost generat și salvat.")
                    st.markdown(summary)

        st.divider()

        st.subheader("Rezumate salvate pentru acest proiect")

        saved_project_summaries = get_project_summaries(selected_project_id)

        if not saved_project_summaries:
            st.caption("Nu există rezumate salvate pentru acest proiect.")
        else:
            for summary in saved_project_summaries:
                with st.expander(f"Rezumat generat la {summary['created_at']}"):
                    st.markdown(summary["content"])

                    st.divider()

                    with st.form(f"edit_project_summary_form_{summary['id']}"):
                        edited_summary = st.text_area(
                            "Modifică rezumatul proiectului",
                            value=summary["content"],
                            height=300,
                            key=f"edited_project_summary_{summary['id']}"
                        )

                        submitted_summary_edit = st.form_submit_button("Salvează modificarea")

                        if submitted_summary_edit:
                            if not edited_summary.strip():
                                st.error("Rezumatul nu poate fi gol.")
                            else:
                                update_summary(
                                    summary_id=summary["id"],
                                    new_content=edited_summary.strip()
                                )

                                st.success("Rezumatul proiectului a fost modificat.")
                                st.rerun()

                    st.divider()

                    st.error("Zonă de ștergere")

                    confirm_delete_summary = st.checkbox(
                        "Confirm că vreau să șterg acest rezumat de proiect",
                        key=f"confirm_delete_project_summary_{summary['id']}"
                    )

                    if st.button(
                        "Șterge rezumatul de proiect",
                        key=f"delete_project_summary_{summary['id']}",
                        disabled=not confirm_delete_summary
                    ):
                        delete_summary(summary["id"])

                        st.success("Rezumatul de proiect a fost șters.")
                        st.rerun()


    with tab_ideas:
        st.subheader("💡 Idei principale extrase din proiect")

        project_messages = get_project_messages(selected_project_id)

        if not project_messages:
            st.warning("Acest proiect nu are încă notițe.")
        else:
            st.write(f"Număr total de mesaje analizate: **{len(project_messages)}**")

            if st.button("Extrage ideile principale"):
                with st.spinner("Gemini extrage ideile principale..."):
                    ideas = extract_project_ideas(
                        project_name=selected_project["name"],
                        messages=project_messages
                    )

                delete_project_ideas(selected_project_id)
                save_project_ideas(selected_project_id, ideas)

                st.success("Ideile principale au fost extrase și salvate.")

        st.divider()

        saved_ideas = get_project_ideas(selected_project_id)

        if not saved_ideas:
            st.caption("Nu există încă idei principale salvate pentru acest proiect.")
        else:
            for idea in saved_ideas:
                importance = idea["importance"] or "medium"

                with st.expander(f"{idea['title']} — importanță: {importance}"):
                    st.write("**Descriere:**")
                    st.write(idea["description"])

                    if idea["evidence"]:
                        st.write("**Dovadă / observație relevantă:**")
                        st.write(idea["evidence"])

                    st.caption(f"Creat la: {idea['created_at']}")

                    st.divider()

                    with st.form(f"edit_project_idea_form_{idea['id']}"):
                        edited_title = st.text_input(
                            "Titlu idee",
                            value=idea["title"],
                            key=f"edited_idea_title_{idea['id']}"
                        )

                        edited_description = st.text_area(
                            "Descriere idee",
                            value=idea["description"],
                            height=150,
                            key=f"edited_idea_description_{idea['id']}"
                        )

                        edited_evidence = st.text_area(
                            "Dovadă / observație relevantă",
                            value=idea["evidence"] or "",
                            height=120,
                            key=f"edited_idea_evidence_{idea['id']}"
                        )

                        edited_importance = st.selectbox(
                            "Importanță",
                            ["high", "medium", "low"],
                            index=["high", "medium", "low"].index(importance)
                            if importance in ["high", "medium", "low"]
                            else 1,
                            key=f"edited_idea_importance_{idea['id']}"
                        )

                        submitted_idea_edit = st.form_submit_button("Salvează modificarea")

                        if submitted_idea_edit:
                            if not edited_title.strip():
                                st.error("Titlul ideii nu poate fi gol.")
                            elif not edited_description.strip():
                                st.error("Descrierea ideii nu poate fi goală.")
                            else:
                                update_project_idea(
                                    idea_id=idea["id"],
                                    title=edited_title.strip(),
                                    description=edited_description.strip(),
                                    evidence=edited_evidence.strip(),
                                    importance=edited_importance
                                )

                                st.success("Ideea principală a fost modificată.")
                                st.rerun()
                    st.divider()

                    st.error("Zonă de ștergere")

                    confirm_delete_idea = st.checkbox(
                        "Confirm că vreau să șterg această idee principală",
                        key=f"confirm_delete_project_idea_{idea['id']}"
                    )

                    if st.button(
                        "Șterge ideea principală",
                        key=f"delete_project_idea_{idea['id']}",
                        disabled=not confirm_delete_idea
                    ):
                        delete_project_idea(idea["id"])

                        st.success("Ideea principală a fost ștearsă.")
                        st.rerun()
