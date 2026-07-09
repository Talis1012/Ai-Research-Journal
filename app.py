import streamlit as st

from db.database import init_db


st.set_page_config(
    page_title="Research Journal AI",
    page_icon="🧪",
    layout="wide"
)

init_db()

st.title("🧪 Research Journal AI")

st.write("""
Bine ai venit în aplicația de jurnal AI pentru cercetare.

Momentan sunt implementate:
- creare proiecte;
- creare chat-uri / experimente;
- adăugare notițe text;
- adăugare notițe audio + transcriere;
- afișare istoric notițe;
- modificare si stergere notite;
- rezumat pentru un chat;
- rezumat pentru un proiect;
- idei principale dintr-un proiect.
""")

st.info("Folosește meniul din stânga pentru a intra în Projects sau Experiment Chat.")