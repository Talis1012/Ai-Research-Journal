import streamlit as st

from db.database import init_db
from db.queries import get_project_ideas, get_project_messages, get_projects
from services.bibliography_service import generate_bibliography_search_profile
from services.openalex_service import search_works, search_works_for_queries
from utils.ui import load_css, page_brand_header, render_html, sidebar_nav


def render_results(results, *, include_matched_query=False):
    if not results:
        st.info("Nu au fost găsite rezultate.")
        return

    for index, work in enumerate(results, start=1):
        with st.container(border=True):
            st.markdown(f"### {index}. {work['title']}")

            if include_matched_query:
                st.write(
                    "**Query care a găsit lucrarea:** "
                    f"{work.get('matched_query', 'Nespecificat')}"
                )

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


init_db()
load_css()
page_brand_header()

render_html(
    """
    <style>
    .bibliography-manual-column,
    .bibliography-project-column {
        display: none;
    }

    div[data-testid="stHorizontalBlock"]:has(
        > div[data-testid="column"]:first-child .bibliography-manual-column
    ) {
        gap: 0 !important;
        align-items: stretch;
    }

    div[data-testid="stHorizontalBlock"]:has(
        > div[data-testid="column"]:first-child .bibliography-manual-column
    ) > div[data-testid="column"]:first-child {
        padding: 0 30px 36px 0 !important;
        border-right: 1px solid var(--line);
    }

    div[data-testid="stHorizontalBlock"]:has(
        > div[data-testid="column"]:first-child .bibliography-manual-column
    ) > div[data-testid="column"]:last-child {
        padding: 0 0 36px 30px !important;
    }

    @media (max-width: 900px) {
        div[data-testid="stHorizontalBlock"]:has(
            > div[data-testid="column"]:first-child .bibliography-manual-column
        ) {
            flex-direction: column;
        }

        div[data-testid="stHorizontalBlock"]:has(
            > div[data-testid="column"]:first-child .bibliography-manual-column
        ) > div[data-testid="column"] {
            width: 100% !important;
            flex: 1 1 100% !important;
        }

        div[data-testid="stHorizontalBlock"]:has(
            > div[data-testid="column"]:first-child .bibliography-manual-column
        ) > div[data-testid="column"]:first-child {
            padding: 0 0 28px 0 !important;
            border-right: 0;
            border-bottom: 1px solid var(--line);
        }

        div[data-testid="stHorizontalBlock"]:has(
            > div[data-testid="column"]:first-child .bibliography-manual-column
        ) > div[data-testid="column"]:last-child {
            padding: 28px 0 36px 0 !important;
        }
    }
    </style>
    """
)

nav_col, main_col = st.columns([1.05, 5.3], gap="small")

with nav_col:
    sidebar_nav("bibliography")

with main_col:
    st.title("🔎 Căutare bibliografie")

    manual_col, project_col = st.columns(2)

    with manual_col:
        render_html('<div class="bibliography-manual-column"></div>')

        st.subheader("Căutare manuală")
        st.write("Caută direct lucrări științifice în OpenAlex.")

        query = st.text_input(
            "Caută lucrări științifice (query-ul trebuie să fie în engleză)",
            placeholder="Ex: medicinal chemistry thermal stability bioactive compounds",
            key="manual_bibliography_query",
        )

        per_page = st.slider(
            "Număr rezultate",
            min_value=5,
            max_value=25,
            value=10,
            step=5,
            key="manual_bibliography_per_page",
        )

        if st.button("Caută în OpenAlex", key="manual_bibliography_search"):
            if not query.strip():
                st.error("Scrie un termen de căutare.")
            else:
                with st.spinner("Se caută lucrări în OpenAlex..."):
                    try:
                        data = search_works(
                            query=query.strip(),
                            per_page=per_page,
                        )

                        st.session_state["manual_bibliography_results"] = data[
                            "results"
                        ]
                        st.session_state["manual_bibliography_meta"] = data["meta"]

                    except Exception as exc:
                        st.error(f"A apărut o eroare la căutare: {exc}")

        manual_meta = st.session_state.get("manual_bibliography_meta")

        if manual_meta:
            st.caption(
                "Total rezultate găsite în OpenAlex: "
                f"{manual_meta.get('count', 'necunoscut')}"
            )

        if "manual_bibliography_results" in st.session_state:
            st.divider()
            st.subheader("Rezultate")
            render_results(st.session_state["manual_bibliography_results"])

    with project_col:
        render_html('<div class="bibliography-project-column"></div>')

        st.subheader("Căutare după proiect")
        st.write(
            "Alege un proiect, iar aplicația va folosi notițele și ideile "
            "principale pentru a genera query-uri în engleză."
        )

        projects = get_projects()

        if not projects:
            st.warning("Nu există proiecte. Creează mai întâi un proiect.")
        else:
            project_options = {
                f"{project['name']} — {project['domain']}": project
                for project in projects
            }

            selected_project_label = st.selectbox(
                "Alege proiectul",
                list(project_options.keys()),
                key="bibliography_project_selector",
            )

            selected_project = project_options[selected_project_label]
            selected_project_id = selected_project["id"]
            project_messages = get_project_messages(selected_project_id)
            project_ideas = get_project_ideas(selected_project_id)

            st.subheader("Date folosite")
            st.write(f"**Proiect:** {selected_project['name']}")
            st.write(f"**Domeniu:** {selected_project['domain']}")
            st.write(f"**Notițe / mesaje:** {len(project_messages)}")
            st.write(f"**Idei principale:** {len(project_ideas)}")

            st.subheader("Generare query-uri")
            st.write(
                "Gemini va citi notițele proiectului și va propune query-uri "
                "în engleză pentru căutarea de lucrări similare."
            )

            if not project_messages:
                st.warning(
                    "Acest proiect nu are încă notițe. Adaugă notițe înainte "
                    "de căutare."
                )
            elif st.button(
                "Generează query-uri cu Gemini",
                key="generate_bibliography_queries",
            ):
                with st.spinner(
                    "Gemini analizează proiectul și generează query-uri..."
                ):
                    profile = generate_bibliography_search_profile(
                        project_name=selected_project["name"],
                        project_domain=selected_project["domain"],
                        messages=project_messages,
                        ideas=project_ideas,
                    )

                st.session_state["bibliography_profile"] = profile
                st.session_state["bibliography_profile_project_id"] = (
                    selected_project_id
                )
                st.session_state["bibliography_queries_text"] = "\n".join(
                    profile.get("search_queries", [])
                )
                st.session_state["bibliography_queries_editor"] = st.session_state[
                    "bibliography_queries_text"
                ]
                st.success("Query-urile au fost generate.")

            profile_belongs_to_project = (
                st.session_state.get("bibliography_profile_project_id")
                == selected_project_id
            )

            if (
                "bibliography_profile" in st.session_state
                and profile_belongs_to_project
            ):
                profile = st.session_state["bibliography_profile"]

                st.divider()
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

                st.subheader("Query-uri pentru OpenAlex")

                if "bibliography_queries_editor" not in st.session_state:
                    st.session_state["bibliography_queries_editor"] = (
                        st.session_state.get("bibliography_queries_text", "")
                    )

                queries_text = st.text_area(
                    "Poți modifica query-urile înainte de căutare. Scrie un "
                    "query pe fiecare linie.",
                    height=160,
                    key="bibliography_queries_editor",
                )

                per_query = st.slider(
                    "Rezultate per query",
                    min_value=3,
                    max_value=15,
                    value=5,
                    step=1,
                    key="project_bibliography_per_query",
                )

                if st.button(
                    "Caută lucrări în OpenAlex",
                    key="project_bibliography_search",
                ):
                    queries = [
                        line.strip()
                        for line in queries_text.splitlines()
                        if line.strip()
                    ]

                    if not queries:
                        st.error("Nu există niciun query valid.")
                    else:
                        st.session_state["bibliography_queries_text"] = "\n".join(
                            queries
                        )

                        with st.spinner("Se caută lucrări în OpenAlex..."):
                            try:
                                results = search_works_for_queries(
                                    queries=queries,
                                    per_page=per_query,
                                )

                                st.session_state[
                                    "project_bibliography_results"
                                ] = results
                                st.session_state[
                                    "project_bibliography_results_project_id"
                                ] = selected_project_id
                                st.success(
                                    f"Au fost găsite {len(results)} rezultate unice."
                                )

                            except Exception as exc:
                                st.error(
                                    "A apărut o eroare la căutarea în OpenAlex: "
                                    f"{exc}"
                                )

            results_belong_to_project = (
                st.session_state.get(
                    "project_bibliography_results_project_id"
                )
                == selected_project_id
            )

            if (
                "project_bibliography_results" in st.session_state
                and results_belong_to_project
            ):
                st.divider()
                st.subheader("Rezultate OpenAlex")
                render_results(
                    st.session_state["project_bibliography_results"],
                    include_matched_query=True,
                )
