import streamlit as st

from db.database import init_db
from db.queries import (
    create_project,
    get_projects,
    create_chat,
    get_chats,
    delete_project,
    delete_chat,
    get_audio_file_paths_by_project,
    get_audio_file_paths_by_chat
)
from services.transcription_service import delete_audio_file

init_db()

st.title("📁 Projects")

st.write("Aici creezi proiecte de cercetare și experimente/chat-uri pentru fiecare proiect.")

st.divider()

with st.form("create_project_form"):
    st.subheader("Creează un proiect nou")

    name = st.text_input("Nume proiect", placeholder="Chimie Medicală")
    domain = st.text_input("Domeniu", placeholder="Chimie")
    description = st.text_area("Descriere proiect", placeholder="Scopul general al proiectului...")

    submitted = st.form_submit_button("Creează proiect")

    if submitted:
        if not name.strip():
            st.error("Numele proiectului este obligatoriu.")
        elif not domain.strip():
            st.error("Domeniul este obligatoriu.")
        else:
            create_project(
                name=name.strip(),
                domain=domain.strip(),
                description=description.strip()
            )

            st.success("Proiectul a fost creat.")
            st.rerun()

st.divider()

st.subheader("Proiecte existente")
projects = get_projects()

if not projects:
    st.info("Nu există proiecte încă.")
else:
    for project in projects:
        with st.expander(f"{project['name']} — {project['domain']}"):
            st.write("**Descriere:**")
            st.write(project["description"] if project["description"] else "Fără descriere.")

            st.caption(f"Creat la: {project['created_at']}")

            with st.expander(f"🗑️ Șterge proiectul: {project['name']}"):
                st.error(
                    "Atenție! Această acțiune va șterge definitiv proiectul, "
                    "toate experimentele, toate notițele, transcrierile audio, "
                    "rezumatele, ideile principale, mindmap-ul și fișierele audio asociate."
                )

                confirm_delete_project = st.checkbox(
                    "Confirm că vreau să șterg definitiv acest proiect",
                    key=f"confirm_delete_project_{project['id']}"
                )

                if st.button(
                    "Șterge proiectul",
                    key=f"delete_project_{project['id']}",
                    disabled=not confirm_delete_project
                ):
                    audio_paths = get_audio_file_paths_by_project(project["id"])

                    for audio_path in audio_paths:
                        delete_audio_file(audio_path)

                    delete_project(project["id"])

                    st.success("Proiectul a fost șters.")
                    st.rerun()

            st.divider()

            st.write("### Experimente / Chat-uri")

            chats = get_chats(project["id"])

            if not chats:
                st.info("Acest proiect nu are încă experimente.")
            else:
                for chat in chats:
                    with st.container():
                        st.write(f"🧪 **{chat['title']}**")

                        if chat["objective"]:
                            st.caption(chat["objective"])

                        st.caption(f"Creat la: {chat['created_at']}")

                        with st.expander(f"🗑️ Șterge experimentul: {chat['title']}"):
                            st.warning(
                                "Această acțiune va șterge experimentul, toate notițele lui, "
                                "transcrierile audio, rezumatele asociate și fișierele audio salvate local."
                            )

                            confirm_delete_chat = st.checkbox(
                                "Confirm că vreau să șterg acest experiment",
                                key=f"confirm_delete_chat_{chat['id']}"
                            )

                            if st.button(
                                "Șterge experimentul",
                                key=f"delete_chat_{chat['id']}",
                                disabled=not confirm_delete_chat
                            ):
                                audio_paths = get_audio_file_paths_by_chat(chat["id"])

                                for audio_path in audio_paths:
                                    delete_audio_file(audio_path)

                                delete_chat(chat["id"])

                                st.success("Experimentul a fost șters.")
                                st.rerun()

                        st.divider()


            with st.form(f"create_chat_form_{project['id']}"):
                st.write("### Adaugă experiment/chat nou")

                chat_title = st.text_input(
                    "Titlu experiment",
                    placeholder="Experiment 1 — Test compus A",
                    key=f"chat_title_{project['id']}"
                )

                objective = st.text_area(
                    "Obiectiv experiment",
                    placeholder="Ce urmărește cercetătorul în acest experiment?",
                    key=f"objective_{project['id']}"
                )

                chat_submitted = st.form_submit_button("Adaugă experiment")

                if chat_submitted:
                    if not chat_title.strip():
                        st.error("Titlul experimentului este obligatoriu.")
                    else:
                        create_chat(
                            project_id=project["id"],
                            title=chat_title.strip(),
                            objective=objective.strip()
                        )

                        st.success("Experimentul a fost creat.")
                        st.rerun()