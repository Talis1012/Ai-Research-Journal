import math
from datetime import datetime

import streamlit as st
from streamlit_agraph import agraph, Config, Edge, Node

from db.database import DatabaseIntegrityError, init_db_once
from db.discovery_queries import (
    get_latest_project_discovery_results,
    get_project_discovery_results,
    replace_project_discovery_results,
)
from db.library_queries import (
    LIBRARY_ITEM_TYPES,
    LIBRARY_STATUSES,
    create_library_folder,
    create_library_item,
    delete_library_folder,
    delete_library_item,
    find_library_item_by_external_ids,
    get_library_external_keys,
    get_library_folders,
    get_library_item,
    get_library_item_count,
    get_library_items,
    get_library_stats,
    move_library_items,
    normalize_doi,
    normalize_openalex_id,
    rename_library_folder,
    update_library_item,
)
from db.research_case_queries import (
    get_project_research_cases,
    get_research_case,
)
from db.queries import get_project_ideas, get_project_messages, get_projects
from services.library_service import (
    delete_library_file,
    read_library_file,
    save_library_upload,
    validate_library_upload_batch,
)
from services.research_case_service import (
    generate_project_research_cases,
    generate_research_case_for_item,
    get_research_case_coverage,
    is_research_case_current,
    recommend_relevant_experiments,
    research_case_to_mindmap,
)
from utils.auth import authenticated_callback, require_auth
from utils.content_safety import safe_external_url, sanitize_untrusted_markdown
from utils.query_cache import cached_read
from utils.ui import (
    chat_message,
    compact_date,
    header_icons,
    load_css,
    render_html,
    render_untrusted_caption,
    render_untrusted_markdown,
    safe_html,
    sidebar_nav,
    top_brand,
)


st.set_page_config(
    page_title="Library · Research Journal AI",
    page_icon="📚",
    layout="wide",
)

require_auth()
init_db_once(st.session_state)
load_css()


TYPE_LABELS = {
    "paper": "Paper",
    "pdf": "PDF",
    "dataset": "Dataset",
    "audio": "Audio",
    "document": "Document",
    "other": "Other",
}

TYPE_ICONS = {
    "paper": "▤",
    "pdf": "PDF",
    "dataset": "▦",
    "audio": "◉",
    "document": "▧",
    "other": "◇",
}


def render_page_css():
    render_html(
        """
        <style>
        .library-page-scope,
        .library-folders-scope,
        .library-list-scope,
        .library-details-scope {
            display: none;
        }

        div[data-testid="column"]:has(.library-page-scope) {
            min-height: calc(100vh - var(--topbar-h));
            padding: 22px 26px 36px !important;
            background: #ffffff;
        }

        div[data-testid="column"]:has(.library-page-scope)
        > div[data-testid="stVerticalBlock"] {
            gap: 0.72rem;
        }

        .library-context {
            min-height: var(--topbar-h);
            display: flex;
            align-items: center;
            gap: 10px;
            color: #344054;
            font-size: 0.88rem;
            font-weight: 780;
        }

        .library-context-icon {
            width: 32px;
            height: 32px;
            border: 1px solid #dfe6ef;
            border-radius: 8px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: #f8fbff;
            color: #1769d2;
        }

        .library-heading {
            color: #101828;
            font-size: 1.85rem;
            font-weight: 880;
            line-height: 1.08;
            padding-top: 4px;
        }

        .library-subtitle {
            color: #667085;
            font-size: 0.9rem;
            margin-top: 7px;
        }

        div[data-testid="column"]:has(.library-folders-scope),
        div[data-testid="column"]:has(.library-list-scope),
        div[data-testid="column"]:has(.library-details-scope) {
            min-height: 720px;
            border: 1px solid #dfe6ef;
            background: #ffffff;
            box-shadow: 0 8px 22px rgba(16, 24, 40, 0.045);
            padding: 16px !important;
        }

        div[data-testid="column"]:has(.library-folders-scope) {
            border-radius: 9px 0 0 9px;
        }

        div[data-testid="column"]:has(.library-list-scope) {
            border-left: 0;
            border-right: 0;
        }

        div[data-testid="column"]:has(.library-details-scope) {
            border-radius: 0 9px 9px 0;
        }

        div[data-testid="column"]:has(.library-folders-scope)
        > div[data-testid="stVerticalBlock"],
        div[data-testid="column"]:has(.library-list-scope)
        > div[data-testid="stVerticalBlock"],
        div[data-testid="column"]:has(.library-details-scope)
        > div[data-testid="stVerticalBlock"] {
            gap: 0.6rem;
        }

        .library-panel-title {
            color: #101828;
            font-size: 0.98rem;
            font-weight: 850;
        }

        .library-panel-caption {
            color: #667085;
            font-size: 0.76rem;
            line-height: 1.42;
            margin-top: 3px;
        }

        .library-section-label {
            color: #8a95a8;
            font-size: 0.67rem;
            font-weight: 850;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin: 8px 0 2px;
        }

        .library-item-icon {
            width: 42px;
            height: 42px;
            border-radius: 9px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #eaf3ff;
            color: #1769d2;
            font-size: 0.76rem;
            font-weight: 900;
            margin-top: 2px;
        }

        .library-item-title {
            color: #101828;
            font-size: 0.9rem;
            font-weight: 820;
            line-height: 1.32;
            margin-top: 2px;
        }

        .library-item-meta {
            color: #667085;
            font-size: 0.72rem;
            line-height: 1.45;
            margin-top: 4px;
        }

        .library-status {
            display: inline-flex;
            border-radius: 999px;
            padding: 3px 8px;
            font-size: 0.66rem;
            font-weight: 800;
            background: #f2f4f7;
            color: #475467;
            margin-top: 4px;
        }

        .library-empty {
            min-height: 300px;
            border: 1px dashed #cfd9e6;
            border-radius: 9px;
            background: #fbfdff;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            color: #667085;
            padding: 28px;
        }

        .library-empty-icon {
            width: 52px;
            height: 52px;
            border-radius: 12px;
            background: #eaf3ff;
            color: #1769d2;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.45rem;
            margin-bottom: 12px;
        }

        .library-details-title {
            color: #101828;
            font-size: 1rem;
            font-weight: 850;
            line-height: 1.35;
        }

        .library-details-meta {
            color: #667085;
            font-size: 0.75rem;
            line-height: 1.5;
            margin-top: 5px;
        }

        div[class*="st-key-library_collection_"] button {
            justify-content: flex-start !important;
            text-align: left !important;
            min-height: 36px !important;
            border-color: transparent !important;
            background: transparent !important;
            color: #344054 !important;
            font-size: 0.78rem !important;
        }

        div[class*="st-key-library_collection_"] button:hover {
            border-color: #d7e7fb !important;
            background: #f3f8ff !important;
            color: #1769d2 !important;
        }

        div[class*="st-key-library_collection_active_"] button {
            border-color: #c8ddfa !important;
            background: #eaf3ff !important;
            color: #1769d2 !important;
            font-weight: 820 !important;
        }

        div[class*="st-key-open_library_item_"] button {
            min-width: 36px !important;
            padding-left: 6px !important;
            padding-right: 6px !important;
            font-size: 1rem !important;
        }

        div[class*="st-key-library_search"] div[data-baseweb="input"] {
            min-height: 40px !important;
            border: 1px solid #d8e1ed !important;
            border-radius: 8px !important;
            background: #ffffff !important;
            box-shadow: none !important;
        }

        div[class*="st-key-library_search"] input {
            min-height: 38px !important;
            font-size: 0.78rem !important;
        }

        .discover-results-scope,
        .discover-chat-scope {
            display: none;
        }

        div[data-testid="column"]:has(.discover-results-scope),
        div[data-testid="column"]:has(.discover-chat-scope),
        div[data-testid="stColumn"]:has(.discover-results-scope),
        div[data-testid="stColumn"]:has(.discover-chat-scope) {
            min-height: 760px;
            border: 1px solid #dfe6ef;
            border-radius: 9px;
            background: #ffffff;
            box-shadow: 0 8px 22px rgba(16, 24, 40, 0.045);
            padding: 18px !important;
        }

        div[data-testid="column"]:has(.discover-chat-scope),
        div[data-testid="stColumn"]:has(.discover-chat-scope) {
            position: sticky;
            top: 10px;
            align-self: flex-start;
            min-height: min(760px, calc(100vh - 20px));
            max-height: calc(100vh - 20px);
            overflow-y: auto;
        }

        div[data-testid="column"]:has(.discover-results-scope)
        > div[data-testid="stVerticalBlock"],
        div[data-testid="column"]:has(.discover-chat-scope)
        > div[data-testid="stVerticalBlock"],
        div[data-testid="stColumn"]:has(.discover-results-scope)
        > div[data-testid="stVerticalBlock"],
        div[data-testid="stColumn"]:has(.discover-chat-scope)
        > div[data-testid="stVerticalBlock"] {
            gap: 0.68rem;
        }

        .discover-title {
            color: #101828;
            font-size: 1.04rem;
            font-weight: 860;
            line-height: 1.3;
        }

        .discover-caption {
            color: #667085;
            font-size: 0.78rem;
            line-height: 1.5;
            margin-top: 4px;
        }

        .discover-profile {
            border: 1px solid #cfe0f7;
            border-radius: 9px;
            background: #f5f9ff;
            color: #344054;
            padding: 12px 14px;
            font-size: 0.76rem;
            line-height: 1.5;
        }

        .discover-paper-title {
            color: #101828;
            font-size: 0.95rem;
            font-weight: 850;
            line-height: 1.38;
        }

        .discover-paper-meta {
            color: #667085;
            font-size: 0.72rem;
            line-height: 1.48;
            margin-top: 5px;
        }

        .discover-score {
            width: 52px;
            height: 52px;
            border-radius: 12px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            background: #eaf3ff;
            border: 1px solid #c9def8;
            color: #1769d2;
        }

        .discover-score strong {
            font-size: 1rem;
            line-height: 1;
        }

        .discover-score span {
            font-size: 0.58rem;
            font-weight: 800;
            margin-top: 3px;
            text-transform: uppercase;
        }

        .discover-ai-reason {
            border-left: 3px solid #6aa8ee;
            background: #f7faff;
            color: #344054;
            border-radius: 0 7px 7px 0;
            padding: 9px 11px;
            font-size: 0.75rem;
            line-height: 1.48;
        }

        .discover-chip {
            display: inline-flex;
            padding: 3px 8px;
            margin: 5px 4px 0 0;
            border-radius: 999px;
            background: #eef4ff;
            color: #285f9d;
            font-size: 0.64rem;
            font-weight: 760;
        }

        .discover-chat-context {
            border: 1px solid #d9e5f3;
            border-radius: 8px;
            background: #f8fbff;
            color: #475467;
            padding: 10px 12px;
            font-size: 0.72rem;
            line-height: 1.45;
        }

        .discover-abstract-scroll {
            max-height: 210px;
            overflow-y: auto;
            border: 1px solid #e5eaf1;
            border-radius: 7px;
            background: #fbfcfe;
            color: #344054;
            padding: 11px 12px;
            font-size: 0.76rem;
            line-height: 1.58;
        }

        .recommendations-hero {
            border: 1px solid #cfe0f7;
            border-radius: 12px;
            background: linear-gradient(135deg, #f5f9ff 0%, #fbfdff 100%);
            padding: 16px 18px;
            margin-bottom: 4px;
        }

        .recommendations-hero-title {
            color: #101828;
            font-size: 1.05rem;
            font-weight: 860;
        }

        .recommendations-hero-caption {
            color: #667085;
            font-size: 0.78rem;
            line-height: 1.5;
            margin-top: 4px;
        }

        .recommendation-baseline-note {
            border-left: 3px solid #7d4ad8;
            border-radius: 0 8px 8px 0;
            background: #faf8ff;
            color: #475467;
            font-size: 0.76rem;
            line-height: 1.5;
            padding: 10px 12px;
        }

        .recommendation-template-title {
            color: #101828;
            font-size: 1rem;
            font-weight: 850;
            line-height: 1.35;
        }

        .recommendation-template-meta {
            color: #667085;
            font-size: 0.72rem;
            margin-top: 4px;
        }

        div[class*="st-key-experiment_recommendation_card_"] {
            border-color: #dfe6ef !important;
            box-shadow: 0 4px 12px rgba(16, 24, 40, 0.035);
        }

        div[class*="st-key-discover_result_"] {
            border-color: #dfe6ef !important;
            box-shadow: 0 4px 12px rgba(16, 24, 40, 0.035);
        }

        @media (max-width: 1100px) {
            div[data-testid="stHorizontalBlock"]:has(.library-folders-scope) {
                flex-direction: column;
            }

            div[data-testid="column"]:has(.library-folders-scope),
            div[data-testid="column"]:has(.library-list-scope),
            div[data-testid="column"]:has(.library-details-scope) {
                width: 100% !important;
                flex: 1 1 100% !important;
                min-height: auto;
                border: 1px solid #dfe6ef;
                border-radius: 9px;
            }

            div[data-testid="stHorizontalBlock"]:has(.discover-results-scope) {
                flex-direction: column;
            }

            div[data-testid="column"]:has(.discover-results-scope),
            div[data-testid="column"]:has(.discover-chat-scope),
            div[data-testid="stColumn"]:has(.discover-results-scope),
            div[data-testid="stColumn"]:has(.discover-chat-scope) {
                width: 100% !important;
                flex: 1 1 100% !important;
                min-height: auto;
                position: static;
                max-height: none;
                overflow-y: visible;
            }
        }
        </style>
        """
    )


def folder_paths(folders) -> dict[int, str]:
    by_id = {folder["id"]: folder for folder in folders}
    paths = {}

    def build_path(folder_id: int, visited: set[int] | None = None) -> str:
        if folder_id in paths:
            return paths[folder_id]

        visited = set(visited or ())

        if folder_id in visited:
            return by_id[folder_id]["name"]

        visited.add(folder_id)
        folder = by_id[folder_id]
        parent_id = folder["parent_id"]
        path = folder["name"]

        if parent_id in by_id:
            path = f"{build_path(parent_id, visited)} / {path}"

        paths[folder_id] = path
        return path

    for folder_id in by_id:
        build_path(folder_id)

    return paths


def folder_descendant_ids(folders, folder_id: int) -> set[int]:
    descendants = {folder_id}
    changed = True

    while changed:
        changed = False

        for folder in folders:
            if folder["parent_id"] in descendants and folder["id"] not in descendants:
                descendants.add(folder["id"])
                changed = True

    return descendants


def split_tags(value: str) -> list[str]:
    return [tag.strip() for tag in value.split(",") if tag.strip()]


def project_ids_from_row(item) -> list[int]:
    return [
        int(project_id)
        for project_id in str(item["project_ids"] or "").split(",")
        if project_id.strip()
    ]


def format_file_size(file_size: int | None) -> str:
    size = int(file_size or 0)

    if size < 1024:
        return f"{size} B"

    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"

    return f"{size / (1024 * 1024):.1f} MB"


def render_collection_button(label: str, collection_key: str, button_key: str):
    selected = st.session_state.get("library_collection", "all") == collection_key
    container_key = (
        f"library_collection_active_{button_key}"
        if selected
        else f"library_collection_{button_key}"
    )

    with st.container(key=container_key):
        if st.button(label, key=f"collection_button_{button_key}", width="stretch"):
            st.session_state["library_collection"] = collection_key
            st.session_state["library_page_number"] = 1
            st.rerun()


def render_folder_tree(folders, parent_id: int | None = None, depth: int = 0):
    children = sorted(
        [folder for folder in folders if folder["parent_id"] == parent_id],
        key=lambda folder: folder["name"].casefold(),
    )

    for folder in children:
        prefix = "↳ " * depth
        render_collection_button(
            f"{prefix}📁 {folder['name']}  ·  {folder['item_count']}",
            f"folder:{folder['id']}",
            f"folder_{folder['id']}",
        )
        render_folder_tree(folders, folder["id"], depth + 1)


def selected_folder_id() -> int | None:
    collection = st.session_state.get("library_collection", "all")

    if collection.startswith("folder:"):
        return int(collection.split(":", 1)[1])

    return None


def render_add_controls(folders, projects, paths):
    upload_col, paper_col = st.columns(2, gap="small")
    folder_options = [None, *[folder["id"] for folder in folders]]
    project_options = [project["id"] for project in projects]
    projects_by_id = {project["id"]: project for project in projects}
    initial_folder_id = selected_folder_id()
    initial_folder_index = (
        folder_options.index(initial_folder_id)
        if initial_folder_id in folder_options
        else 0
    )

    with upload_col:
        with st.popover("↑ Upload files", width="stretch"):
            st.caption(
                "PDFs, documents, datasets, or audio · max. 10 files, "
                "25 MB each, 100 MB per batch"
            )

            with st.form("library_upload_form", clear_on_submit=True):
                uploads = st.file_uploader(
                    "Choose files",
                    accept_multiple_files=True,
                    key="library_file_upload",
                )
                folder_id = st.selectbox(
                    "Add to folder",
                    folder_options,
                    index=initial_folder_index,
                    key=f"library_upload_folder_{initial_folder_id or 'unfiled'}",
                    format_func=lambda value: (
                        paths[value] if value is not None else "Unfiled"
                    ),
                )
                status = st.selectbox("Reading status", LIBRARY_STATUSES)
                tags = st.text_input(
                    "Tags",
                    placeholder="e.g. synthesis, review",
                )
                project_ids = st.multiselect(
                    "Link to projects",
                    project_options,
                    format_func=lambda value: projects_by_id[value]["name"],
                )
                submitted = st.form_submit_button(
                    "Add to My Library",
                    width="stretch",
                )

            if submitted:
                if not uploads:
                    st.error("Choose at least one file.")
                else:
                    try:
                        validated_uploads = validate_library_upload_batch(uploads)
                    except (ValueError, RuntimeError) as exc:
                        st.error(str(exc))
                    else:
                        added = 0

                        for upload in validated_uploads:
                            saved_file = None

                            try:
                                saved_file = save_library_upload(upload)
                                item_id = create_library_item(
                                    **saved_file,
                                    folder_id=folder_id,
                                    status=status,
                                    tags=split_tags(tags),
                                    project_ids=project_ids,
                                )
                                st.session_state["library_selected_item_id"] = item_id
                                added += 1
                            except Exception as exc:
                                if saved_file:
                                    delete_library_file(saved_file["file_path"])

                                st.error(f"{upload.name}: {exc}")

                        if added:
                            st.toast(f"Added {added} file{'s' if added != 1 else ''}.")
                            st.rerun()

    with paper_col:
        with st.popover("＋ Add paper", width="stretch"):
            st.caption("Save a reference even when you do not have the PDF yet.")

            with st.form("library_manual_paper_form", clear_on_submit=True):
                title = st.text_input("Title *")
                authors = st.text_input("Authors")
                year = st.number_input(
                    "Publication year",
                    min_value=0,
                    max_value=2100,
                    value=0,
                    step=1,
                )
                source_name = st.text_input("Journal / source")
                doi = st.text_input("DOI")
                url = st.text_input("URL")
                folder_id = st.selectbox(
                    "Folder",
                    folder_options,
                    index=initial_folder_index,
                    format_func=lambda value: (
                        paths[value] if value is not None else "Unfiled"
                    ),
                    key=f"manual_paper_folder_{initial_folder_id or 'unfiled'}",
                )
                abstract = st.text_area("Abstract", height=100)
                tags = st.text_input(
                    "Tags",
                    placeholder="e.g. synthesis, review",
                    key="manual_paper_tags",
                )
                project_ids = st.multiselect(
                    "Link to projects",
                    project_options,
                    format_func=lambda value: projects_by_id[value]["name"],
                    key="manual_paper_projects",
                )
                submitted = st.form_submit_button(
                    "Save paper",
                    width="stretch",
                )

            if submitted:
                try:
                    item_id = create_library_item(
                        title=title,
                        item_type="paper",
                        folder_id=folder_id,
                        authors=authors,
                        publication_year=int(year) or None,
                        source_name=source_name,
                        doi=doi,
                        url=url,
                        abstract=abstract,
                        tags=split_tags(tags),
                        project_ids=project_ids,
                    )
                    st.session_state["library_selected_item_id"] = item_id
                    st.toast("Paper added to My Library.")
                    st.rerun()
                except DatabaseIntegrityError:
                    st.error("A paper with this DOI is already in My Library.")
                except Exception as exc:
                    st.error(str(exc))


def render_folder_panel(folders, stats, paths):
    render_html('<div class="library-folders-scope"></div>')
    title_col, add_col = st.columns([1, 0.35], gap="small")

    with title_col:
        render_html(
            """
            <div class="library-panel-title">Folders</div>
            <div class="library-panel-caption">Organize your research collection.</div>
            """
        )

    with add_col:
        with st.popover("＋", help="Create folder", width="stretch"):
            parent_options = [None, *[folder["id"] for folder in folders]]
            current_folder = selected_folder_id()
            default_index = (
                parent_options.index(current_folder)
                if current_folder in parent_options
                else 0
            )

            with st.form("create_library_folder_form", clear_on_submit=True):
                name = st.text_input("Folder name")
                parent_id = st.selectbox(
                    "Inside",
                    parent_options,
                    index=default_index,
                    format_func=lambda value: (
                        paths[value] if value is not None else "My Library (root)"
                    ),
                )
                submitted = st.form_submit_button("Create folder", width="stretch")

            if submitted:
                try:
                    folder_id = create_library_folder(name, parent_id)
                    st.session_state["library_collection"] = f"folder:{folder_id}"
                    st.toast("Folder created.")
                    st.rerun()
                except DatabaseIntegrityError:
                    st.error("A folder with this name already exists here.")
                except Exception as exc:
                    st.error(str(exc))

    render_html('<div class="library-section-label">Library</div>')
    render_collection_button(
        f"▦  All items  ·  {stats['total']}",
        "all",
        "all",
    )
    render_collection_button(
        f"◇  Unfiled  ·  {stats['unfiled']}",
        "unfiled",
        "unfiled",
    )
    render_collection_button(
        f"▤  Papers  ·  {stats['papers'] + stats['pdfs']}",
        "papers",
        "papers",
    )
    render_collection_button(
        f"▦  Datasets  ·  {stats['datasets']}",
        "type:dataset",
        "datasets",
    )
    render_collection_button(
        f"◉  Audio  ·  {stats['audio']}",
        "type:audio",
        "audio",
    )
    render_collection_button(
        f"○  To read  ·  {stats['to_read']}",
        "status:To read",
        "to_read",
    )

    render_html('<div class="library-section-label">My folders</div>')

    if folders:
        render_folder_tree(folders)
    else:
        st.caption("Create a folder to start organizing papers.")

    folder_id = selected_folder_id()

    if folder_id is None:
        return

    selected_folder = next(
        (folder for folder in folders if folder["id"] == folder_id),
        None,
    )

    if not selected_folder:
        st.session_state["library_collection"] = "all"
        return

    with st.expander("Folder options"):
        with st.form(f"rename_library_folder_{folder_id}"):
            new_name = st.text_input("Rename folder", value=selected_folder["name"])
            rename_submitted = st.form_submit_button("Save name", width="stretch")

        if rename_submitted:
            try:
                rename_library_folder(folder_id, new_name)
                st.toast("Folder renamed.")
                st.rerun()
            except DatabaseIntegrityError:
                st.error("A folder with this name already exists here.")
            except Exception as exc:
                st.error(str(exc))

        st.divider()
        delete_contents = st.checkbox(
            "Also delete items in this folder and its subfolders",
            key=f"delete_folder_contents_{folder_id}",
        )
        confirm_delete = st.checkbox(
            "I understand this removes the folder",
            key=f"confirm_delete_folder_{folder_id}",
        )

        if st.button(
            "Delete folder",
            key=f"delete_folder_{folder_id}",
            type="secondary",
            disabled=not confirm_delete,
            width="stretch",
        ):
            try:
                file_paths = delete_library_folder(
                    folder_id,
                    delete_items=delete_contents,
                )

                for file_path in file_paths:
                    delete_library_file(file_path)

                st.session_state["library_collection"] = "all"
                st.toast(
                    "Folder deleted. Its items were moved to Unfiled."
                    if not delete_contents
                    else "Folder and its contents were deleted."
                )
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


def collection_query(collection: str) -> dict:
    if collection == "unfiled":
        return {"only_unfiled": True}

    if collection == "papers":
        return {}

    if collection.startswith("folder:"):
        return {"folder_id": int(collection.split(":", 1)[1])}

    if collection.startswith("type:"):
        return {"item_type": collection.split(":", 1)[1]}

    if collection.startswith("status:"):
        return {"status": collection.split(":", 1)[1]}

    return {}


def render_item_row(item):
    row_key = f"library_item_{item['id']}"

    with st.container(border=True, key=row_key):
        check_col, icon_col, info_col, status_col, open_col = st.columns(
            [0.16, 0.38, 2.4, 0.62, 0.42],
            gap="small",
            vertical_alignment="center",
        )

        with check_col:
            st.checkbox(
                "Select",
                key=f"library_select_item_{item['id']}",
                label_visibility="collapsed",
            )

        with icon_col:
            render_html(
                f'<div class="library-item-icon">{safe_html(TYPE_ICONS.get(item["item_type"], "◇"))}</div>'
            )

        with info_col:
            meta_parts = []

            if item["authors"]:
                meta_parts.append(item["authors"])

            if item["publication_year"]:
                meta_parts.append(str(item["publication_year"]))

            if item["source_name"]:
                meta_parts.append(item["source_name"])

            if item["tags"]:
                meta_parts.append(f"Tags: {item['tags']}")

            render_html(
                f"""
                <div class="library-item-title">{safe_html(item['title'])}</div>
                <div class="library-item-meta">{safe_html(' · '.join(meta_parts) or 'No metadata yet')}</div>
                """
            )

        with status_col:
            render_html(
                f'<span class="library-status">{safe_html(item["status"])}</span>'
            )

        with open_col:
            if st.button(
                "→",
                key=f"open_library_item_{item['id']}",
                help="Open item details",
                width="stretch",
            ):
                st.session_state["library_selected_item_id"] = item["id"]
                st.rerun()


@st.fragment
@authenticated_callback
def render_library_list(folders, projects, paths):
    render_html('<div class="library-list-scope"></div>')
    heading_col, count_col = st.columns([1, 0.36], gap="small")

    with heading_col:
        render_html(
            """
            <div class="library-panel-title">Research items</div>
            <div class="library-panel-caption">Search, filter, and move items between folders.</div>
            """
        )

    collection = st.session_state.get("library_collection", "all")
    filters = collection_query(collection)
    search = st.text_input(
        "Search My Library",
        placeholder="Search title, author, DOI, source, or tag…",
        key="library_search",
        label_visibility="collapsed",
    )
    type_col, status_col, project_col, sort_col = st.columns(
        [1, 1, 1.2, 1],
        gap="small",
    )

    with type_col:
        selected_type = st.selectbox(
            "Type",
            ["All types", *LIBRARY_ITEM_TYPES],
            format_func=lambda value: (
                value if value == "All types" else TYPE_LABELS[value]
            ),
        )

    with status_col:
        selected_status = st.selectbox(
            "Status",
            ["All statuses", *LIBRARY_STATUSES],
        )

    projects_by_id = {project["id"]: project for project in projects}

    with project_col:
        selected_project_id = st.selectbox(
            "Project",
            [None, *projects_by_id],
            format_func=lambda value: (
                "All projects" if value is None else projects_by_id[value]["name"]
            ),
        )

    with sort_col:
        selected_sort = st.selectbox(
            "Sort",
            ["newest", "oldest", "title", "year_desc", "year_asc"],
            format_func={
                "newest": "Newest",
                "oldest": "Oldest",
                "title": "Title A–Z",
                "year_desc": "Year ↓",
                "year_asc": "Year ↑",
            }.get,
        )

    query_filters = {
        "folder_id": filters.get("folder_id"),
        "only_unfiled": filters.get("only_unfiled", False),
        "status": filters.get("status", selected_status),
        "project_id": selected_project_id,
        "search": search,
    }

    if collection == "papers" and selected_type == "All types":
        query_filters["item_types"] = ("paper", "pdf")
    else:
        query_filters["item_type"] = filters.get("item_type", selected_type)

    page_size = 8
    total_items = cached_read(get_library_item_count, **query_filters)
    total_pages = max(1, math.ceil(total_items / page_size))
    page_number = min(
        max(int(st.session_state.get("library_page_number", 1)), 1),
        total_pages,
    )
    st.session_state["library_page_number"] = page_number
    page_items = cached_read(
        get_library_items,
        **query_filters,
        sort=selected_sort,
        limit=page_size,
        offset=(page_number - 1) * page_size,
    )

    with count_col:
        st.caption(f"{total_items} item{'s' if total_items != 1 else ''}")

    selected_ids = [
        item["id"]
        for item in page_items
        if st.session_state.get(f"library_select_item_{item['id']}")
    ]

    if selected_ids:
        move_col, action_col = st.columns([1.5, 0.72], gap="small")
        folder_options = [None, *[folder["id"] for folder in folders]]

        with move_col:
            target_folder = st.selectbox(
                f"Move {len(selected_ids)} selected item(s)",
                folder_options,
                format_func=lambda value: (
                    paths[value] if value is not None else "Unfiled"
                ),
                key="library_bulk_move_folder",
            )

        with action_col:
            st.write("")

            if st.button("Move", key="library_bulk_move", width="stretch"):
                move_library_items(selected_ids, target_folder)

                for item_id in selected_ids:
                    st.session_state[f"library_select_item_{item_id}"] = False

                st.toast("Selected items moved.")
                st.rerun()

    if not page_items:
        render_html(
            """
            <div class="library-empty">
                <div class="library-empty-icon">▤</div>
                <strong>No items found</strong>
                <span style="font-size:.78rem;margin-top:6px;">Upload a file, add a paper, or change the active filters.</span>
            </div>
            """
        )
    else:
        for item in page_items:
            render_item_row(item)

    if total_pages > 1:
        previous_col, page_col, next_col = st.columns([0.7, 1, 0.7], gap="small")

        with previous_col:
            if st.button(
                "←",
                key="library_previous_page",
                disabled=page_number == 1,
                width="stretch",
            ):
                st.session_state["library_page_number"] = page_number - 1
                st.rerun(scope="fragment")

        with page_col:
            st.caption(f"Page {page_number} of {total_pages}")

        with next_col:
            if st.button(
                "→",
                key="library_next_page",
                disabled=page_number == total_pages,
                width="stretch",
            ):
                st.session_state["library_page_number"] = page_number + 1
                st.rerun(scope="fragment")


@st.fragment
@authenticated_callback
def render_library_download(item):
    """Read file bytes only after the user explicitly requests a download."""
    if not st.button(
        "Prepare download",
        key=f"prepare_library_download_{item['id']}",
        width="stretch",
    ):
        return

    try:
        with st.spinner("Preparing file..."):
            file_bytes = read_library_file(item["file_path"])
    except (FileNotFoundError, OSError, ValueError) as exc:
        st.warning(str(exc))
        return

    st.download_button(
        "↓ Download file",
        data=file_bytes,
        file_name=item["original_filename"] or item["title"],
        mime=item["mime_type"] or "application/octet-stream",
        key=f"library_download_{item['id']}",
        on_click="ignore",
        width="stretch",
    )


def render_details_panel(folders, projects, paths):
    render_html('<div class="library-details-scope"></div>')
    item_id = st.session_state.get("library_selected_item_id")
    item = cached_read(get_library_item, item_id) if item_id else None

    if not item:
        render_html(
            """
            <div class="library-panel-title">Item details</div>
            <div class="library-panel-caption">Select an item to view and edit its metadata.</div>
            <div class="library-empty" style="min-height:410px;margin-top:12px;">
                <div class="library-empty-icon">◇</div>
                <strong>No item selected</strong>
                <span style="font-size:.78rem;margin-top:6px;">Choose Open next to an item in your library.</span>
            </div>
            """
        )
        return

    render_html(
        f"""
        <div class="library-details-title">{safe_html(item['title'])}</div>
        <div class="library-details-meta">
            {safe_html(TYPE_LABELS.get(item['item_type'], 'Other'))}
            · Added {safe_html(compact_date(item['created_at']))}
            {f" · {safe_html(item['folder_name'])}" if item['folder_name'] else ''}
        </div>
        """
    )

    if item["file_path"]:
        file_col, size_col = st.columns([1, 0.46], gap="small")

        with file_col:
            render_library_download(item)

        with size_col:
            st.caption(format_file_size(item["file_size"]))

    folder_options = [None, *[folder["id"] for folder in folders]]
    current_folder_index = (
        folder_options.index(item["folder_id"])
        if item["folder_id"] in folder_options
        else 0
    )
    project_options = [project["id"] for project in projects]
    projects_by_id = {project["id"]: project for project in projects}
    item_project_ids = [
        project_id
        for project_id in project_ids_from_row(item)
        if project_id in projects_by_id
    ]

    with st.form(f"edit_library_item_{item['id']}"):
        title = st.text_input("Title", value=item["title"])
        item_type = st.selectbox(
            "Type",
            LIBRARY_ITEM_TYPES,
            index=LIBRARY_ITEM_TYPES.index(item["item_type"]),
            format_func=lambda value: TYPE_LABELS[value],
        )
        folder_id = st.selectbox(
            "Folder",
            folder_options,
            index=current_folder_index,
            format_func=lambda value: (
                paths[value] if value is not None else "Unfiled"
            ),
        )
        authors = st.text_input("Authors", value=item["authors"] or "")
        publication_year = st.number_input(
            "Publication year",
            min_value=0,
            max_value=2100,
            value=int(item["publication_year"] or 0),
            step=1,
        )
        source_name = st.text_input(
            "Journal / source",
            value=item["source_name"] or "",
        )
        doi = st.text_input("DOI", value=item["doi"] or "")
        url = st.text_input("URL", value=item["url"] or "")
        status = st.selectbox(
            "Reading status",
            LIBRARY_STATUSES,
            index=LIBRARY_STATUSES.index(item["status"]),
        )
        tags = st.text_input("Tags", value=item["tags"] or "")
        project_ids = st.multiselect(
            "Linked projects",
            project_options,
            default=item_project_ids,
            format_func=lambda value: projects_by_id[value]["name"],
        )
        abstract = st.text_area(
            "Abstract",
            value=item["abstract"] or "",
            height=130,
        )
        personal_notes = st.text_area(
            "Personal notes",
            value=item["personal_notes"] or "",
            height=110,
        )
        submitted = st.form_submit_button("Save changes", width="stretch")

    if submitted:
        try:
            update_library_item(
                item["id"],
                title=title,
                item_type=item_type,
                folder_id=folder_id,
                authors=authors,
                publication_year=int(publication_year) or None,
                source_name=source_name,
                doi=doi,
                url=url,
                abstract=abstract,
                status=status,
                personal_notes=personal_notes,
                tags=split_tags(tags),
                project_ids=project_ids,
            )
            st.toast("Library item updated.")
            st.rerun()
        except DatabaseIntegrityError:
            st.error("A different paper with this DOI is already in My Library.")
        except Exception as exc:
            st.error(str(exc))

    if item["item_type"] in {"paper", "pdf"}:
        st.divider()
        st.markdown("**Research Case**")

        if not item_project_ids:
            st.caption(
                "Link this paper to a project before generating its semantic Research Case."
            )
        else:
            case_project_id = st.selectbox(
                "Project for this Research Case",
                item_project_ids,
                key=f"research_case_project_{item['id']}",
                format_func=lambda value: projects_by_id[value]["name"],
            )
            research_case = cached_read(
                get_research_case,
                case_project_id,
                int(item["id"]),
            )

            if research_case and is_research_case_current(research_case, item):
                experiment_count = len(
                    research_case.get("semantic", {}).get(
                        "experimental_strategy",
                        [],
                    )
                )
                st.success(
                    f"Research Case ready · {experiment_count} experiment(s) extracted."
                )
            elif research_case and research_case.get("status") == "failed":
                st.warning(
                    "The last generation failed: "
                    + str(research_case.get("error_message") or "Unknown error")
                )
            elif research_case:
                st.info("The Research Case is outdated and should be regenerated.")
            else:
                st.caption("No Research Case has been generated for this project yet.")

            if st.button(
                "Generate / update Research Case",
                key=f"generate_research_case_{item['id']}_{case_project_id}",
                width="stretch",
            ):
                try:
                    with st.spinner("Extracting the semantic Research Case..."):
                        generate_research_case_for_item(
                            case_project_id,
                            int(item["id"]),
                        )
                    st.session_state.pop(
                        f"experiment_recommendation_result_{case_project_id}",
                        None,
                    )
                    st.toast("Research Case generated.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    st.divider()
    confirm_delete = st.checkbox(
        "I understand this permanently removes the item",
        key=f"confirm_delete_library_item_{item['id']}",
    )

    if st.button(
        "Delete item",
        key=f"delete_library_item_{item['id']}",
        disabled=not confirm_delete,
        width="stretch",
    ):
        file_path = delete_library_item(item["id"])

        if file_path:
            delete_library_file(file_path)

        st.session_state["library_selected_item_id"] = None
        st.toast("Item deleted from My Library.")
        st.rerun()


def _project_by_id(projects, project_id: int | None):
    return next(
        (project for project in projects if project["id"] == project_id),
        None,
    )


def _apply_discovery_snapshot(snapshot: dict, *, restore_mode: bool = False):
    queries = [
        str(query).strip()
        for query in snapshot.get("queries", [])
        if str(query).strip()
    ]
    source_mode = snapshot.get("source_mode") or "AI Recommendations"
    search_options = snapshot.get("search_options", {})
    st.session_state["discover_results"] = snapshot.get("results", [])
    st.session_state["discover_profile"] = snapshot.get("profile", {})
    st.session_state["discover_queries"] = queries
    st.session_state["discover_queries_editor"] = "\n".join(queries)
    st.session_state["discover_project_id"] = snapshot.get("project_id")
    st.session_state["discover_ai_error"] = snapshot.get("ai_error", "")
    st.session_state["discover_search_options"] = search_options
    st.session_state["discover_page"] = snapshot.get("page", 1)
    st.session_state["discover_source_mode"] = source_mode
    st.session_state["discover_selected_work_id"] = None
    st.session_state["discover_chat_history"] = []

    if source_mode == "AI Recommendations":
        st.session_state["discover_ai_open_access"] = bool(
            search_options.get("open_access_only", False)
        )
        st.session_state["discover_ai_from_year"] = int(
            search_options.get("from_year") or max(1900, datetime.now().year - 10)
        )
        st.session_state["discover_ai_to_year"] = int(
            search_options.get("to_year") or datetime.now().year
        )
        st.session_state["discover_ai_result_limit"] = int(
            search_options.get("result_limit") or 10
        )
        st.session_state["discover_ai_order"] = (
            search_options.get("order") or "hybrid"
        )
    else:
        st.session_state["discover_manual_query"] = queries[0] if queries else ""
        st.session_state["discover_manual_open_access"] = bool(
            search_options.get("open_access_only", False)
        )
        st.session_state["discover_manual_from_year"] = int(
            search_options.get("from_year") or max(1900, datetime.now().year - 10)
        )
        st.session_state["discover_manual_to_year"] = int(
            search_options.get("to_year") or datetime.now().year
        )
        st.session_state["discover_manual_result_limit"] = int(
            search_options.get("result_limit") or 10
        )
        st.session_state["discover_manual_order"] = (
            search_options.get("order") or "hybrid"
        )

    if restore_mode and source_mode in ("Manual Search", "AI Recommendations"):
        st.session_state["discover_mode"] = source_mode

        if source_mode == "AI Recommendations":
            st.session_state["discover_ai_project_selector"] = snapshot.get(
                "project_id"
            )
        else:
            st.session_state["discover_manual_project_id"] = snapshot.get(
                "project_id"
            )


def _clear_discovery_state_for_project(
    project_id: int | None,
    source_mode: str,
):
    st.session_state["discover_results"] = []
    st.session_state["discover_profile"] = {}
    st.session_state["discover_queries"] = []
    st.session_state["discover_queries_editor"] = ""
    st.session_state["discover_project_id"] = project_id
    st.session_state["discover_ai_error"] = ""
    st.session_state["discover_search_options"] = {}
    st.session_state["discover_page"] = 1
    st.session_state["discover_source_mode"] = source_mode
    st.session_state["discover_selected_work_id"] = None
    st.session_state["discover_chat_history"] = []


def _load_saved_discovery_for_project(project_id: int, source_mode: str):
    snapshot = cached_read(
        get_project_discovery_results,
        project_id,
        source_mode,
    )

    if snapshot:
        _apply_discovery_snapshot(snapshot)
    else:
        _clear_discovery_state_for_project(project_id, source_mode)


def _hydrate_discovery_state_from_database():
    if "discover_results" in st.session_state:
        return

    project_id = st.session_state.get("discover_project_id")
    source_mode = st.session_state.get(
        "discover_source_mode",
        st.session_state.get("discover_mode", "Manual Search"),
    )
    snapshot = (
        cached_read(get_project_discovery_results, project_id, source_mode)
        if project_id
        else cached_read(get_latest_project_discovery_results)
    )

    if snapshot:
        _apply_discovery_snapshot(snapshot, restore_mode=True)
    else:
        _clear_discovery_state_for_project(project_id, source_mode)


def _manual_discovery_profile(query: str, project=None) -> dict:
    description = "Manual scientific literature search."

    if project:
        project_description = (project["description"] or "").strip()
        description = (
            f"Manual search in the context of {project['name']}. "
            f"{project_description}"
        ).strip()

    return {
        "research_topic": query.strip(),
        "short_description": description,
        "keywords": [word for word in query.split() if len(word) > 2][:12],
        "search_queries": [query.strip()],
        "exclude_terms": [],
    }


def _sort_discovery_results(results: list[dict], order: str) -> list[dict]:
    if order == "citations":
        return sorted(
            results,
            key=lambda work: (
                -int(work.get("cited_by_count") or 0),
                -float(work.get("final_score") or 0),
            ),
        )

    if order == "newest":
        return sorted(
            results,
            key=lambda work: (
                -int(work.get("publication_year") or 0),
                -float(work.get("final_score") or 0),
            ),
        )

    if order == "openalex":
        return sorted(
            results,
            key=lambda work: (
                -float(work.get("relevance_score") or 0),
                -float(work.get("final_score") or 0),
            ),
        )

    return sorted(
        results,
        key=lambda work: (
            -float(work.get("final_score") or 0),
            -float(work.get("base_score") or 0),
        ),
    )


def _run_discovery_search(
    *,
    queries: list[str],
    profile: dict,
    project_id: int | None,
    ideas,
    from_year: int | None,
    to_year: int | None,
    open_access_only: bool,
    result_limit: int,
    order: str,
    page: int = 1,
    source_mode: str | None = None,
    sync_query_editor: bool = True,
):
    # Keep network and AI dependencies off ordinary Library page loads.
    from services.discovery_service import rank_discovery_results
    from services.openalex_service import search_works_for_queries

    normalized_queries = [query.strip() for query in queries if query.strip()]

    if not normalized_queries:
        raise ValueError("At least one valid search query is required.")

    per_query = max(3, min(15, math.ceil(result_limit / len(normalized_queries))))
    openalex_sort = order if order in ("citations", "newest") else "relevance"
    candidates = search_works_for_queries(
        normalized_queries,
        per_page=per_query,
        from_year=from_year,
        to_year=to_year,
        open_access_only=open_access_only,
        sort=openalex_sort,
        exclude_terms=profile.get("exclude_terms", []),
        page=page,
    )
    candidates = candidates[: max(result_limit, 1)]
    ranked_results, ai_error = rank_discovery_results(
        candidates,
        profile=profile,
        ideas=ideas,
        queries=normalized_queries,
    )
    ranked_results = _sort_discovery_results(ranked_results, order)
    normalized_mode = source_mode or st.session_state.get(
        "discover_source_mode",
        st.session_state.get("discover_mode", "Manual Search"),
    )
    search_options = {
        "from_year": from_year,
        "to_year": to_year,
        "open_access_only": open_access_only,
        "result_limit": result_limit,
        "order": order,
    }

    if project_id is not None:
        replace_project_discovery_results(
            project_id,
            results=ranked_results,
            profile=profile,
            queries=normalized_queries,
            search_options=search_options,
            ai_error=ai_error,
            source_mode=normalized_mode,
            page=page,
        )

    st.session_state["discover_results"] = ranked_results
    st.session_state["discover_profile"] = profile
    st.session_state["discover_queries"] = normalized_queries

    if sync_query_editor:
        st.session_state["discover_queries_editor"] = "\n".join(normalized_queries)
    st.session_state["discover_project_id"] = project_id
    st.session_state["discover_ai_error"] = ai_error
    st.session_state["discover_source_mode"] = normalized_mode
    st.session_state["discover_selected_work_id"] = None
    st.session_state["discover_chat_history"] = []
    st.session_state["discover_search_options"] = search_options
    st.session_state["discover_page"] = page


def _render_discovery_search_controls(projects):
    current_year = datetime.now().year
    project_ids = [project["id"] for project in projects]
    projects_by_id = {project["id"]: project for project in projects}
    mode = st.radio(
        "Discovery mode",
        ["Manual Search", "AI Recommendations"],
        horizontal=True,
        key="discover_mode",
    )

    if mode != st.session_state.get("discover_source_mode"):
        current_project_id = st.session_state.get("discover_project_id")

        if mode == "Manual Search":
            target_project_id = st.session_state.get(
                "discover_manual_project_id"
            )

            if target_project_id not in project_ids:
                target_project_id = (
                    current_project_id
                    if current_project_id in project_ids
                    else None
                )

            st.session_state["discover_manual_project_id"] = target_project_id
        else:
            target_project_id = st.session_state.get(
                "discover_ai_project_selector"
            )

            if target_project_id not in project_ids:
                target_project_id = (
                    current_project_id
                    if current_project_id in project_ids
                    else (project_ids[0] if project_ids else None)
                )

            if target_project_id is not None:
                st.session_state["discover_ai_project_selector"] = target_project_id

        if target_project_id is not None:
            _load_saved_discovery_for_project(target_project_id, mode)
        else:
            _clear_discovery_state_for_project(None, mode)

    if mode == "Manual Search":
        current_project_id = st.session_state.get("discover_project_id")
        manual_project_options = [None, *project_ids]
        project_id = st.selectbox(
            "Project context (optional)",
            manual_project_options,
            key="discover_manual_project_id",
            format_func=lambda value: (
                "No project context"
                if value is None
                else projects_by_id[value]["name"]
            ),
        )

        if (
            current_project_id != project_id
            or st.session_state.get("discover_source_mode") != "Manual Search"
        ):
            if project_id is None:
                _clear_discovery_state_for_project(None, "Manual Search")
            else:
                _load_saved_discovery_for_project(project_id, "Manual Search")

        with st.form("discover_manual_search_form"):
            query = st.text_input(
                "Search papers",
                placeholder="e.g. thiazole derivatives antibacterial SAR",
                key="discover_manual_query",
            )
            filter_col, from_col, to_col, count_col = st.columns(
                [1.05, 0.8, 0.8, 0.8],
                gap="small",
            )

            with filter_col:
                open_access_only = st.checkbox(
                    "Open Access only",
                    key="discover_manual_open_access",
                )

            with from_col:
                from_year = st.number_input(
                    "From year",
                    min_value=1900,
                    max_value=current_year,
                    step=1,
                    key="discover_manual_from_year",
                    **(
                        {}
                        if "discover_manual_from_year" in st.session_state
                        else {"value": max(1900, current_year - 10)}
                    ),
                )

            with to_col:
                to_year = st.number_input(
                    "To year",
                    min_value=1900,
                    max_value=current_year,
                    step=1,
                    key="discover_manual_to_year",
                    **(
                        {}
                        if "discover_manual_to_year" in st.session_state
                        else {"value": current_year}
                    ),
                )

            with count_col:
                result_limit = st.selectbox(
                    "Results",
                    [5, 10, 15, 20],
                    key="discover_manual_result_limit",
                    **(
                        {}
                        if "discover_manual_result_limit" in st.session_state
                        else {"index": 1}
                    ),
                )

            order = st.selectbox(
                "Result order",
                ["hybrid", "openalex", "citations", "newest"],
                format_func={
                    "hybrid": "Hybrid AI relevance",
                    "openalex": "OpenAlex relevance",
                    "citations": "Most cited",
                    "newest": "Newest",
                }.get,
                key="discover_manual_order",
            )
            submitted = st.form_submit_button("Search and rank papers", width="stretch")

        if submitted:
            if not query.strip():
                st.error("Enter a scientific search query.")
            elif from_year > to_year:
                st.error("From year cannot be later than To year.")
            else:
                project = projects_by_id.get(project_id)
                ideas = cached_read(get_project_ideas, project_id) if project_id else []
                profile = _manual_discovery_profile(query, project)

                with st.spinner("Searching OpenAlex and calculating hybrid scores..."):
                    try:
                        _run_discovery_search(
                            queries=[query],
                            profile=profile,
                            project_id=project_id,
                            ideas=ideas,
                            from_year=int(from_year),
                            to_year=int(to_year),
                            open_access_only=open_access_only,
                            result_limit=result_limit,
                            order=order,
                            source_mode="Manual Search",
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
    else:
        if not projects:
            st.warning("Create a project before generating AI recommendations.")
            return

        current_project_id = st.session_state.get("discover_project_id")
        default_project_index = (
            project_ids.index(current_project_id)
            if current_project_id in project_ids
            else 0
        )
        project_id = st.selectbox(
            "Project",
            project_ids,
            key="discover_ai_project_selector",
            format_func=lambda value: projects_by_id[value]["name"],
            **(
                {}
                if "discover_ai_project_selector" in st.session_state
                else {"index": default_project_index}
            ),
        )

        if (
            current_project_id != project_id
            or st.session_state.get("discover_source_mode")
            != "AI Recommendations"
        ):
            _load_saved_discovery_for_project(
                project_id,
                "AI Recommendations",
            )

        with st.form("discover_ai_recommendations_form"):
            filter_col, from_col, to_col, count_col = st.columns(
                [1.05, 0.8, 0.8, 0.8],
                gap="small",
            )

            with filter_col:
                open_access_only = st.checkbox(
                    "Open Access only",
                    key="discover_ai_open_access",
                )

            with from_col:
                from_year = st.number_input(
                    "From year",
                    min_value=1900,
                    max_value=current_year,
                    step=1,
                    key="discover_ai_from_year",
                    **(
                        {}
                        if "discover_ai_from_year" in st.session_state
                        else {"value": max(1900, current_year - 10)}
                    ),
                )

            with to_col:
                to_year = st.number_input(
                    "To year",
                    min_value=1900,
                    max_value=current_year,
                    step=1,
                    key="discover_ai_to_year",
                    **(
                        {}
                        if "discover_ai_to_year" in st.session_state
                        else {"value": current_year}
                    ),
                )

            with count_col:
                result_limit = st.selectbox(
                    "Results",
                    [5, 10, 15, 20],
                    key="discover_ai_result_limit",
                    **(
                        {}
                        if "discover_ai_result_limit" in st.session_state
                        else {"index": 1}
                    ),
                )

            order = st.selectbox(
                "Result order",
                ["hybrid", "openalex", "citations", "newest"],
                format_func={
                    "hybrid": "Hybrid AI relevance",
                    "openalex": "OpenAlex relevance",
                    "citations": "Most cited",
                    "newest": "Newest",
                }.get,
                key="discover_ai_order",
            )
            submitted = st.form_submit_button(
                "Generate AI recommendations",
                width="stretch",
            )

        if submitted:
            if from_year > to_year:
                st.error("From year cannot be later than To year.")
            else:
                project = projects_by_id[project_id]
                messages = cached_read(get_project_messages, project_id)
                ideas = cached_read(get_project_ideas, project_id)

                with st.spinner("AI is building the search strategy and ranking papers..."):
                    try:
                        from services.bibliography_service import (
                            generate_bibliography_search_profile,
                        )

                        profile = generate_bibliography_search_profile(
                            project_name=project["name"],
                            project_domain=project["domain"],
                            messages=messages,
                            ideas=ideas,
                        )
                        queries = profile.get("search_queries", [])

                        if not queries:
                            raise ValueError("AI did not generate any usable search queries.")

                        _run_discovery_search(
                            queries=queries,
                            profile=profile,
                            project_id=project_id,
                            ideas=ideas,
                            from_year=int(from_year),
                            to_year=int(to_year),
                            open_access_only=open_access_only,
                            result_limit=result_limit,
                            order=order,
                            source_mode="AI Recommendations",
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))


def _render_discovery_profile_editor(projects):
    profile = st.session_state.get("discover_profile")

    if not profile:
        return

    keywords = profile.get("keywords", [])
    render_html(
        f"""
        <div class="discover-profile">
            <strong>{safe_html(profile.get('research_topic') or 'Search profile')}</strong><br>
            {safe_html(profile.get('short_description') or '')}
            {f"<br><strong>Keywords:</strong> {safe_html(', '.join(keywords))}" if keywords else ''}
        </div>
        """
    )

    with st.expander("View or edit AI search strategy"):
        queries_text = st.text_area(
            "One OpenAlex query per line",
            key="discover_queries_editor",
            height=120,
        )

        if st.button("Run edited queries", key="discover_run_edited_queries", width="stretch"):
            queries = [line.strip() for line in queries_text.splitlines() if line.strip()]
            options = st.session_state.get("discover_search_options", {})
            project_id = st.session_state.get("discover_project_id")
            ideas = cached_read(get_project_ideas, project_id) if project_id else []

            with st.spinner("Searching OpenAlex and recalculating scores..."):
                try:
                    _run_discovery_search(
                        queries=queries,
                        profile={**profile, "search_queries": queries},
                        project_id=project_id,
                        ideas=ideas,
                        from_year=options.get("from_year"),
                        to_year=options.get("to_year"),
                        open_access_only=options.get("open_access_only", False),
                        result_limit=options.get("result_limit", 10),
                        order=options.get("order", "hybrid"),
                        page=1,
                        source_mode=st.session_state.get(
                            "discover_source_mode",
                            "AI Recommendations",
                        ),
                        sync_query_editor=False,
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


def _discovery_work_is_saved(work: dict, external_keys: dict[str, set[str]]) -> bool:
    openalex_id = normalize_openalex_id(work.get("openalex_id"))
    doi = normalize_doi(work.get("doi"))
    return bool(
        (openalex_id and openalex_id in external_keys["openalex_ids"])
        or (doi and doi in external_keys["dois"])
    )


def _render_add_discovered_paper(work, folders, projects, paths, project_id):
    ranking_id = work["ranking_id"]
    folder_options = [None, *[folder["id"] for folder in folders]]
    project_options = [project["id"] for project in projects]
    projects_by_id = {project["id"]: project for project in projects}
    default_projects = [project_id] if project_id in projects_by_id else []

    with st.popover("＋ Add to Library", width="stretch"):
        with st.form(f"add_discovered_paper_{ranking_id}", clear_on_submit=True):
            folder_id = st.selectbox(
                "Folder",
                folder_options,
                format_func=lambda value: paths[value] if value is not None else "Unfiled",
            )
            status = st.selectbox("Reading status", LIBRARY_STATUSES)
            tags = st.text_input(
                "Tags",
                value=", ".join(work.get("matched_concepts", [])[:3]),
            )
            project_ids = st.multiselect(
                "Link to projects",
                project_options,
                default=default_projects,
                format_func=lambda value: projects_by_id[value]["name"],
            )
            submitted = st.form_submit_button("Save paper", width="stretch")

        if submitted:
            duplicate = find_library_item_by_external_ids(
                doi=work.get("doi", ""),
                openalex_id=work.get("openalex_id", ""),
            )

            if duplicate:
                st.info(
                    sanitize_untrusted_markdown(
                        f"Already saved as “{duplicate['title']}”."
                    )
                )
            else:
                try:
                    item_id = create_library_item(
                        title=work.get("title", "Untitled paper"),
                        item_type="paper",
                        folder_id=folder_id,
                        authors=work.get("authors", ""),
                        publication_year=work.get("publication_year"),
                        source_name=work.get("source_name", ""),
                        doi=work.get("doi", ""),
                        openalex_id=work.get("openalex_id", ""),
                        url=work.get("url", ""),
                        abstract=work.get("abstract", ""),
                        status=status,
                        personal_notes=work.get("ai_reason", ""),
                        tags=split_tags(tags),
                        project_ids=project_ids,
                    )
                    st.session_state["library_selected_item_id"] = item_id
                    st.toast("Paper added to My Library.")
                    st.rerun()
                except DatabaseIntegrityError:
                    st.info("This paper is already in My Library.")
                except Exception as exc:
                    st.error(str(exc))


def _render_discovery_score_details(work):
    ai_score = work.get("ai_score")
    ai_score_label = f"{ai_score:.1f}" if ai_score is not None else "unavailable"
    st.markdown(
        f"**Calculated:** {work.get('base_score', 0):.1f}  ·  "
        f"**AI:** {ai_score_label}"
    )
    st.caption(f"Final hybrid score: {work.get('final_score', 0):.1f} / 100")
    component_rows = [
        ("Topic match · 40%", work.get("topic_match_score", 0)),
        ("Query coverage · 20%", work.get("query_coverage_score", 0)),
        ("Key Ideas · 15%", work.get("key_ideas_score", 0)),
        ("Citation impact · 10%", work.get("citation_score", 0)),
        ("Recency · 10%", work.get("recency_score", 0)),
        ("Open Access · 5%", work.get("open_access_score", 0)),
    ]

    for label, value in component_rows:
        st.progress(min(max(float(value) / 100, 0.0), 1.0), text=f"{label}: {value:.1f}")

    rubric = work.get("ai_rubric", {})

    if rubric:
        st.markdown("**AI rubric**")
        st.caption(
            "Direct topic relevance "
            f"{rubric.get('direct_topic_relevance', 0):.0f}/40 · "
            "Method compatibility "
            f"{rubric.get('method_compatibility', 0):.0f}/25 · "
            "Outcome relevance "
            f"{rubric.get('outcome_relevance', 0):.0f}/20 · "
            "Research-gap contribution "
            f"{rubric.get('research_gap_contribution', 0):.0f}/15"
        )


def _render_discovery_result(work, folders, projects, paths, external_keys):
    ranking_id = work["ranking_id"]
    project_id = st.session_state.get("discover_project_id")
    selected = st.session_state.get("discover_selected_work_id") == ranking_id

    with st.container(border=True, key=f"discover_result_{ranking_id}"):
        score_col, info_col = st.columns([0.42, 3.3], gap="small")

        with score_col:
            render_html(
                f"""
                <div class="discover-score">
                    <strong>{safe_html(round(work.get('final_score', 0)))}</strong>
                    <span>score</span>
                </div>
                """
            )

        with info_col:
            meta = " · ".join(
                value
                for value in (
                    work.get("authors", ""),
                    str(work.get("publication_year") or ""),
                    work.get("source_name", ""),
                )
                if value
            )
            badges = []

            if work.get("is_open_access"):
                badges.append("Open Access")

            badges.append(f"{int(work.get('cited_by_count') or 0)} citations")
            render_html(
                f"""
                <div class="discover-paper-title">{safe_html(work.get('title'))}</div>
                <div class="discover-paper-meta">{safe_html(meta or 'Metadata unavailable')} · {safe_html(' · '.join(badges))}</div>
                """
            )

        render_html(
            f"""
            <div class="discover-ai-reason">
                <strong>Why this paper?</strong><br>
                {safe_html(work.get('ai_reason') or 'AI explanation unavailable.')}
                {''.join(f'<span class="discover-chip">{safe_html(concept)}</span>' for concept in work.get('matched_concepts', []))}
            </div>
            """
        )
        action_col, source_col, save_col = st.columns([1.05, 0.85, 1.15], gap="small")

        with action_col:
            if st.button(
                "✓ AI context" if selected else "Ask AI about this",
                key=f"discover_select_{ranking_id}",
                width="stretch",
            ):
                st.session_state["discover_selected_work_id"] = ranking_id
                st.rerun()

        with source_col:
            source_url = safe_external_url(work.get("url"))

            if source_url:
                st.link_button("Open source", source_url, width="stretch")

        with save_col:
            if _discovery_work_is_saved(work, external_keys):
                st.button(
                    "✓ In My Library",
                    key=f"discover_saved_{ranking_id}",
                    disabled=True,
                    width="stretch",
                )
            else:
                _render_add_discovered_paper(
                    work,
                    folders,
                    projects,
                    paths,
                    project_id,
                )

        with st.expander("Abstract and score breakdown"):
            detail_bits = []

            if work.get("doi"):
                detail_bits.append(f"DOI: {work['doi']}")

            if work.get("work_type"):
                detail_bits.append(f"Type: {work['work_type']}")

            if work.get("language"):
                detail_bits.append(f"Language: {work['language']}")

            if detail_bits:
                st.caption(" · ".join(detail_bits))

            if work.get("abstract"):
                render_html(
                    f'<div class="discover-abstract-scroll">{safe_html(work["abstract"])}</div>'
                )
            else:
                st.info("OpenAlex does not provide an abstract for this paper.")

            if work.get("ai_limitations"):
                render_untrusted_caption(
                    f"AI limitation: {work['ai_limitations']}"
                )

            _render_discovery_score_details(work)


def _render_discovery_results(folders, projects, paths):
    render_html('<div class="discover-results-scope"></div>')
    render_html(
        """
        <div class="discover-title">Discover scientific papers</div>
        <div class="discover-caption">Search OpenAlex manually or let AI build a project-specific discovery strategy.</div>
        """
    )
    _render_discovery_search_controls(projects)
    _render_discovery_profile_editor(projects)
    results = st.session_state.get("discover_results", [])
    ai_error = st.session_state.get("discover_ai_error", "")

    if ai_error:
        st.warning(
            "The calculated ranking is available, but the AI ranking could not be "
            f"completed: {ai_error}"
        )

    if not results:
        render_html(
            """
            <div class="library-empty" style="min-height:330px;">
                <div class="library-empty-icon">⌕</div>
                <strong>Start a literature search</strong>
                <span style="font-size:.78rem;margin-top:7px;max-width:430px;">
                    Search by topic or select a project to generate AI-ranked recommendations.
                </span>
            </div>
            """
        )
        return

    external_keys = cached_read(get_library_external_keys)
    st.caption(f"{len(results)} unique papers · ranked with calculated and AI scores")

    for work in results:
        _render_discovery_result(work, folders, projects, paths, external_keys)

    page = int(st.session_state.get("discover_page", 1))
    previous_col, page_col, next_col = st.columns([0.7, 1, 0.7], gap="small")

    def load_page(target_page: int):
        profile = st.session_state.get("discover_profile", {})
        queries = st.session_state.get("discover_queries", [])
        project_id = st.session_state.get("discover_project_id")
        options = st.session_state.get("discover_search_options", {})
        ideas = cached_read(get_project_ideas, project_id) if project_id else []
        _run_discovery_search(
            queries=queries,
            profile=profile,
            project_id=project_id,
            ideas=ideas,
            from_year=options.get("from_year"),
            to_year=options.get("to_year"),
            open_access_only=options.get("open_access_only", False),
            result_limit=options.get("result_limit", 10),
            order=options.get("order", "hybrid"),
            page=target_page,
            source_mode=st.session_state.get(
                "discover_source_mode",
                "AI Recommendations",
            ),
            sync_query_editor=False,
        )

    with previous_col:
        if st.button(
            "← Previous",
            key="discover_previous_page",
            disabled=page <= 1,
            width="stretch",
        ):
            with st.spinner("Loading and ranking the previous page..."):
                try:
                    load_page(page - 1)
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    with page_col:
        st.caption(f"OpenAlex result page {page}")

    with next_col:
        if st.button(
            "Next →",
            key="discover_next_page",
            width="stretch",
        ):
            with st.spinner("Loading and ranking the next page..."):
                try:
                    load_page(page + 1)
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


def _selected_discovery_work() -> dict | None:
    selected_id = st.session_state.get("discover_selected_work_id")

    return next(
        (
            work
            for work in st.session_state.get("discover_results", [])
            if work.get("ranking_id") == selected_id
        ),
        None,
    )


def _submit_discovery_question(question: str, projects):
    normalized_question = question.strip()

    if not normalized_question:
        return

    history = st.session_state.setdefault("discover_chat_history", [])
    project_id = st.session_state.get("discover_project_id")
    project = _project_by_id(projects, project_id)
    project_messages = cached_read(get_project_messages, project_id) if project_id else []
    project_ideas = cached_read(get_project_ideas, project_id) if project_id else []
    history.append({
        "role": "user",
        "content": normalized_question,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    })

    try:
        from services.discovery_service import answer_question_about_discovery

        answer = answer_question_about_discovery(
            user_question=normalized_question,
            profile=st.session_state.get("discover_profile", {}),
            results=st.session_state.get("discover_results", []),
            selected_work=_selected_discovery_work(),
            project=project,
            project_messages=project_messages,
            project_ideas=project_ideas,
            chat_history=history[:-1],
        )
    except Exception as exc:
        answer = f"AI response could not be generated: {exc}"

    history.append({
        "role": "assistant",
        "content": answer,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    })


@st.fragment
@authenticated_callback
def _render_discovery_chat(projects):
    render_html('<div class="discover-chat-scope"></div>')
    render_html(
        """
        <div class="discover-title">✦ Research AI</div>
        <div class="discover-caption">Discuss the current search, compare papers, and connect evidence to your project.</div>
        """
    )
    results = st.session_state.get("discover_results", [])
    selected_work = _selected_discovery_work()
    project = _project_by_id(projects, st.session_state.get("discover_project_id"))
    context_parts = []

    if project:
        context_parts.append(f"Project: {project['name']}")

    if selected_work:
        context_parts.append(f"Selected paper: {selected_work['title']}")
    elif results:
        context_parts.append(f"Search context: {len(results)} ranked papers")
    else:
        context_parts.append("Run a search to provide paper context")

    render_html(
        f'<div class="discover-chat-context">{safe_html(" · ".join(context_parts))}</div>'
    )

    if results:
        prompt_rows = [
            (
                "Summarize selected",
                "Summarize the selected paper using only its available abstract.",
                True,
            ),
            (
                "Project relevance",
                "How is the selected paper relevant to my project?",
                True,
            ),
            (
                "Compare results",
                "Compare the strongest papers in the current results.",
                False,
            ),
            (
                "Research gaps",
                "What research gaps appear across these results?",
                False,
            ),
        ]

        for row_index in range(0, len(prompt_rows), 2):
            left_col, right_col = st.columns(2, gap="small")

            for column, (label, prompt, requires_selected) in zip(
                (left_col, right_col),
                prompt_rows[row_index:row_index + 2],
            ):
                with column:
                    if st.button(
                        label,
                        key=f"discover_quick_prompt_{row_index}_{label}",
                        disabled=requires_selected and selected_work is None,
                        width="stretch",
                    ):
                        with st.spinner("AI is reviewing the discovery context..."):
                            _submit_discovery_question(prompt, projects)
                        st.rerun(scope="fragment")

    history = st.session_state.setdefault("discover_chat_history", [])

    if history:
        for message in history[-12:]:
            assistant = message["role"] == "assistant"
            chat_message(
                "Research Journal AI" if assistant else "You",
                "✦" if assistant else "YO",
                message.get("created_at", ""),
                message["content"],
                assistant=assistant,
            )
    else:
        st.info("Select a paper or ask about the current result set.")

    with st.form("discover_ai_chat_form", clear_on_submit=True):
        question = st.text_area(
            "Ask Research AI",
            placeholder="Ask about relevance, methods, evidence, or research gaps…",
            height=90,
            disabled=not results,
        )
        submitted = st.form_submit_button(
            "Ask AI",
            disabled=not results,
            width="stretch",
        )

    if submitted:
        if not question.strip():
            st.error("Write a question for Research AI.")
        else:
            with st.spinner("AI is reviewing the discovery context..."):
                _submit_discovery_question(question, projects)
            st.rerun(scope="fragment")

    if history and st.button(
        "Clear conversation",
        key="clear_discover_chat",
        width="stretch",
    ):
        st.session_state["discover_chat_history"] = []
        st.rerun(scope="fragment")


def _research_case_source_url(example: dict) -> str:
    article_url = safe_external_url(example.get("url"))

    if article_url:
        return article_url

    doi = str(example.get("doi") or "").strip()

    if doi:
        return safe_external_url(f"https://doi.org/{doi}")

    return ""


def _render_recommendation_example(example: dict, index: int):
    experiment = example.get("experiment", {})
    title = str(example.get("article_title") or "Untitled article")
    year = example.get("publication_year")
    expander_label = (
        f"{index}. {title}"
        + (f" ({year})" if year else "")
        + f" · similarity {example.get('similarity_score', 0):.1f}%"
    )

    with st.expander(expander_label):
        metadata_parts = [
            f"Retrieval rank #{example.get('top_k_rank', '—')}",
            f"Source: {str(example.get('source_quality') or 'unknown').replace('_', ' ')}",
        ]

        if example.get("article_authors"):
            metadata_parts.append(str(example["article_authors"]))

        render_untrusted_caption(" · ".join(metadata_parts))
        source_url = _research_case_source_url(example)

        if source_url:
            st.link_button("Open source article", source_url)

        detail_rows = (
            ("Goal", experiment.get("goal")),
            ("Changed variable", experiment.get("changed_variable")),
            (
                "Controlled variables",
                ", ".join(experiment.get("controlled_variables", [])),
            ),
            ("Evaluation", experiment.get("evaluation_metric")),
            ("Purpose", experiment.get("motivation")),
            ("Concrete example", experiment.get("concrete_example")),
        )

        for label, value in detail_rows:
            if value:
                st.markdown(f"**{label}**")
                render_untrusted_markdown(value)

        evidence = experiment.get("evidence", {})

        if evidence.get("excerpt"):
            evidence_location = " · ".join(
                part
                for part in (
                    str(evidence.get("section") or ""),
                    f"page {evidence['page']}" if evidence.get("page") else "",
                )
                if part
            )
            st.markdown("**Source evidence**")

            if evidence_location:
                render_untrusted_caption(evidence_location)

            render_untrusted_markdown(evidence["excerpt"])


def _render_experiment_recommendation_results(result: dict):
    recommendations = result.get("recommendations", [])
    st.markdown("### Experiments from similar research")
    render_html(
        """
        <div class="recommendation-baseline-note">
            Literature retrieval baseline: these are experiments reported in
            similar Research Cases. The system is not generating a new experiment
            or claiming that a retrieved experiment is scientifically appropriate.
        </div>
        """
    )
    st.caption(
        f"Retrieved {result.get('retrieved_case_count', 0)} of "
        f"{result.get('available_case_count', 0)} current Research Cases · "
        f"top-k = {result.get('top_k', 0)}"
    )

    if not recommendations:
        st.info(
            "The closest Research Cases do not contain source-supported experimental "
            "strategies yet. Add full-text papers or richer abstracts and update the cases."
        )
        return

    for index, recommendation in enumerate(recommendations, start=1):
        with st.container(
            border=True,
            key=f"experiment_recommendation_card_{index}_{recommendation['template_type']}",
        ):
            title_col, frequency_col, similarity_col = st.columns(
                [3.2, 0.85, 0.85],
                gap="small",
            )

            with title_col:
                render_html(
                    f"""
                    <div class="recommendation-template-title">
                        {index}. {safe_html(recommendation['template_label'])}
                    </div>
                    <div class="recommendation-template-meta">
                        {safe_html(recommendation['template_description'])}
                    </div>
                    """
                )

            with frequency_col:
                st.metric(
                    "Articles",
                    recommendation["template_frequency"],
                    help="Unique retrieved articles that contain this template.",
                )

            with similarity_col:
                st.metric(
                    "Best match",
                    f"{recommendation['best_similarity_score']:.1f}%",
                    help="Highest semantic similarity among supporting articles.",
                )

            representative = recommendation.get("representative", {})

            if representative.get("goal"):
                st.markdown("**Representative goal**")
                render_untrusted_markdown(representative["goal"])

            st.caption(
                f"Best retrieval rank: #{recommendation['best_top_k_rank']} · "
                "frequency is descriptive literature support, not evidence of quality."
            )

            for example_index, example in enumerate(
                recommendation.get("examples", []),
                start=1,
            ):
                _render_recommendation_example(example, example_index)


def _render_research_case_mindmap(case: dict):
    mindmap = research_case_to_mindmap(case.get("semantic", {}))
    prefix = f"research_case_{case['id']}_"
    node_sizes = {"high": 34, "medium": 27, "low": 22}
    node_colors = {"high": "#1769d2", "medium": "#6aa8ee", "low": "#8e62cf"}
    graph_nodes = [
        Node(
            id=prefix + node["id"],
            label=node["label"],
            title="Extracted semantic concept",
            size=node_sizes.get(node.get("importance", "medium"), 27),
            color=node_colors.get(node.get("importance", "medium"), "#6aa8ee"),
            font={
                "size": 16,
                "face": "Inter",
                "color": "#111827",
                "strokeWidth": 3,
                "strokeColor": "#ffffff",
            },
        )
        for node in mindmap["nodes"]
    ]
    graph_edges = [
        Edge(
            source=prefix + edge["source"],
            target=prefix + edge["target"],
        )
        for edge in mindmap["edges"]
    ]
    agraph(
        nodes=graph_nodes,
        edges=graph_edges,
        config=Config(
            width=980,
            height=420,
            directed=True,
            physics=True,
            hierarchical=False,
            groups={},
        ),
    )
    st.caption(
        f"{len(graph_nodes)} nodes · {len(graph_edges)} connections · "
        "visualization derived from the saved semantic JSON"
    )


def _render_research_case_library(project_id: int, cases: list[dict]):
    st.divider()
    st.markdown("### Research Case Library")
    st.caption(
        "Project-scoped semantic cases. The mind map is derived for visualization; "
        "the standardized JSON remains the source of truth."
    )
    ready_cases = [case for case in cases if case.get("status") == "ready"]

    if not cases:
        st.info("No Research Cases have been generated for this project.")
        return

    status_rows = []

    for case in cases:
        experiment_count = len(
            case.get("semantic", {}).get("experimental_strategy", [])
        )
        status_rows.append({
            "Article": case.get("article_title") or "Untitled article",
            "Status": case.get("status", "unknown"),
            "Experiments": experiment_count,
            "Updated": compact_date(case.get("updated_at")),
        })

    st.dataframe(status_rows, hide_index=True, width="stretch")

    if not ready_cases:
        st.warning("No ready Research Case is available to inspect.")
        return

    cases_by_id = {int(case["id"]): case for case in ready_cases}
    selected_case_id = st.selectbox(
        "Inspect Research Case",
        list(cases_by_id),
        key=f"inspect_research_case_{project_id}",
        format_func=lambda value: cases_by_id[value]["article_title"],
    )
    selected_case = cases_by_id[selected_case_id]
    semantic = selected_case.get("semantic", {})
    source_quality = semantic.get("metadata", {}).get("source_quality", "unknown")
    st.caption(
        f"Source quality: {source_quality.replace('_', ' ')} · "
        f"schema {selected_case.get('schema_version', '—')} · "
        f"model {selected_case.get('generation_model', '—')}"
    )
    _render_research_case_mindmap(selected_case)

    with st.expander("View saved semantic JSON"):
        st.json(semantic, expanded=False)

    if selected_case.get("error_message"):
        render_untrusted_caption(selected_case["error_message"])


def render_experiment_recommendations(projects):
    render_html(
        """
        <div class="recommendations-hero">
            <div class="recommendations-hero-title">Experiment Recommendations</div>
            <div class="recommendations-hero-caption">
                Build project-specific Research Cases and retrieve experimental
                strategies from the most semantically similar literature.
            </div>
        </div>
        """
    )

    if not projects:
        st.info("Create a research project before building Research Cases.")
        return

    project_ids = [int(project["id"]) for project in projects]
    projects_by_id = {int(project["id"]): project for project in projects}
    preferred_project_id = st.session_state.get("experiment_recommendations_project_id")

    if preferred_project_id not in project_ids:
        discovery_project_id = st.session_state.get("discover_project_id")
        preferred_project_id = (
            discovery_project_id
            if discovery_project_id in project_ids
            else project_ids[0]
        )

    project_id = st.selectbox(
        "Project",
        project_ids,
        index=project_ids.index(preferred_project_id),
        key="experiment_recommendations_project_id",
        format_func=lambda value: projects_by_id[value]["name"],
        help="Research Cases and recommendations are isolated to this project.",
    )
    project_items = cached_read(
        get_library_items,
        project_id=project_id,
        item_types=("paper", "pdf"),
        sort="newest",
        limit=500,
    )
    cases = cached_read(get_project_research_cases, project_id)
    coverage = get_research_case_coverage(project_items, cases)
    eligible_col, ready_col, update_col, failed_col = st.columns(4, gap="small")

    with eligible_col:
        st.metric("Linked papers", coverage["eligible"])

    with ready_col:
        st.metric("Ready cases", coverage["ready"])

    with update_col:
        st.metric("To process", coverage["to_process"])

    with failed_col:
        st.metric("Failed", coverage["failed"])

    action_col, retrieve_col, top_k_col = st.columns([1.35, 1.35, 0.75], gap="small")

    with top_k_col:
        top_k = st.number_input(
            "Top-k papers",
            min_value=1,
            max_value=30,
            value=min(8, max(1, coverage["ready"])),
            step=1,
            disabled=coverage["ready"] == 0,
            key=f"experiment_recommendations_top_k_{project_id}",
        )

    with action_col:
        st.write("")

        if st.button(
            "Generate / update Research Cases",
            key=f"generate_project_research_cases_{project_id}",
            disabled=coverage["eligible"] == 0 or coverage["to_process"] == 0,
            width="stretch",
            help="Processes missing, failed, or outdated paper cases in a bounded batch.",
        ):
            try:
                with st.spinner("Generating project Research Cases..."):
                    report = generate_project_research_cases(project_id)
                st.session_state[f"research_case_batch_report_{project_id}"] = report
                st.session_state.pop(
                    f"experiment_recommendation_result_{project_id}",
                    None,
                )
                st.toast(
                    f"Generated {len(report['generated'])} Research Case(s)."
                )
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with retrieve_col:
        st.write("")

        if st.button(
            "Find relevant experiments",
            key=f"recommend_relevant_experiments_{project_id}",
            disabled=coverage["ready"] == 0,
            type="primary",
            width="stretch",
            help="Retrieves literature precedents; it does not generate a new experiment.",
        ):
            try:
                with st.spinner("Matching the project to similar Research Cases..."):
                    result = recommend_relevant_experiments(
                        project_id,
                        top_k=int(top_k),
                    )
                st.session_state[
                    f"experiment_recommendation_result_{project_id}"
                ] = result
            except Exception as exc:
                st.error(str(exc))

    if coverage["eligible"] == 0:
        st.info(
            "Link papers or PDFs from My Library to this project before generating cases."
        )
    elif coverage["ready"] < coverage["eligible"]:
        st.caption(
            f"Coverage: {coverage['ready']} of {coverage['eligible']} linked papers "
            "have a current Research Case."
        )

    report = st.session_state.get(f"research_case_batch_report_{project_id}")

    if report and report.get("failures"):
        with st.expander(
            f"{len(report['failures'])} paper(s) could not be processed",
            expanded=True,
        ):
            for failure in report["failures"]:
                render_untrusted_caption(
                    f"{failure['title']}: {failure['error']}"
                )

    result = st.session_state.get(f"experiment_recommendation_result_{project_id}")

    if result:
        _render_experiment_recommendation_results(result)
    else:
        st.info(
            "Generate the Research Cases, then retrieve experiments reported in "
            "the most similar articles."
        )

    _render_research_case_library(project_id, cases)


render_page_css()
st.session_state.setdefault("library_collection", "all")
st.session_state.setdefault("library_page_number", 1)

folders = cached_read(get_library_folders)
projects = cached_read(get_projects)
paths = folder_paths(folders)

top_brand_col, top_context_col, top_space_col, top_user_col = st.columns(
    [1.25, 2.8, 1.9, 1.65],
    gap="large",
)

with top_brand_col:
    top_brand()

with top_context_col:
    render_html(
        """
        <div class="top-project-scope"></div>
        <div class="library-context">
            <span class="library-context-icon">▦</span>
            <span>Global research library</span>
        </div>
        """
    )

with top_space_col:
    render_html('<div class="top-search-scope"></div>')

with top_user_col:
    render_html('<div class="top-user-scope"></div>')
    header_icons()

nav_col, page_col = st.columns([1.05, 6.48], gap="small")

with nav_col:
    render_html('<div class="nav-panel-scope"></div>')
    sidebar_nav("library")

with page_col:
    render_html('<div class="library-page-scope"></div>')
    heading_col, action_col = st.columns([2.2, 1], gap="large")

    with heading_col:
        render_html(
            """
            <div class="library-heading">Library</div>
            <div class="library-subtitle">Your papers, files, and research references in one connected workspace.</div>
            """
        )

    with action_col:
        render_add_controls(folders, projects, paths)

    my_library_tab, discover_tab, recommendations_tab = st.tabs(
        ["My Library", "Discover papers", "Experiment Recommendations"],
        key="library_primary_tab",
        on_change="rerun",
    )

    if my_library_tab.open:
        with my_library_tab:
            stats = cached_read(get_library_stats)
            folder_col, list_col, details_col = st.columns(
                [1.05, 2.75, 1.65],
                gap="small",
            )

            with folder_col:
                render_folder_panel(folders, stats, paths)

            with list_col:
                render_library_list(folders, projects, paths)

            with details_col:
                render_details_panel(folders, projects, paths)

    if discover_tab.open:
        with discover_tab:
            _hydrate_discovery_state_from_database()
            discover_results_col, discover_chat_col = st.columns(
                [3.05, 1.45],
                gap="small",
            )

            with discover_results_col:
                _render_discovery_results(folders, projects, paths)

            with discover_chat_col:
                _render_discovery_chat(projects)

    if recommendations_tab.open:
        with recommendations_tab:
            render_experiment_recommendations(projects)
