from db.library_queries import get_library_items
from db.research_case_queries import mark_research_case_processing, save_research_case
from services.research_case_service import (
    current_embedding_model,
    current_generation_model,
    research_case_source_hash,
)


project_id = 2
items = get_library_items(project_id=project_id, item_types=("paper", "pdf"), limit=20)
templates = [
    ("parameter_sensitivity", "Vary pH across buffered conditions", "pH", "relative catalytic activity"),
    ("robustness_stress_test", "Apply controlled temperature stress", "temperature", "activity retention"),
    ("validation_replication", "Repeat the stability protocol with independent replicates", "replicate batch", "between-run variance"),
    ("comparative_evaluation", "Compare solvent conditions under one protocol", "solvent composition", "relative catalytic activity"),
]

for index, item in enumerate(items):
    template_type, goal, changed_variable, metric = templates[index % len(templates)]
    embedding_model = current_embedding_model()
    generation_model = current_generation_model()
    source_hash = research_case_source_hash(
        item,
        embedding_model=embedding_model,
        generation_model=generation_model,
    )
    mark_research_case_processing(
        project_id=project_id,
        library_item_id=item["id"],
        schema_version="research-case-v1",
        prompt_version="baseline-extraction-v2",
        source_hash=source_hash,
        embedding_model=embedding_model,
        generation_model=generation_model,
    )
    semantic = {
        "metadata": {
            "title": item["title"],
            "domain": "Heterogeneous catalysis",
            "keywords": ["catalyst stability", "validation", changed_variable],
            "source_quality": "abstract_and_metadata",
        },
        "research_context": {
            "problem": "Catalyst deactivation under operating conditions",
            "motivation": "Define a reproducible stability window",
            "limitations": ["Different catalyst formulation", "Short observation window"],
        },
        "proposed_solution": {
            "main_idea": goal,
            "novelty": "Trace experimental strategy to explicit source evidence",
            "components": ["controlled conditions", "replicates", "activity measurement"],
        },
        "experimental_strategy": [
            {
                "template_type": template_type,
                "goal": goal,
                "changed_variable": changed_variable,
                "controlled_variables": ["catalyst loading", "assay duration", "measurement protocol"],
                "evaluation_metric": metric,
                "motivation": "Estimate robustness while preserving comparability.",
                "concrete_example": f"Test {changed_variable} at three controlled levels with triplicate measurements.",
                "evidence": {
                    "section": "Methods and Results",
                    "page": "abstract",
                    "excerpt": "The source reports a controlled comparison with repeated measurements.",
                },
            }
        ],
        "findings": {
            "main_results": ["Controlled validation identifies an operational stability window."],
            "negative_results": ["Performance declines outside the preferred operating range."],
            "future_work": ["Replicate the protocol on the CM-01 formulation."],
        },
        "traceability": {
            "sections": [{"name": "Abstract", "page_range": "abstract"}]
        },
    }
    embedding = [round(((item["id"] * 13 + position * 7) % 23) / 23, 6) for position in range(16)]
    save_research_case(
        project_id=project_id,
        library_item_id=item["id"],
        schema_version="research-case-v1",
        prompt_version="baseline-extraction-v2",
        source_hash=source_hash,
        semantic=semantic,
        embedding=embedding,
        embedding_model=embedding_model,
        generation_model=generation_model,
    )

print(f"Seeded {len(items)} Research Cases")
