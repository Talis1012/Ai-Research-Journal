"""Seed realistic, isolated data used only for real UI screenshots."""

import json
import os

from db.data_analysis_queries import complete_analysis_run, create_analysis_run
from db.database import get_connection, init_db
from db.discovery_queries import replace_project_discovery_results
from db.library_queries import create_library_folder, create_library_item
from db.queries import (
    add_experiment_ai_message,
    add_message,
    create_chat,
    create_project,
    save_project_ideas,
    save_project_mindmap,
    save_summary,
)
from db.writing_queries import (
    create_manuscript,
    create_manuscript_version,
    get_manuscript_sections,
    update_manuscript_section,
)
from utils.user_scope import activate_user_scope


activate_user_scope(
    "https://presentation.local/",
    "auth0|internship-presentation",
    claims={"role": "authenticated", "name": "Vlad Ciripescu"},
)
init_db()

conn = get_connection()
if conn.execute("SELECT COUNT(*) AS total FROM projects").fetchone()["total"]:
    print("Presentation database already seeded:", os.environ["DATABASE_PATH"])
    conn.close()
    raise SystemExit(0)
conn.close()

# A secondary project makes the real selectors and cross-project views credible.
secondary_project = create_project(
    "Biodegradable Polymer Screening",
    "Materials Science",
    "Screening protocol for biodegradable packaging candidates.",
)
secondary_chat = create_chat(
    secondary_project,
    "Baseline tensile tests",
    "Compare tensile strength before and after accelerated ageing.",
)
add_message(
    secondary_chat,
    "user",
    "text",
    "The baseline films retained 91% of tensile strength after seven days.",
)

project_id = create_project(
    "CM-01 Catalyst Stability",
    "Materials Chemistry",
    "Evaluate the operational stability of catalyst CM-01 across pH and temperature conditions, while preserving evidence for a reproducible manuscript.",
)

experiment_specs = [
    (
        "Stability profile of CM-01",
        "Measure catalytic activity across pH 5.0–8.0 and identify the stable operating window.",
        [
            "Day 1: prepared six buffered conditions at pH 5.0, 5.8, 6.5, 7.2, 7.8 and 8.0. Temperature held at 25 °C.",
            "The pH 6.5–7.2 samples retained more than 92% relative activity after 48 hours; activity decreased sharply below pH 5.8.",
            "Replicate variance stayed below 4.1%. Repeat the pH 7.2 point at 35 °C before finalizing the conclusion.",
        ],
    ),
    (
        "Temperature stress validation",
        "Validate the optimum pH under 25 °C, 35 °C and 45 °C stress.",
        [
            "At 35 °C, the catalyst retained 88% activity after 24 hours.",
            "At 45 °C, aggregation became visible after six hours and activity fell to 61%.",
        ],
    ),
    (
        "Solvent compatibility screen",
        "Compare aqueous buffer with 5% ethanol and 2% DMSO.",
        [
            "Two percent DMSO showed no measurable effect on initial activity.",
            "Five percent ethanol reduced activity by 12% after 24 hours.",
        ],
    ),
]

chat_ids = []
for title, objective, messages in experiment_specs:
    chat_id = create_chat(project_id, title, objective)
    chat_ids.append(chat_id)
    for message in messages:
        add_message(chat_id, "user", "text", message)

primary_chat = chat_ids[0]
add_experiment_ai_message(
    primary_chat,
    "user",
    "Which observation provides the strongest evidence for the stability window?",
)
add_experiment_ai_message(
    primary_chat,
    "assistant",
    "The strongest evidence is the paired observation that pH 6.5–7.2 retained over 92% activity after 48 hours while replicate variance remained below 4.1%. This supports both effect size and repeatability.",
)

save_summary(
    "chat",
    "## Objective\nMap the operational pH window for catalyst CM-01.\n\n## Evidence\n- Activity remained above 92% between pH 6.5 and 7.2 after 48 hours.\n- Replicate variance was below 4.1%.\n\n## Open question\nConfirm the pH 7.2 result at 35 °C.",
    project_id=project_id,
    chat_id=primary_chat,
)
save_summary(
    "project",
    "## Current finding\nCM-01 is most stable in a near-neutral pH window. Temperature stress, rather than solvent compatibility, is the main remaining risk.\n\n## Evidence coverage\nThree experiments contribute seven traceable observations.\n\n## Next step\nValidate pH 7.2 at 35 °C with three replicates.",
    project_id=project_id,
)
save_project_ideas(
    project_id,
    [
        {
            "title": "Near-neutral stability window",
            "description": "pH 6.5–7.2 preserves catalytic activity for at least 48 hours.",
            "evidence": "Stability profile observations 2 and 3.",
            "importance": "high",
        },
        {
            "title": "Temperature is the dominant risk",
            "description": "Performance remains acceptable at 35 °C but declines at 45 °C.",
            "evidence": "Temperature stress validation.",
            "importance": "high",
        },
        {
            "title": "DMSO compatibility",
            "description": "Two percent DMSO is compatible with the tested protocol.",
            "evidence": "Solvent compatibility screen.",
            "importance": "medium",
        },
    ],
)
save_project_mindmap(
    project_id,
    {
        "nodes": [
            {"id": "cm01", "label": "CM-01 stability", "description": "Project focus", "importance": "high"},
            {"id": "ph", "label": "pH window", "description": "6.5–7.2", "importance": "high"},
            {"id": "temp", "label": "Temperature", "description": "35 °C acceptable; 45 °C risk", "importance": "high"},
            {"id": "solvent", "label": "Solvents", "description": "2% DMSO compatible", "importance": "medium"},
            {"id": "repeat", "label": "Validation", "description": "Repeat pH 7.2 at 35 °C", "importance": "medium"},
        ],
        "edges": [
            {"source": "cm01", "target": "ph", "relation": "depends on"},
            {"source": "cm01", "target": "temp", "relation": "limited by"},
            {"source": "cm01", "target": "solvent", "relation": "tested with"},
            {"source": "ph", "target": "repeat", "relation": "requires"},
            {"source": "temp", "target": "repeat", "relation": "requires"},
        ],
    },
)

folder_catalyst = create_library_folder("CM-01 Stability")
folder_methods = create_library_folder("Methods & Validation")
library_rows = [
    {
        "title": "pH-Dependent Stability of Heterogeneous Catalyst Systems",
        "authors": "L. Yu; T. Brenner; S. Khan",
        "publication_year": 2024,
        "source_name": "Catalysis Science & Technology",
        "doi": "10.1039/d4cy00421a",
        "abstract": "A systematic study of catalyst deactivation across buffered pH conditions.",
        "status": "Reviewed",
        "tags": ["stability", "pH", "catalysis"],
        "folder_id": folder_catalyst,
    },
    {
        "title": "Thermal Deactivation Pathways in Porous Catalysts",
        "authors": "M. Ionescu; R. Patel",
        "publication_year": 2023,
        "source_name": "Applied Catalysis A",
        "doi": "10.1016/j.apcata.2023.119210",
        "abstract": "Mechanistic analysis of thermal aggregation and activity loss.",
        "status": "Reading",
        "tags": ["temperature", "mechanism"],
        "folder_id": folder_catalyst,
    },
    {
        "title": "Reproducible Screening Protocols for Catalyst Stability",
        "authors": "E. Popescu; J. Miller; A. Chen",
        "publication_year": 2025,
        "source_name": "Nature Protocols",
        "doi": "10.1038/s41596-025-01010-2",
        "abstract": "A validation-oriented workflow for replicate screening experiments.",
        "status": "Reviewed",
        "tags": ["protocol", "reproducibility"],
        "folder_id": folder_methods,
    },
    {
        "title": "Solvent Effects on Supported Metal Catalysts",
        "authors": "C. Rossi; N. Ahmed",
        "publication_year": 2022,
        "source_name": "Chemical Engineering Journal",
        "doi": "10.1016/j.cej.2022.137401",
        "abstract": "Solvent compatibility and stability effects in supported systems.",
        "status": "To read",
        "tags": ["solvent", "stability"],
        "folder_id": folder_methods,
    },
]

library_item_ids = []
for row in library_rows:
    library_item_ids.append(
        create_library_item(
            **row,
            item_type="paper",
            project_ids=[project_id],
            personal_notes="Relevant evidence for the CM-01 manuscript.",
        )
    )

discovery_results = [
    {
        "ranking_id": "candidate-1",
        "openalex_id": "W4401000001",
        "title": "Long-Term Stability of Heterogeneous Catalysts under Variable pH",
        "authors": "A. Novak; P. Laurent; K. Ito",
        "publication_year": 2025,
        "publication_date": "2025-03-18",
        "source_name": "Journal of Catalysis",
        "doi": "10.1016/j.jcat.2025.115012",
        "url": "https://doi.org/10.1016/j.jcat.2025.115012",
        "pdf_url": "",
        "cited_by_count": 19,
        "is_open_access": True,
        "oa_status": "gold",
        "abstract": "Catalyst activity is profiled across pH and temperature with repeated measurements and mechanistic controls.",
        "relevance_score": 0.96,
        "base_score": 87.4,
        "ai_score": 93.0,
        "final_score": 91.2,
        "match_reasons": ["Direct pH stability evidence", "Includes temperature interaction", "Open-access full text"],
        "ai_reasoning": "Closest methodological match to the CM-01 validation plan.",
        "ai_limitations": "Different catalyst support material.",
        "matched_queries": ["heterogeneous catalyst pH stability temperature"],
        "matched_query": "heterogeneous catalyst pH stability temperature",
    },
    {
        "ranking_id": "candidate-2",
        "openalex_id": "W4401000002",
        "title": "Accelerated Ageing Tests for Catalyst Deactivation",
        "authors": "D. Marin; S. Weber",
        "publication_year": 2024,
        "publication_date": "2024-09-02",
        "source_name": "Catalysis Today",
        "doi": "10.1016/j.cattod.2024.114321",
        "url": "https://doi.org/10.1016/j.cattod.2024.114321",
        "pdf_url": "",
        "cited_by_count": 42,
        "is_open_access": False,
        "oa_status": "closed",
        "abstract": "A comparative protocol for measuring catalyst deactivation under thermal stress.",
        "relevance_score": 0.88,
        "base_score": 81.5,
        "ai_score": 86.0,
        "final_score": 84.4,
        "match_reasons": ["Strong validation protocol", "Thermal stress focus"],
        "ai_reasoning": "Useful for designing the 35 °C and 45 °C validation steps.",
        "ai_limitations": "Does not evaluate pH directly.",
        "matched_queries": ["catalyst deactivation accelerated ageing"],
        "matched_query": "catalyst deactivation accelerated ageing",
    },
    {
        "ranking_id": "candidate-3",
        "openalex_id": "W4401000003",
        "title": "Solvent Compatibility in Catalytic Screening Workflows",
        "authors": "F. García; L. Smith; C. Zhou",
        "publication_year": 2023,
        "publication_date": "2023-11-21",
        "source_name": "Reaction Chemistry & Engineering",
        "doi": "10.1039/d3re00418f",
        "url": "https://doi.org/10.1039/d3re00418f",
        "pdf_url": "",
        "cited_by_count": 27,
        "is_open_access": True,
        "oa_status": "green",
        "abstract": "A screening framework for DMSO and ethanol effects on catalyst performance.",
        "relevance_score": 0.82,
        "base_score": 75.1,
        "ai_score": 79.0,
        "final_score": 77.6,
        "match_reasons": ["Direct solvent comparison", "Includes DMSO and ethanol"],
        "ai_reasoning": "Supports interpretation of the solvent compatibility experiment.",
        "ai_limitations": "Short-term observations only.",
        "matched_queries": ["DMSO ethanol catalyst stability"],
        "matched_query": "DMSO ethanol catalyst stability",
    },
]
replace_project_discovery_results(
    project_id,
    results=discovery_results,
    profile={
        "research_topic": "Operational stability of catalyst CM-01",
        "short_description": "Evidence for pH, temperature and solvent effects in heterogeneous catalyst stability.",
        "keywords": ["catalyst stability", "pH", "temperature", "DMSO", "deactivation"],
        "search_queries": [
            "heterogeneous catalyst pH stability temperature",
            "catalyst deactivation accelerated ageing",
            "DMSO ethanol catalyst stability",
        ],
        "exclude_terms": ["photocatalysis"],
    },
    queries=[
        "heterogeneous catalyst pH stability temperature",
        "catalyst deactivation accelerated ageing",
        "DMSO ethanol catalyst stability",
    ],
    search_options={
        "from_year": 2021,
        "to_year": 2026,
        "open_access_only": False,
        "result_limit": 10,
        "order": "hybrid",
    },
    source_mode="AI Recommendations",
)

manuscript_id = create_manuscript(
    project_id,
    "Stability Profile of CM-01 under pH and Temperature Stress",
    status="In review",
    citation_style="APA 7",
)
sections = get_manuscript_sections(manuscript_id)
section_content = {
    "Abstract": "CM-01 catalyst stability was evaluated across buffered pH conditions and controlled temperature stress. Activity remained above 92% between pH 6.5 and 7.2 after 48 hours, while elevated temperature accelerated deactivation.",
    "Introduction": "Operational stability determines whether catalytic performance can be translated from screening to a reproducible process. This study integrates experimental notes with traceable literature evidence.",
    "Methods": "Six buffered conditions were tested at 25 °C. Follow-up measurements at 35 °C and 45 °C used three replicates per condition. Relative activity was normalized to the initial measurement.",
    "Results": "The near-neutral window retained the highest activity. At pH 6.5–7.2, mean relative activity exceeded 92% after 48 hours. At 45 °C, visible aggregation coincided with a decline to 61% activity.",
    "Discussion": "The combined evidence indicates that temperature is the primary operational constraint. Solvent compatibility is acceptable at 2% DMSO, but the 35 °C condition requires confirmation at pH 7.2.",
    "Conclusion": "CM-01 is stable under near-neutral conditions, with a validated operating window centered on pH 6.5–7.2.",
}
for section in sections:
    if section["title"] in section_content:
        update_manuscript_section(section["id"], content_md=section_content[section["title"]])
create_manuscript_version(
    manuscript_id,
    "Results reviewed",
    trigger_type="manual",
    note="Integrated the temperature-stress evidence and clarified the stability window.",
)
create_manuscript_version(
    manuscript_id,
    "Initial structured draft",
    trigger_type="manual",
    note="Created the IMRaD outline from project evidence.",
)

run_id = create_analysis_run(
    library_item_id=None,
    source_kind="upload",
    source_name="cm01_stability_screen.csv",
    objective="classification",
    algorithm_key="random_forest_classifier",
    algorithm_label="Random Forest",
    target_column="stability_class",
    feature_columns=["pH", "temperature", "elapsed_hours", "relative_activity"],
    parameters={"n_estimators": 200, "max_depth": 6, "random_state": 42},
    preprocessing={"imputation": "median", "scaling": True, "encoding": "one-hot", "test_size": 0.2, "random_state": 42},
    row_count=1248,
    column_count=12,
)
complete_analysis_run(
    run_id,
    metrics={"accuracy": 0.92, "f1": 0.90, "roc_auc": 0.95, "precision": 0.91},
    results={
        "warnings": [],
        "charts": {
            "class_distribution": [{"label": "Stable", "count": 986}, {"label": "Unstable", "count": 262}],
            "roc_curve": {"false_positive_rate": [0, 0.04, 0.12, 0.25, 1], "true_positive_rate": [0, 0.62, 0.84, 0.94, 1], "auc": 0.95},
            "confusion_matrix": {"labels": ["Stable", "Unstable"], "matrix": [[192, 8], [12, 38]]},
            "feature_importance": [
                {"feature": "pH", "importance": 0.37},
                {"feature": "temperature", "importance": 0.31},
                {"feature": "elapsed_hours", "importance": 0.19},
                {"feature": "relative_activity", "importance": 0.13},
            ],
        },
        "preview": [
            {"pH": 6.5, "temperature": 25, "actual": "Stable", "prediction": "Stable", "probability": 0.97},
            {"pH": 7.2, "temperature": 35, "actual": "Stable", "prediction": "Stable", "probability": 0.88},
            {"pH": 5.0, "temperature": 45, "actual": "Unstable", "prediction": "Unstable", "probability": 0.94},
        ],
    },
    predictions_file_path=None,
    report_file_path=None,
)

print(json.dumps({"project_id": project_id, "primary_chat": primary_chat, "manuscript_id": manuscript_id, "analysis_run_id": run_id}))
