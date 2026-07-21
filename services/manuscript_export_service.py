import io
import re
from html import escape
from pathlib import Path


def _author_parts(authors: str) -> list[str]:
    return [part.strip() for part in re.split(r"[;]", authors or "") if part.strip()]


def _author_surname(author: str) -> str:
    if "," in author:
        return author.split(",", 1)[0].strip() or "Unknown"

    words = re.findall(r"[\wÀ-ž'-]+", author)
    return words[-1] if words else "Unknown"


def _apa_inline(source) -> str:
    authors = _author_parts(source["authors"] or "")
    year = source["publication_year"] or "n.d."

    if not authors:
        author_label = source["title"] or "Unknown source"
    elif len(authors) == 1:
        author_label = _author_surname(authors[0])
    elif len(authors) == 2:
        author_label = (
            f"{_author_surname(authors[0])} & {_author_surname(authors[1])}"
        )
    else:
        author_label = f"{_author_surname(authors[0])} et al."

    return f"({author_label}, {year})"


def _apa_reference(source) -> str:
    authors = source["authors"] or "Unknown author"
    year = source["publication_year"] or "n.d."
    title = source["title"] or "Untitled source"
    journal = source["source_name"] or ""
    doi = source["doi"] or ""
    url = source["url"] or ""
    tail = f" https://doi.org/{doi}" if doi else (f" {url}" if url else "")
    journal_part = f" *{journal}*." if journal else ""
    return f"{authors} ({year}). {title}.{journal_part}{tail}".strip()


def _vancouver_reference(source, number: int) -> str:
    authors = source["authors"] or "Unknown author"
    title = source["title"] or "Untitled source"
    journal = source["source_name"] or ""
    year = source["publication_year"] or "n.d."
    doi = source["doi"] or ""
    tail = f" doi:{doi}." if doi else ""
    journal_part = f" {journal}." if journal else ""
    return f"{number}. {authors}. {title}.{journal_part} {year}.{tail}".strip()


def render_citations(text: str, sources, style: str) -> str:
    by_key = {source["citation_key"].casefold(): source for source in sources}
    vancouver_numbers = {
        source["citation_key"].casefold(): index
        for index, source in enumerate(sources, start=1)
    }

    def replace(match):
        key = match.group(1).strip().casefold()
        source = by_key.get(key)

        if not source:
            return match.group(0)

        if style == "Vancouver":
            return f"[{vancouver_numbers[key]}]"

        return _apa_inline(source)

    return re.sub(r"\[@([^\]]+)\]", replace, text or "")


def bibliography_lines(sources, style: str) -> list[str]:
    ordered = list(sources)

    if style == "APA 7":
        ordered.sort(key=lambda source: (
            str(source["authors"] or "").casefold(),
            str(source["title"] or "").casefold(),
        ))
        return [_apa_reference(source) for source in ordered]

    return [
        _vancouver_reference(source, index)
        for index, source in enumerate(ordered, start=1)
    ]


def manuscript_markdown(manuscript, sections, sources) -> str:
    style = manuscript["citation_style"]
    parts = [f"# {manuscript['title']}"]
    references_written = False

    for section in sections:
        title = section["title"]
        parts.append(f"\n## {title}\n")

        if section["section_type"] == "references":
            lines = bibliography_lines(sources, style)
            parts.append("\n\n".join(lines) if lines else "No sources attached.")
            references_written = True
        else:
            parts.append(render_citations(section["content_md"], sources, style))

    if sources and not references_written:
        parts.append("\n## References\n")
        parts.append("\n\n".join(bibliography_lines(sources, style)))

    return "\n".join(parts).strip() + "\n"


def manuscript_docx(manuscript, sections, sources) -> bytes:
    try:
        from docx import Document
        from docx.shared import Inches, Pt
    except ImportError as exc:
        raise RuntimeError(
            "DOCX export requires the python-docx dependency."
        ) from exc

    document = Document()
    document.core_properties.title = manuscript["title"]
    document.sections[0].top_margin = Inches(0.8)
    document.sections[0].bottom_margin = Inches(0.8)
    normal = document.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(11)
    document.add_heading(manuscript["title"], level=0)
    style = manuscript["citation_style"]
    references_written = False

    for section in sections:
        document.add_heading(section["title"], level=1)

        if section["section_type"] == "references":
            lines = bibliography_lines(sources, style)

            for line in lines or ["No sources attached."]:
                document.add_paragraph(line)

            references_written = True
            continue

        content = render_citations(section["content_md"], sources, style)

        for block in re.split(r"\n\s*\n", content.strip()):
            if not block:
                continue

            if block.startswith("- "):
                for line in block.splitlines():
                    document.add_paragraph(line.removeprefix("- "), style="List Bullet")
            else:
                document.add_paragraph(block)

    if sources and not references_written:
        document.add_heading("References", level=1)

        for line in bibliography_lines(sources, style):
            document.add_paragraph(line)

    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _register_pdf_font() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = (
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )

    for path in candidates:
        if path.is_file():
            pdfmetrics.registerFont(TTFont("ResearchJournalUnicode", str(path)))
            return "ResearchJournalUnicode"

    return "Helvetica"


def manuscript_pdf(manuscript, sections, sources) -> bytes:
    try:
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ImportError as exc:
        raise RuntimeError(
            "PDF export requires the reportlab dependency."
        ) from exc

    output = io.BytesIO()
    font_name = _register_pdf_font()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ResearchTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=19,
        leading=23,
        alignment=TA_CENTER,
        spaceAfter=14,
    )
    heading_style = ParagraphStyle(
        "ResearchHeading",
        parent=styles["Heading1"],
        fontName=font_name,
        fontSize=14,
        leading=18,
        spaceBefore=10,
        spaceAfter=7,
    )
    body_style = ParagraphStyle(
        "ResearchBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=15,
        spaceAfter=8,
    )
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=22 * mm,
        leftMargin=22 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=manuscript["title"],
    )
    story = [Paragraph(escape(manuscript["title"]), title_style)]
    style = manuscript["citation_style"]
    references_written = False

    for section in sections:
        story.append(Paragraph(escape(section["title"]), heading_style))

        if section["section_type"] == "references":
            blocks = bibliography_lines(sources, style) or ["No sources attached."]
            references_written = True
        else:
            content = render_citations(section["content_md"], sources, style)
            blocks = re.split(r"\n\s*\n", content.strip()) if content.strip() else [""]

        for block in blocks:
            safe_block = escape(block).replace("\n", "<br/>")
            story.append(Paragraph(safe_block or "&#160;", body_style))

    if sources and not references_written:
        story.append(Paragraph("References", heading_style))

        for line in bibliography_lines(sources, style):
            story.append(Paragraph(escape(line), body_style))

    story.append(Spacer(1, 5 * mm))
    document.build(story)
    return output.getvalue()
