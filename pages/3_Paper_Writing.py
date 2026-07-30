import difflib
import hashlib
import re
from datetime import datetime

import pandas as pd
import streamlit as st

from db.database import init_db_once
from db.queries import get_projects
from db.writing_queries import (
    AI_CONTEXT_MODES,
    CITATION_STYLES,
    MANUSCRIPT_STATUSES,
    StoredFileCleanupError,
    add_manuscript_version_comment,
    add_manuscript_ai_message,
    add_manuscript_section,
    attach_manuscript_evidence,
    attach_manuscript_source,
    clear_manuscript_ai_messages,
    create_manuscript_asset,
    create_manuscript,
    create_manuscript_version,
    delete_manuscript,
    delete_manuscript_asset,
    delete_manuscript_section,
    detach_manuscript_evidence,
    detach_manuscript_source,
    duplicate_manuscript_version,
    get_manuscript,
    get_manuscript_assets,
    get_manuscript_ai_messages,
    get_manuscript_ai_context,
    get_manuscript_evidence,
    get_manuscript_section,
    get_manuscript_sections,
    get_manuscript_sources,
    get_manuscript_submission_profile,
    get_manuscript_version,
    get_manuscript_version_comments,
    get_manuscript_versions,
    get_manuscripts,
    get_project_evidence_candidates,
    get_project_library_sources,
    insert_section_citation,
    insert_section_citations,
    insert_manuscript_asset_reference,
    manuscript_word_count,
    move_manuscript_section,
    restore_manuscript_version,
    restore_manuscript_section_from_version,
    snapshot_to_text,
    update_manuscript,
    update_manuscript_asset,
    update_manuscript_ai_context,
    update_manuscript_section,
    update_manuscript_source,
    update_manuscript_submission_profile,
    update_manuscript_version,
    validate_section_citations,
)
from services.manuscript_export_service import (
    bibliography_lines,
    manuscript_docx,
    manuscript_markdown,
    manuscript_pdf,
    render_asset_references,
    render_citations,
)
from services.manuscript_asset_service import (
    delete_manuscript_asset_file,
    read_manuscript_asset_file,
    save_figure_upload,
)
from services.writing_service import WRITING_MODES, generate_writing_suggestion
from services.manuscript_review_service import (
    JOURNAL_TEMPLATES,
    publication_readiness,
    run_manuscript_checks,
    template_rules,
)
from utils.auth import authenticated_callback, require_auth
from utils.content_safety import safe_external_url
from utils.markdown_toolbar import render_markdown_toolbar
from utils.ui import (
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
    page_title="Paper Writing · Research Journal AI",
    page_icon="✎",
    layout="wide",
)

require_auth()
init_db_once(st.session_state)
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
        .writing-editor-label {
            color:#101828; font-size:.86rem; font-weight:760; margin:2px 0 -4px;
        }

        div[class*="st-key-writing_section_content_"] {
            margin-top:-.62rem;
        }

        div[class*="st-key-writing_section_content_"] div[data-baseweb="textarea"] {
            border-radius:0 0 9px 9px !important;
        }

        div[class*="st-key-writing_section_content_"] textarea {
            font-family:Arial, sans-serif !important;
            font-size:.91rem !important;
            line-height:1.65 !important;
        }

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

        .writing-context-summary {
            border:1px solid #cfe0f6; background:#f6faff; border-radius:8px;
            padding:9px 10px; color:#344054; font-size:.74rem; line-height:1.45;
        }

        .writing-ai-diff {
            max-height:300px; overflow:auto; border:1px solid #dfe6ef;
            border-radius:8px; background:#fbfcfe; padding:11px 12px;
            color:#344054; font-size:.76rem; line-height:1.6; white-space:pre-wrap;
        }
        .writing-ai-diff .diff-added {
            background:#dcfae6; color:#08602f; border-radius:3px; text-decoration:none;
        }
        .writing-ai-diff .diff-removed {
            background:#fee4e2; color:#b42318; border-radius:3px; text-decoration:line-through;
        }

        .writing-citation-status {
            border:1px solid #e1e8f0; background:#f8fafc; border-radius:7px;
            padding:8px 10px; color:#475467; font-size:.72rem; line-height:1.45;
        }

        .writing-object-label {
            display:inline-flex; align-items:center; gap:6px; padding:4px 8px;
            border-radius:999px; background:#eaf3ff; color:#1769d2;
            font-size:.68rem; font-weight:820; margin-bottom:6px;
        }

        .writing-object-caption {
            color:#344054; font-size:.76rem; line-height:1.45; margin-bottom:8px;
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

        .writing-check-summary {
            display:flex; align-items:center; justify-content:space-between; gap:12px;
            border:1px solid #cfe0f6; background:#f6faff; border-radius:9px;
            padding:11px 13px; color:#344054; font-size:.78rem;
        }
        .writing-check-score { color:#0d65d9; font-size:1.1rem; font-weight:880; }
        .writing-check-card {
            border:1px solid #e1e8f0; border-left:4px solid #f79009;
            border-radius:8px; background:#fff; padding:10px 12px; margin:7px 0;
            color:#475467; font-size:.76rem; line-height:1.46;
        }
        .writing-check-card.error { border-left-color:#d92d20; }
        .writing-check-card.info { border-left-color:#1473e6; }
        .writing-check-card strong { display:block; color:#101828; font-size:.8rem; margin-bottom:3px; }
        .writing-check-suggestion { color:#1769d2; margin-top:4px; }
        .writing-ready-grid {
            display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:7px;
            margin-top:8px;
        }
        .writing-ready-item {
            border:1px solid #e1e8f0; border-radius:7px; padding:8px 10px;
            color:#475467; font-size:.72rem; background:#fff;
        }
        .writing-ready-item.done { border-color:#abefc6; background:#ecfdf3; color:#067647; }
        .writing-version-comment {
            border-left:3px solid #b2ccff; padding-left:9px; color:#475467;
            font-size:.75rem; line-height:1.45;
        }

        @media (max-width: 1050px) {
            div[data-testid="stHorizontalBlock"]:has(.writing-outline-scope) { flex-direction:column; }
            div[data-testid="stColumn"]:has(.writing-outline-scope),
            div[data-testid="stColumn"]:has(.writing-editor-scope),
            div[data-testid="stColumn"]:has(.writing-assistant-scope) {
                width:100% !important; flex:1 1 100% !important; border:1px solid #dfe6ef;
                border-radius:9px; min-height:auto; position:static; max-height:none;
            }
            .writing-ready-grid { grid-template-columns:1fr; }
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


@authenticated_callback
def _autosave_section(section_id: int):
    content_key = f"writing_section_content_{section_id}"
    update_manuscript_section(
        section_id,
        content_md=st.session_state.get(content_key, ""),
    )
    st.session_state["writing_last_saved_at"] = datetime.now().strftime("%H:%M:%S")


@authenticated_callback
def _autosave_section_title(section_id: int):
    title_key = f"writing_section_title_{section_id}"
    update_manuscript_section(
        section_id,
        title=st.session_state.get(title_key, ""),
    )
    st.session_state["writing_last_saved_at"] = datetime.now().strftime("%H:%M:%S")


@authenticated_callback
def _save_manuscript_meta(manuscript_id: int):
    update_manuscript(
        manuscript_id,
        title=st.session_state[f"writing_title_{manuscript_id}"],
        status=st.session_state[f"writing_status_{manuscript_id}"],
        citation_style=st.session_state[f"writing_style_{manuscript_id}"],
    )
    st.session_state["writing_last_saved_at"] = datetime.now().strftime("%H:%M:%S")


@authenticated_callback
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


def _evidence_context_key(row) -> str:
    return f"{row['evidence_type']}:{row['evidence_id']}"


def _resolve_ai_context(manuscript_id, section, sections, sources, evidence):
    settings = get_manuscript_ai_context(manuscript_id)
    mode = settings["context_mode"]

    if mode == "Whole manuscript":
        context_sections = list(sections)
        context_sources = list(sources)
        context_evidence = list(evidence)
    elif mode == "Custom":
        selected_section_ids = set(settings["section_ids"])
        selected_source_ids = set(settings["source_ids"])
        selected_evidence_keys = set(settings["evidence_keys"])
        context_sections = [
            row for row in sections if row["id"] in selected_section_ids
        ]
        context_sources = [
            row
            for row in sources
            if row["library_item_id"] in selected_source_ids
        ]
        context_evidence = [
            row
            for row in evidence
            if _evidence_context_key(row) in selected_evidence_keys
        ]
    else:
        context_sections = [section] if section else []
        context_sources = list(sources)
        context_evidence = list(evidence)

    return settings, context_sections, context_sources, context_evidence


def _split_paragraphs(text: str) -> list[str]:
    return [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", str(text or "").strip())
        if paragraph.strip()
    ]


def _word_diff_html(current_text: str, suggested_text: str) -> str:
    token_pattern = r"\s+|[\w'-]+|[^\w\s]"
    current_tokens = re.findall(token_pattern, str(current_text or ""), flags=re.UNICODE)
    suggested_tokens = re.findall(token_pattern, str(suggested_text or ""), flags=re.UNICODE)
    matcher = difflib.SequenceMatcher(None, current_tokens, suggested_tokens)
    rendered = []

    for operation, left_start, left_end, right_start, right_end in matcher.get_opcodes():
        left = safe_html("".join(current_tokens[left_start:left_end]))
        right = safe_html("".join(suggested_tokens[right_start:right_end]))

        if operation == "equal":
            rendered.append(left)
        elif operation == "delete":
            rendered.append(f'<span class="diff-removed">{left}</span>')
        elif operation == "insert":
            rendered.append(f'<span class="diff-added">{right}</span>')
        else:
            rendered.append(f'<span class="diff-removed">{left}</span>')
            rendered.append(f'<span class="diff-added">{right}</span>')

    return "".join(rendered)


def _merge_suggestion(
    current_text: str,
    suggestion_text: str,
    placement: str,
    after_paragraph: int | None = None,
) -> str:
    current = str(current_text or "").strip()
    suggestion = str(suggestion_text or "").strip()

    if placement == "replace":
        return suggestion

    if placement == "beginning":
        return f"{suggestion}\n\n{current}".strip()

    if placement == "after_paragraph" and current:
        paragraphs = _split_paragraphs(current)
        position = max(0, min(int(after_paragraph or 0) + 1, len(paragraphs)))
        paragraphs.insert(position, suggestion)
        return "\n\n".join(paragraphs).strip()

    return f"{current}\n\n{suggestion}".strip()


def _clear_ai_suggestion():
    for key in (
        "writing_ai_suggestion",
        "writing_ai_suggestion_section_id",
        "writing_ai_suggestion_mode",
    ):
        st.session_state.pop(key, None)


def _apply_ai_suggestion(manuscript, section, text: str, placement: str, after_paragraph=None):
    create_manuscript_version(
        manuscript["id"],
        "Before AI suggestion apply",
        trigger_type="ai",
        note=f"Automatic snapshot before applying an AI suggestion ({placement}).",
    )
    merged = _merge_suggestion(
        section["content_md"],
        text,
        placement,
        after_paragraph,
    )
    update_manuscript_section(section["id"], content_md=merged)
    _reset_section_editor(section["id"])
    _clear_ai_suggestion()


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


def _export_fingerprint(manuscript, sections, sources, assets, submission_profile) -> str:
    payload = (
        tuple((key, manuscript[key]) for key in ("id", "title", "citation_style", "updated_at")),
        [
            (section["id"], section["title"], section["content_md"], section["updated_at"])
            for section in sections
        ],
        [
            (
                source["library_item_id"],
                source["citation_key"],
                source["title"],
                source["authors"],
                source["publication_year"],
            )
            for source in sources
        ],
        [
            (
                asset["id"],
                asset["section_id"],
                asset["asset_type"],
                asset["caption"],
                asset.get("storage_path"),
                repr(asset.get("content", {})),
                asset["updated_at"],
            )
            for asset in assets
        ],
        repr(submission_profile or {}),
    )
    return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()


def _render_export_popover(manuscript, sections, sources, assets, submission_profile):
    safe_filename = re.sub(r"[^A-Za-z0-9._-]+", "_", manuscript["title"]).strip("_")
    safe_filename = safe_filename or "manuscript"
    fingerprint = _export_fingerprint(
        manuscript,
        sections,
        sources,
        assets,
        submission_profile,
    )
    markdown_data = manuscript_markdown(
        manuscript,
        sections,
        sources,
        assets,
    ).encode("utf-8")

    with st.popover("↓ Export", width="stretch"):
        st.caption("Exports use the saved publication profile. A version snapshot is created on download.")
        st.download_button(
            "Markdown (.md)",
            data=markdown_data,
            file_name=f"{safe_filename}.md",
            mime="text/markdown",
            width="stretch",
            on_click=_create_export_version,
            args=(manuscript["id"], "Markdown"),
        )

        docx_key = f"writing_prepared_docx_{manuscript['id']}"
        docx_entry = st.session_state.get(docx_key, {})

        if docx_entry.get("fingerprint") != fingerprint:
            docx_entry = {}

        if st.button(
            "Prepare Word (.docx)",
            key=f"writing_prepare_docx_{manuscript['id']}",
            width="stretch",
        ):
            try:
                with st.spinner("Preparing Word document…"):
                    docx_entry = {
                        "fingerprint": fingerprint,
                        "data": manuscript_docx(
                            manuscript,
                            sections,
                            sources,
                            assets,
                            submission_profile,
                        ),
                    }
                st.session_state[docx_key] = docx_entry
            except RuntimeError as exc:
                st.caption(str(exc))

        if docx_entry:
            st.download_button(
                "Download Word (.docx)",
                data=docx_entry["data"],
                file_name=f"{safe_filename}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                width="stretch",
                on_click=_create_export_version,
                args=(manuscript["id"], "DOCX"),
            )

        pdf_key = f"writing_prepared_pdf_{manuscript['id']}"
        pdf_entry = st.session_state.get(pdf_key, {})

        if pdf_entry.get("fingerprint") != fingerprint:
            pdf_entry = {}

        if st.button(
            "Prepare PDF (.pdf)",
            key=f"writing_prepare_pdf_{manuscript['id']}",
            width="stretch",
        ):
            try:
                with st.spinner("Preparing PDF…"):
                    pdf_entry = {
                        "fingerprint": fingerprint,
                        "data": manuscript_pdf(manuscript, sections, sources, assets),
                    }
                st.session_state[pdf_key] = pdf_entry
            except RuntimeError as exc:
                st.caption(str(exc))

        if pdf_entry:
            st.download_button(
                "Download PDF (.pdf)",
                data=pdf_entry["data"],
                file_name=f"{safe_filename}.pdf",
                mime="application/pdf",
                width="stretch",
                on_click=_create_export_version,
                args=(manuscript["id"], "PDF"),
            )


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


def _citation_source_label(source) -> str:
    authors = str(source["authors"] or "Unknown author").split(";")[0].split(",")[0]
    year = source["publication_year"] or "n.d."
    title = str(source["title"] or "Untitled source")
    return f"[@{source['citation_key']}] · {authors} ({year}) · {title}"


def _render_citation_tools(section, sources, current_content: str):
    validation = validate_section_citations(current_content, sources)
    used_count = len(validation["valid_keys"])
    unknown_count = len(validation["unknown_keys"])
    status_text = f"{used_count} valid citation{'s' if used_count != 1 else ''}"

    if unknown_count:
        status_text += f" · {unknown_count} unknown"

    with st.expander(f"Citations · {status_text}", expanded=bool(unknown_count)):
        if validation["unknown_keys"]:
            st.warning(
                "Unknown citation keys: "
                + ", ".join(f"[@{key}]" for key in validation["unknown_keys"])
            )
            st.caption("Attach the missing source or replace the token with an attached citation key.")
        elif validation["valid_keys"]:
            render_html(
                '<div class="writing-citation-status">All citation tokens in this section '
                'match attached sources.</div>'
            )

        if not sources:
            st.info("Attach sources in the Sources tab before inserting citations.")
            return

        source_ids = [source["library_item_id"] for source in sources]
        sources_by_id = {source["library_item_id"]: source for source in sources}
        selected_ids = st.multiselect(
            "Search and select attached sources",
            source_ids,
            format_func=lambda value: _citation_source_label(sources_by_id[value]),
            key=f"writing_quick_citation_sources_{section['id']}",
            help="Start typing an author, title, DOI, or citation key to filter the list.",
        )
        placements = {
            "End of section": "end",
            "Beginning of section": "beginning",
            "After a paragraph": "after_paragraph",
        }
        placement_label = st.selectbox(
            "Insert position",
            list(placements),
            key=f"writing_citation_placement_{section['id']}",
        )
        after_paragraph = None

        if placements[placement_label] == "after_paragraph":
            paragraphs = _split_paragraphs(current_content)

            if paragraphs:
                paragraph_options = list(range(len(paragraphs)))
                after_paragraph = st.selectbox(
                    "Insert after",
                    paragraph_options,
                    format_func=lambda index: (
                        f"Paragraph {index + 1} · {paragraphs[index][:70]}"
                    ),
                    key=f"writing_citation_after_paragraph_{section['id']}",
                )
            else:
                st.caption("The section is empty; citations will be inserted at the end.")

        if st.button(
            "＋ Insert selected citations",
            key=f"writing_insert_selected_citations_{section['id']}",
            disabled=not selected_ids,
            width="stretch",
        ):
            tokens = insert_section_citations(
                section["id"],
                selected_ids,
                placement=placements[placement_label],
                after_paragraph=after_paragraph,
            )
            _reset_section_editor(section["id"])
            st.toast(f"Inserted {' '.join(tokens)}")
            st.rerun()


def _asset_option_label(asset) -> str:
    caption = str(asset.get("caption") or "Untitled object")
    return f"{asset['label']} · {caption[:72]}"


def _parse_table_columns(value: str) -> list[str]:
    columns = []

    for raw_column in str(value or "").split(","):
        column = re.sub(r"\s+", " ", raw_column).strip()

        if column and column not in columns:
            columns.append(column)

    return columns


def _clean_table_cell(value) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def _render_readonly_asset(asset):
    caption = f"{asset['label']}. {asset.get('caption', '')}".strip()

    if asset["asset_type"] == "figure":
        try:
            st.image(
                read_manuscript_asset_file(asset["storage_path"]),
                caption=caption,
                width="stretch",
            )
        except (FileNotFoundError, ValueError, OSError):
            st.warning(f"{asset['label']}: stored image is unavailable.")
        return

    if asset["asset_type"] == "equation":
        st.latex(asset.get("content", {}).get("latex", ""))
        render_untrusted_caption(caption)
        return

    columns = asset.get("content", {}).get("columns", [])
    rows = asset.get("content", {}).get("rows", [])
    render_untrusted_caption(caption)
    st.dataframe(pd.DataFrame(rows, columns=columns), width="stretch", hide_index=True)


def _render_add_manuscript_object(manuscript, section):
    object_type = st.selectbox(
        "Object type",
        ("Figure", "Table", "Equation"),
        key=f"writing_add_object_type_{section['id']}",
    )

    if object_type == "Figure":
        upload = st.file_uploader(
            "Upload figure",
            type=("png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff"),
            key=f"writing_new_figure_file_{section['id']}",
            help="Images are validated and stored as PNG. Maximum size: 25 MB.",
        )
        caption = st.text_input(
            "Caption",
            key=f"writing_new_figure_caption_{section['id']}",
            placeholder="Describe what the figure shows.",
        )
        alt_text = st.text_input(
            "Alternative text",
            key=f"writing_new_figure_alt_{section['id']}",
            placeholder="Concise visual description for accessibility.",
        )

        if st.button(
            "Add figure",
            key=f"writing_add_figure_{section['id']}",
            disabled=upload is None or not caption.strip(),
            width="stretch",
        ):
            stored = None

            try:
                stored = save_figure_upload(upload, manuscript["id"])
                create_manuscript_asset(
                    manuscript["id"],
                    section["id"],
                    "figure",
                    caption,
                    alt_text=alt_text,
                    **stored,
                )
                st.toast("Figure added and numbered automatically.")
                st.rerun()
            except Exception as exc:
                if stored:
                    delete_manuscript_asset_file(stored["storage_path"])
                st.error(str(exc))

    elif object_type == "Table":
        caption = st.text_input(
            "Caption",
            key=f"writing_new_table_caption_{section['id']}",
        )
        columns_text = st.text_input(
            "Columns (comma separated)",
            value="Variable, Value, Unit",
            key=f"writing_new_table_columns_{section['id']}",
        )
        row_count = st.number_input(
            "Initial rows",
            min_value=1,
            max_value=50,
            value=3,
            key=f"writing_new_table_rows_{section['id']}",
        )
        columns = _parse_table_columns(columns_text)

        if st.button(
            "Create editable table",
            key=f"writing_add_table_{section['id']}",
            disabled=not caption.strip() or not columns,
            width="stretch",
        ):
            try:
                create_manuscript_asset(
                    manuscript["id"],
                    section["id"],
                    "table",
                    caption,
                    content={
                        "columns": columns,
                        "rows": [dict.fromkeys(columns, "") for _ in range(int(row_count))],
                    },
                )
                st.toast("Editable table created.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    else:
        caption = st.text_input(
            "Caption",
            key=f"writing_new_equation_caption_{section['id']}",
        )
        latex = st.text_area(
            "LaTeX equation",
            value=r"E = mc^2",
            height=90,
            key=f"writing_new_equation_latex_{section['id']}",
            help="Enter the expression without $$ delimiters.",
        )

        if latex.strip():
            st.latex(latex)

        if st.button(
            "Add equation",
            key=f"writing_add_equation_{section['id']}",
            disabled=not caption.strip() or not latex.strip(),
            width="stretch",
        ):
            try:
                create_manuscript_asset(
                    manuscript["id"],
                    section["id"],
                    "equation",
                    caption,
                    content={"latex": latex.strip()},
                )
                st.toast("Equation added and numbered automatically.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


def _render_manage_manuscript_object(
    manuscript,
    section,
    sections,
    assets,
    current_content,
):
    if not assets:
        st.info("No figures, tables, or equations have been added yet.")
        return

    assets_by_id = {asset["id"]: asset for asset in assets}
    asset_id = st.selectbox(
        "Select manuscript object",
        list(assets_by_id),
        format_func=lambda value: _asset_option_label(assets_by_id[value]),
        key=f"writing_selected_object_{section['id']}",
    )
    asset = assets_by_id[asset_id]
    section_titles = {row["id"]: row["title"] for row in sections}
    assigned_section = section_titles.get(asset["section_id"], "Unknown section")
    render_html(
        f'<span class="writing-object-label">{safe_html(asset["label"])}</span>'
        f'<div class="writing-object-caption">Assigned to '
        f'<strong>{safe_html(assigned_section)}</strong> · references use '
        f'<code>{safe_html(asset["reference_token"])}</code></div>'
    )
    _render_readonly_asset(asset)
    caption = st.text_input(
        "Caption",
        value=asset.get("caption", ""),
        key=f"writing_object_caption_{asset_id}",
    )
    new_upload = None
    alt_text = asset.get("alt_text", "") or ""
    latex = asset.get("content", {}).get("latex", "")
    table_columns = []
    edited_table = None

    if asset["asset_type"] == "figure":
        alt_text = st.text_input(
            "Alternative text",
            value=alt_text,
            key=f"writing_object_alt_{asset_id}",
        )
        new_upload = st.file_uploader(
            "Replace image (optional)",
            type=("png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff"),
            key=f"writing_replace_figure_{asset_id}",
        )
    elif asset["asset_type"] == "equation":
        latex = st.text_area(
            "LaTeX equation",
            value=latex,
            height=90,
            key=f"writing_object_latex_{asset_id}",
        )

        if latex.strip():
            st.latex(latex)
    else:
        content = asset.get("content", {})
        old_columns = [str(column) for column in content.get("columns", [])]
        table_columns_text = st.text_input(
            "Columns (comma separated)",
            value=", ".join(old_columns),
            key=f"writing_object_columns_{asset_id}",
            help="Save to apply renamed or added columns.",
        )
        table_columns = _parse_table_columns(table_columns_text)
        edited_table = st.data_editor(
            pd.DataFrame(content.get("rows", []), columns=old_columns),
            num_rows="dynamic",
            width="stretch",
            hide_index=True,
            key=f"writing_object_table_editor_{asset_id}",
        )

    if st.button(
        "Save object",
        key=f"writing_save_object_{asset_id}",
        disabled=not caption.strip(),
        width="stretch",
    ):
        stored = None

        try:
            original_filename = asset.get("original_filename")
            storage_path = asset.get("storage_path")
            mime_type = asset.get("mime_type")
            content = asset.get("content", {})

            if asset["asset_type"] == "figure" and new_upload is not None:
                stored = save_figure_upload(
                    new_upload,
                    manuscript["id"],
                    replacing_storage_path=asset.get("storage_path"),
                )
                original_filename = stored["original_filename"]
                storage_path = stored["storage_path"]
                mime_type = stored["mime_type"]
                content = stored["content"]
            elif asset["asset_type"] == "equation":
                if not latex.strip():
                    raise ValueError("Equation LaTeX is required.")
                content = {"latex": latex.strip()}
            elif asset["asset_type"] == "table":
                if not table_columns:
                    raise ValueError("Add at least one table column.")
                rows = []

                for values in edited_table.itertuples(index=False, name=None):
                    rows.append({
                        column: _clean_table_cell(
                            values[index] if index < len(values) else ""
                        )
                        for index, column in enumerate(table_columns)
                    })
                content = {"columns": table_columns, "rows": rows}

            update_manuscript_asset(
                asset_id,
                caption=caption,
                alt_text=alt_text,
                original_filename=original_filename,
                storage_path=storage_path,
                mime_type=mime_type,
                content=content,
            )
            st.toast(f"{asset['label']} saved.")
            st.rerun()
        except Exception as exc:
            if stored and not isinstance(exc, StoredFileCleanupError):
                delete_manuscript_asset_file(stored["storage_path"])
            st.error(str(exc))

    st.divider()
    placements = {
        "End of current section": "end",
        "Beginning of current section": "beginning",
        "After a paragraph": "after_paragraph",
    }
    placement_label = st.selectbox(
        "Reference position",
        list(placements),
        key=f"writing_object_placement_{section['id']}_{asset_id}",
    )
    after_paragraph = None

    if placements[placement_label] == "after_paragraph":
        paragraphs = _split_paragraphs(current_content)

        if paragraphs:
            after_paragraph = st.selectbox(
                "Insert after",
                list(range(len(paragraphs))),
                format_func=lambda index: f"Paragraph {index + 1} · {paragraphs[index][:70]}",
                key=f"writing_object_after_paragraph_{section['id']}_{asset_id}",
            )

    if st.button(
        f"Insert {asset['label']} reference",
        key=f"writing_insert_object_reference_{section['id']}_{asset_id}",
        width="stretch",
    ):
        insert_manuscript_asset_reference(
            section["id"],
            asset_id,
            placement=placements[placement_label],
            after_paragraph=after_paragraph,
        )
        _reset_section_editor(section["id"])
        st.toast(f"Inserted {asset['label']} in the current section.")
        st.rerun()

    confirm_delete = st.checkbox(
        "Remove this object and its in-text references",
        key=f"writing_confirm_object_delete_{asset_id}",
    )

    if st.button(
        "Delete object",
        key=f"writing_delete_object_{asset_id}",
        disabled=not confirm_delete,
        width="stretch",
    ):
        delete_manuscript_asset(asset_id)
        _reset_section_editor(section["id"])
        st.rerun()


def _render_manuscript_objects(manuscript, section, sections, assets, current_content):
    type_counts = {
        asset_type: len([asset for asset in assets if asset["asset_type"] == asset_type])
        for asset_type in ("figure", "table", "equation")
    }
    label = (
        "Figures, tables & equations · "
        f"{type_counts['figure']} / {type_counts['table']} / {type_counts['equation']}"
    )

    with st.expander(label, expanded=False):
        manage_tab, add_tab = st.tabs(["Manage & reference", "Add new"])

        with manage_tab:
            _render_manage_manuscript_object(
                manuscript,
                section,
                sections,
                assets,
                current_content,
            )

        with add_tab:
            render_untrusted_caption(
                f"New objects are attached to {section['title']} and numbered globally."
            )
            _render_add_manuscript_object(manuscript, section)


def _render_editor(manuscript, section, sections, sources, assets):
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
    render_html('<div class="writing-editor-label">Manuscript text</div>')
    render_markdown_toolbar(content_key)
    st.text_area(
        "Manuscript text",
        key=content_key,
        height=470,
        placeholder="Write this section or ask AI to draft it from attached evidence…",
        label_visibility="collapsed",
        on_change=_autosave_section,
        args=(section["id"],),
    )
    _render_citation_tools(
        section,
        sources,
        st.session_state.get(content_key, ""),
    )
    _render_manuscript_objects(
        manuscript,
        section,
        sections,
        assets,
        st.session_state.get(content_key, ""),
    )
    saved_at = st.session_state.get("writing_last_saved_at")
    st.caption(
        f"Saved automatically at {saved_at}." if saved_at else "Changes save automatically when the editor loses focus."
    )

    with st.expander("Preview formatted section", expanded=False):
        preview = render_asset_references(
            render_citations(
                st.session_state.get(content_key, ""),
                sources,
                manuscript["citation_style"],
            ),
            assets,
        )
        render_untrusted_markdown(preview or "*This section is empty.*")

        for asset in assets:
            if asset["section_id"] == section["id"]:
                _render_readonly_asset(asset)


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


def _render_ai_context_selector(manuscript, section, sections, sources, evidence):
    settings = get_manuscript_ai_context(manuscript["id"])
    mode_key = f"writing_context_mode_{manuscript['id']}"
    section_key = f"writing_context_sections_{manuscript['id']}"
    source_key = f"writing_context_sources_{manuscript['id']}"
    evidence_key = f"writing_context_evidence_{manuscript['id']}"
    section_ids = [row["id"] for row in sections]
    source_ids = [row["library_item_id"] for row in sources]
    evidence_keys = [_evidence_context_key(row) for row in evidence]
    sections_by_id = {row["id"]: row for row in sections}
    sources_by_id = {row["library_item_id"]: row for row in sources}
    evidence_by_key = {_evidence_context_key(row): row for row in evidence}
    st.session_state.setdefault(mode_key, settings["context_mode"])

    for widget_key, allowed, saved in (
        (section_key, section_ids, settings["section_ids"]),
        (source_key, source_ids, settings["source_ids"]),
        (evidence_key, evidence_keys, settings["evidence_keys"]),
    ):
        allowed_set = set(allowed)

        if widget_key not in st.session_state:
            st.session_state[widget_key] = [value for value in saved if value in allowed_set]
        else:
            st.session_state[widget_key] = [
                value for value in st.session_state[widget_key] if value in allowed_set
            ]

    with st.expander(f"Select AI context · {settings['context_mode']}"):
        selected_mode = st.radio(
            "Context scope",
            AI_CONTEXT_MODES,
            key=mode_key,
        )

        if selected_mode == "Current section":
            st.caption(
                "Uses the active section plus all attached bibliographic sources and project evidence."
            )
        elif selected_mode == "Whole manuscript":
            st.caption(
                "Uses every manuscript section plus all attached bibliographic sources and project evidence."
            )
        else:
            st.multiselect(
                "Manuscript sections",
                section_ids,
                format_func=lambda value: sections_by_id[value]["title"],
                key=section_key,
            )
            st.multiselect(
                "Bibliographic sources",
                source_ids,
                format_func=lambda value: _citation_source_label(sources_by_id[value]),
                key=source_key,
                help="Type to search by title, author, or citation key.",
            )
            st.multiselect(
                "Project evidence",
                evidence_keys,
                format_func=lambda value: (
                    f"{evidence_by_key[value]['evidence_type'].replace('_', ' ').title()} · "
                    f"{evidence_by_key[value]['label']}"
                ),
                key=evidence_key,
            )
            st.caption("The active section remains the writing target even when it is not selected here.")

        if st.button(
            "Save AI context",
            key=f"writing_save_context_{manuscript['id']}",
            width="stretch",
        ):
            update_manuscript_ai_context(
                manuscript["id"],
                context_mode=selected_mode,
                section_ids=st.session_state.get(section_key, settings["section_ids"]),
                source_ids=st.session_state.get(source_key, settings["source_ids"]),
                evidence_keys=st.session_state.get(evidence_key, settings["evidence_keys"]),
            )
            st.toast("AI context saved.")
            st.rerun()

    settings, context_sections, context_sources, context_evidence = _resolve_ai_context(
        manuscript["id"],
        section,
        sections,
        sources,
        evidence,
    )
    render_html(
        '<div class="writing-context-summary">'
        f'<strong>{safe_html(settings["context_mode"])}</strong><br>'
        f'{len(context_sections)} section(s) · {len(context_sources)} source(s) · '
        f'{len(context_evidence)} evidence item(s)</div>'
    )
    return settings, context_sections, context_sources, context_evidence


def _render_ai_assistant(manuscript, section, sections, sources, evidence):
    render_html('<div class="writing-assistant-scope"></div>')
    render_html(
        '<div class="writing-panel-title">✦ AI Writing Assistant</div>'
        '<div class="writing-panel-caption">Choose exactly what AI may use for this request.</div>'
    )
    context_settings, context_sections, context_sources, context_evidence = (
        _render_ai_context_selector(manuscript, section, sections, sources, evidence)
    )
    mode = st.radio(
        "Assistant mode",
        WRITING_MODES,
        horizontal=True,
        key="writing_ai_mode",
    )
    render_html(
        '<div class="writing-ai-note">AI uses only the active context shown above. '
        'Suggestions are never applied automatically.</div>'
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
            render_untrusted_markdown(message["content"])

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
                    sources=context_sources,
                    evidence=context_evidence,
                    context_mode=context_settings["context_mode"],
                    context_sections=context_sections,
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
        suggestion_mode = st.session_state.get("writing_ai_suggestion_mode")
        suggested_text = suggestion.get("suggested_text", "")
        suggestion_tab, changes_tab = st.tabs(["Suggestion", "Changes"])

        with suggestion_tab:
            render_html(
                f'<div class="writing-suggestion"><strong>Suggested revision</strong><br><br>'
                f'{safe_html(suggested_text).replace(chr(10), "<br>")}</div>'
            )

        with changes_tab:
            render_html(
                '<div class="writing-ai-diff">'
                f'{_word_diff_html(section["content_md"], suggested_text)}'
                '</div>'
            )
            st.caption("Red text will be removed; green text will be added.")

        if suggestion.get("explanation"):
            render_untrusted_caption(suggestion["explanation"])

        context_used = suggestion.get("context_used") or {}

        if context_used:
            st.caption(
                f"Context used: {context_used.get('mode', 'Custom')} · "
                f"{len(context_used.get('section_ids', []))} sections · "
                f"{len(context_used.get('source_ids', []))} sources · "
                f"{len(context_used.get('evidence_keys', []))} evidence items"
            )

        if suggestion.get("evidence_used"):
            with st.expander("Evidence used", expanded=True):
                for item in suggestion["evidence_used"]:
                    render_html(
                        f'<div class="writing-evidence-card"><strong>{safe_html(item["label"])}</strong><br>'
                        f'{safe_html(item["support"])}</div>'
                    )

        if suggestion.get("claims"):
            with st.expander("Claim check", expanded=suggestion_mode == "Check claims"):
                for claim in suggestion["claims"]:
                    status_icon = {"supported": "✓", "weak": "△", "unsupported": "!"}[claim["status"]]
                    render_untrusted_markdown(
                        f"**{status_icon} {claim['status'].title()}** — {claim['claim']}"
                    )
                    render_untrusted_caption(
                        claim["reason"] or "No reason returned."
                    )

        if suggestion_mode != "Check claims":
            blocks = _split_paragraphs(suggested_text) or [suggested_text.strip()]
            suggestion_hash = hashlib.sha1(suggested_text.encode("utf-8")).hexdigest()[:10]
            selected_blocks_key = (
                f"writing_ai_selected_blocks_{section['id']}_{suggestion_hash}"
            )
            block_options = list(range(len(blocks)))

            selected_blocks_default = block_options

            if selected_blocks_key in st.session_state:
                st.session_state[selected_blocks_key] = [
                    value
                    for value in st.session_state[selected_blocks_key]
                    if value in block_options
                ]
                selected_blocks_default = None

            selected_blocks = st.multiselect(
                "Suggested blocks to apply",
                block_options,
                default=selected_blocks_default,
                format_func=lambda index: f"Block {index + 1} · {blocks[index][:75]}",
                key=selected_blocks_key,
            )
            placements = {
                "Replace current section": "replace",
                "Append to end": "end",
                "Insert at beginning": "beginning",
                "Insert after a paragraph": "after_paragraph",
            }
            placement_label = st.selectbox(
                "Apply position",
                list(placements),
                key=f"writing_ai_apply_position_{section['id']}_{suggestion_hash}",
            )
            after_paragraph = None

            if placements[placement_label] == "after_paragraph":
                current_paragraphs = _split_paragraphs(section["content_md"])

                if current_paragraphs:
                    paragraph_options = list(range(len(current_paragraphs)))
                    after_paragraph = st.selectbox(
                        "Insert after",
                        paragraph_options,
                        format_func=lambda index: (
                            f"Paragraph {index + 1} · {current_paragraphs[index][:65]}"
                        ),
                        key=f"writing_ai_after_paragraph_{section['id']}_{suggestion_hash}",
                    )
                else:
                    st.caption("The section is empty; the suggestion will be appended.")

            selected_text = "\n\n".join(blocks[index] for index in selected_blocks)
            selected_col, all_col = st.columns(2, gap="small")

            with selected_col:
                if st.button(
                    "Apply selected",
                    key=f"writing_ai_apply_selected_{suggestion_hash}",
                    disabled=not selected_blocks,
                    width="stretch",
                ):
                    _apply_ai_suggestion(
                        manuscript,
                        section,
                        selected_text,
                        placements[placement_label],
                        after_paragraph,
                    )
                    st.toast("Selected AI blocks applied.")
                    st.rerun()

            with all_col:
                if st.button(
                    "Apply all",
                    key=f"writing_ai_apply_all_{suggestion_hash}",
                    width="stretch",
                ):
                    _apply_ai_suggestion(
                        manuscript,
                        section,
                        suggested_text,
                        placements[placement_label],
                        after_paragraph,
                    )
                    st.toast("AI suggestion applied.")
                    st.rerun()

        if st.button(
            "Reject suggestion" if suggestion_mode != "Check claims" else "Dismiss analysis",
            key=f"writing_ai_reject_{section['id']}",
            width="stretch",
        ):
            _clear_ai_suggestion()
            st.rerun()

    if messages and st.button("Clear AI conversation", width="stretch"):
        clear_manuscript_ai_messages(manuscript["id"])
        _clear_ai_suggestion()
        st.rerun()


def _apply_submission_template_defaults(manuscript_id: int):
    template_name = st.session_state.get(
        f"writing_submission_template_{manuscript_id}",
        "General IMRaD",
    )
    rules = template_rules(template_name)
    st.session_state[f"writing_submission_word_limit_{manuscript_id}"] = rules["word_limit"]
    st.session_state[f"writing_submission_abstract_limit_{manuscript_id}"] = rules[
        "abstract_word_limit"
    ]


def _render_manuscript_checks(manuscript, sections, sources, profile):
    checks = run_manuscript_checks(manuscript, sections, sources, profile)
    error_count = checks["counts"].get("error", 0)
    warning_count = checks["counts"].get("warning", 0)

    with st.expander(
        f"Manuscript checks · {checks['score']}/100 · {error_count} errors · {warning_count} warnings",
        expanded=False,
    ):
        render_html(
            '<div class="writing-check-summary">'
            f'<div><strong>{safe_html(checks["template"])}</strong><br>'
            f'{checks["word_count"]:,}/{checks["word_limit"]:,} manuscript words · '
            f'{checks["abstract_word_count"]:,}/{checks["abstract_word_limit"]:,} abstract words</div>'
            f'<div class="writing-check-score">{checks["score"]}/100</div></div>'
        )

        if not checks["issues"]:
            st.success("No manuscript issues were detected by the current rule set.")
            return checks

        categories = sorted({issue["category"] for issue in checks["issues"]})
        filter_col, severity_col = st.columns(2, gap="small")

        with filter_col:
            category = st.selectbox(
                "Check category",
                ["All", *categories],
                key=f"writing_check_category_{manuscript['id']}",
            )

        with severity_col:
            severity = st.selectbox(
                "Severity",
                ["All", "error", "warning", "info"],
                format_func=lambda value: value.title(),
                key=f"writing_check_severity_{manuscript['id']}",
            )

        visible = [
            issue
            for issue in checks["issues"]
            if (category == "All" or issue["category"] == category)
            and (severity == "All" or issue["severity"] == severity)
        ]

        for index, issue in enumerate(visible):
            render_html(
                f'<div class="writing-check-card {safe_html(issue["severity"])}">'
                f'<strong>{safe_html(issue["title"])}</strong>'
                f'<span>{safe_html(issue["category"])} · {safe_html(issue["severity"].title())}</span><br>'
                f'{safe_html(issue["detail"])}'
                + (
                    f'<div class="writing-check-suggestion">Suggestion: {safe_html(issue["suggestion"])}</div>'
                    if issue.get("suggestion")
                    else ""
                )
                + "</div>"
            )

            if issue.get("section_id") and st.button(
                f"Open {issue['section_title']}",
                key=f"writing_open_check_{manuscript['id']}_{index}_{issue['section_id']}",
            ):
                st.session_state["writing_section_id"] = issue["section_id"]
                st.rerun()

    return checks


def _clean_editor_records(frame, fields):
    records = []

    for raw in frame.to_dict("records"):
        record = {}

        for field in fields:
            value = raw.get(field, "")
            record[field] = "" if pd.isna(value) else str(value).strip()

        if record.get(fields[0]):
            records.append(record)

    return records


def _render_publication_panel(manuscript, sections, sources, assets, profile, checks):
    manuscript_id = manuscript["id"]
    template_key = f"writing_submission_template_{manuscript_id}"
    word_limit_key = f"writing_submission_word_limit_{manuscript_id}"
    abstract_limit_key = f"writing_submission_abstract_limit_{manuscript_id}"
    st.session_state.setdefault(template_key, profile["journal_template"])
    st.session_state.setdefault(word_limit_key, profile["word_limit"])
    st.session_state.setdefault(abstract_limit_key, profile["abstract_word_limit"])

    with st.expander("Publication readiness", expanded=False):
        render_html(
            '<div class="writing-panel-title">Submission profile</div>'
            '<div class="writing-panel-caption">Configure front matter, journal rules, and the final submission checklist.</div>'
        )
        journal_template = st.selectbox(
            "Journal template",
            list(JOURNAL_TEMPLATES),
            key=template_key,
            on_change=_apply_submission_template_defaults,
            args=(manuscript_id,),
        )
        st.caption(JOURNAL_TEMPLATES[journal_template]["description"])

        with st.form(f"writing_submission_profile_form_{manuscript_id}"):
            journal_col, template_col = st.columns([1.25, 1], gap="small")

            with journal_col:
                target_journal = st.text_input(
                    "Target journal",
                    value=profile["target_journal"],
                    placeholder="Journal name",
                )
                short_title = st.text_input(
                    "Short title",
                    value=profile["short_title"],
                    max_chars=80,
                )

            with template_col:
                word_limit = st.number_input(
                    "Main-text word limit",
                    min_value=1,
                    step=100,
                    key=word_limit_key,
                )
                abstract_word_limit = st.number_input(
                    "Abstract word limit",
                    min_value=1,
                    step=25,
                    key=abstract_limit_key,
                )

            st.markdown("**Authors**")
            author_rows = profile["authors"] or [
                {"name": "", "affiliations": "", "email": "", "orcid": ""}
            ]
            authors_frame = st.data_editor(
                pd.DataFrame(author_rows),
                num_rows="dynamic",
                hide_index=True,
                width="stretch",
                key=f"writing_submission_authors_{manuscript_id}",
                column_config={
                    "name": st.column_config.TextColumn("Name", required=True),
                    "affiliations": st.column_config.TextColumn("Affiliation IDs", help="For example: 1,2"),
                    "email": st.column_config.TextColumn("Email"),
                    "orcid": st.column_config.TextColumn("ORCID"),
                },
            )

            st.markdown("**Affiliations**")
            affiliation_rows = profile["affiliations"] or [
                {"label": "1", "institution": "", "location": ""}
            ]
            affiliations_frame = st.data_editor(
                pd.DataFrame(affiliation_rows),
                num_rows="dynamic",
                hide_index=True,
                width="stretch",
                key=f"writing_submission_affiliations_{manuscript_id}",
                column_config={
                    "label": st.column_config.TextColumn("ID", width="small"),
                    "institution": st.column_config.TextColumn("Institution", required=True),
                    "location": st.column_config.TextColumn("City, country"),
                },
            )

            corresponding = profile.get("corresponding_author") or {}
            corresponding_col, email_col = st.columns(2, gap="small")

            with corresponding_col:
                corresponding_name = st.text_input(
                    "Corresponding author",
                    value=corresponding.get("name", ""),
                )

            with email_col:
                corresponding_email = st.text_input(
                    "Corresponding author email",
                    value=corresponding.get("email", ""),
                )

            keywords_text = st.text_input(
                "Keywords",
                value=", ".join(profile["keywords"]),
                placeholder="keyword one, keyword two, keyword three",
                help="Separate keywords with commas.",
            )

            st.markdown("**Submission checklist**")
            checklist = {}
            checklist_labels = {
                "author_approval": "All authors approved the final manuscript",
                "cover_letter": "Cover letter prepared",
                "conflicts_disclosed": "Conflicts of interest disclosed",
                "ethics_statement": "Ethics statement verified",
                "data_availability": "Data availability statement verified",
                "figures_verified": "Figure resolution and legends verified",
                "supplementary_files": "Supplementary files attached or not applicable",
            }
            checklist_columns = st.columns(2, gap="small")

            for index, (key, label) in enumerate(checklist_labels.items()):
                with checklist_columns[index % 2]:
                    checklist[key] = st.checkbox(
                        label,
                        value=bool(profile["checklist"].get(key)),
                        key=f"writing_submission_checklist_{manuscript_id}_{key}",
                    )

            submitted = st.form_submit_button(
                "Save publication profile",
                width="stretch",
            )

        if submitted:
            try:
                update_manuscript_submission_profile(
                    manuscript_id,
                    target_journal=target_journal,
                    journal_template=journal_template,
                    short_title=short_title,
                    authors=_clean_editor_records(
                        authors_frame,
                        ("name", "affiliations", "email", "orcid"),
                    ),
                    affiliations=_clean_editor_records(
                        affiliations_frame,
                        ("institution", "label", "location"),
                    ),
                    corresponding_author={
                        "name": corresponding_name.strip(),
                        "email": corresponding_email.strip(),
                    },
                    keywords=[value.strip() for value in keywords_text.split(",") if value.strip()],
                    word_limit=word_limit,
                    abstract_word_limit=abstract_word_limit,
                    checklist=checklist,
                )
                st.toast("Publication profile saved.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        readiness = publication_readiness(
            manuscript,
            sections,
            sources,
            assets,
            profile,
            checks,
        )
        render_html(
            f'<div class="writing-check-summary"><div><strong>Submission checklist</strong><br>'
            f'{readiness["complete"]}/{readiness["total"]} checks completed</div>'
            f'<div class="writing-check-score">{readiness["percent"]}%</div></div>'
        )
        items_html = "".join(
            f'<div class="writing-ready-item {"done" if item["complete"] else ""}">'
            f'{"✓" if item["complete"] else "○"} <strong>{safe_html(item["label"])}</strong><br>'
            f'{safe_html(item["detail"])}</div>'
            for item in readiness["items"]
        )
        render_html(f'<div class="writing-ready-grid">{items_html}</div>')
        abstract_section = next(
            (
                section
                for section in sections
                if str(section["section_type"]).casefold() == "abstract"
            ),
            None,
        )

        if abstract_section and st.button(
            "Open Abstract section",
            key=f"writing_open_submission_abstract_{manuscript_id}",
        ):
            st.session_state["writing_section_id"] = abstract_section["id"]
            st.rerun()

        st.caption(
            "Journal requirements change. Treat the selected template as an editable starting point and verify the target journal's current author instructions before submission."
        )


def _render_manuscript_tab(manuscript):
    sections = get_manuscript_sections(manuscript["id"])
    sources = get_manuscript_sources(manuscript["id"])
    assets = get_manuscript_assets(manuscript["id"])
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
        _render_editor(manuscript, section, sections, sources, assets)

    with assistant_col:
        _render_ai_assistant(manuscript, section, sections, sources, evidence)

    profile = get_manuscript_submission_profile(manuscript["id"])
    checks = _render_manuscript_checks(manuscript, sections, sources, profile)
    _render_publication_panel(
        manuscript,
        sections,
        sources,
        assets,
        profile,
        checks,
    )


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
        render_untrusted_markdown(
            source["abstract"] or "No abstract is available."
        )

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

        source_url = safe_external_url(source["url"])

        if source_url:
            st.link_button("Open original source", source_url, width="stretch")


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
                render_untrusted_markdown(line)

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
                render_untrusted_markdown(f"**{row['label']}**")
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
                render_untrusted_markdown(f"**{row['label']}**")
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


def _snapshot_section_for_current(snapshot: dict, current_section) -> dict | None:
    snapshot_sections = snapshot.get("sections", [])
    current_id = int(current_section["id"])
    by_id = next(
        (row for row in snapshot_sections if int(row.get("id") or 0) == current_id),
        None,
    )

    if by_id:
        return by_id

    current_type = str(current_section["section_type"] or "").casefold()
    current_title = str(current_section["title"] or "").casefold()
    return next(
        (
            row
            for row in snapshot_sections
            if str(row.get("section_type") or "").casefold() == current_type
            and str(row.get("title") or "").casefold() == current_title
        ),
        None,
    )


def _version_section_text(version_id: int, current_section, versions_by_id) -> str:
    if version_id == 0:
        return str(current_section["content_md"] or "")

    version = versions_by_id.get(version_id)

    if not version:
        return ""

    snapshot_section = _snapshot_section_for_current(version["snapshot"], current_section)
    return (
        str(snapshot_section.get("content_md") or "")
        if snapshot_section
        else "[Section not present in this version]"
    )


def _render_versions_tab(manuscript):
    render_html('<div class="writing-versions-scope"></div>')
    versions = get_manuscript_versions(manuscript["id"])
    version_details = {
        version["id"]: get_manuscript_version(version["id"])
        for version in versions
    }
    sections = get_manuscript_sections(manuscript["id"])
    create_col, compare_col = st.columns([1, 2], gap="small")

    with create_col:
        render_html(
            '<div class="writing-panel-title">Create snapshot</div>'
            '<div class="writing-panel-caption">Save an immutable version of the current manuscript.</div>'
        )

        with st.form("create_manuscript_version_form", clear_on_submit=True):
            label_preset = st.selectbox(
                "Version label",
                (
                    "Before supervisor review",
                    "Before co-author review",
                    "Before journal submission",
                    "Milestone draft",
                    "Custom label",
                ),
            )
            custom_label = st.text_input(
                "Custom label",
                placeholder=f"Draft {len(versions) + 1}",
                disabled=label_preset != "Custom label",
            )
            note = st.text_area(
                "Version description",
                height=90,
                placeholder="What changed or what should reviewers focus on?",
            )
            submitted = st.form_submit_button("Save version", width="stretch")

        if submitted:
            try:
                label = (
                    custom_label or f"Draft {len(versions) + 1}"
                    if label_preset == "Custom label"
                    else label_preset
                )
                create_manuscript_version(
                    manuscript["id"],
                    label,
                    note=note,
                )
                st.toast("Version saved.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with compare_col:
        render_html(
            '<div class="writing-panel-title">Compare versions</div>'
            '<div class="writing-panel-caption">Compare the whole manuscript or the same section between snapshots.</div>'
        )
        options = [0, *[version["id"] for version in versions]]
        versions_by_id = {
            version_id: details
            for version_id, details in version_details.items()
            if details
        }

        def version_label(value):
            if value == 0:
                return "Current manuscript"

            row = next(version for version in versions if version["id"] == value)
            return f"{row['label']} · {compact_date(row['created_at'])}"

        compare_scope = st.radio(
            "Comparison scope",
            ("Whole manuscript", "Single section"),
            horizontal=True,
            key=f"writing_diff_scope_{manuscript['id']}",
        )
        compare_section = None

        if compare_scope == "Single section" and sections:
            section_ids = [section["id"] for section in sections]
            section_by_id = {section["id"]: section for section in sections}
            compare_section_id = st.selectbox(
                "Section",
                section_ids,
                format_func=lambda value: section_by_id[value]["title"],
                key=f"writing_diff_section_{manuscript['id']}",
            )
            compare_section = section_by_id[compare_section_id]

        left_col, right_col = st.columns(2, gap="small")

        with left_col:
            left_version = st.selectbox(
                "From",
                options,
                format_func=version_label,
                key=f"writing_diff_left_{manuscript['id']}",
            )

        with right_col:
            right_version = st.selectbox(
                "To",
                options,
                index=1 if len(options) > 1 else 0,
                format_func=version_label,
                key=f"writing_diff_right_{manuscript['id']}",
            )

        if compare_section is not None:
            left_text = _version_section_text(
                left_version,
                compare_section,
                versions_by_id,
            )
            right_text = _version_section_text(
                right_version,
                compare_section,
                versions_by_id,
            )
        else:
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
                render_untrusted_markdown(f"**{version['label']}**")
                render_html(
                    f'<div class="writing-version-comment">'
                    f'{safe_html(version["note"] or "No version comment.")}</div>'
                )

            with meta_col:
                st.caption(
                    f"{'AI' if version['trigger_type'] == 'ai' else version['trigger_type'].title()} · "
                    f"{version['word_count']:,} words · "
                    f"{compact_date(version['created_at'])}"
                )

            restore_col, section_col, duplicate_col = st.columns(3, gap="small")

            with restore_col:
                with st.popover("Restore all", width="stretch"):
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

            with section_col:
                with st.popover("Restore section", width="stretch"):
                    details = version_details.get(version["id"])
                    snapshot_sections = details["snapshot"].get("sections", []) if details else []

                    if not snapshot_sections or not sections:
                        st.caption("No section is available for granular restoration.")
                    else:
                        snapshot_ids = [int(row["id"]) for row in snapshot_sections]
                        snapshot_by_id = {int(row["id"]): row for row in snapshot_sections}
                        selected_snapshot_id = st.selectbox(
                            "Version section",
                            snapshot_ids,
                            format_func=lambda value: snapshot_by_id[value].get("title", "Untitled section"),
                            key=f"writing_restore_snapshot_section_{version['id']}",
                        )
                        selected_snapshot = snapshot_by_id[selected_snapshot_id]
                        target_ids = [section["id"] for section in sections]
                        target_by_id = {section["id"]: section for section in sections}
                        matching_target = next(
                            (
                                section["id"]
                                for section in sections
                                if str(section["section_type"]).casefold()
                                == str(selected_snapshot.get("section_type") or "").casefold()
                            ),
                            target_ids[0],
                        )
                        target_section_id = st.selectbox(
                            "Restore into",
                            target_ids,
                            index=target_ids.index(matching_target),
                            format_func=lambda value: target_by_id[value]["title"],
                            key=f"writing_restore_target_section_{version['id']}_{selected_snapshot_id}",
                        )
                        restore_title = st.checkbox(
                            "Also restore the section title",
                            key=f"writing_restore_section_title_{version['id']}",
                        )
                        st.caption("Restores text and citations. Current figures, tables, and equations are preserved.")

                        if st.button(
                            "Confirm section restore",
                            key=f"writing_restore_section_confirm_{version['id']}",
                            width="stretch",
                        ):
                            create_manuscript_version(
                                manuscript["id"],
                                f"Before restoring {target_by_id[target_section_id]['title']}",
                                trigger_type="restore",
                                note=f"Automatic snapshot before restoring one section from {version['label']}.",
                            )
                            restore_manuscript_section_from_version(
                                version["id"],
                                selected_snapshot_id,
                                target_section_id,
                                restore_title=restore_title,
                            )
                            _reset_section_editor(target_section_id)
                            st.session_state["writing_section_id"] = target_section_id
                            st.toast("Section restored.")
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

            with st.expander("Edit label and description"):
                with st.form(f"writing_edit_version_{version['id']}"):
                    edited_label = st.text_input(
                        "Version label",
                        value=version["label"],
                    )
                    edited_note = st.text_area(
                        "Version description",
                        value=version["note"] or "",
                        height=90,
                    )
                    save_annotation = st.form_submit_button(
                        "Save label and description",
                        width="stretch",
                    )

                if save_annotation:
                    try:
                        update_manuscript_version(
                            version["id"],
                            label=edited_label,
                            note=edited_note,
                        )
                        st.toast("Version annotation saved.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

            with st.expander(f"Comments · {version['comment_count']}"):
                comments = get_manuscript_version_comments(version["id"])

                if not comments:
                    st.caption("No review comments attached to this version.")

                for comment in comments:
                    render_html(
                        f'<div class="writing-version-comment"><strong>'
                        f'{safe_html(comment["author_name"])}</strong> · '
                        f'{safe_html(compact_date(comment["created_at"]))}<br>'
                        f'{safe_html(comment["content"])}</div>'
                    )

                with st.form(f"writing_add_version_comment_{version['id']}", clear_on_submit=True):
                    comment_author = st.text_input(
                        "Comment author",
                        value="Dr. Alex Morgan",
                    )
                    comment_content = st.text_area(
                        "Add review comment",
                        height=80,
                        placeholder="Add feedback or a decision associated with this snapshot…",
                    )
                    add_comment = st.form_submit_button(
                        "Add comment",
                        width="stretch",
                    )

                if add_comment:
                    try:
                        add_manuscript_version_comment(
                            version["id"],
                            comment_content,
                            author_name=comment_author,
                        )
                        st.toast("Version comment added.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))


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
    assets = get_manuscript_assets(manuscript_id)
    submission_profile = get_manuscript_submission_profile(manuscript_id)
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
        _render_export_popover(
            manuscript,
            sections,
            sources,
            assets,
            submission_profile,
        )

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
