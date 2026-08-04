import hashlib
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from db.data_analysis_queries import (
    complete_analysis_run,
    create_analysis_run,
    fail_analysis_run,
    get_analysis_run,
    get_analysis_runs,
)
from db.database import init_db_once
from db.library_queries import create_library_item, get_library_item, get_library_items
from services.data_analysis_service import (
    ALGORITHM_CATALOG,
    OBJECTIVE_LABELS,
    SUPERVISED_OBJECTIVES,
    SUPPORTED_DATASET_EXTENSIONS,
    algorithms_for_objective,
    build_analysis_report,
    default_algorithm_for_objective,
    load_tabular_data,
    normalize_algorithm_parameters,
    profile_dataset,
    read_analysis_artifact,
    recommended_feature_columns,
    run_analysis,
    save_analysis_artifacts,
    serializable_analysis_result,
)
from services.library_service import (
    delete_library_file,
    read_library_file,
    save_library_upload,
)
from utils.auth import authenticated_callback, require_auth
from utils.ui import (
    header_icons,
    load_css,
    render_html,
    safe_html,
    sidebar_nav,
    top_brand,
)


st.set_page_config(
    page_title="Data Analysis · Research Journal AI",
    page_icon="📊",
    layout="wide",
)

require_auth()
init_db_once(st.session_state)
load_css()


BLUE = "#1769d2"
CYAN = "#1492bc"
MINT = "#79d7ae"
RED = "#e05b65"
GRID = "#e8eef6"
TEXT = "#344054"


def render_page_css():
    render_html(
        """
        <style>
        .analysis-page-scope,
        .analysis-top-context-scope,
        .analysis-results-scope {
            display: none;
        }

        div[data-testid="column"]:has(.analysis-page-scope) {
            min-height: calc(100vh - var(--topbar-h));
            padding: 20px 26px 42px !important;
            background: #ffffff;
        }

        div[data-testid="column"]:has(.analysis-page-scope)
        > div[data-testid="stVerticalBlock"] {
            gap: 0.68rem;
        }

        .analysis-top-context {
            min-height: var(--topbar-h);
            display: flex;
            align-items: center;
            gap: 10px;
            color: #344054;
            font-size: 0.86rem;
            font-weight: 780;
        }

        .analysis-top-context-icon {
            width: 32px;
            height: 32px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border: 1px solid #d8e5f4;
            border-radius: 8px;
            background: #f3f8ff;
            color: #1769d2;
            font-size: 1rem;
        }

        .analysis-heading {
            color: #101828;
            font-size: 1.85rem;
            font-weight: 880;
            line-height: 1.08;
            padding-top: 3px;
        }

        .analysis-subtitle {
            color: #667085;
            font-size: 0.88rem;
            margin-top: 7px;
        }

        .analysis-step-heading {
            display: flex;
            align-items: center;
            gap: 9px;
            color: #101828;
            font-size: 0.94rem;
            font-weight: 850;
            margin-bottom: 2px;
        }

        .analysis-step-number {
            width: 23px;
            height: 23px;
            border-radius: 999px;
            background: #1769d2;
            color: #ffffff;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 0.72rem;
            font-weight: 900;
            flex: 0 0 auto;
        }

        .analysis-step-caption {
            color: #667085;
            font-size: 0.73rem;
            line-height: 1.4;
            margin: 3px 0 8px 32px;
        }

        div[class*="st-key-analysis_source_card"],
        div[class*="st-key-analysis_preview_card"],
        div[class*="st-key-analysis_setup_card"],
        div[class*="st-key-analysis_results_card"],
        div[class*="st-key-analysis_history_card"] {
            border: 1px solid #dfe6ef !important;
            border-radius: 9px !important;
            background: #ffffff !important;
            box-shadow: 0 7px 20px rgba(16, 24, 40, 0.035) !important;
        }

        div[class*="st-key-analysis_source_card"] {
            padding: 14px 15px 12px !important;
        }

        div[class*="st-key-analysis_preview_card"],
        div[class*="st-key-analysis_setup_card"] {
            min-height: 470px;
            padding: 15px !important;
        }

        div[class*="st-key-analysis_results_card"] {
            padding: 15px !important;
            margin-top: 2px;
        }

        div[class*="st-key-analysis_history_card"] {
            padding: 15px !important;
            margin-bottom: 10px;
        }

        div[class*="st-key-analysis_source_card"] > div[data-testid="stVerticalBlock"],
        div[class*="st-key-analysis_preview_card"] > div[data-testid="stVerticalBlock"],
        div[class*="st-key-analysis_setup_card"] > div[data-testid="stVerticalBlock"],
        div[class*="st-key-analysis_results_card"] > div[data-testid="stVerticalBlock"] {
            gap: 0.58rem;
        }

        .analysis-source-ready {
            min-height: 61px;
            border: 1px solid #dce5ef;
            border-radius: 8px;
            padding: 9px 12px;
            display: flex;
            align-items: center;
            gap: 11px;
            background: #ffffff;
        }

        .analysis-source-icon {
            width: 36px;
            height: 36px;
            border-radius: 8px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: #eaf8ef;
            color: #159447;
            font-size: 1.1rem;
            font-weight: 900;
        }

        .analysis-source-name {
            color: #101828;
            font-size: 0.82rem;
            font-weight: 840;
            line-height: 1.3;
        }

        .analysis-source-meta {
            color: #667085;
            font-size: 0.69rem;
            margin-top: 3px;
        }

        .analysis-ready-chip,
        .analysis-status-chip {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            border-radius: 7px;
            padding: 5px 9px;
            color: #157f3b;
            background: #eaf8ef;
            border: 1px solid #c8ead5;
            font-size: 0.69rem;
            font-weight: 820;
            white-space: nowrap;
        }

        .analysis-status-chip.failed {
            color: #b42318;
            border-color: #f5c9c5;
            background: #fff0ef;
        }

        .analysis-summary-card {
            min-height: 70px;
            border: 1px solid #dfe6ef;
            border-radius: 8px;
            padding: 10px 11px;
            background: #ffffff;
        }

        .analysis-summary-value {
            color: #101828;
            font-size: 1.15rem;
            font-weight: 880;
            line-height: 1;
        }

        .analysis-summary-label {
            color: #667085;
            font-size: 0.68rem;
            margin-top: 5px;
        }

        .analysis-kind-badge {
            display: inline-flex;
            border-radius: 999px;
            padding: 2px 6px;
            color: #1769d2;
            background: #eaf3ff;
            font-size: 0.61rem;
            font-weight: 800;
            margin-right: 4px;
        }

        .analysis-card-note {
            color: #667085;
            font-size: 0.72rem;
            line-height: 1.42;
        }

        .analysis-results-header {
            display: flex;
            align-items: center;
            gap: 10px;
            color: #101828;
            font-size: 1rem;
            font-weight: 880;
            margin-bottom: 1px;
        }

        .analysis-metric-card {
            min-height: 76px;
            border: 1px solid #dfe6ef;
            border-radius: 8px;
            background: #ffffff;
            padding: 10px 12px;
            text-align: center;
        }

        .analysis-metric-label {
            color: #667085;
            font-size: 0.67rem;
            font-weight: 730;
        }

        .analysis-metric-value {
            color: #1769d2;
            font-size: 1.5rem;
            font-weight: 850;
            line-height: 1.1;
            margin-top: 6px;
        }

        .analysis-chart-title {
            color: #101828;
            font-size: 0.76rem;
            font-weight: 850;
            margin: 2px 0 3px;
        }

        .analysis-history-title {
            color: #101828;
            font-size: 0.84rem;
            font-weight: 840;
        }

        .analysis-history-meta {
            color: #667085;
            font-size: 0.69rem;
            margin-top: 4px;
        }

        .analysis-empty {
            min-height: 240px;
            border: 1px dashed #cfd9e6;
            border-radius: 9px;
            background: #fbfdff;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            color: #667085;
            padding: 24px;
        }

        .analysis-empty-icon {
            width: 50px;
            height: 50px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #eaf3ff;
            color: #1769d2;
            font-size: 1.3rem;
            margin-bottom: 10px;
        }

        div[class*="st-key-analysis_source_mode"] [data-baseweb="button-group"] {
            width: 100%;
        }

        div[class*="st-key-analysis_source_mode"] button {
            flex: 1 1 0;
            min-height: 41px !important;
        }

        div[class*="st-key-analysis_run_button"] button {
            min-height: 45px !important;
            font-weight: 850 !important;
            background: linear-gradient(90deg, #1769d2 0%, #0876e1 100%) !important;
            border-color: #1769d2 !important;
        }

        div[class*="st-key-analysis_results_card"] div[data-testid="stTabs"] button {
            min-height: 38px !important;
            font-size: 0.76rem !important;
            font-weight: 780 !important;
        }

        div[class*="st-key-analysis_preview_table"] [data-testid="stDataFrame"] {
            border-radius: 7px;
            overflow: hidden;
        }

        @media (max-width: 1100px) {
            div[data-testid="column"]:has(.analysis-page-scope) {
                padding-left: 18px !important;
                padding-right: 18px !important;
            }
        }
        </style>
        """
    )


def step_heading(number: int, title: str, caption: str = ""):
    render_html(
        f"""
        <div class="analysis-step-heading">
            <span class="analysis-step-number">{number}</span>
            <span>{safe_html(title)}</span>
        </div>
        {f'<div class="analysis-step-caption">{safe_html(caption)}</div>' if caption else ''}
        """
    )


def format_file_size(value: int | None) -> str:
    size = int(value or 0)

    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def compact_datetime(value: str | None) -> str:
    if not value:
        return "Unknown date"

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime("%b %-d, %Y · %H:%M")
    except ValueError:
        return str(value)


@st.cache_data(show_spinner=False, max_entries=24)
def cached_dataset(filename: str, content: bytes) -> pd.DataFrame:
    return load_tabular_data(filename, content)


def library_datasets():
    rows = get_library_items(item_type="dataset", sort="newest", limit=200)
    return [
        row
        for row in rows
        if row["file_path"]
        and Path(row["original_filename"] or row["file_path"]).suffix.lower()
        in SUPPORTED_DATASET_EXTENSIONS
    ]


def dataset_source(datasets) -> dict | None:
    with st.container(border=True, key="analysis_source_card"):
        step_heading(
            1,
            "Data source",
            "Upload a tabular file or reuse a dataset from My Library.",
        )
        mode_options = ["Upload file", "My Library"]
        default_mode = "My Library" if datasets else "Upload file"
        source_mode = st.segmented_control(
            "Data source",
            mode_options,
            default=default_mode,
            key="analysis_source_mode",
            label_visibility="collapsed",
            width="stretch",
        )
        source_mode = source_mode or default_mode
        filename = ""
        content = b""
        item = None
        upload = None
        save_to_library = True

        if source_mode == "My Library":
            if not datasets:
                st.info("No supported datasets are available in My Library yet. Upload CSV, TSV, XLSX, or JSON here or from Library.")
                return None

            dataset_ids = [int(row["id"]) for row in datasets]
            by_id = {int(row["id"]): row for row in datasets}
            selected_id = st.selectbox(
                "Dataset from My Library",
                dataset_ids,
                format_func=lambda value: by_id[value]["title"],
                key="analysis_library_dataset",
            )
            item = by_id[selected_id]
            filename = item["original_filename"] or f"{item['title']}{Path(item['file_path']).suffix}"

            try:
                content = read_library_file(item["file_path"])
            except (FileNotFoundError, OSError, ValueError) as exc:
                st.error(str(exc))
                return None
        else:
            upload = st.file_uploader(
                "Choose CSV, TSV, XLSX, or JSON",
                type=[suffix.lstrip(".") for suffix in SUPPORTED_DATASET_EXTENSIONS],
                key="analysis_upload",
            )
            save_to_library = st.checkbox(
                "Save this dataset to My Library",
                value=True,
                key="analysis_save_upload_to_library",
            )

            if upload is None:
                st.caption("Supported formats: CSV, TSV, XLSX and tabular JSON · maximum 25 MB")
                return None

            filename = Path(str(upload.name)).name
            content = upload.getvalue()

        signature = hashlib.sha256(content).hexdigest()[:20]

        try:
            dataframe = cached_dataset(filename, content)
        except (ValueError, RuntimeError) as exc:
            st.error(str(exc))
            return None

        ready_col, status_col = st.columns([3.6, 0.9], gap="small", vertical_alignment="center")

        with ready_col:
            render_html(
                f"""
                <div class="analysis-source-ready">
                    <span class="analysis-source-icon">▦</span>
                    <span>
                        <div class="analysis-source-name">{safe_html(filename)}</div>
                        <div class="analysis-source-meta">
                            {len(dataframe):,} rows&nbsp; · &nbsp;{len(dataframe.columns)} columns&nbsp; · &nbsp;
                            {safe_html(Path(filename).suffix.lstrip('.').upper())}&nbsp; · &nbsp;{safe_html(format_file_size(len(content)))}
                        </div>
                    </span>
                </div>
                """
            )

        with status_col:
            render_html('<span class="analysis-ready-chip">✓ Dataset ready</span>')

        return {
            "mode": source_mode,
            "source_kind": "library" if item else "upload",
            "filename": filename,
            "content": content,
            "dataframe": dataframe,
            "signature": signature,
            "library_item": item,
            "upload": upload,
            "save_to_library": save_to_library,
        }


def summary_card(value: str, label: str):
    render_html(
        f"""
        <div class="analysis-summary-card">
            <div class="analysis-summary-value">{safe_html(value)}</div>
            <div class="analysis-summary-label">{safe_html(label)}</div>
        </div>
        """
    )


def render_dataset_preview(dataframe: pd.DataFrame, profile: dict):
    with st.container(border=True, key="analysis_preview_card"):
        step_heading(2, "Dataset preview", "Inspect the inferred structure before running a model.")
        row_col, column_col, missing_col = st.columns(3, gap="small")

        with row_col:
            summary_card(f"{profile['rows']:,}", "Rows")
        with column_col:
            summary_card(f"{profile['columns_count']:,}", "Columns")
        with missing_col:
            summary_card(f"{profile['missing_percent']:.1f}%", "Missing")

        preview = dataframe.head(8).copy()

        for column in preview.columns:
            if preview[column].dtype == "object":
                preview[column] = preview[column].astype("string").str.slice(0, 42)

        st.dataframe(
            preview,
            hide_index=True,
            height=252,
            width="stretch",
            key="analysis_preview_table",
        )

        with st.expander("View all columns and inferred types"):
            column_table = pd.DataFrame(profile["columns"])[
                ["name", "kind", "dtype", "unique", "missing_percent"]
            ].rename(columns={
                "name": "Column",
                "kind": "Role",
                "dtype": "Data type",
                "unique": "Unique",
                "missing_percent": "Missing %",
            })
            st.dataframe(column_table, hide_index=True, width="stretch", height=240)

        if profile["duplicate_rows"]:
            st.caption(f"{profile['duplicate_rows']:,} duplicate rows detected.")


def render_parameter_controls(algorithm_key: str, signature: str) -> dict:
    parameters = {}
    specs = ALGORITHM_CATALOG[algorithm_key]["parameters"]

    with st.expander("Advanced parameters"):
        for name, spec in specs.items():
            key = f"analysis_param_{signature}_{algorithm_key}_{name}"

            if spec["type"] == "choice":
                parameters[name] = st.selectbox(
                    spec["label"],
                    spec["choices"],
                    index=spec["choices"].index(spec["default"]),
                    key=key,
                )
            elif spec["type"] == "int":
                parameters[name] = st.number_input(
                    spec["label"],
                    min_value=int(spec["min"]),
                    max_value=int(spec["max"]),
                    value=int(spec["default"]),
                    step=1,
                    key=key,
                )
            else:
                step = 0.01 if float(spec["max"]) <= 20 else 0.1
                parameters[name] = st.number_input(
                    spec["label"],
                    min_value=float(spec["min"]),
                    max_value=float(spec["max"]),
                    value=float(spec["default"]),
                    step=step,
                    format="%.3f",
                    key=key,
                )

    return normalize_algorithm_parameters(algorithm_key, parameters)


def target_default(dataframe: pd.DataFrame, objective: str) -> str:
    columns = list(dataframe.columns)

    if objective == "regression":
        numeric = [column for column in columns if pd.api.types.is_numeric_dtype(dataframe[column])]
        return numeric[-1] if numeric else columns[-1]

    categorical = [
        column
        for column in columns
        if not pd.api.types.is_numeric_dtype(dataframe[column])
        and 2 <= dataframe[column].nunique(dropna=True) <= 20
    ]
    return categorical[-1] if categorical else columns[-1]


def render_analysis_setup(dataframe: pd.DataFrame, signature: str) -> dict:
    with st.container(border=True, key="analysis_setup_card"):
        step_heading(3, "Analysis setup", "Choose an objective, columns, and a validated scikit-learn tool.")
        objective = st.selectbox(
            "Objective",
            list(OBJECTIVE_LABELS),
            format_func=OBJECTIVE_LABELS.get,
            key=f"analysis_objective_{signature}",
        )
        target_column = None

        if objective in SUPERVISED_OBJECTIVES:
            default_target = target_default(dataframe, objective)
            target_column = st.selectbox(
                "Target column",
                list(dataframe.columns),
                index=list(dataframe.columns).index(default_target),
                key=f"analysis_target_{signature}_{objective}",
            )

        recommended = recommended_feature_columns(dataframe, target_column)
        feature_columns = st.multiselect(
            "Features",
            list(dataframe.columns),
            default=recommended,
            key=f"analysis_features_{signature}_{objective}_{target_column or 'none'}",
            help="High-cardinality ID and free-text columns are excluded from the default selection.",
        )
        algorithms = algorithms_for_objective(objective)
        algorithm_keys = [key for key, _ in algorithms]
        default_algorithm = default_algorithm_for_objective(objective)
        algorithm_key = st.selectbox(
            "Algorithm",
            algorithm_keys,
            index=algorithm_keys.index(default_algorithm),
            format_func=lambda value: ALGORITHM_CATALOG[value]["label"],
            key=f"analysis_algorithm_{signature}_{objective}",
        )
        st.caption(ALGORITHM_CATALOG[algorithm_key]["description"])
        render_html('<div class="analysis-card-note"><strong>Automatic preprocessing</strong></div>')
        pre_col_one, pre_col_two = st.columns(2, gap="small")

        with pre_col_one:
            impute_missing = st.checkbox(
                "Impute missing values",
                value=True,
                key=f"analysis_impute_{signature}",
            )
            encode_categories = st.checkbox(
                "Encode categories",
                value=True,
                key=f"analysis_encode_{signature}",
            )

        with pre_col_two:
            scale_numeric = st.checkbox(
                "Scale numeric features",
                value=True,
                key=f"analysis_scale_{signature}",
            )
            st.checkbox(
                "Deterministic seed · 42",
                value=True,
                disabled=True,
                key=f"analysis_seed_{signature}",
            )

        test_size = 0.2

        if objective in SUPERVISED_OBJECTIVES:
            split_label = st.selectbox(
                "Train / test split",
                ["90% / 10%", "80% / 20%", "70% / 30%", "60% / 40%"],
                index=1,
                key=f"analysis_split_{signature}_{objective}",
            )
            test_size = {
                "90% / 10%": 0.1,
                "80% / 20%": 0.2,
                "70% / 30%": 0.3,
                "60% / 40%": 0.4,
            }[split_label]

        parameters = render_parameter_controls(algorithm_key, signature)
        run_clicked = st.button(
            "✦  ▶  Run analysis",
            type="primary",
            width="stretch",
            key="analysis_run_button",
        )
        return {
            "objective": objective,
            "target_column": target_column,
            "feature_columns": feature_columns,
            "algorithm_key": algorithm_key,
            "parameters": parameters,
            "preprocessing": {
                "impute_missing": impute_missing,
                "scale_numeric": scale_numeric,
                "encode_categories": encode_categories,
                "random_state": 42,
            },
            "test_size": test_size,
            "run_clicked": run_clicked,
        }


def save_upload_to_library_once(source: dict) -> int | None:
    if source["library_item"]:
        return int(source["library_item"]["id"])

    if not source["save_to_library"]:
        return None

    mapping = dict(st.session_state.get("analysis_upload_library_ids", {}))
    existing_id = mapping.get(source["signature"])

    if existing_id:
        if get_library_item(int(existing_id)):
            return int(existing_id)

        mapping.pop(source["signature"], None)

    saved_file = None

    try:
        saved_file = save_library_upload(source["upload"])
        item_id = create_library_item(
            **saved_file,
            status="To read",
            tags=["data analysis"],
        )
    except Exception:
        if saved_file:
            delete_library_file(saved_file["file_path"])
        raise

    mapping[source["signature"]] = int(item_id)
    st.session_state["analysis_upload_library_ids"] = mapping
    return int(item_id)


def execute_analysis(source: dict, setup: dict, profile: dict):
    library_item_id = save_upload_to_library_once(source)
    algorithm = ALGORITHM_CATALOG[setup["algorithm_key"]]
    run_id = create_analysis_run(
        library_item_id=library_item_id,
        source_kind=source["source_kind"],
        source_name=source["filename"],
        objective=setup["objective"],
        algorithm_key=setup["algorithm_key"],
        algorithm_label=algorithm["label"],
        target_column=setup["target_column"],
        feature_columns=setup["feature_columns"],
        parameters=setup["parameters"],
        preprocessing=setup["preprocessing"],
        row_count=profile["rows"],
        column_count=profile["columns_count"],
    )

    try:
        outcome = run_analysis(
            source["dataframe"],
            objective=setup["objective"],
            algorithm_key=setup["algorithm_key"],
            feature_columns=setup["feature_columns"],
            target_column=setup["target_column"],
            parameters=setup["parameters"],
            preprocessing=setup["preprocessing"],
            test_size=setup["test_size"],
        )
        report = build_analysis_report(
            run_id=run_id,
            source_name=source["filename"],
            outcome=outcome,
            row_count=profile["rows"],
            column_count=profile["columns_count"],
        )
        paths = save_analysis_artifacts(
            run_id,
            predictions=outcome["predictions"],
            report_markdown=report,
        )
        complete_analysis_run(
            run_id,
            metrics=outcome["metrics"],
            results=serializable_analysis_result(outcome),
            **paths,
        )
    except Exception as exc:
        fail_analysis_run(run_id, str(exc))
        raise

    st.session_state["analysis_active_run_id"] = run_id
    st.session_state["analysis_active_signature"] = source["signature"]
    return run_id


def render_bar_chart(rows: list[dict], *, title: str, label_field: str, value_field: str, color=BLUE):
    data = pd.DataFrame(rows)

    if data.empty:
        st.info("No chart data available.")
        return

    chart = (
        alt.Chart(data)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3, color=color)
        .encode(
            x=alt.X(f"{label_field}:N", title=None, sort=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y(f"{value_field}:Q", title=None),
            tooltip=[alt.Tooltip(f"{label_field}:N"), alt.Tooltip(f"{value_field}:Q")],
        )
        .properties(title=title, height=205)
        .configure_title(color=TEXT, fontSize=12, fontWeight=700, anchor="start")
        .configure_axis(labelColor="#667085", titleColor="#667085", gridColor=GRID, domainColor="#dfe6ef", labelFontSize=9)
        .configure_view(stroke="#dfe6ef", cornerRadius=6)
    )
    st.altair_chart(chart, width="stretch")


def render_roc_curve(chart_data: dict):
    points = pd.DataFrame({"FPR": chart_data.get("fpr", []), "TPR": chart_data.get("tpr", [])})
    diagonal = pd.DataFrame({"FPR": [0, 1], "TPR": [0, 1]})
    line = alt.Chart(points).mark_line(color=BLUE, strokeWidth=2.5).encode(
        x=alt.X("FPR:Q", title="False positive rate", scale=alt.Scale(domain=[0, 1])),
        y=alt.Y("TPR:Q", title="True positive rate", scale=alt.Scale(domain=[0, 1])),
        tooltip=[alt.Tooltip("FPR:Q", format=".3f"), alt.Tooltip("TPR:Q", format=".3f")],
    )
    baseline = alt.Chart(diagonal).mark_line(color="#98a2b3", strokeDash=[5, 4]).encode(x="FPR:Q", y="TPR:Q")
    chart = (line + baseline).properties(
        title=f"ROC curve · AUC {chart_data.get('auc', 0):.2f}",
        height=205,
    ).configure_title(color=TEXT, fontSize=12, fontWeight=700, anchor="start").configure_axis(
        labelColor="#667085", titleColor="#667085", gridColor=GRID, domainColor="#dfe6ef", labelFontSize=9, titleFontSize=9
    ).configure_view(stroke="#dfe6ef", cornerRadius=6)
    st.altair_chart(chart, width="stretch")


def render_confusion_matrix(chart_data: dict):
    labels = chart_data.get("labels", [])
    matrix = chart_data.get("matrix", [])
    rows = []

    for actual_index, actual in enumerate(labels):
        for predicted_index, predicted in enumerate(labels):
            rows.append({
                "Actual": str(actual),
                "Predicted": str(predicted),
                "Count": int(matrix[actual_index][predicted_index]),
            })

    data = pd.DataFrame(rows)

    if data.empty:
        st.info("No confusion matrix available.")
        return

    heatmap = alt.Chart(data).mark_rect(cornerRadius=2).encode(
        x=alt.X("Predicted:N", title="Predicted", sort=labels),
        y=alt.Y("Actual:N", title="Actual", sort=labels),
        color=alt.Color("Count:Q", scale=alt.Scale(range=["#eef5ff", BLUE]), legend=None),
        tooltip=["Actual:N", "Predicted:N", "Count:Q"],
    )
    text = alt.Chart(data).mark_text(fontSize=11, fontWeight=700).encode(
        x=alt.X("Predicted:N", sort=labels),
        y=alt.Y("Actual:N", sort=labels),
        text="Count:Q",
        color=alt.condition("datum.Count > 0", alt.value("#101828"), alt.value("#667085")),
    )
    chart = (heatmap + text).properties(title="Confusion matrix", height=205).configure_title(
        color=TEXT, fontSize=12, fontWeight=700, anchor="start"
    ).configure_axis(
        labelColor="#667085", titleColor="#667085", domain=False, ticks=False, labelFontSize=9, titleFontSize=9
    ).configure_view(stroke="#dfe6ef", cornerRadius=6)
    st.altair_chart(chart, width="stretch")


def render_feature_importance(rows: list[dict]):
    data = pd.DataFrame(rows).head(8)

    if data.empty:
        st.info("Feature importance is unavailable for this result.")
        return

    chart = alt.Chart(data).mark_bar(color=BLUE, cornerRadiusEnd=3).encode(
        y=alt.Y("feature:N", title=None, sort="-x"),
        x=alt.X("importance:Q", title="Importance"),
        tooltip=["feature:N", alt.Tooltip("importance:Q", format=".3f")],
    ).properties(title="Feature importance", height=205).configure_title(
        color=TEXT, fontSize=12, fontWeight=700, anchor="start"
    ).configure_axis(
        labelColor="#667085", titleColor="#667085", gridColor=GRID, domainColor="#dfe6ef", labelFontSize=9, titleFontSize=9
    ).configure_view(stroke="#dfe6ef", cornerRadius=6)
    st.altair_chart(chart, width="stretch")


def render_histogram(chart_data: dict, title: str):
    counts = chart_data.get("counts", [])
    edges = chart_data.get("edges", [])
    rows = [
        {"bin": (edges[index] + edges[index + 1]) / 2, "count": count}
        for index, count in enumerate(counts)
        if index + 1 < len(edges)
    ]
    render_bar_chart(rows, title=title, label_field="bin", value_field="count", color=CYAN)


def render_scatter(chart_data: dict, *, title: str, label_field: str | None = None):
    rows = {
        "X": chart_data.get("x", []),
        "Y": chart_data.get("y", []),
    }

    if label_field:
        rows[label_field] = chart_data.get("labels", [])

    data = pd.DataFrame(rows)
    encoding = {
        "x": alt.X("X:Q", title="Component 1"),
        "y": alt.Y("Y:Q", title="Component 2"),
        "tooltip": [alt.Tooltip("X:Q", format=".3f"), alt.Tooltip("Y:Q", format=".3f")],
    }

    if label_field:
        encoding["color"] = alt.Color(f"{label_field}:N", scale=alt.Scale(scheme="tableau10"), legend=alt.Legend(title=label_field))

    chart = alt.Chart(data).mark_circle(size=45, opacity=0.72, color=BLUE).encode(**encoding).properties(
        title=title, height=205
    ).configure_title(color=TEXT, fontSize=12, fontWeight=700, anchor="start").configure_axis(
        labelColor="#667085", titleColor="#667085", gridColor=GRID, domainColor="#dfe6ef", labelFontSize=9, titleFontSize=9
    ).configure_view(stroke="#dfe6ef", cornerRadius=6)
    st.altair_chart(chart, width="stretch")


def metric_configuration(objective: str) -> list[tuple[str, str, str]]:
    return {
        "classification": [
            ("accuracy", "Accuracy", "score"),
            ("f1", "F1 score", "score"),
            ("roc_auc", "ROC AUC", "score"),
            ("precision", "Precision", "score"),
        ],
        "regression": [
            ("r2", "R²", "score"),
            ("mae", "MAE", "number"),
            ("rmse", "RMSE", "number"),
        ],
        "clustering": [
            ("clusters", "Clusters", "integer"),
            ("silhouette", "Silhouette", "score"),
            ("noise_ratio", "Noise", "percent"),
        ],
        "dimensionality_reduction": [
            ("components", "Components", "integer"),
            ("explained_variance", "Explained variance", "percent"),
        ],
        "anomaly_detection": [
            ("anomalies", "Anomalies", "integer"),
            ("anomaly_ratio", "Anomaly rate", "percent"),
        ],
    }[objective]


def format_metric(value, style: str) -> str:
    if value is None:
        return "—"
    if style == "integer":
        return f"{int(value):,}"
    if style == "percent":
        return f"{100 * float(value):.1f}%"
    if style == "number":
        return f"{float(value):.3f}"
    return f"{float(value):.2f}"


def render_performance_charts(run: dict):
    objective = run["objective"]
    charts = run["results"].get("charts", {})

    if objective == "classification":
        chart_columns = st.columns(4, gap="small")
        with chart_columns[0]:
            render_bar_chart(charts.get("class_distribution", []), title="Class distribution", label_field="label", value_field="count")
        with chart_columns[1]:
            if charts.get("roc_curve"):
                render_roc_curve(charts["roc_curve"])
            else:
                st.info("ROC curve is available for binary probabilistic classifiers.")
        with chart_columns[2]:
            render_confusion_matrix(charts.get("confusion_matrix", {}))
        with chart_columns[3]:
            render_feature_importance(charts.get("feature_importance", []))
    elif objective == "regression":
        chart_columns = st.columns(3, gap="small")
        actual = charts.get("actual_vs_predicted", {})

        with chart_columns[0]:
            scatter = pd.DataFrame({"Actual": actual.get("actual", []), "Predicted": actual.get("predicted", [])})
            chart = alt.Chart(scatter).mark_circle(size=50, opacity=0.68, color=BLUE).encode(
                x=alt.X("Actual:Q", title="Actual"),
                y=alt.Y("Predicted:Q", title="Predicted"),
                tooltip=[alt.Tooltip("Actual:Q", format=".3f"), alt.Tooltip("Predicted:Q", format=".3f")],
            ).properties(title="Actual vs predicted", height=205).configure_title(
                color=TEXT, fontSize=12, fontWeight=700, anchor="start"
            ).configure_axis(labelColor="#667085", titleColor="#667085", gridColor=GRID, labelFontSize=9).configure_view(stroke="#dfe6ef", cornerRadius=6)
            st.altair_chart(chart, width="stretch")
        with chart_columns[1]:
            render_histogram(charts.get("residual_distribution", {}), "Residual distribution")
        with chart_columns[2]:
            render_feature_importance(charts.get("feature_importance", []))
    elif objective == "clustering":
        chart_columns = st.columns(2, gap="small")
        with chart_columns[0]:
            render_bar_chart(charts.get("cluster_distribution", []), title="Cluster distribution", label_field="label", value_field="count")
        with chart_columns[1]:
            render_scatter(charts.get("cluster_scatter", {}), title="Cluster projection", label_field="Cluster")
    elif objective == "dimensionality_reduction":
        chart_columns = st.columns(2, gap="small")
        with chart_columns[0]:
            render_bar_chart(charts.get("explained_variance", []), title="Explained variance", label_field="label", value_field="value")
        with chart_columns[1]:
            render_scatter(charts.get("pca_scatter", {}), title="PCA projection")
    else:
        chart_columns = st.columns(3, gap="small")
        with chart_columns[0]:
            render_bar_chart(charts.get("anomaly_distribution", []), title="Anomaly distribution", label_field="label", value_field="count", color=RED)
        with chart_columns[1]:
            render_histogram(charts.get("score_distribution", {}), "Anomaly scores")
        with chart_columns[2]:
            render_scatter(charts.get("anomaly_scatter", {}), title="Anomaly projection", label_field="Prediction")


def render_data_distributions(dataframe: pd.DataFrame | None, run: dict):
    if dataframe is None:
        st.info("Open the source dataset in New analysis to inspect its live distributions.")
        return

    feature_columns = [column for column in run["feature_columns"] if column in dataframe.columns]
    numeric = [column for column in feature_columns if pd.api.types.is_numeric_dtype(dataframe[column])][:4]

    if not numeric:
        st.info("No numeric features are available for distribution charts.")
        return

    columns = st.columns(len(numeric), gap="small")

    for container, column in zip(columns, numeric):
        with container:
            data = pd.DataFrame({column: pd.to_numeric(dataframe[column], errors="coerce")}).dropna()
            chart = alt.Chart(data).mark_bar(color=CYAN).encode(
                x=alt.X(f"{column}:Q", bin=alt.Bin(maxbins=18), title=column),
                y=alt.Y("count():Q", title="Rows"),
                tooltip=[alt.Tooltip("count():Q", title="Rows")],
            ).properties(title=f"{column} distribution", height=205).configure_title(
                color=TEXT, fontSize=12, fontWeight=700, anchor="start"
            ).configure_axis(labelColor="#667085", titleColor="#667085", gridColor=GRID, labelFontSize=9).configure_view(stroke="#dfe6ef", cornerRadius=6)
            st.altair_chart(chart, width="stretch")


@st.fragment
@authenticated_callback
def render_exports(run: dict):
    if not st.button(
        "Prepare exports",
        icon=":material/download:",
        key=f"analysis_prepare_exports_{run['id']}",
    ):
        return

    try:
        predictions = read_analysis_artifact(run["predictions_file_path"])
        report = read_analysis_artifact(run["report_file_path"])
    except (FileNotFoundError, OSError, ValueError) as exc:
        st.warning(str(exc))
        return

    prediction_col, report_col = st.columns(2, gap="small")

    with prediction_col:
        st.download_button(
            "Download predictions",
            data=predictions,
            file_name=f"analysis-run-{run['id']}-predictions.csv",
            mime="text/csv",
            width="stretch",
            on_click="ignore",
            key=f"analysis_download_predictions_{run['id']}",
        )

    with report_col:
        st.download_button(
            "Download full report",
            data=report,
            file_name=f"analysis-run-{run['id']}-report.md",
            mime="text/markdown",
            width="stretch",
            on_click="ignore",
            key=f"analysis_download_report_{run['id']}",
        )


def render_results_dashboard(run: dict | None, dataframe: pd.DataFrame | None = None):
    with st.container(border=True, key="analysis_results_card"):
        render_html('<div class="analysis-results-scope"></div>')

        if run and run.get("status") == "failed":
            st.error(run.get("error_message") or "This analysis run failed.")
            return

        if not run or run.get("status") != "completed":
            render_html(
                """
                <div class="analysis-empty">
                    <div class="analysis-empty-icon">⌁</div>
                    <strong>No completed analysis yet</strong>
                    <span style="font-size:.74rem;margin-top:6px;">Configure a workflow and run it to generate metrics, charts, predictions, and a reproducible report.</span>
                </div>
                """
            )
            return

        render_html(
            f"""
            <div class="analysis-results-header">
                <span>Results dashboard</span>
                <span class="analysis-status-chip">✓ Completed</span>
            </div>
            <div class="analysis-card-note">
                Run #{run['id']} · {safe_html(run['algorithm_label'])} · {safe_html(run['source_name'])}
            </div>
            """
        )
        metric_specs = [
            spec
            for spec in metric_configuration(run["objective"])
            if spec[0] in run["metrics"]
        ]
        metric_columns = st.columns(max(1, len(metric_specs)), gap="small")

        for container, (key, label, style) in zip(metric_columns, metric_specs):
            with container:
                render_html(
                    f"""
                    <div class="analysis-metric-card">
                        <div class="analysis-metric-label">{safe_html(label)}</div>
                        <div class="analysis-metric-value">{safe_html(format_metric(run['metrics'].get(key), style))}</div>
                    </div>
                    """
                )

        for warning in run["results"].get("warnings", []):
            st.warning(warning)

        performance_tab, distribution_tab, predictions_tab = st.tabs(
            ["Model performance", "Data distributions", "Predictions"],
            key=f"analysis_result_tabs_{run['id']}",
        )

        with performance_tab:
            render_performance_charts(run)

        with distribution_tab:
            render_data_distributions(dataframe, run)

        with predictions_tab:
            preview = pd.DataFrame(run["results"].get("preview", []))

            if preview.empty:
                st.info("No prediction preview is available.")
            else:
                st.dataframe(preview, hide_index=True, width="stretch", height=270)

        render_exports(run)


def render_history():
    runs = get_analysis_runs(limit=50)

    if not runs:
        render_html(
            """
            <div class="analysis-empty">
                <div class="analysis-empty-icon">↻</div>
                <strong>No saved runs</strong>
                <span style="font-size:.74rem;margin-top:6px;">Completed and failed analyses will appear here.</span>
            </div>
            """
        )
        return

    selected_id = st.session_state.get("analysis_history_selected_id")

    for run in runs:
        with st.container(border=True, key=f"analysis_history_card_{run['id']}"):
            info_col, metrics_col, action_col = st.columns([2.2, 1.2, 0.55], gap="small", vertical_alignment="center")

            with info_col:
                status_class = "failed" if run["status"] == "failed" else ""
                render_html(
                    f"""
                    <div class="analysis-history-title">#{run['id']} · {safe_html(run['algorithm_label'])}</div>
                    <div class="analysis-history-meta">
                        {safe_html(run['source_name'])} · {safe_html(OBJECTIVE_LABELS.get(run['objective'], run['objective']))} · {safe_html(compact_datetime(run['created_at']))}
                    </div>
                    <span class="analysis-status-chip {status_class}">{safe_html(run['status'].title())}</span>
                    """
                )

            with metrics_col:
                values = [
                    f"{label}: {format_metric(run['metrics'].get(key), style)}"
                    for key, label, style in metric_configuration(run["objective"])
                    if key in run["metrics"]
                ][:3]
                st.caption(" · ".join(values) or run.get("error_message") or "No metrics")

            with action_col:
                if st.button("Open", key=f"open_analysis_run_{run['id']}", width="stretch"):
                    st.session_state["analysis_history_selected_id"] = run["id"]
                    st.rerun()

    if selected_id:
        selected = get_analysis_run(int(selected_id))
        st.divider()
        render_results_dashboard(selected)


render_page_css()
st.session_state.setdefault("analysis_upload_library_ids", {})
st.session_state.setdefault("analysis_tab_token", 0)
st.session_state.setdefault("analysis_preferred_tab", "New analysis")

top_brand_col, top_context_col, top_space_col, top_user_col = st.columns(
    [1.25, 2.8, 1.9, 1.65],
    gap="large",
)

with top_brand_col:
    top_brand()

with top_context_col:
    render_html(
        """
        <div class="analysis-top-context-scope"></div>
        <div class="analysis-top-context">
            <span class="analysis-top-context-icon">▥</span>
            <span>Reproducible analysis workspace</span>
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
    sidebar_nav("data_analysis")

with page_col:
    render_html('<div class="analysis-page-scope"></div>')
    heading_col, history_col = st.columns([2.8, 0.65], gap="large", vertical_alignment="center")

    with heading_col:
        render_html(
            """
            <div class="analysis-heading">Data Analysis</div>
            <div class="analysis-subtitle">Explore datasets and run reproducible machine learning workflows.</div>
            """
        )

    with history_col:
        history_requested = st.button(
            "Run history",
            icon=":material/history:",
            width="stretch",
            key="analysis_history_shortcut",
        )

    if history_requested:
        st.session_state["analysis_preferred_tab"] = "Saved runs"
        st.session_state["analysis_tab_token"] += 1

    tab_key = f"analysis_primary_tabs_{st.session_state['analysis_tab_token']}"
    new_tab, saved_tab = st.tabs(
        ["New analysis", "Saved runs"],
        default=st.session_state["analysis_preferred_tab"],
        key=tab_key,
        on_change="rerun",
    )

    if new_tab.open:
        with new_tab:
            datasets = library_datasets()
            source = dataset_source(datasets)

            if source is None:
                render_results_dashboard(None)
            else:
                dataframe = source["dataframe"]
                profile = profile_dataset(dataframe)
                preview_col, setup_col = st.columns([1.02, 1.08], gap="small")

                with preview_col:
                    render_dataset_preview(dataframe, profile)

                with setup_col:
                    setup = render_analysis_setup(dataframe, source["signature"])

                if setup["run_clicked"]:
                    try:
                        with st.spinner("Running the validated scikit-learn pipeline..."):
                            run_id = execute_analysis(source, setup, profile)
                        st.toast(f"Analysis run #{run_id} completed.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

                active_run = None

                if st.session_state.get("analysis_active_signature") == source["signature"]:
                    active_id = st.session_state.get("analysis_active_run_id")
                    active_run = get_analysis_run(int(active_id)) if active_id else None

                render_results_dashboard(active_run, dataframe)

    if saved_tab.open:
        with saved_tab:
            render_history()
