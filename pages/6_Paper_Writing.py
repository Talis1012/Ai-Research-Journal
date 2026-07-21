import difflib
import re
from datetime import datetime

import streamlit as st

from db.database import init_db
from db.queries import get_projects
from db.writing_queries import (
    CITATION_STYLES,
    MANUSCRIPT_STATUSES,
    add_manuscript_ai_message,
    add_manuscript_section,
    attach_manuscript_evidence,
    attach_manuscript_source,
    clear_manuscript_ai_messages,
    create_manuscript,
    create_manuscript_version,
    delete_manuscript,
    delete_manuscript_section,
    detach_manuscript_evidence,
    detach_manuscript_source,
    duplicate_manuscript_version,
    get_manuscript,
    get_manuscript_ai_messages,
    get_manuscript_evidence,
    get_manuscript_section,
    get_manuscript_sections,
    get_manuscript_sources,
    get_manuscript_version,
    get_manuscript_versions,
    get_manuscripts,
    get_project_evidence_candidates,
    get_project_library_sources,
    insert_section_citation,
    manuscript_word_count,
    move_manuscript_section,
    restore_manuscript_version,
    snapshot_to_text,
    update_manuscript,
    update_manuscript_section,
    update_manuscript_source,
)
from services.manuscript_export_service import (
    bibliography_lines,
    manuscript_docx,
    manuscript_markdown,
    manuscript_pdf,
    render_citations,
)
from services.writing_service import WRITING_MODES, generate_writing_suggestion
from utils.ui import (
    compact_date,
    header_icons,
    load_css,
    render_html,
    safe_html,
    sidebar_nav,
    top_brand,
)


st.set_page_config(
    page_title="Paper Writing · Research Journal AI",
    page_icon="✎",
    layout="wide",
)

init_db()
load_css()


def render_page_css():
    render_html(
        """
        <style>
        .writing-page-scope,
        .writing-outline-scope,
        .writing-editor-scope,
        .writing-assistant-scope,
        .writing-sources-scope,
        .writing-versions-scope { display:none; }

        div[data-testid="stColumn"]:has(.writing-page-scope) {
            min-height: calc(100vh - var(--topbar-h));
            padding: 22px 26px 40px !important;
            background: #fff;
        }

        div[data-testid="stColumn"]:has(.writing-page-scope)
        > div[data-testid="stVerticalBlock"] { gap:.72rem; }

        .writing-context {
            min-height: var(--topbar-h); display:flex; align-items:center;
            gap:10px; color:#344054; font-size:.88rem; font-weight:780;
        }

        .writing-context-icon {
            width:32px; height:32px; border:1px solid #dfe6ef;
            border-radius:8px; display:inline-flex; align-items:center;
            justify-content:center; background:#f8fbff; color:#1769d2;
        }

        .writing-heading { color:#101828; font-size:1.85rem; font-weight:880; line-height:1.08; }
        .writing-subtitle { color:#667085; font-size:.9rem; margin-top:7px; }
        .writing-panel-title { color:#101828; font-size:1rem; font-weight:850; }
        .writing-panel-caption { color:#667085; font-size:.76rem; line-height:1.4; margin-top:3px; }

        div[data-testid="stColumn"]:has(.writing-outline-scope),
        div[data-testid="stColumn"]:has(.writing-editor-scope),
        div[data-testid="stColumn"]:has(.writing-assistant-scope) {
            border:1px solid #dfe6ef; background:#fff;
            min-height:710px; padding:16px !important;
            box-shadow:0 8px 22px rgba(16,24,40,.045);
        }

        div[data-testid="stColumn"]:has(.writing-outline-scope) { border-radius:9px 0 0 9px; }
        div[data-testid="stColumn"]:has(.writing-editor-scope) { border-left:0; border-right:0; }
        div[data-testid="stColumn"]:has(.writing-assistant-scope) {
            border-radius:0 9px 9px 0; position:sticky; top:10px;
            max-height:calc(100vh - 20px); overflow-y:auto;
        }

        div[class*="st-key-writing_outline_section_"] button[kind="primary"],
        div[class*="st-key-writing_outline_section_"] button[data-testid="stBaseButton-primary"] {
            background:#eaf3ff !important;
            border:1.5px solid #1473e6 !important;
            color:#0d65d9 !important;
            box-shadow:none !important;
        }

        div[class*="st-key-writing_outline_section_"] button[kind="primary"]:hover,
        div[class*="st-key-writing_outline_section_"] button[data-testid="stBaseButton-primary"]:hover {
            background:#deedff !important;
            border-color:#0d65d9 !important;
            color:#0957b8 !important;
        }

        div[data-testid="stColumn"]:has(.writing-outline-scope) > div,
        div[data-testid="stColumn"]:has(.writing-editor-scope) > div,
        div[data-testid="stColumn"]:has(.writing-assistant-scope) > div { gap:.62rem; }

        .writing-stat {
            border:1px solid #e3eaf3; background:#f8fbff; border-radius:8px;
            padding:9px 11px; color:#475467; font-size:.75rem;
        }
        .writing-stat strong { color:#101828; font-size:.9rem; }

        .writing-ai-note {
            border:1px solid #cfe0f6; background:#f3f8ff; color:#344054;
            border-radius:8px; padding:11px 12px; font-size:.8rem; line-height:1.48;
        }

        .writing-suggestion {
            border:1px solid #d8e3f0; border-radius:9px; padding:13px;
            background:#fff; color:#344054; font-size:.82rem; line-height:1.55;
            max-height:330px; overflow-y:auto;
        }

        .writing-evidence-card {
            border:1px solid #e1e8f0; border-radius:8px; padding:10px 11px;
            margin:5px 0; background:#fff; color:#475467; font-size:.76rem;
        }

        .writing-source-title { color:#101828; font-size:.86rem; font-weight:820; line-height:1.35; }
        .writing-source-meta { color:#667085; font-size:.72rem; line-height:1.4; margin-top:3px; }
        .writing-chip {
            display:inline-block; margin:5px 5px 0 0; padding:3px 7px;
            border-radius:999px; background:#eaf3ff; color:#1769d2;
            font-size:.66rem; font-weight:760;
        }

        div[data-testid="stColumn"]:has(.writing-sources-scope),
        div[data-testid="stColumn"]:has(.writing-versions-scope) {
            border:1px solid #dfe6ef; border-radius:9px; padding:16px !important;
            min-height:650px; background:#fff;
        }

        .writing-diff {
            max-height:500px; overflow:auto; border:1px solid #dfe6ef;
            background:#f8fafc; border-radius:8px; padding:12px;
            font: .74rem/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
            white-space:pre-wrap;
        }

        @media (max-width: 1050px) {
            div[data-testid="stHorizontalBlock"]:has(.writing-outline-scope) { flex-direction:column; }
            div[data-testid="stColumn"]:has(.writing-outline-scope),
            div[data-testid="stColumn"]:has(.writing-editor-scope),
            div[data-testid="stColumn"]:has(.writing-assistant-scope) {
                width:100% !important; flex:1 1 100% !important; border:1px solid #dfe6ef;
                border-radius:9px; min-height:auto; position:static; max-height:none;
            }
        }
        </style>
        """
    )


def _reset_section_editor(section_id: int):
    st.session_state["writing_pending_editor_reset"] = section_id


def _process_pending_editor_reset():
    section_id = st.session_state.pop("writing_pending_editor_reset", None)

    if section_id:
        st.session_state.pop(f"writing_section_content_{section_id}", None)
        st.session_state.pop(f"writing_section_title_{section_id}", None)


def _autosave_section(section_id: int):
    content_key = f"writing_section_content_{section_id}"
    update_manuscript_section(
        section_id,
        content_md=st.session_state.get(content_key, ""),
    )
    st.session_state["writing_last_saved_at"] = datetime.now().strftime("%H:%M:%S")


def _autosave_section_title(section_id: int):
    title_key = f"writing_section_title_{section_id}"
    update_manuscript_section(
        section_id,
        title=st.session_state.get(title_key, ""),
    )
    st.session_state["writing_last_saved_at"] = datetime.now().strftime("%H:%M:%S")


def _save_manuscript_meta(manuscript_id: int):
    update_manuscript(
        manuscript_id,
        title=st.session_state[f"writing_title_{manuscript_id}"],
        status=st.session_state[f"writing_status_{manuscript_id}"],
        citation_style=st.session_state[f"writing_style_{manuscript_id}"],
    )
    st.session_state["writing_last_saved_at"] = datetime.now().strftime("%H:%M:%S")


def _create_export_version(manuscript_id: int, export_type: str):
    create_manuscript_version(
        manuscript_id,
        f"Before {export_type} export",
        trigger_type="export",
        note=f"Automatic snapshot before {export_type} export.",
    )


def _select_manuscript_after_rerun(manuscript_id: int | None):
    """Queue a selector change without mutating an instantiated widget."""
    st.session_state["writing_pending_manuscript_id"] = manuscript_id


def _current_manuscript_text(manuscript, sections) -> str:
    parts = [f"# {manuscript['title']}"]

    for section in sections:
        parts.extend((f"\n## {section['title']}\n", section["content_md"] or ""))

    return "\n".join(parts).strip()


def _render_create_manuscript(project_id: int, key: str):
    with st.form(key, clear_on_submit=True):
        title = st.text_input(
            "Manuscript title",
            placeholder="e.g. Stability Profile of CM-01",
        )
        citation_style = st.selectbox("Citation style", CITATION_STYLES)
        submitted = st.form_submit_button("Create manuscript", width="stretch")

    if submitted:
        try:
            manuscript_id = create_manuscript(
                project_id,
                title,
                citation_style=citation_style,
            )
            _select_manuscript_after_rerun(manuscript_id)
            st.toast("Manuscript created.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def _render_export_popover(manuscript, sections, sources):
    safe_filename = re.sub(r"[^A-Za-z0-9._-]+", "_", manuscript["title"]).strip("_")
    safe_filename = safe_filename or "manuscript"
    markdown_data = manuscript_markdown(manuscript, sections, sources).encode("utf-8")

    with st.popover("↓ Export", width="stretch"):
        st.caption("A version snapshot is created when an export is downloaded.")
        st.download_button(
            "Markdown (.md)",
            data=markdown_data,
            file_name=f"{safe_filename}.md",
            mime="text/markdown",
            width="stretch",
            on_click=_create_export_version,
            args=(manuscript["id"], "Markdown"),
        )

        try:
            docx_data = manuscript_docx(manuscript, sections, sources)
            st.download_button(
                "Word (.docx)",
                data=docx_data,
                file_name=f"{safe_filename}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                width="stretch",
                on_click=_create_export_version,
                args=(manuscript["id"], "DOCX"),
            )
        except RuntimeError as exc:
            st.caption(str(exc))

        try:
            pdf_data = manuscript_pdf(manuscript, sections, sources)
            st.download_button(
                "PDF (.pdf)",
                data=pdf_data,
                file_name=f"{safe_filename}.pdf",
                mime="application/pdf",
                width="stretch",
                on_click=_create_export_version,
                args=(manuscript["id"], "PDF"),
            )
        except RuntimeError as exc:
            st.caption(str(exc))


def _render_outline(manuscript, sections, sources):
    render_html('<div class="writing-outline-scope"></div>')
    render_html(
        '<div class="writing-panel-title">Outline</div>'
        '<div class="writing-panel-caption">Select and organize manuscript sections.</div>'
    )
    section_ids = [section["id"] for section in sections]

    if st.session_state.get("writing_section_id") not in section_ids:
        st.session_state["writing_section_id"] = section_ids[0] if section_ids else None

    for section in sections:
        selected = st.session_state.get("writing_section_id") == section["id"]

        if st.button(
            section["title"],
            key=f"writing_outline_section_{section['id']}",
            type="primary" if selected else "secondary",
            width="stretch",
        ):
            st.session_state["writing_section_id"] = section["id"]
            st.rerun()

    with st.popover("＋ Add section", width="stretch"):
        with st.form("add_manuscript_section_form", clear_on_submit=True):
            title = st.text_input("Section title")
            submitted = st.form_submit_button("Add section", width="stretch")

        if submitted:
            try:
                section_id = add_manuscript_section(manuscript["id"], title)
                st.session_state["writing_section_id"] = section_id
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    selected_id = st.session_state.get("writing_section_id")

    if selected_id:
        up_col, down_col = st.columns(2, gap="small")

        with up_col:
            if st.button("↑ Move", key="writing_move_section_up", width="stretch"):
                move_manuscript_section(selected_id, -1)
                st.rerun()

        with down_col:
            if st.button("↓ Move", key="writing_move_section_down", width="stretch"):
                move_manuscript_section(selected_id, 1)
                st.rerun()

        with st.expander("Delete selected section"):
            confirm = st.checkbox(
                "I understand this removes the current section",
                key="writing_confirm_section_delete",
            )

            if st.button(
                "Delete section",
                disabled=not confirm,
                width="stretch",
            ):
                delete_manuscript_section(selected_id)
                st.session_state["writing_section_id"] = None
                st.rerun()

    word_count = manuscript_word_count([dict(section) for section in sections])
    render_html(
        f'<div class="writing-stat"><strong>{word_count:,}</strong> words<br>'
        f'<strong>{len(sources)}</strong> attached sources</div>'
    )


def _render_editor(manuscript, section, sections, sources):
    render_html('<div class="writing-editor-scope"></div>')

    if not section:
        st.info("Add a section to begin writing.")
        return

    title_key = f"writing_section_title_{section['id']}"
    content_key = f"writing_section_content_{section['id']}"
    st.session_state.setdefault(title_key, section["title"])
    st.session_state.setdefault(content_key, section["content_md"] or "")
    st.text_input(
        "Section title",
        key=title_key,
        on_change=_autosave_section_title,
        args=(section["id"],),
    )
    st.text_area(
        "Markdown editor",
        key=content_key,
        height=470,
        placeholder="Write this section or ask AI to draft it from attached evidence…",
        on_change=_autosave_section,
        args=(section["id"],),
    )
    saved_at = st.session_state.get("writing_last_saved_at")
    st.caption(
        f"Saved automatically at {saved_at}." if saved_at else "Changes save automatically when the editor loses focus."
    )

    with st.expander("Preview formatted section", expanded=False):
        preview = render_citations(
            st.session_state.get(content_key, ""),
            sources,
            manuscript["citation_style"],
        )
        st.markdown(preview or "*This section is empty.*")


def _writing_quick_prompts(mode: str) -> list[tuple[str, str]]:
    prompts = {
        "Draft": [
            ("Draft from evidence", "Draft this section using only the attached evidence."),
            ("Add transition", "Add a concise transition that connects this section to the outline."),
        ],
        "Rewrite": [
            ("Academic tone", "Rewrite for a precise academic tone without changing factual meaning."),
            ("Improve clarity", "Improve clarity and flow while preserving citations and claims."),
        ],
        "Cite": [
            ("Suggest citations", "Add citations only where the attached abstracts directly support the claim."),
            ("Find uncited claims", "Identify claims that need citations and cite supported ones."),
        ],
        "Check claims": [
            ("Check every claim", "Assess every factual claim against the attached sources and project evidence."),
            ("Find weak evidence", "Identify claims supported only weakly or by abstract-level evidence."),
        ],
    }
    return prompts[mode]


def _render_ai_assistant(manuscript, section, sections, sources, evidence):
    render_html('<div class="writing-assistant-scope"></div>')
    render_html(
        '<div class="writing-panel-title">✦ AI Writing Assistant</div>'
        f'<div class="writing-panel-caption">Using {len(evidence)} project evidence items + '
        f'{len(sources)} bibliographic sources.</div>'
    )
    mode = st.radio(
        "Assistant mode",
        WRITING_MODES,
        horizontal=True,
        key="writing_ai_mode",
    )
    render_html(
        '<div class="writing-ai-note">AI uses only the selected section and attached '
        'evidence. Suggestions are never applied automatically.</div>'
    )
    instruction_key = "writing_ai_instruction"
    prompt_columns = st.columns(2, gap="small")

    for column, (label, prompt) in zip(prompt_columns, _writing_quick_prompts(mode)):
        with column:
            if st.button(label, key=f"writing_prompt_{mode}_{label}", width="stretch"):
                st.session_state[instruction_key] = prompt

    messages = get_manuscript_ai_messages(manuscript["id"], limit=8)

    for message in messages[-4:]:
        with st.chat_message("assistant" if message["role"] == "assistant" else "user"):
            st.markdown(message["content"])

    with st.form("writing_ai_form", clear_on_submit=False):
        instruction = st.text_area(
            "Ask AI to write, revise, or cite",
            key=instruction_key,
            height=90,
            placeholder="Describe what you want AI to do with this section…",
        )
        submitted = st.form_submit_button(
            "Generate suggestion",
            disabled=section is None,
            width="stretch",
        )

    if submitted:
        try:
            add_manuscript_ai_message(
                manuscript["id"],
                section_id=section["id"],
                role="user",
                mode=mode,
                content=instruction.strip() or _writing_quick_prompts(mode)[0][1],
            )

            with st.spinner("AI is reviewing the selected evidence..."):
                result = generate_writing_suggestion(
                    mode=mode,
                    instruction=instruction,
                    manuscript=manuscript,
                    section=section,
                    sections=sections,
                    sources=sources,
                    evidence=evidence,
                )

            add_manuscript_ai_message(
                manuscript["id"],
                section_id=section["id"],
                role="assistant",
                mode=mode,
                content=result["explanation"] or "Suggestion ready.",
                payload=result,
            )
            st.session_state["writing_ai_suggestion"] = result
            st.session_state["writing_ai_suggestion_section_id"] = section["id"]
            st.session_state["writing_ai_suggestion_mode"] = mode
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    suggestion = st.session_state.get("writing_ai_suggestion")

    if suggestion and st.session_state.get("writing_ai_suggestion_section_id") == section["id"]:
        render_html(
            f'<div class="writing-suggestion"><strong>Suggested revision</strong><br><br>'
            f'{safe_html(suggestion.get("suggested_text", "")).replace(chr(10), "<br>")}</div>'
        )

        if suggestion.get("explanation"):
            st.caption(suggestion["explanation"])

        if suggestion.get("evidence_used"):
            with st.expander("Evidence used", expanded=True):
                for item in suggestion["evidence_used"]:
                    render_html(
                        f'<div class="writing-evidence-card"><strong>{safe_html(item["label"])}</strong><br>'
                        f'{safe_html(item["support"])}</div>'
                    )

        if suggestion.get("claims"):
            with st.expander("Claim check", expanded=mode == "Check claims"):
                for claim in suggestion["claims"]:
                    status_icon = {"supported": "✓", "weak": "△", "unsupported": "!"}[claim["status"]]
                    st.markdown(
                        f"**{status_icon} {claim['status'].title()}** — {claim['claim']}"
                    )
                    st.caption(claim["reason"] or "No reason returned.")

        if st.session_state.get("writing_ai_suggestion_mode") != "Check claims":
            insert_col, replace_col = st.columns(2, gap="small")

            with insert_col:
                if st.button("＋ Insert", key="writing_ai_insert", width="stretch"):
                    create_manuscript_version(
                        manuscript["id"],
                        "Before AI insert",
                        trigger_type="ai",
                    )
                    current = section["content_md"].rstrip()
                    suggested = suggestion["suggested_text"].strip()
                    combined = f"{current}\n\n{suggested}".strip()
                    update_manuscript_section(section["id"], content_md=combined)
                    _reset_section_editor(section["id"])
                    st.session_state.pop("writing_ai_suggestion", None)
                    st.rerun()

            with replace_col:
                if st.button("↻ Replace section", key="writing_ai_replace", width="stretch"):
                    create_manuscript_version(
                        manuscript["id"],
                        "Before AI replacement",
                        trigger_type="ai",
                    )
                    update_manuscript_section(
                        section["id"],
                        content_md=suggestion["suggested_text"],
                    )
                    _reset_section_editor(section["id"])
                    st.session_state.pop("writing_ai_suggestion", None)
                    st.rerun()

    if messages and st.button("Clear AI conversation", width="stretch"):
        clear_manuscript_ai_messages(manuscript["id"])
        st.session_state.pop("writing_ai_suggestion", None)
        st.rerun()


def _render_manuscript_tab(manuscript):
    sections = get_manuscript_sections(manuscript["id"])
    sources = get_manuscript_sources(manuscript["id"])
    evidence = get_manuscript_evidence(manuscript["id"])
    section_ids = [section["id"] for section in sections]

    if st.session_state.get("writing_section_id") not in section_ids:
        st.session_state["writing_section_id"] = section_ids[0] if section_ids else None

    section = get_manuscript_section(st.session_state.get("writing_section_id")) if section_ids else None
    outline_col, editor_col, assistant_col = st.columns(
        [1.05, 2.8, 1.55],
        gap="small",
    )

    with outline_col:
        _render_outline(manuscript, sections, sources)

    with editor_col:
        _render_editor(manuscript, section, sections, sources)

    with assistant_col:
        _render_ai_assistant(manuscript, section, sections, sources, evidence)


def _render_source_card(source, manuscript, selected_section_id: int | None):
    render_html(
        f'<div class="writing-source-title">{safe_html(source["title"])}</div>'
        f'<div class="writing-source-meta">{safe_html(source["authors"] or "Unknown authors")} · '
        f'{safe_html(source["publication_year"] or "n.d.")} · '
        f'{safe_html(source["source_name"] or "Unknown source")}</div>'
        f'<span class="writing-chip">[@{safe_html(source["citation_key"])}]</span>'
    )
    action_col, remove_col = st.columns([1.2, .8], gap="small")

    with action_col:
        if st.button(
            "Insert citation",
            key=f"insert_source_{source['library_item_id']}",
            disabled=selected_section_id is None,
            width="stretch",
        ):
            try:
                token = insert_section_citation(
                    selected_section_id,
                    source["library_item_id"],
                )
                _reset_section_editor(selected_section_id)
                st.toast(f"Inserted {token}")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with remove_col:
        if st.button(
            "Remove",
            key=f"remove_source_{source['library_item_id']}",
            width="stretch",
        ):
            detach_manuscript_source(manuscript["id"], source["library_item_id"])
            st.rerun()

    with st.expander("Abstract and citation settings"):
        st.write(source["abstract"] or "No abstract is available.")

        with st.form(f"source_settings_{source['library_item_id']}"):
            citation_key = st.text_input(
                "Citation key",
                value=source["citation_key"],
            )
            notes = st.text_area(
                "Researcher notes",
                value=source["source_notes"] or "",
                height=80,
            )
            submitted = st.form_submit_button("Save source settings", width="stretch")

        if submitted:
            try:
                update_manuscript_source(
                    manuscript["id"],
                    source["library_item_id"],
                    citation_key=citation_key,
                    notes=notes,
                )
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        if source["url"]:
            st.link_button("Open original source", source["url"], width="stretch")


def _render_sources_tab(manuscript):
    sources = get_manuscript_sources(manuscript["id"])
    attached_ids = {source["library_item_id"] for source in sources}
    search = st.text_input(
        "Search project library",
        placeholder="Search title, author, or DOI…",
        key="writing_source_search",
    )
    available = [
        source
        for source in get_project_library_sources(manuscript["project_id"], search)
        if source["id"] not in attached_ids
    ]
    available_col, attached_col, evidence_col = st.columns(
        [1.25, 1.55, 1.2],
        gap="small",
    )

    with available_col:
        render_html('<div class="writing-sources-scope"></div>')
        render_html(
            '<div class="writing-panel-title">Project Library</div>'
            '<div class="writing-panel-caption">Sources linked to this project in My Library.</div>'
        )

        if not available:
            st.info("No additional project sources found.")
            render_html(
                '<a href="/Library" target="_self" style="color:#1769d2;'
                'font-size:.8rem;font-weight:750;">Open Library</a>'
            )

        for source in available:
            with st.container(border=True):
                render_html(
                    f'<div class="writing-source-title">{safe_html(source["title"])}</div>'
                    f'<div class="writing-source-meta">{safe_html(source["authors"] or "Unknown authors")} · '
                    f'{safe_html(source["publication_year"] or "n.d.")}</div>'
                )

                if st.button(
                    "＋ Attach source",
                    key=f"attach_source_{source['id']}",
                    width="stretch",
                ):
                    try:
                        key = attach_manuscript_source(manuscript["id"], source["id"])
                        st.toast(f"Attached as [@{key}].")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

    with attached_col:
        render_html('<div class="writing-sources-scope"></div>')
        render_html(
            f'<div class="writing-panel-title">Attached Sources · {len(sources)}</div>'
            '<div class="writing-panel-caption">Only attached sources are available to AI and citation tools.</div>'
        )

        if not sources:
            st.info("Attach at least one paper to add citations.")

        for source in sources:
            with st.container(border=True):
                _render_source_card(
                    source,
                    manuscript,
                    st.session_state.get("writing_section_id"),
                )

        with st.expander("Generated bibliography", expanded=bool(sources)):
            lines = bibliography_lines(sources, manuscript["citation_style"])

            for line in lines:
                st.markdown(line)

            reference_section = next(
                (
                    section
                    for section in get_manuscript_sections(manuscript["id"])
                    if section["section_type"] == "references"
                ),
                None,
            )

            if reference_section and st.button(
                "Refresh References section",
                disabled=not sources,
                width="stretch",
            ):
                update_manuscript_section(
                    reference_section["id"],
                    content_md="\n\n".join(lines),
                )
                _reset_section_editor(reference_section["id"])
                st.toast("References section updated.")
                st.rerun()

    with evidence_col:
        render_html('<div class="writing-sources-scope"></div>')
        attached_evidence = get_manuscript_evidence(manuscript["id"])
        attached_keys = {
            (row["evidence_type"], row["evidence_id"])
            for row in attached_evidence
        }
        candidates = get_project_evidence_candidates(manuscript["project_id"])
        render_html(
            f'<div class="writing-panel-title">Project Evidence · {len(attached_evidence)}</div>'
            '<div class="writing-panel-caption">Experiments, summaries, and key ideas used by the assistant.</div>'
        )

        for row in attached_evidence:
            with st.container(border=True):
                st.markdown(f"**{row['label']}**")
                st.caption(row["evidence_type"].replace("_", " ").title())

                if st.button(
                    "Remove evidence",
                    key=f"remove_evidence_{row['evidence_type']}_{row['evidence_id']}",
                    width="stretch",
                ):
                    detach_manuscript_evidence(
                        manuscript["id"],
                        row["evidence_type"],
                        row["evidence_id"],
                    )
                    st.rerun()

        with st.expander("Add project evidence", expanded=not attached_evidence):
            unattached = [
                row
                for row in candidates
                if (row["evidence_type"], row["evidence_id"]) not in attached_keys
            ]

            if not unattached:
                st.caption("No additional project evidence is available.")

            for row in unattached:
                st.markdown(f"**{row['label']}**")
                st.caption(row["evidence_type"].replace("_", " ").title())

                if st.button(
                    "＋ Attach",
                    key=f"attach_evidence_{row['evidence_type']}_{row['evidence_id']}",
                    width="stretch",
                ):
                    attach_manuscript_evidence(
                        manuscript["id"],
                        row["evidence_type"],
                        row["evidence_id"],
                        row["label"],
                        row["excerpt"],
                    )
                    st.rerun()


def _version_text(version_id: int | None, manuscript, sections) -> str:
    if version_id is None or version_id == 0:
        return _current_manuscript_text(manuscript, sections)

    version = get_manuscript_version(version_id)
    return snapshot_to_text(version["snapshot"]) if version else ""


def _render_versions_tab(manuscript):
    render_html('<div class="writing-versions-scope"></div>')
    versions = get_manuscript_versions(manuscript["id"])
    sections = get_manuscript_sections(manuscript["id"])
    create_col, compare_col = st.columns([1, 2], gap="small")

    with create_col:
        render_html(
            '<div class="writing-panel-title">Create snapshot</div>'
            '<div class="writing-panel-caption">Save an immutable version of the current manuscript.</div>'
        )

        with st.form("create_manuscript_version_form", clear_on_submit=True):
            label = st.text_input(
                "Version name",
                placeholder=f"Draft {len(versions) + 1}",
            )
            note = st.text_area("Note", height=90)
            submitted = st.form_submit_button("Save version", width="stretch")

        if submitted:
            try:
                create_manuscript_version(
                    manuscript["id"],
                    label or f"Draft {len(versions) + 1}",
                    note=note,
                )
                st.toast("Version saved.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with compare_col:
        render_html(
            '<div class="writing-panel-title">Compare versions</div>'
            '<div class="writing-panel-caption">Review line-level additions and removals.</div>'
        )
        options = [0, *[version["id"] for version in versions]]
        versions_by_id = {version["id"]: version for version in versions}

        def version_label(value):
            if value == 0:
                return "Current manuscript"

            row = versions_by_id[value]
            return f"{row['label']} · {compact_date(row['created_at'])}"

        left_col, right_col = st.columns(2, gap="small")

        with left_col:
            left_version = st.selectbox(
                "From",
                options,
                format_func=version_label,
                key="writing_diff_left",
            )

        with right_col:
            right_version = st.selectbox(
                "To",
                options,
                index=1 if len(options) > 1 else 0,
                format_func=version_label,
                key="writing_diff_right",
            )

        left_text = _version_text(left_version, manuscript, sections)
        right_text = _version_text(right_version, manuscript, sections)
        diff = "\n".join(
            difflib.unified_diff(
                left_text.splitlines(),
                right_text.splitlines(),
                fromfile=version_label(left_version),
                tofile=version_label(right_version),
                lineterm="",
            )
        )
        render_html(
            f'<div class="writing-diff">{safe_html(diff or "No differences between the selected versions.")}</div>'
        )

    st.divider()
    render_html(
        f'<div class="writing-panel-title">Version history · {len(versions)}</div>'
    )

    if not versions:
        st.info("No versions saved yet. AI replacements and exports create automatic snapshots.")

    for version in versions:
        with st.container(border=True):
            title_col, meta_col = st.columns([2, 1], gap="small")

            with title_col:
                st.markdown(f"**{version['label']}**")
                st.caption(version["note"] or "No version note.")

            with meta_col:
                st.caption(
                    f"{'AI' if version['trigger_type'] == 'ai' else version['trigger_type'].title()} · "
                    f"{version['word_count']:,} words · "
                    f"{compact_date(version['created_at'])}"
                )

            restore_col, duplicate_col = st.columns(2, gap="small")

            with restore_col:
                with st.popover("Restore", width="stretch"):
                    st.warning("The current manuscript will be saved before restoration.")

                    if st.button(
                        "Confirm restore",
                        key=f"restore_version_{version['id']}",
                        width="stretch",
                    ):
                        create_manuscript_version(
                            manuscript["id"],
                            "Before version restore",
                            trigger_type="restore",
                        )
                        restore_manuscript_version(version["id"])
                        st.session_state["writing_section_id"] = None
                        st.session_state["writing_pending_clear_editors"] = True
                        st.toast("Version restored.")
                        st.rerun()

            with duplicate_col:
                if st.button(
                    "Duplicate as manuscript",
                    key=f"duplicate_version_{version['id']}",
                    width="stretch",
                ):
                    new_id = duplicate_manuscript_version(version["id"])
                    _select_manuscript_after_rerun(new_id)
                    st.session_state["writing_section_id"] = None
                    st.toast("Version duplicated as a new manuscript.")
                    st.rerun()


render_page_css()
_process_pending_editor_reset()

if st.session_state.pop("writing_pending_clear_editors", False):
    for key in list(st.session_state):
        if key.startswith("writing_section_content_") or key.startswith("writing_section_title_"):
            st.session_state.pop(key, None)

projects = get_projects()

top_brand_col, top_context_col, top_space_col, top_user_col = st.columns(
    [1.25, 2.8, 1.9, 1.65],
    gap="large",
)

with top_brand_col:
    top_brand()

with top_context_col:
    render_html('<div class="top-project-scope"></div>')
    render_html(
        '<div class="writing-context"><span class="writing-context-icon">✎</span>'
        '<span>Evidence-grounded manuscript workspace</span></div>'
    )

with top_space_col:
    render_html('<div class="top-search-scope"></div>')

with top_user_col:
    render_html('<div class="top-user-scope"></div>')
    header_icons()

nav_col, page_col = st.columns([1.05, 6.48], gap="small")

with nav_col:
    render_html('<div class="nav-panel-scope"></div>')
    sidebar_nav("paper_writing")

with page_col:
    render_html('<div class="writing-page-scope"></div>')
    heading_col, action_col = st.columns([2.1, 1.15], gap="large")

    with heading_col:
        render_html(
            '<div class="writing-heading">Paper Writing</div>'
            '<div class="writing-subtitle">Draft with evidence from your experiments and library.</div>'
        )

    if not projects:
        st.warning("Create a project in Experiments before starting a manuscript.")
        st.stop()

    project_ids = [project["id"] for project in projects]
    projects_by_id = {project["id"]: project for project in projects}

    if st.session_state.get("writing_project_id") not in project_ids:
        st.session_state["writing_project_id"] = project_ids[0]

    with action_col:
        project_id = st.selectbox(
            "Project",
            project_ids,
            key="writing_project_id",
            format_func=lambda value: projects_by_id[value]["name"],
        )

    manuscripts = get_manuscripts(project_id)
    manuscript_ids = [manuscript["id"] for manuscript in manuscripts]

    if "writing_pending_manuscript_id" in st.session_state:
        pending_manuscript_id = st.session_state.pop("writing_pending_manuscript_id")
        st.session_state["writing_manuscript_id"] = (
            pending_manuscript_id
            if pending_manuscript_id in manuscript_ids
            else (manuscript_ids[0] if manuscript_ids else None)
        )
    elif st.session_state.get("writing_manuscript_id") not in manuscript_ids:
        st.session_state["writing_manuscript_id"] = manuscript_ids[0] if manuscript_ids else None

    selector_col, new_col = st.columns([3.4, .8], gap="small")

    with selector_col:
        if manuscripts:
            manuscript_id = st.selectbox(
                "Manuscript",
                manuscript_ids,
                key="writing_manuscript_id",
                format_func=lambda value: next(
                    manuscript["title"] for manuscript in manuscripts if manuscript["id"] == value
                ),
            )
        else:
            st.text_input("Manuscript", value="Create your first manuscript", disabled=True)
            manuscript_id = None

    with new_col:
        with st.popover("＋ New", width="stretch"):
            _render_create_manuscript(project_id, "create_manuscript_popover_form")

    if manuscript_id is None:
        render_html(
            '<div class="writing-ai-note" style="margin-top:12px;">Create a manuscript to get '
            'the default scientific outline, attach project sources, and start drafting with AI.</div>'
        )
        _render_create_manuscript(project_id, "create_manuscript_empty_form")
        st.stop()

    manuscript = get_manuscript(manuscript_id)
    sections = get_manuscript_sections(manuscript_id)
    sources = get_manuscript_sources(manuscript_id)
    meta_col, status_col, style_col, export_col = st.columns(
        [2.3, .8, .9, .75],
        gap="small",
    )

    with meta_col:
        title_key = f"writing_title_{manuscript_id}"
        st.session_state.setdefault(title_key, manuscript["title"])
        st.text_input(
            "Manuscript title",
            key=title_key,
            on_change=_save_manuscript_meta,
            args=(manuscript_id,),
        )

    with status_col:
        status_key = f"writing_status_{manuscript_id}"
        st.session_state.setdefault(status_key, manuscript["status"])
        st.selectbox(
            "Status",
            MANUSCRIPT_STATUSES,
            key=status_key,
            on_change=_save_manuscript_meta,
            args=(manuscript_id,),
        )

    with style_col:
        style_key = f"writing_style_{manuscript_id}"
        st.session_state.setdefault(style_key, manuscript["citation_style"])
        st.selectbox(
            "Citation style",
            CITATION_STYLES,
            key=style_key,
            on_change=_save_manuscript_meta,
            args=(manuscript_id,),
        )

    with export_col:
        st.caption("Export")
        _render_export_popover(manuscript, sections, sources)

    with st.expander("Manuscript settings"):
        st.caption("Deleting a manuscript also deletes its sections, versions, and AI history.")
        confirm_delete = st.checkbox(
            "I understand this action cannot be undone",
            key=f"confirm_delete_manuscript_{manuscript_id}",
        )

        if st.button(
            "Delete manuscript",
            disabled=not confirm_delete,
            key=f"delete_manuscript_{manuscript_id}",
        ):
            delete_manuscript(manuscript_id)
            _select_manuscript_after_rerun(None)
            st.session_state["writing_section_id"] = None
            st.rerun()

    manuscript_tab, sources_tab, versions_tab = st.tabs(
        ["Manuscript", "Sources", "Versions"]
    )

    with manuscript_tab:
        _render_manuscript_tab(manuscript)

    with sources_tab:
        _render_sources_tab(manuscript)

    with versions_tab:
        _render_versions_tab(manuscript)
