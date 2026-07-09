import streamlit as st

from services.openalex_service import search_works


st.title("🔎 Căutare bibliografie")

st.write("""
Prima versiune: cauți manual lucrări științifice în OpenAlex.
După ce verificăm că funcționează, vom lega căutarea de datele proiectului și de Gemini.
""")

query = st.text_input(
    "Caută lucrări științifice",
    placeholder="Ex: medicinal chemistry thermal stability bioactive compounds"
)

per_page = st.slider(
    "Număr rezultate",
    min_value=5,
    max_value=25,
    value=10,
    step=5
)

if st.button("Caută în OpenAlex"):
    if not query.strip():
        st.error("Scrie un termen de căutare.")
    else:
        with st.spinner("Se caută lucrări în OpenAlex..."):
            try:
                data = search_works(
                    query=query.strip(),
                    per_page=per_page
                )

                st.session_state["bibliography_results"] = data["results"]
                st.session_state["bibliography_meta"] = data["meta"]

            except Exception as e:
                st.error(f"A apărut o eroare la căutare: {e}")

if "bibliography_meta" in st.session_state:
    meta = st.session_state["bibliography_meta"]

    if meta:
        st.caption(
            f"Total rezultate găsite în OpenAlex: {meta.get('count', 'necunoscut')}"
        )

if "bibliography_results" in st.session_state:
    results = st.session_state["bibliography_results"]

    if not results:
        st.info("Nu au fost găsite rezultate.")
    else:
        st.subheader("Rezultate")

        for index, work in enumerate(results, start=1):
            with st.container(border=True):
                st.markdown(f"### {index}. {work['title']}")

                st.write(f"**Autori:** {work['authors'] or 'Nespecificat'}")
                st.write(f"**An:** {work['publication_year'] or 'Nespecificat'}")
                st.write(f"**Sursă:** {work['source_name'] or 'Nespecificat'}")
                st.write(f"**Citări:** {work['cited_by_count']}")
                st.write(
                    f"**Open Access:** {'Da' if work['is_open_access'] else 'Nu'}"
                )

                if work["doi"]:
                    st.write(f"**DOI:** {work['doi']}")

                if work["url"]:
                    st.link_button("Deschide lucrarea", work["url"])

                if work["abstract"]:
                    with st.expander("Vezi abstract"):
                        st.write(work["abstract"])
                else:
                    st.caption("Nu există abstract disponibil în OpenAlex.")