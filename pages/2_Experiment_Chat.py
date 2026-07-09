import streamlit as st

from db.database import init_db
from db.queries import (
    get_projects,
    get_chats,
    get_messages,
    add_message,
    create_audio_record,
    get_audio_records,
    update_message_content,
    update_audio_transcript_by_message_id,
    get_audio_record_by_message_id,
    delete_audio_record_by_message_id,
    delete_message
)
from services.transcription_service import (
    save_audio_file,
    transcribe_audio,
    delete_audio_file
)

init_db()

st.title("💬 Experiment Chat")

st.write("Aici alegi un proiect și un experiment, apoi adaugi notițe text sau audio.")

projects = get_projects()

if not projects:
    st.warning("Nu există proiecte. Creează mai întâi un proiect în pagina Projects.")
    st.stop()

project_options = {
    f"{project['name']} — {project['domain']}": project["id"]
    for project in projects
}

selected_project_label = st.selectbox(
    "Alege proiectul",
    list(project_options.keys())
)

selected_project_id = project_options[selected_project_label]

chats = get_chats(selected_project_id)

if not chats:
    st.warning("Acest proiect nu are experimente. Creează un experiment în pagina Projects.")
    st.stop()

chat_options = {
    chat["title"]: chat["id"]
    for chat in chats
}

selected_chat_label = st.selectbox(
    "Alege experimentul/chat-ul",
    list(chat_options.keys())
)

selected_chat_id = chat_options[selected_chat_label]

selected_chat = None

for chat in chats:
    if chat["id"] == selected_chat_id:
        selected_chat = chat
        break

st.divider()

st.subheader(f"🧪 {selected_chat['title']}")

if selected_chat["objective"]:
    st.write("**Obiectiv:**")
    st.write(selected_chat["objective"])

st.caption(f"Creat la: {selected_chat['created_at']}")

st.divider()

#------------                 -----------------------------
st.subheader("Istoric notițe")

messages = get_messages(selected_chat_id)

if not messages:
    st.info("Nu există notițe încă pentru acest experiment.")
else:
    for message in messages:
        with st.chat_message("user"):

            if message["type"] == "audio_transcript":
                st.markdown("🎙️ **Transcriere audio:**")
                st.write(message["content"])
                st.caption(f"{message['type']} · {message['created_at']}")

                with st.expander("✏️ Corectează transcrierea audio"):
                    with st.form(f"edit_audio_transcript_form_{message['id']}"):
                        edited_transcript = st.text_area(
                            "Transcriere corectată",
                            value=message["content"],
                            height=160,
                            key=f"edited_transcript_{message['id']}"
                        )

                        submitted_edit = st.form_submit_button("Salvează corectarea")

                        if submitted_edit:
                            if not edited_transcript.strip():
                                st.error("Transcrierea nu poate fi goală.")
                            else:
                                update_message_content(
                                    message_id=message["id"],
                                    new_content=edited_transcript.strip()
                                )

                                update_audio_transcript_by_message_id(
                                    message_id=message["id"],
                                    new_transcript=edited_transcript.strip()
                                )

                                st.success("Transcrierea audio a fost actualizată.")
                                st.rerun()

                with st.expander("🗑️ Șterge transcrierea audio"):
                    st.warning(
                        "Această acțiune va șterge transcrierea din chat, "
                        "înregistrarea din baza de date și fișierul audio salvat local."
                    )

                    confirm_delete_audio = st.checkbox(
                        "Confirm că vreau să șterg această transcriere audio",
                        key=f"confirm_delete_audio_{message['id']}"
                    )

                    if st.button(
                        "Șterge transcrierea audio",
                        key=f"delete_audio_{message['id']}",
                        disabled=not confirm_delete_audio
                    ):
                        audio_record = get_audio_record_by_message_id(message["id"])

                        if audio_record:
                            delete_audio_file(audio_record["file_path"])
                            delete_audio_record_by_message_id(message["id"])

                        delete_message(message["id"])

                        st.success("Transcrierea audio a fost ștearsă.")
                        st.rerun()

            elif message["type"] == "text":
                st.markdown("📝 **Notiță text:**")
                st.write(message["content"])
                st.caption(f"{message['type']} · {message['created_at']}")

                with st.expander("✏️ Modifică notița text"):
                    with st.form(f"edit_text_note_form_{message['id']}"):
                        edited_note = st.text_area(
                            "Notiță modificată",
                            value=message["content"],
                            height=160,
                            key=f"edited_note_{message['id']}"
                        )

                        submitted_note_edit = st.form_submit_button("Salvează modificarea")

                        if submitted_note_edit:
                            if not edited_note.strip():
                                st.error("Notița nu poate fi goală.")
                            else:
                                update_message_content(
                                    message_id=message["id"],
                                    new_content=edited_note.strip()
                                )

                                st.success("Notița text a fost actualizată.")
                                st.rerun()

                with st.expander("🗑️ Șterge notița text"):
                    st.warning("Această acțiune va șterge definitiv notița din chat.")

                    confirm_delete_note = st.checkbox(
                        "Confirm că vreau să șterg această notiță",
                        key=f"confirm_delete_note_{message['id']}"
                    )

                    if st.button(
                        "Șterge notița text",
                        key=f"delete_text_note_{message['id']}",
                        disabled=not confirm_delete_note
                    ):
                        delete_message(message["id"])

                        st.success("Notița text a fost ștearsă.")
                        st.rerun()

            else:
                st.write(message["content"])
                st.caption(f"{message['type']} · {message['created_at']}")

st.divider()
#---------------------------------------------------------

st.subheader("✍️ Adaugă notiță text")

with st.form("add_text_note_form"):
    note = st.text_area(
        "Scrie o observație nouă despre experiment",
        placeholder="Ex: Am observat că soluția și-a schimbat culoarea după încălzire..."
    )

    submitted_note = st.form_submit_button("Salvează notița")

    if submitted_note:
        if not note.strip():
            st.error("Notița nu poate fi goală.")
        else:
            add_message(
                chat_id=selected_chat_id,
                role="user",
                message_type="text",
                content=note.strip()
            )

            st.success("Notița a fost salvată.")
            st.rerun()

st.divider()
#---------------------------------------------------------
st.subheader("🎙️ Înregistrare audio")

st.write("""
Înregistrează o observație audio. După înregistrare, va fi transcrisă și adăugată în istoricul chat-ului.
""")

language_option = st.selectbox(
    "Limba transcrierii",
    ["auto", "ro", "en"],
    help="Alege auto pentru detectare automată, ro pentru română, en pentru engleză."
)

audio_file = st.audio_input("Înregistrează observația audio")

if audio_file is not None:
    st.audio(audio_file)

    if st.button("Salvează audio și transcrie"):
        with st.spinner("Se salvează fișierul audio..."):
            audio_path = save_audio_file(audio_file, selected_chat_id)

        selected_language = None if language_option == "auto" else language_option

        with st.spinner("Se transcrie audio-ul local..."):
            transcript = transcribe_audio(
                audio_path=audio_path,
                language=selected_language
            )

        if not transcript:
            st.error("Nu s-a putut obține o transcriere.")
        else:
            message_id = add_message(
                chat_id=selected_chat_id,
                role="user",
                message_type="audio_transcript",
                content=transcript
            )

            create_audio_record(
                chat_id=selected_chat_id,
                message_id=message_id,
                file_path=audio_path,
                transcript=transcript
            )

            st.success("Audio-ul a fost salvat, transcris și adăugat în chat.")
            st.rerun()

st.divider()
#---------------------------------------------------------
st.subheader("Fișiere audio salvate")

audio_records = get_audio_records(selected_chat_id)

if not audio_records:
    st.caption("Nu există încă fișiere audio salvate pentru acest experiment.")
else:
    for record in audio_records:
        st.write(f"🎧 `{record['file_path']}`")
        st.caption(f"Creat la: {record['created_at']}")

        if record["transcript"]:
            with st.expander("Vezi transcrierea"):
                st.write(record["transcript"])