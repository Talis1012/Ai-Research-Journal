import io
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from db.data_analysis_queries import (
    complete_analysis_run,
    create_analysis_run,
    fail_analysis_run,
    get_analysis_run,
    get_analysis_runs,
)
from db.database import init_db
from services.data_analysis_service import (
    load_tabular_data,
    predictions_csv_bytes,
    profile_dataset,
    read_analysis_artifact,
    run_analysis,
    save_analysis_artifacts,
    serializable_analysis_result,
)
from utils.user_scope import activate_user_scope, clear_user_scope


def research_dataframe(rows: int = 90) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "compound_id": f"CM-{index:03}",
            "ph": 4.0 + (index % 9) * 0.5,
            "temperature": 20 + (index % 4) * 5,
            "excipient": ("A", "B", "C")[index % 3],
            "solubility": 3.0 + (index % 11) * 1.4,
            "stability": "Stable" if index % 9 > 3 else "Unstable",
        }
        for index in range(rows)
    ])


class DataAnalysisTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.saved_environment = {
            name: os.environ.get(name)
            for name in (
                "DATABASE_PATH",
                "RATE_LIMIT_DATABASE_PATH",
                "DATA_ANALYSIS_STORAGE_PATH",
                "MAX_ANALYSIS_ROWS",
                "MAX_ANALYSIS_STORAGE_BYTES",
            )
        }
        os.environ["DATABASE_PATH"] = str(root / "app.db")
        os.environ["RATE_LIMIT_DATABASE_PATH"] = str(root / "limits.db")
        os.environ["DATA_ANALYSIS_STORAGE_PATH"] = str(root / "analysis")
        os.environ["MAX_ANALYSIS_ROWS"] = "1000"
        os.environ["MAX_ANALYSIS_STORAGE_BYTES"] = str(20 * 1024 * 1024)
        activate_user_scope("https://tests.local", "data-analysis")
        init_db()

    def tearDown(self):
        clear_user_scope()

        for name, value in self.saved_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

        self.temp_dir.cleanup()

    def test_csv_tsv_json_and_xlsx_loading_and_profile(self):
        csv_frame = load_tabular_data(
            "screening.csv",
            b"compound,ph,status\nCM-1,7.4,Stable\nCM-2,,Unstable\n",
        )
        self.assertEqual(csv_frame.shape, (2, 3))
        self.assertEqual(profile_dataset(csv_frame)["missing_cells"], 1)

        tsv_frame = load_tabular_data(
            "screening.tsv",
            b"compound\tph\nCM-1\t7.4\nCM-2\t6.8\n",
        )
        self.assertEqual(list(tsv_frame.columns), ["compound", "ph"])

        json_frame = load_tabular_data(
            "screening.json",
            b'[{"compound":"CM-1","ph":7.4},{"compound":"CM-2","ph":6.8}]',
        )
        self.assertEqual(len(json_frame), 2)

        excel_bytes = io.BytesIO()
        pd.DataFrame({"compound": ["CM-1", "CM-2"], "ph": [7.4, 6.8]}).to_excel(
            excel_bytes,
            index=False,
        )
        excel_frame = load_tabular_data("screening.xlsx", excel_bytes.getvalue())
        self.assertEqual(excel_frame.shape, (2, 2))

    def test_loader_enforces_format_and_row_limits(self):
        with self.assertRaises(ValueError):
            load_tabular_data("unsafe.pkl", b"not a pickle")

        os.environ["MAX_ANALYSIS_ROWS"] = "10"
        content = "value\n" + "\n".join(str(value) for value in range(11))

        with self.assertRaises(ValueError):
            load_tabular_data("too-many.csv", content.encode())

    def test_classification_pipeline_returns_metrics_and_charts(self):
        dataframe = research_dataframe()
        outcome = run_analysis(
            dataframe,
            objective="classification",
            algorithm_key="logistic_regression",
            feature_columns=["ph", "temperature", "excipient", "solubility"],
            target_column="stability",
            parameters={"max_iter": 400},
        )

        self.assertIn("accuracy", outcome["metrics"])
        self.assertIn("f1", outcome["metrics"])
        self.assertIn("confusion_matrix", outcome["charts"])
        self.assertIn("roc_curve", outcome["charts"])
        self.assertIn("feature_importance", outcome["charts"])
        self.assertEqual(set(outcome["predictions"]["Prediction"]), {"Stable", "Unstable"})

    def test_other_analysis_objectives_smoke(self):
        dataframe = research_dataframe()
        cases = (
            (
                "regression",
                "ridge_regression",
                ["ph", "temperature", "excipient"],
                "solubility",
                {},
                "rmse",
                "actual_vs_predicted",
            ),
            (
                "clustering",
                "kmeans",
                ["ph", "temperature", "solubility"],
                None,
                {"n_clusters": 3},
                "clusters",
                "cluster_scatter",
            ),
            (
                "dimensionality_reduction",
                "pca",
                ["ph", "temperature", "solubility"],
                None,
                {"n_components": 2},
                "explained_variance",
                "pca_scatter",
            ),
            (
                "anomaly_detection",
                "isolation_forest",
                ["ph", "temperature", "solubility"],
                None,
                {"n_estimators": 50, "contamination": 0.05},
                "anomalies",
                "anomaly_scatter",
            ),
        )

        for objective, algorithm, features, target, parameters, metric, chart in cases:
            with self.subTest(objective=objective):
                outcome = run_analysis(
                    dataframe,
                    objective=objective,
                    algorithm_key=algorithm,
                    feature_columns=features,
                    target_column=target,
                    parameters=parameters,
                )
                self.assertIn(metric, outcome["metrics"])
                self.assertIn(chart, outcome["charts"])
                self.assertFalse(outcome["predictions"].empty)

    def test_run_history_and_private_artifacts(self):
        run_id = create_analysis_run(
            library_item_id=None,
            source_kind="upload",
            source_name="screening.csv",
            objective="classification",
            algorithm_key="logistic_regression",
            algorithm_label="Logistic Regression",
            target_column="stability",
            feature_columns=["ph"],
            parameters={"c": 1.0},
            preprocessing={"random_state": 42},
            row_count=90,
            column_count=6,
        )
        predictions = pd.DataFrame({
            "Source row": [0, 1],
            "Actual": ["Stable", "Unstable"],
            "Prediction": ["Stable", "Unstable"],
        })
        paths = save_analysis_artifacts(
            run_id,
            predictions=predictions,
            report_markdown="# Analysis report",
        )
        complete_analysis_run(
            run_id,
            metrics={"accuracy": 1.0},
            results={"charts": {}, "preview": []},
            **paths,
        )
        saved = get_analysis_run(run_id)

        self.assertEqual(saved["status"], "completed")
        self.assertEqual(saved["metrics"]["accuracy"], 1.0)
        self.assertEqual(get_analysis_runs()[0]["id"], run_id)
        self.assertIn(b"Stable", read_analysis_artifact(saved["predictions_file_path"]))

        outside = Path(self.temp_dir.name) / "outside.csv"
        outside.write_text("private", encoding="utf-8")

        with self.assertRaises(ValueError):
            read_analysis_artifact(str(outside))

    def test_failed_run_is_persisted_and_csv_formulas_are_neutralized(self):
        run_id = create_analysis_run(
            library_item_id=None,
            source_kind="upload",
            source_name="failed.csv",
            objective="classification",
            algorithm_key="logistic_regression",
            algorithm_label="Logistic Regression",
            target_column="target",
            feature_columns=["value"],
            parameters={},
            preprocessing={},
            row_count=1,
            column_count=2,
        )
        fail_analysis_run(run_id, "Not enough rows")
        self.assertEqual(get_analysis_run(run_id)["status"], "failed")

        csv_bytes = predictions_csv_bytes(pd.DataFrame({"unsafe": ["=2+2", "@SUM(A:A)"]}))
        self.assertIn(b"'=2+2", csv_bytes)
        self.assertIn(b"'@SUM", csv_bytes)

    def test_serializable_result_drops_runtime_dataframe(self):
        outcome = run_analysis(
            research_dataframe(),
            objective="classification",
            algorithm_key="logistic_regression",
            feature_columns=["ph", "temperature"],
            target_column="stability",
        )
        serialized = serializable_analysis_result(outcome)
        self.assertNotIn("predictions", serialized)
        self.assertIn("preview", serialized)


if __name__ == "__main__":
    unittest.main()
