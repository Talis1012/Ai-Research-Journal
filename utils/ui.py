import html
import math
from datetime import datetime
from textwrap import dedent

import streamlit as st

from utils.auth import current_user_profile, logout


def safe_html(value) -> str:
    return html.escape(str(value or ""))


def _mindmap_row_value(row, key: str, default=""):
    try:
        value = row[key]
    except (KeyError, TypeError, IndexError):
        value = default

    return default if value is None else value


def _mindmap_label_lines(label: str, max_chars: int = 22) -> list[str]:
    words = str(label or "Fără etichetă").split()
    lines = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()

        if current and len(candidate) > max_chars:
            lines.append(current)
            current = word
        else:
            current = candidate

    if current:
        lines.append(current)

    if len(lines) > 2:
        lines = [lines[0], f"{lines[1][:max_chars - 1].rstrip()}…"]

    return lines or ["Fără etichetă"]


def mindmap_preview_svg(nodes, edges, max_nodes: int = 9) -> str:
    if not nodes:
        return ""

    node_data = {
        str(_mindmap_row_value(node, "node_key")): {
            "key": str(_mindmap_row_value(node, "node_key")),
            "label": str(_mindmap_row_value(node, "label", "Fără etichetă")),
            "description": str(_mindmap_row_value(node, "description", "")),
            "importance": str(
                _mindmap_row_value(node, "importance", "medium")
            ).lower(),
        }
        for node in nodes
        if _mindmap_row_value(node, "node_key")
    }

    if not node_data:
        return ""

    valid_edges = []
    degree = {node_key: 0 for node_key in node_data}

    for edge in edges or []:
        source = str(_mindmap_row_value(edge, "source_key"))
        target = str(_mindmap_row_value(edge, "target_key"))

        if source not in node_data or target not in node_data or source == target:
            continue

        valid_edges.append({
            "source": source,
            "target": target,
            "relation": str(_mindmap_row_value(edge, "relation", "")),
        })
        degree[source] += 1
        degree[target] += 1

    ordered_keys = sorted(
        node_data,
        key=lambda node_key: (-degree[node_key], node_data[node_key]["label"].lower()),
    )
    center_key = ordered_keys[0]
    neighbor_keys = []

    for edge in valid_edges:
        if edge["source"] == center_key:
            neighbor_keys.append(edge["target"])
        elif edge["target"] == center_key:
            neighbor_keys.append(edge["source"])

    neighbor_keys = sorted(
        set(neighbor_keys),
        key=lambda node_key: (-degree[node_key], node_data[node_key]["label"].lower()),
    )
    remaining_keys = [
        node_key
        for node_key in ordered_keys
        if node_key != center_key and node_key not in neighbor_keys
    ]
    visible_keys = [center_key, *(neighbor_keys + remaining_keys)[: max_nodes - 1]]
    visible_set = set(visible_keys)

    width = 900
    height = 440
    center_x = width / 2
    center_y = 215
    positions = {center_key: (center_x, center_y)}
    peripheral_keys = visible_keys[1:]

    for index, node_key in enumerate(peripheral_keys):
        angle = -math.pi / 2 + (2 * math.pi * index / len(peripheral_keys))
        positions[node_key] = (
            center_x + 330 * math.cos(angle),
            center_y + 160 * math.sin(angle),
        )

    edge_markup = []

    for edge in valid_edges:
        if edge["source"] not in visible_set or edge["target"] not in visible_set:
            continue

        source_x, source_y = positions[edge["source"]]
        target_x, target_y = positions[edge["target"]]
        edge_markup.append(
            f"""
            <line x1="{source_x:.1f}" y1="{source_y:.1f}"
                  x2="{target_x:.1f}" y2="{target_y:.1f}"
                  class="mindmap-preview-edge" marker-end="url(#mindmap-arrow)">
                <title>{safe_html(edge['relation'] or 'Legătură')}</title>
            </line>
            """
        )

    palette = {
        "high": ("#fff0f3", "#d14f71", "#9d3151"),
        "medium": ("#eaf3ff", "#8fc0ff", "#285f9d"),
        "low": ("#eef8e6", "#b9dc91", "#52752e"),
    }
    node_markup = []

    for node_key in visible_keys:
        node = node_data[node_key]
        x, y = positions[node_key]
        is_center = node_key == center_key
        node_width = 220 if is_center else 174
        node_height = 58 if is_center else 48

        if is_center:
            fill, stroke, text_color = "#73b7f3", "#0e58ad", "#111827"
        else:
            fill, stroke, text_color = palette.get(
                node["importance"],
                palette["medium"],
            )

        label_lines = _mindmap_label_lines(
            node["label"],
            max_chars=26 if is_center else 20,
        )
        first_line_y = y - 7 if len(label_lines) == 2 else y + 5
        tspans = "".join(
            f'<tspan x="{x:.1f}" y="{first_line_y + line_index * 17:.1f}">'
            f"{safe_html(line)}</tspan>"
            for line_index, line in enumerate(label_lines)
        )
        node_markup.append(
            f"""
            <g class="mindmap-preview-node">
                <title>{safe_html(node['description'] or node['label'])}</title>
                <rect x="{x - node_width / 2:.1f}" y="{y - node_height / 2:.1f}"
                      width="{node_width}" height="{node_height}" rx="11"
                      fill="{fill}" stroke="{stroke}" stroke-width="1.5"></rect>
                <text x="{x:.1f}" text-anchor="middle" fill="{text_color}"
                      class="{'mindmap-preview-center-text' if is_center else 'mindmap-preview-node-text'}">
                    {tspans}
                </text>
            </g>
            """
        )

    hidden_count = max(0, len(node_data) - len(visible_keys))
    hidden_markup = (
        f'<text x="450" y="430" text-anchor="middle" class="mindmap-preview-more">'
        f'+{hidden_count} noduri disponibile în mindmap-ul complet</text>'
        if hidden_count
        else ""
    )

    return dedent(
        f"""
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                overflow: hidden;
                background: transparent;
            }}

            .mindmap-graph-preview {{
                width: 100%;
                overflow: hidden;
                border-radius: 8px;
                background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
            }}

            .mindmap-graph-preview svg {{
                display: block;
                width: 100%;
                height: 320px;
            }}

            .mindmap-preview-edge {{
                stroke: #98a4b7;
                stroke-width: 2;
                opacity: 0.82;
            }}

            .mindmap-preview-node-text,
            .mindmap-preview-center-text {{
                font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                font-size: 14px;
                font-weight: 760;
                pointer-events: none;
            }}

            .mindmap-preview-center-text {{
                font-size: 15px;
                font-weight: 820;
            }}

            .mindmap-preview-more {{
                fill: #667085;
                font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                font-size: 13px;
                font-weight: 650;
            }}
        </style>
        <div class="mindmap-graph-preview">
            <svg viewBox="0 0 {width} {height}" role="img"
                 aria-label="Preview al mindmap-ului salvat">
                <defs>
                    <marker id="mindmap-arrow" markerWidth="8" markerHeight="8"
                            refX="7" refY="3" orient="auto" markerUnits="strokeWidth">
                        <path d="M0,0 L0,6 L7,3 z" fill="#98a4b7"></path>
                    </marker>
                </defs>
                {''.join(edge_markup)}
                {''.join(node_markup)}
                {hidden_markup}
            </svg>
        </div>
        """
    ).strip()


def render_mindmap_preview(nodes, edges, max_nodes: int = 9):
    markup = mindmap_preview_svg(nodes, edges, max_nodes=max_nodes)

    if markup:
        st.iframe(
            markup,
            width="stretch",
            height=330,
            tab_index=-1,
        )


def render_html(markup: str):
    st.html(dedent(str(markup)).strip())


def compact_date(value: str | None) -> str:
    if not value:
        return ""

    try:
        created = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)

    now = datetime.now()

    if created.date() == now.date():
        return created.strftime("%-I:%M %p")

    if created.year == now.year:
        return created.strftime("%b %-d")

    return created.strftime("%b %-d, %Y")


def load_css():
    render_html(
        """
        <style>
        :root {
            --app-bg: #ffffff;
            --topbar-h: 62px;
            --panel: #ffffff;
            --panel-soft: #f8fbff;
            --line: #dfe6ef;
            --line-soft: #edf1f6;
            --text: #101828;
            --muted: #667085;
            --muted-2: #8a95a8;
            --blue: #1769d2;
            --blue-2: #0f8ab7;
            --blue-soft: #e8f2ff;
            --teal: #138c98;
            --green: #2d9b59;
            --purple: #7d4ad8;
            --amber: #b98216;
            --pink: #cf4a6c;
            --shadow: 0 8px 22px rgba(16, 24, 40, 0.055);
        }

        .stApp {
            background: var(--app-bg);
            color: var(--text);
        }

        html, body, [class*="css"] {
            font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            letter-spacing: 0;
        }

        header[data-testid="stHeader"] {
            display: none;
        }

        section[data-testid="stSidebar"] {
            display: none;
        }

        .block-container {
            max-width: 1920px;
            padding: 0;
        }

        div[data-testid="stVerticalBlock"] {
            gap: 0.35rem;
        }

        div[data-testid="column"] {
            padding: 0 !important;
        }

        .top-brand-scope,
        .top-project-scope,
        .top-search-scope,
        .top-user-scope,
        .nav-panel-scope,
        .work-panel-scope,
        .center-panel-scope,
        .right-panel-scope {
            display: none;
        }

        h1, h2, h3, p {
            letter-spacing: 0;
        }

        h1, h2, h3 {
            color: var(--text);
        }

        .muted {
            color: var(--muted);
            font-size: 0.88rem;
        }

        .tiny-muted {
            color: var(--muted-2);
            font-size: 0.76rem;
        }

        .rjai-shell {
            min-height: 100vh;
            background: var(--app-bg);
        }

        div[data-testid="stHorizontalBlock"]:has(.top-brand-scope) {
            min-height: var(--topbar-h);
            background: #ffffff;
            border-bottom: 1px solid var(--line);
        }

        div[data-testid="column"]:has(.top-brand-scope),
        div[data-testid="column"]:has(.top-project-scope),
        div[data-testid="column"]:has(.top-search-scope),
        div[data-testid="column"]:has(.top-user-scope) {
            min-height: var(--topbar-h);
            background: #ffffff;
            border-bottom: 1px solid var(--line);
        }

        div[data-testid="column"]:has(.top-project-scope) {
            padding: 7px 14px 0 0 !important;
        }

        div[data-testid="column"]:has(.top-search-scope) {
            padding: 0 16px 0 12px !important;
        }

        div[data-testid="column"]:has(.top-user-scope) {
            padding: 0 18px 0 0 !important;
        }

        .topbar {
            min-height: var(--topbar-h);
            padding: 0 16px 0 20px;
            background: transparent;
            border-bottom: 0;
            display: flex;
            align-items: center;
        }

        .brand-wrap {
            display: flex;
            align-items: center;
            gap: 10px;
            min-height: 42px;
        }

        .brand-logo {
            width: 48px;
            height: 48px;
            flex: 0 0 auto;
            color: #1492bc;
        }

        .molecule-logo {
            width: 38px;
            height: 38px;
            flex: 0 0 auto;
            position: relative;
        }

        .molecule-logo .node {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #1296bf;
            position: absolute;
            transform: translate(-50%, -50%);
        }

        .molecule-logo .bond {
            height: 2px;
            background: #1296bf;
            position: absolute;
            transform-origin: left center;
            opacity: 0.9;
        }

        .molecule-logo .n1 { left: 50%; top: 8%; }
        .molecule-logo .n2 { left: 13%; top: 28%; }
        .molecule-logo .n3 { left: 13%; top: 72%; }
        .molecule-logo .n4 { left: 50%; top: 92%; }
        .molecule-logo .n5 { left: 87%; top: 72%; }
        .molecule-logo .n6 { left: 87%; top: 28%; }
        .molecule-logo .n7 { left: 50%; top: 50%; }

        .molecule-logo .b1 { width: 15px; left: 50%; top: 13%; transform: rotate(90deg); }
        .molecule-logo .b2 { width: 16px; left: 18%; top: 31%; transform: rotate(30deg); }
        .molecule-logo .b3 { width: 16px; left: 18%; top: 69%; transform: rotate(-30deg); }
        .molecule-logo .b4 { width: 15px; left: 50%; top: 87%; transform: rotate(-90deg); }
        .molecule-logo .b5 { width: 16px; left: 82%; top: 69%; transform: rotate(210deg); }
        .molecule-logo .b6 { width: 16px; left: 82%; top: 31%; transform: rotate(150deg); }

        .brand-title {
            font-size: 1.08rem;
            font-weight: 820;
            color: #111827;
            line-height: 1;
            white-space: nowrap;
        }

        .header-icons {
            display: flex;
            justify-content: flex-end;
            align-items: center;
            gap: 16px;
            min-height: var(--topbar-h);
            padding-top: 0;
            color: #526078;
            font-weight: 700;
        }

        .icon-circle {
            width: 28px;
            height: 28px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border: 1px solid transparent;
            font-size: 1rem;
            position: relative;
        }

        .icon-help,
        .icon-bell {
            width: 22px;
            height: 22px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            position: relative;
            color: #526078;
        }

        .icon-help::before,
        .icon-bell::before {
            content: "";
            width: 20px;
            height: 20px;
            background: currentColor;
            opacity: 0.92;
        }

        .icon-help::before {
            mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.1' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='10'/%3E%3Cpath d='M9.09 9a3 3 0 1 1 5.82 1c0 2-3 2-3 4'/%3E%3Cpath d='M12 17h.01'/%3E%3C/svg%3E") center / contain no-repeat;
            -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.1' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='10'/%3E%3Cpath d='M9.09 9a3 3 0 1 1 5.82 1c0 2-3 2-3 4'/%3E%3Cpath d='M12 17h.01'/%3E%3C/svg%3E") center / contain no-repeat;
        }

        .icon-bell::before {
            mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.1' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M18 8a6 6 0 0 0-12 0c0 7-3 7-3 7h18s-3 0-3-7'/%3E%3Cpath d='M13.73 21a2 2 0 0 1-3.46 0'/%3E%3C/svg%3E") center / contain no-repeat;
            -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.1' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M18 8a6 6 0 0 0-12 0c0 7-3 7-3 7h18s-3 0-3-7'/%3E%3Cpath d='M13.73 21a2 2 0 0 1-3.46 0'/%3E%3C/svg%3E") center / contain no-repeat;
        }

        .notification-dot {
            position: absolute;
            right: -6px;
            top: -7px;
            min-width: 15px;
            height: 15px;
            border-radius: 999px;
            background: #0ea5d5;
            color: #ffffff;
            font-size: 0.58rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border: 2px solid #ffffff;
        }

        .user-chip {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: #111827;
            font-size: 0.82rem;
            font-weight: 800;
            white-space: nowrap;
        }

        .avatar-photo {
            width: 34px;
            height: 34px;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background:
                radial-gradient(circle at 50% 28%, #f5c6a2 0 18%, transparent 19%),
                linear-gradient(180deg, #17324d 0 52%, #e7edf5 53% 100%);
            border: 2px solid #e6edf7;
            overflow: hidden;
        }

        div[data-testid="column"]:has(.top-project-scope) label {
            color: #667085 !important;
            font-size: 0.68rem !important;
            font-weight: 760 !important;
            line-height: 1.05 !important;
            margin-bottom: 3px !important;
        }

        div[data-testid="column"]:has(.top-project-scope) div[data-baseweb="select"] > div {
            min-height: 40px !important;
            height: 40px !important;
            border: 1px solid #d8e1ed !important;
            border-radius: 8px !important;
            background: #ffffff !important;
            box-shadow: none !important;
            font-size: 0.82rem !important;
            font-weight: 800 !important;
        }

        div[data-testid="column"]:has(.top-project-scope) div[data-baseweb="select"] > div::before {
            content: "⚗";
            color: #526078;
            font-size: 1rem;
            margin: 0 9px 0 4px;
        }

        div[class*="st-key-project_global_search"] {
            position: relative;
            margin-top: 10px !important;
        }

        div[class*="st-key-project_global_search"]::before {
            content: "";
            position: absolute;
            left: 15px;
            top: 50%;
            transform: translateY(-50%);
            z-index: 2;
            width: 17px;
            height: 17px;
            background: #566276;
            mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.1' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cpath d='m21 21-4.35-4.35'/%3E%3C/svg%3E") center / contain no-repeat;
            -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.1' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cpath d='m21 21-4.35-4.35'/%3E%3C/svg%3E") center / contain no-repeat;
        }

        div[class*="st-key-project_global_search"]::after {
            content: "⌘K";
            position: absolute;
            right: 11px;
            top: 50%;
            transform: translateY(-50%);
            z-index: 2;
            height: 21px;
            min-width: 31px;
            border-radius: 6px;
            background: #f1f4f8;
            color: #667085;
            font-size: 0.66rem;
            font-weight: 850;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }

        div[class*="st-key-project_global_search"] div[data-baseweb="input"] {
            min-height: 42px !important;
            height: 42px !important;
            border: 1px solid #d8e1ed !important;
            border-radius: 8px !important;
            overflow: hidden !important;
            background: #ffffff !important;
            box-shadow: none !important;
        }

        div[class*="st-key-project_global_search"] div[data-baseweb="base-input"] {
            min-height: 40px !important;
            height: 40px !important;
            border: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
        }

        div[class*="st-key-project_global_search"] input {
            min-height: 40px !important;
            height: 40px !important;
            border: 0 !important;
            border-radius: 0 !important;
            padding-left: 44px !important;
            padding-right: 52px !important;
            box-shadow: none !important;
            font-size: 0.82rem !important;
            font-weight: 600 !important;
            background: transparent !important;
        }

        .left-rail {
            min-height: calc(100vh - var(--topbar-h));
            background: #ffffff;
            border-right: 0;
            padding: 26px 18px 22px 20px;
        }

        div[data-testid="stHorizontalBlock"]:has(.nav-panel-scope) {
            background: #ffffff;
        }

        div[data-testid="column"]:has(.nav-panel-scope) {
            min-height: calc(100vh - var(--topbar-h));
            background: #ffffff;
            border-right: 1px solid var(--line);
        }

        .nav-item {
            height: 48px;
            display: flex;
            align-items: center;
            gap: 12px;
            border-radius: 7px;
            padding: 0 13px;
            color: #2d3748;
            font-size: 0.96rem;
            font-weight: 600;
            margin-bottom: 8px;
            text-decoration: none;
        }

        .nav-item.active {
            background: #eaf3ff;
            color: #1064cc;
        }

        .nav-item:hover {
            background: #f3f7fc;
            color: #1064cc;
        }

        .nav-icon {
            width: 22px;
            text-align: center;
            color: inherit;
            font-size: 1.12rem;
        }

        .work-panel {
            min-height: calc(100vh - var(--topbar-h));
            background: #ffffff;
            border-right: 1px solid var(--line);
            padding: 28px 18px 22px;
        }

        div[data-testid="column"]:has(.work-panel-scope) {
            min-height: calc(100vh - var(--topbar-h));
            background: #ffffff;
            border-right: 1px solid var(--line);
            padding: 26px 18px 22px !important;
        }

        div[data-testid="column"]:has(.work-panel-scope) > div[data-testid="stVerticalBlock"] {
            gap: 0.48rem;
        }

        .center-panel {
            min-height: calc(100vh - var(--topbar-h));
            background: #ffffff;
            border-right: 1px solid var(--line);
            padding: 22px 26px 26px;
        }

        div[data-testid="column"]:has(.center-panel-scope) {
            min-height: calc(100vh - var(--topbar-h));
            background: #ffffff;
            border-right: 1px solid var(--line);
            padding: 22px 26px 26px !important;
        }

        div[data-testid="column"]:has(.center-panel-scope) > div[data-testid="stVerticalBlock"] {
            gap: 0.55rem;
        }

        .right-panel {
            min-height: calc(100vh - var(--topbar-h));
            background: #ffffff;
            padding: 24px 22px 24px;
        }

        div[data-testid="column"]:has(.right-panel-scope) {
            min-height: calc(100vh - var(--topbar-h));
            background: #ffffff;
            padding: 24px 22px 24px !important;
        }

        div[data-testid="column"]:has(.right-panel-scope) > div[data-testid="stVerticalBlock"] {
            gap: 1.05rem;
        }

        .section-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 22px;
        }

        .section-title {
            font-size: 1.03rem;
            font-weight: 850;
            color: #111827;
        }

        div[data-testid="column"]:has(.work-panel-scope) .section-title {
            font-size: 1.06rem;
            line-height: 38px;
            padding-top: 0 !important;
            margin: 0;
        }

        div[class*="st-key-new_experiment_button"] button {
            min-height: 38px !important;
            height: 38px !important;
            border: 0 !important;
            border-radius: 7px !important;
            background: linear-gradient(180deg, #1599ca 0%, #08769f 100%) !important;
            color: #ffffff !important;
            font-size: 0.9rem !important;
            font-weight: 850 !important;
            box-shadow: 0 5px 13px rgba(8, 115, 159, 0.25) !important;
            padding: 0 13px !important;
        }

        div[class*="st-key-new_experiment_button"] button:hover {
            background: linear-gradient(180deg, #18a4d8 0%, #0879a5 100%) !important;
            color: #ffffff !important;
        }

        div[class*="st-key-experiment_search_input"] {
            position: relative;
        }

        div[class*="st-key-experiment_search_input"]::before {
            content: "⌕";
            position: absolute;
            z-index: 2;
            left: 16px;
            top: 50%;
            transform: translateY(-54%);
            color: #566276;
            font-size: 1.28rem;
            line-height: 1;
            pointer-events: none;
        }

        div[class*="st-key-experiment_search_input"] input {
            min-height: 43px !important;
            height: 43px !important;
            border-radius: 7px !important;
            border-color: #d9e1eb !important;
            padding-left: 46px !important;
            font-size: 0.9rem !important;
            font-weight: 600 !important;
            color: #111827 !important;
        }

        div[class*="st-key-experiment_search_input"] input::placeholder {
            color: #8994a7 !important;
            opacity: 1;
        }

        div[class*="st-key-experiment_filter_control"] div[data-testid="stPopover"] > button {
            position: relative !important;
            min-height: 43px !important;
            height: 43px !important;
            width: 43px !important;
            padding: 0 !important;
            border: 1px solid #d9e1eb !important;
            border-radius: 7px !important;
            background: #ffffff !important;
            color: transparent !important;
            font-size: 0 !important;
            font-weight: 850 !important;
            box-shadow: none !important;
        }

        div[class*="st-key-experiment_filter_control"] div[data-testid="stPopover"] > button::before {
            content: "";
            width: 19px;
            height: 19px;
            background: #526078;
            mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.1' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolygon points='22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3'/%3E%3C/svg%3E") center / contain no-repeat;
            -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.1' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolygon points='22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3'/%3E%3C/svg%3E") center / contain no-repeat;
        }

        div[class*="st-key-experiment_filter_control"] div[data-testid="stPopover"] > button:hover {
            border-color: #b8c6d8 !important;
            background: #f8fbff !important;
            color: #1769d2 !important;
        }

        div[class*="st-key-experiment_filter_control"] div[data-testid="stPopover"] > button:hover::before {
            background: #1769d2;
        }

        .new-pill {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            height: 38px;
            padding: 0 15px;
            border-radius: 6px;
            background: linear-gradient(180deg, #0f97c6 0%, #08739f 100%);
            color: #ffffff;
            font-weight: 800;
            font-size: 0.9rem;
            box-shadow: 0 4px 12px rgba(8, 115, 159, 0.22);
        }

        .filter-button {
            height: 42px;
            width: 42px;
            border: 1px solid #d6e0ec;
            border-radius: 7px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #526078;
            background: #ffffff;
            margin-left: 10px;
        }

        .filter-button.active {
            border-color: #1769d2;
            background: #eaf3ff;
            color: #0d65d9;
        }

        .filter-status {
            color: #667085;
            font-size: 0.74rem;
            margin-top: 8px;
            line-height: 1.35;
        }

        .date-label {
            color: #778295;
            font-size: 0.8rem;
            margin: 18px 0 8px;
            font-weight: 600;
        }

        .experiment-row {
            border-bottom: 1px solid var(--line-soft);
            padding: 13px 54px 13px 14px;
            min-height: 74px;
            position: relative;
            border-radius: 0;
            display: block;
            text-decoration: none;
        }

        .experiment-row.selected {
            border: 1px solid #c9dcf7;
            background: linear-gradient(180deg, #eef6ff 0%, #e6f1ff 100%);
            border-radius: 7px;
            box-shadow: 0 6px 16px rgba(21, 101, 192, 0.06);
            margin-bottom: 8px;
            min-height: 76px;
        }

        .experiment-row:hover {
            background: #f7fbff;
        }

        .experiment-title {
            color: #111827;
            font-size: 0.9rem;
            line-height: 1.25;
            font-weight: 820;
            padding-right: 48px;
        }

        .experiment-row.selected .experiment-title {
            color: #1264c9;
        }

        .experiment-snippet {
            color: #667085;
            font-size: 0.79rem;
            line-height: 1.45;
            margin-top: 6px;
            max-width: 100%;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .experiment-time {
            position: absolute;
            top: 15px;
            right: 54px;
            color: #667085;
            font-size: 0.76rem;
            font-weight: 650;
        }

        div[class*="st-key-experiment_item_"] {
            position: relative !important;
            margin-bottom: 0 !important;
        }

        div[class*="st-key-experiment_item_"] div[data-testid="stLayoutWrapper"]:has(div[data-testid="stPopover"]) {
            position: absolute !important;
            top: 12px !important;
            right: 7px !important;
            width: 34px !important;
            z-index: 6 !important;
        }

        div[class*="st-key-experiment_item_"] div[data-testid="stPopover"] {
            width: 34px !important;
        }

        div[class*="st-key-experiment_item_"] div[data-testid="stPopover"] > button {
            min-height: 34px !important;
            height: 34px !important;
            width: 34px !important;
            padding: 0 !important;
            border: 0 !important;
            background: transparent !important;
            color: #526078 !important;
            font-size: 1.1rem !important;
            box-shadow: none !important;
        }

        div[class*="st-key-experiment_item_"] div[data-testid="stPopover"] > button:hover {
            background: rgba(23, 105, 210, 0.08) !important;
        }

        .chat-header {
            border-bottom: 1px solid var(--line);
            padding-bottom: 0;
            margin-bottom: 0;
        }

        .chat-title-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 14px;
        }

        .chat-title {
            font-size: 1.15rem;
            font-weight: 850;
            color: #111827;
            line-height: 1.2;
        }

        .chat-actions {
            color: #526078;
            display: flex;
            gap: 16px;
            font-size: 1.16rem;
            align-items: center;
            white-space: nowrap;
        }

        .tabs {
            display: flex;
            align-items: center;
            gap: 28px;
            margin-top: 25px;
        }

        .tab {
            padding-bottom: 14px;
            color: #526078;
            font-size: 0.94rem;
            font-weight: 720;
        }

        .tab.active {
            color: #0d65d9;
            border-bottom: 3px solid #0d65d9;
        }

        div[data-testid="column"]:has(.center-panel-scope) div[data-testid="stTabs"] {
            margin-top: 6px;
        }

        div[data-testid="column"]:has(.center-panel-scope) div[data-testid="stTabs"] button {
            min-height: 44px !important;
            padding: 0 20px !important;
            color: #526078 !important;
            font-size: 0.9rem !important;
            font-weight: 760 !important;
        }

        div[data-testid="column"]:has(.center-panel-scope) div[data-testid="stTabs"] button[aria-selected="true"] {
            color: #0d65d9 !important;
            font-weight: 850 !important;
        }

        div[data-testid="column"]:has(.center-panel-scope) div[data-testid="stTabs"] hr {
            border-color: var(--line) !important;
        }

        .message-row {
            display: grid;
            grid-template-columns: 42px 1fr;
            gap: 16px;
            margin: 18px 0 22px;
        }

        .avatar-initials,
        .assistant-avatar {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
            font-size: 0.78rem;
            font-weight: 850;
        }

        .avatar-initials {
            background: #1d70dc;
        }

        .assistant-avatar {
            background: linear-gradient(135deg, #229ac6 0%, #48a6ba 100%);
            box-shadow: 0 5px 12px rgba(34, 154, 198, 0.2);
        }

        .message-meta {
            display: flex;
            align-items: center;
            gap: 14px;
            margin-bottom: 8px;
        }

        .message-name {
            color: #111827;
            font-weight: 820;
            font-size: 0.88rem;
        }

        .message-time {
            color: #8a95a8;
            font-size: 0.76rem;
        }

        .message-body {
            color: #1f2937;
            font-size: 0.92rem;
            line-height: 1.58;
        }

        .message-body ul {
            margin: 8px 0 10px 19px;
            padding: 0;
        }

        .message-tools {
            display: flex;
            gap: 8px;
            margin-top: 16px;
        }

        .tool-chip {
            border: 1px solid #d9e1eb;
            border-radius: 6px;
            min-height: 33px;
            padding: 0 11px;
            display: inline-flex;
            align-items: center;
            gap: 7px;
            color: #526078;
            font-size: 0.82rem;
            font-weight: 750;
            background: #ffffff;
        }

        .composer-shell {
            border: 1px solid #d6e0ec;
            border-radius: 9px;
            background: #ffffff;
            padding: 14px 16px 16px;
            margin-top: 28px;
        }

        .composer-toolbar {
            display: flex;
            gap: 17px;
            color: #526078;
            font-weight: 850;
            font-size: 0.95rem;
            margin-bottom: 8px;
        }

        .audio-card {
            border: 1px solid #dce5ef;
            border-radius: 9px;
            background: #ffffff;
            padding: 18px 16px;
            margin-top: 18px;
        }

        .audio-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 18px;
        }

        .audio-title {
            color: #111827;
            font-size: 0.95rem;
            font-weight: 850;
        }

        .audio-clock {
            color: #111827;
            font-size: 0.98rem;
            font-weight: 850;
        }

        .wave-wrap {
            display: grid;
            grid-template-columns: 44px 1fr;
            align-items: center;
            gap: 14px;
        }

        .stop-circle {
            width: 42px;
            height: 42px;
            border-radius: 50%;
            border: 1px solid #a9d4f1;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #0997bd;
            font-size: 1rem;
        }

        .waveform {
            height: 44px;
            background:
                linear-gradient(90deg, transparent 0 3px, #57a8ea 3px 5px, transparent 5px 8px),
                linear-gradient(180deg, transparent 0 45%, rgba(87, 168, 234, 0.22) 45% 55%, transparent 55%);
            background-size: 8px 100%, 100% 100%;
            border-radius: 4px;
            mask-image: repeating-linear-gradient(
                90deg,
                transparent 0 1px,
                #000 1px 4px,
                transparent 4px 8px
            );
        }

        .transcript-preview {
            color: #1f2937;
            font-size: 0.84rem;
            line-height: 1.45;
            margin-top: 16px;
        }

        .metric-card {
            border: 1px solid #dfe6ef;
            background: #ffffff;
            border-radius: 8px;
            padding: 16px 14px;
            min-height: 136px;
            box-shadow: var(--shadow);
        }

        div[data-testid="column"]:has(.right-panel-scope) .metric-card {
            min-height: 136px;
            padding: 15px 14px;
            border-radius: 8px;
        }

        .page-shell {
            padding: 28px 30px 36px;
            min-height: calc(100vh - var(--topbar-h));
            background: #ffffff;
        }

        .page-title {
            color: #111827;
            font-size: 1.85rem;
            font-weight: 880;
            line-height: 1.1;
            margin-bottom: 8px;
        }

        .page-subtitle {
            color: #667085;
            font-size: 0.98rem;
            line-height: 1.5;
            margin-bottom: 24px;
        }

        .theme-card {
            border: 1px solid #dfe6ef;
            border-radius: 8px;
            background: #ffffff;
            box-shadow: var(--shadow);
            padding: 18px;
            margin-bottom: 16px;
        }

        .metric-chip {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: #111827;
            font-size: 0.75rem;
            font-weight: 850;
            margin-bottom: 17px;
        }

        .metric-icon {
            width: 20px;
            height: 20px;
            border-radius: 5px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 0.72rem;
        }

        .metric-value {
            color: #101828;
            font-size: 1.85rem;
            font-weight: 850;
            line-height: 1;
        }

        .metric-subtitle {
            color: #526078;
            font-size: 0.78rem;
            line-height: 1.35;
            margin-top: 4px;
        }

        .metric-updated {
            color: #667085;
            font-size: 0.73rem;
            margin-top: 16px;
        }

        .side-card {
            border: 1px solid #dfe6ef;
            border-radius: 8px;
            background: #ffffff;
            box-shadow: var(--shadow);
            padding: 18px 15px;
            margin-top: 22px;
        }

        .side-card-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 16px;
        }

        .side-title {
            color: #111827;
            font-size: 1rem;
            font-weight: 850;
        }

        .link-button {
            display: inline-flex;
            align-items: center;
            height: 34px;
            padding: 0 14px;
            border-radius: 6px;
            background: #eaf3ff;
            color: #0d65d9;
            font-size: 0.78rem;
            font-weight: 820;
            white-space: nowrap;
        }

        div[data-testid="column"]:has(.center-panel-scope) div[data-testid="stVerticalBlockBorderWrapper"],
        div[data-testid="column"]:has(.right-panel-scope) div[data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid #dfe6ef !important;
            border-radius: 8px !important;
            background: #ffffff !important;
            box-shadow: var(--shadow) !important;
        }

        div[data-testid="column"]:has(.center-panel-scope) div[data-testid="stVerticalBlockBorderWrapper"] > div,
        div[data-testid="column"]:has(.right-panel-scope) div[data-testid="stVerticalBlockBorderWrapper"] > div {
            border-radius: 8px !important;
        }

        div[data-testid="column"]:has(.right-panel-scope) h3 {
            font-size: 0.98rem !important;
            font-weight: 850 !important;
            letter-spacing: 0 !important;
        }

        div[data-testid="column"]:has(.right-panel-scope) div[data-testid="stPageLink"] a {
            min-height: 34px;
            border-radius: 6px;
            background: #eaf3ff;
            color: #0d65d9;
            font-size: 0.78rem;
            font-weight: 820;
            padding: 0 13px;
        }

        .mindmap-graph-preview {
            width: 100%;
            margin: 3px 0 2px;
            overflow: hidden;
            border-radius: 8px;
            background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
        }

        .mindmap-graph-preview svg {
            display: block;
            width: 100%;
            height: auto;
            min-height: 255px;
            max-height: 370px;
        }

        .mindmap-preview-edge {
            stroke: #98a4b7;
            stroke-width: 2;
            opacity: 0.82;
        }

        .mindmap-preview-node-text,
        .mindmap-preview-center-text {
            font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            font-size: 14px;
            font-weight: 760;
            pointer-events: none;
        }

        .mindmap-preview-center-text {
            font-size: 15px;
            font-weight: 820;
        }

        .mindmap-preview-more {
            fill: #667085;
            font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            font-size: 13px;
            font-weight: 650;
        }

        .paper-card {
            border: 1px solid #dfe6ef;
            border-radius: 7px;
            padding: 14px;
            margin-bottom: 10px;
            background: #ffffff;
            min-height: 108px;
            position: relative;
        }

        .paper-bookmark {
            position: absolute;
            top: 17px;
            right: 15px;
            color: #344054;
            font-size: 1.1rem;
        }

        .pill {
            display: inline-flex;
            align-items: center;
            height: 20px;
            padding: 0 8px;
            border-radius: 5px;
            font-size: 0.66rem;
            font-weight: 820;
            margin-right: 5px;
        }

        .pill-blue { background: #e5f1ff; color: #1769d2; }
        .pill-green { background: #e5f7ec; color: #2d9b59; }
        .pill-purple { background: #f0e9ff; color: #7d4ad8; }
        .pill-teal { background: #e0f7f8; color: #138c98; }
        .pill-yellow { background: #fff4d9; color: #b98216; }
        .pill-pink { background: #ffe8ee; color: #cf4a6c; }
        .pill-gray { background: #eef2f6; color: #667085; }

        .paper-title {
            color: #111827;
            font-size: 0.86rem;
            font-weight: 830;
            line-height: 1.35;
            margin-top: 8px;
            padding-right: 26px;
        }

        .paper-authors {
            color: #667085;
            font-size: 0.73rem;
            line-height: 1.35;
            margin-top: 7px;
        }

        .right-footer-link {
            color: #0d65d9;
            text-align: right;
            font-size: 0.8rem;
            font-weight: 820;
            margin-top: 16px;
        }

        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea,
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
            border-color: #d6e0ec !important;
            border-radius: 7px !important;
            min-height: 42px;
            background: #ffffff;
            box-shadow: none !important;
        }

        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea {
            color: #111827;
            font-size: 0.9rem;
        }

        div[data-testid="stTextArea"] textarea {
            min-height: 88px !important;
        }

        .stButton > button,
        div[data-testid="stFormSubmitButton"] button {
            border-radius: 7px;
            border: 1px solid #cbd7e6;
            background: #ffffff;
            color: #145fc4;
            font-weight: 820;
            min-height: 38px;
            box-shadow: none;
        }

        .stButton > button:hover,
        div[data-testid="stFormSubmitButton"] button:hover {
            border-color: #1769d2;
            background: #eef6ff;
            color: #0d65d9;
        }

        details {
            border: 1px solid #dfe6ef !important;
            border-radius: 8px !important;
            background: #ffffff !important;
            box-shadow: none !important;
        }

        @media (max-width: 1100px) {
            .left-rail,
            .work-panel,
            .center-panel,
            .right-panel {
                min-height: auto;
                border-right: 0;
                border-bottom: 1px solid var(--line);
            }

            .topbar {
                min-height: auto;
            }
        }
        </style>
        """
    )


def brand_logo_svg() -> str:
    return """
    <div class="molecule-logo" aria-hidden="true">
        <span class="bond b1"></span>
        <span class="bond b2"></span>
        <span class="bond b3"></span>
        <span class="bond b4"></span>
        <span class="bond b5"></span>
        <span class="bond b6"></span>
        <span class="node n1"></span>
        <span class="node n2"></span>
        <span class="node n3"></span>
        <span class="node n4"></span>
        <span class="node n5"></span>
        <span class="node n6"></span>
        <span class="node n7"></span>
    </div>
    """


def top_brand():
    render_html(
        f"""
        <div class="top-brand-scope"></div>
        <div class="topbar">
            <div class="brand-wrap">
                {brand_logo_svg()}
                <div class="brand-title">Research Journal AI</div>
            </div>
        </div>
        """
    )


def page_brand_header():
    brand_col, _ = st.columns([1.05, 5.3], gap="small")

    with brand_col:
        top_brand()


def user_chip(name: str = "Dr. Alex Morgan"):
    render_html(
        f"""
        <div class="user-chip">
            <span class="avatar-photo"></span>
            <span>{safe_html(name)}</span>
            <span style="color:#667085;">⌄</span>
        </div>
        """
    )


def sidebar_nav(active_page: str = "experiments"):
    active_aliases = {
        "projects": "experiments",
        "experiment_chat": "experiments",
        "summaries": "experiments",
        "mindmap": "experiments",
        "bibliography": "library",
    }
    active_page = active_aliases.get(active_page, active_page)
    items = [
        ("experiments", "/Experiments", "🧪", "Experiments"),
        ("library", "/Library", "📚", "Library"),
        ("paper_writing", "/Paper_Writing", "✎", "Paper Writing"),
    ]

    nav_html = "\n".join(
        f"""
        <a class="nav-item {'active' if item_id == active_page else ''}" href="{href}" target="_self">
            <span class="nav-icon">{icon}</span><span>{label}</span>
        </a>
        """
        for item_id, href, icon, label in items
    )

    render_html(
        f"""
        <div class="left-rail">
            {nav_html}
        </div>
        """
    )


def header_icons():
    profile = current_user_profile()
    icon_col, account_col = st.columns([0.32, 0.68], gap="small")

    with icon_col:
        render_html(
            """
            <div class="header-icons">
                <span class="icon-help" aria-hidden="true"></span>
                <span class="icon-bell" aria-hidden="true"></span>
            </div>
            """
        )

    with account_col:
        with st.popover(
            profile["name"],
            icon=":material/account_circle:",
            width="stretch",
        ):
            st.text(profile["name"])

            if profile["email"]:
                st.caption(profile["email"])

            st.button(
                "Deconectare",
                icon=":material/logout:",
                width="stretch",
                on_click=logout,
                key="auth_logout_button",
            )


def experiment_card(title: str, snippet: str, created_at: str, selected: bool = False, chat_id: int | None = None):
    class_name = "experiment-row selected" if selected else "experiment-row"
    tag = "a" if chat_id is not None else "div"
    href = f' href="?chat_id={chat_id}" target="_self"' if chat_id is not None else ""

    render_html(
        f"""
        <{tag} class="{class_name}"{href}>
            <div class="experiment-title">{safe_html(title)}</div>
            <div class="experiment-time">{safe_html(compact_date(created_at))}</div>
            <div class="experiment-snippet">{safe_html(snippet or "No objective added yet.")}</div>
        </{tag}>
        """
    )


def stat_card(title: str, value: str, subtitle: str, icon: str, tone: str = "blue", updated: str = "Ready"):
    colors = {
        "blue": ("#e5f1ff", "#1769d2"),
        "green": ("#e5f7ec", "#2d9b59"),
        "purple": ("#f0e9ff", "#7d4ad8"),
        "teal": ("#e0f7f8", "#138c98"),
    }
    bg, color = colors.get(tone, colors["blue"])

    render_html(
        f"""
        <div class="metric-card">
            <div class="metric-chip">
                <span class="metric-icon" style="background:{bg}; color:{color};">{safe_html(icon)}</span>
                <span>{safe_html(title)}</span>
            </div>
            <div class="metric-value">{safe_html(value)}</div>
            <div class="metric-subtitle">{safe_html(subtitle)}</div>
            <div class="metric-updated">{safe_html(updated)}</div>
        </div>
        """
    )


def chat_message(author: str, initials: str, created_at: str, content: str, assistant: bool = False):
    avatar_class = "assistant-avatar" if assistant else "avatar-initials"
    body = safe_html(content).replace("\n", "<br>")

    render_html(
        f"""
        <div class="message-row">
            <div class="{avatar_class}">{safe_html(initials)}</div>
            <div>
                <div class="message-meta">
                    <span class="message-name">{safe_html(author)}</span>
                    <span class="message-time">{safe_html(compact_date(created_at))}</span>
                </div>
                <div class="message-body">{body}</div>
            </div>
        </div>
        """
    )


def assistant_summary_message(created_at: str, title: str):
    title = safe_html(title)
    render_html(
        f"""
        <div class="message-row">
            <div class="assistant-avatar">✦</div>
            <div>
                <div class="message-meta">
                    <span class="message-name">Research Journal AI</span>
                    <span class="message-time">{safe_html(compact_date(created_at))}</span>
                </div>
                <div class="message-body">
                    Here's a summary of the SAR trends based on your recent experiments:
                    <ul>
                        <li>{title} shows the strongest signal in the latest notes.</li>
                        <li>Compare solvent, pH, and temperature observations before the next run.</li>
                        <li>Repeated visual changes should be tagged as key stability evidence.</li>
                        <li>Audio transcripts are ready to turn into structured experiment notes.</li>
                    </ul>
                    Would you like a full table of the data or a visualization?
                </div>
                <div class="message-tools">
                    <span class="tool-chip">▣</span>
                    <span class="tool-chip">♡</span>
                    <span class="tool-chip">▽</span>
                    <span class="tool-chip">▥ Visualize</span>
                </div>
            </div>
        </div>
        """
    )


def composer_shell():
    render_html(
        """
        <div class="composer-shell">
            <div class="composer-toolbar">
                <span>B</span><span><i>I</i></span><span><u>U</u></span>
                <span style="height:16px;width:1px;background:#dfe6ef;display:inline-block;"></span>
                <span>≡</span><span>{ }</span><span>↗</span><span>▧</span><span>♙</span>
            </div>
        </div>
        """
    )


def audio_visual_card(transcript: str = ""):
    preview = transcript or "...observed a downfield shift in the aromatic region around 7.8 ppm, which supports the formation of the desired product..."

    render_html(
        f"""
        <div class="audio-card">
            <div class="audio-head">
                <div class="audio-title">Audio Recording &amp; Transcription <span style="color:#8a95a8;">ⓘ</span></div>
                <div class="audio-clock">00:00:24</div>
            </div>
            <div class="wave-wrap">
                <div class="stop-circle">■</div>
                <div class="waveform"></div>
            </div>
            <div class="transcript-preview">{safe_html(preview)}</div>
        </div>
        """
    )
