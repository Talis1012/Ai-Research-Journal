import streamlit as st

from services.openalex_service import search_works
from db.database import init_db
from db.queries import (
    get_projects,
    get_project_messages,
    get_project_ideas
)
from services.bibliography_service import generate_bibliography_search_profile
from services.openalex_service import search_works_for_queries

st.title("🔎 Căutare bibliografie")

st.write("""
Căutare manuală pentru lucrări științifice în OpenAlex.
""")

query = st.text_input(
    "Caută lucrări știintifice (query-ul trebuie in engleză)",
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

st.divider()
st.write("""
Alege un proiect, iar aplicația va folosi notițele și ideile principale pentru a genera
query-uri în engleză. Apoi query-urile sunt folosite pentru a căuta lucrări științifice în OpenAlex.
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

col1, col2 = st.columns(2)

with col1:
    st.subheader("Date folosite")

    st.write(f"**Proiect:** {selected_project['name']}")
    st.write(f"**Domeniu:** {selected_project['domain']}")
    st.write(f"**Notițe / mesaje:** {len(project_messages)}")
    st.write(f"**Idei principale:** {len(project_ideas)}")

with col2:
    st.subheader("Generare query-uri")

    st.write("""
    Gemini va citi notițele proiectului și va propune query-uri în engleză
    pentru căutarea de lucrări similare.
    """)

    if not project_messages:
        st.warning("Acest proiect nu are încă notițe. Adaugă notițe înainte de căutare.")
    else:
        if st.button("Generează query-uri cu Gemini"):
            with st.spinner("Gemini analizează proiectul și generează query-uri..."):
                profile = generate_bibliography_search_profile(
                    project_name=selected_project["name"],
                    project_domain=selected_project["domain"],
                    messages=project_messages,
                    ideas=project_ideas
                )

            st.session_state["bibliography_profile"] = profile
            st.session_state["bibliography_queries_text"] = "\n".join(
                profile.get("search_queries", [])
            )

            st.success("Query-urile au fost generate.")

st.divider()

if "bibliography_profile" in st.session_state:
    profile = st.session_state["bibliography_profile"]

    st.subheader("Profil de căutare generat")

    st.write("**Tema cercetării:**")
    st.write(profile.get("research_topic", ""))

    st.write("**Descriere scurtă:**")
    st.write(profile.get("short_description", ""))

    keywords = profile.get("keywords", [])

    if keywords:
        st.write("**Keywords:**")
        st.write(", ".join(keywords))

    exclude_terms = profile.get("exclude_terms", [])

    if exclude_terms:
        st.write("**Termeni de evitat:**")
        st.write(", ".join(exclude_terms))

    st.divider()

    st.subheader("Query-uri pentru OpenAlex")

    queries_text = st.text_area(
        "Poți modifica query-urile înainte de căutare. Scrie un query pe fiecare linie.",
        value=st.session_state.get("bibliography_queries_text", ""),
        height=160
    )

    per_query = st.slider(
        "Rezultate per query",
        min_value=3,
        max_value=15,
        value=5,
        step=1
    )

    if st.button("Caută lucrări în OpenAlex"):
        queries = [
            line.strip()
            for line in queries_text.splitlines()
            if line.strip()
        ]

        if not queries:
            st.error("Nu există niciun query valid.")
        else:
            st.session_state["bibliography_queries_text"] = "\n".join(queries)

            with st.spinner("Se caută lucrări în OpenAlex..."):
                try:
                    results = search_works_for_queries(
                        queries=queries,
                        per_page=per_query
                    )

                    st.session_state["bibliography_results"] = results

                    st.success(f"Au fost găsite {len(results)} rezultate unice.")

                except Exception as e:
                    st.error(f"A apărut o eroare la căutarea în OpenAlex: {e}")

st.divider()

if "bibliography_results" in st.session_state:
    results = st.session_state["bibliography_results"]

    st.subheader("Rezultate OpenAlex")

    if not results:
        st.info("Nu au fost găsite rezultate.")
    else:
        for index, work in enumerate(results, start=1):
            with st.container(border=True):
                st.markdown(f"### {index}. {work['title']}")

                st.write(f"**Query care a găsit lucrarea:** {work.get('matched_query', 'Nespecificat')}")
                st.write(f"**Autori:** {work['authors'] or 'Nespecificat'}")
                st.write(f"**An:** {work['publication_year'] or 'Nespecificat'}")
                st.write(f"**Sursă:** {work['source_name'] or 'Nespecificat'}")
                st.write(f"**Citări:** {work['cited_by_count']}")
                st.write(f"**Open Access:** {'Da' if work['is_open_access'] else 'Nu'}")

                if work["doi"]:
                    st.write(f"**DOI:** {work['doi']}")

                if work["url"]:
                    st.link_button("Deschide lucrarea", work["url"])

                if work["abstract"]:
                    with st.expander("Vezi abstract"):
                        st.write(work["abstract"])
                else:
                    st.caption("Nu există abstract disponibil în OpenAlex.")