import io
import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_numeric_dtype,
    is_string_dtype,
)

from services.resource_limits import (
    concurrency_slot,
    consume_rate_limit,
    enforce_storage_quota,
    env_int,
)
from utils.user_scope import scoped_path


SUPPORTED_DATASET_EXTENSIONS = (".csv", ".tsv", ".xlsx", ".json")
SUPERVISED_OBJECTIVES = ("classification", "regression")
OBJECTIVE_LABELS = {
    "classification": "Classification",
    "regression": "Regression",
    "clustering": "Clustering",
    "dimensionality_reduction": "Dimensionality reduction",
    "anomaly_detection": "Anomaly detection",
}

ALGORITHM_CATALOG = {
    "logistic_regression": {
        "label": "Logistic Regression",
        "objective": "classification",
        "description": "Fast, interpretable baseline for categorical outcomes.",
        "parameters": {
            "c": {"label": "Regularization C", "type": "float", "default": 1.0, "min": 0.001, "max": 1000.0},
            "max_iter": {"label": "Maximum iterations", "type": "int", "default": 1000, "min": 100, "max": 5000},
        },
    },
    "random_forest_classifier": {
        "label": "Random Forest",
        "objective": "classification",
        "description": "Robust ensemble for nonlinear relationships and mixed features.",
        "parameters": {
            "n_estimators": {"label": "Number of trees", "type": "int", "default": 200, "min": 50, "max": 500},
            "max_depth": {"label": "Maximum depth (0 = automatic)", "type": "int", "default": 0, "min": 0, "max": 100},
            "min_samples_leaf": {"label": "Minimum samples per leaf", "type": "int", "default": 1, "min": 1, "max": 50},
        },
    },
    "knn_classifier": {
        "label": "K-Nearest Neighbors",
        "objective": "classification",
        "description": "Distance-based classifier suited to compact datasets.",
        "parameters": {
            "n_neighbors": {"label": "Neighbors", "type": "int", "default": 5, "min": 1, "max": 100},
            "weights": {"label": "Weighting", "type": "choice", "default": "distance", "choices": ["uniform", "distance"]},
        },
    },
    "ridge_regression": {
        "label": "Ridge Regression",
        "objective": "regression",
        "description": "Regularized linear baseline for continuous outcomes.",
        "parameters": {
            "alpha": {"label": "Regularization alpha", "type": "float", "default": 1.0, "min": 0.0, "max": 1000.0},
        },
    },
    "random_forest_regressor": {
        "label": "Random Forest Regressor",
        "objective": "regression",
        "description": "Nonlinear ensemble for continuous outcomes.",
        "parameters": {
            "n_estimators": {"label": "Number of trees", "type": "int", "default": 200, "min": 50, "max": 500},
            "max_depth": {"label": "Maximum depth (0 = automatic)", "type": "int", "default": 0, "min": 0, "max": 100},
            "min_samples_leaf": {"label": "Minimum samples per leaf", "type": "int", "default": 1, "min": 1, "max": 50},
        },
    },
    "gradient_boosting_regressor": {
        "label": "Gradient Boosting Regressor",
        "objective": "regression",
        "description": "Boosted decision trees for accurate nonlinear regression.",
        "parameters": {
            "n_estimators": {"label": "Number of stages", "type": "int", "default": 150, "min": 50, "max": 500},
            "learning_rate": {"label": "Learning rate", "type": "float", "default": 0.05, "min": 0.001, "max": 1.0},
            "max_depth": {"label": "Tree depth", "type": "int", "default": 3, "min": 1, "max": 12},
        },
    },
    "kmeans": {
        "label": "K-Means",
        "objective": "clustering",
        "description": "Groups samples into a chosen number of compact clusters.",
        "parameters": {
            "n_clusters": {"label": "Clusters", "type": "int", "default": 3, "min": 2, "max": 20},
        },
    },
    "dbscan": {
        "label": "DBSCAN",
        "objective": "clustering",
        "description": "Density-based clustering that can identify noise points.",
        "parameters": {
            "eps": {"label": "Neighborhood radius", "type": "float", "default": 0.5, "min": 0.01, "max": 20.0},
            "min_samples": {"label": "Minimum samples", "type": "int", "default": 5, "min": 2, "max": 100},
        },
    },
    "pca": {
        "label": "Principal Component Analysis (PCA)",
        "objective": "dimensionality_reduction",
        "description": "Projects features into components that preserve maximum variance.",
        "parameters": {
            "n_components": {"label": "Components", "type": "int", "default": 2, "min": 2, "max": 20},
        },
    },
    "isolation_forest": {
        "label": "Isolation Forest",
        "objective": "anomaly_detection",
        "description": "Detects unusual observations through random isolation trees.",
        "parameters": {
            "n_estimators": {"label": "Number of trees", "type": "int", "default": 200, "min": 50, "max": 500},
            "contamination": {"label": "Expected anomaly fraction", "type": "float", "default": 0.05, "min": 0.001, "max": 0.5},
        },
    },
}


def algorithms_for_objective(objective: str) -> list[tuple[str, dict]]:
    return [
        (key, value)
        for key, value in ALGORITHM_CATALOG.items()
        if value["objective"] == objective
    ]


def default_algorithm_for_objective(objective: str) -> str:
    defaults = {
        "classification": "random_forest_classifier",
        "regression": "random_forest_regressor",
        "clustering": "kmeans",
        "dimensionality_reduction": "pca",
        "anomaly_detection": "isolation_forest",
    }
    return defaults[objective]


def normalize_algorithm_parameters(algorithm_key: str, values: dict | None = None) -> dict:
    if algorithm_key not in ALGORITHM_CATALOG:
        raise ValueError("Choose a supported analysis algorithm.")

    provided = values or {}
    normalized = {}

    for key, spec in ALGORITHM_CATALOG[algorithm_key]["parameters"].items():
        raw_value = provided.get(key, spec["default"])

        if spec["type"] == "choice":
            normalized[key] = raw_value if raw_value in spec["choices"] else spec["default"]
            continue

        converter = int if spec["type"] == "int" else float

        try:
            numeric_value = converter(raw_value)
        except (TypeError, ValueError):
            numeric_value = converter(spec["default"])

        numeric_value = max(spec["min"], min(numeric_value, spec["max"]))
        normalized[key] = converter(numeric_value)

    return normalized


def validate_dataset_filename(filename: str) -> str:
    normalized = Path(str(filename or "")).name.strip()
    suffix = Path(normalized).suffix.lower()

    if not normalized:
        raise ValueError("The dataset must have a filename.")

    if suffix not in SUPPORTED_DATASET_EXTENSIONS:
        supported = ", ".join(SUPPORTED_DATASET_EXTENSIONS)
        raise ValueError(f"Unsupported dataset format. Choose one of: {supported}.")

    return normalized


def _normalize_object_cells(dataframe: pd.DataFrame) -> pd.DataFrame:
    normalized = dataframe.copy()

    def normalize_value(value):
        if isinstance(value, (dict, list, tuple, set)):
            return json.dumps(value, ensure_ascii=False, default=str)
        return value

    for column in normalized.columns:
        if normalized[column].dtype == "object":
            normalized[column] = normalized[column].map(normalize_value)

    return normalized


def _validate_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        raise ValueError("The dataset does not contain any data rows.")

    max_rows = env_int("MAX_ANALYSIS_ROWS", 100_000, maximum=1_000_000)
    max_columns = env_int("MAX_ANALYSIS_COLUMNS", 250, maximum=2_000)

    if len(dataframe) > max_rows:
        raise ValueError(f"The dataset exceeds the limit of {max_rows:,} rows.")

    if len(dataframe.columns) > max_columns:
        raise ValueError(f"The dataset exceeds the limit of {max_columns} columns.")

    column_names = [str(value).strip() or f"Column {index + 1}" for index, value in enumerate(dataframe.columns)]

    if len(set(column_names)) != len(column_names):
        raise ValueError("Dataset column names must be unique.")

    dataframe = dataframe.copy()
    dataframe.columns = column_names
    dataframe = _normalize_object_cells(dataframe)
    return dataframe


def load_tabular_data(filename: str, file_bytes: bytes) -> pd.DataFrame:
    filename = validate_dataset_filename(filename)
    content = bytes(file_bytes or b"")
    max_bytes = env_int(
        "MAX_ANALYSIS_FILE_SIZE",
        25 * 1024 * 1024,
        minimum=1024,
        maximum=250 * 1024 * 1024,
    )

    if not content:
        raise ValueError("The selected dataset is empty.")

    if len(content) > max_bytes:
        raise ValueError(f"The dataset exceeds the {max_bytes // (1024 * 1024)} MB analysis limit.")

    suffix = Path(filename).suffix.lower()
    source = io.BytesIO(content)

    try:
        if suffix == ".csv":
            dataframe = pd.read_csv(source, sep=None, engine="python")
        elif suffix == ".tsv":
            dataframe = pd.read_csv(source, sep="\t")
        elif suffix == ".xlsx":
            dataframe = pd.read_excel(source, engine="openpyxl")
        else:
            try:
                dataframe = pd.read_json(source)
            except ValueError:
                source.seek(0)
                dataframe = pd.read_json(source, lines=True)
    except (ImportError, UnicodeDecodeError, ValueError, TypeError) as exc:
        raise ValueError(f"The dataset could not be parsed: {exc}") from exc

    return _validate_dataframe(dataframe)


def column_kind(series: pd.Series) -> str:
    if is_bool_dtype(series.dtype):
        return "Category"
    if is_numeric_dtype(series.dtype):
        return "Numeric"
    if is_datetime64_any_dtype(series.dtype):
        return "Date"

    non_missing = series.dropna()
    unique_count = int(non_missing.nunique(dropna=True))
    threshold = min(50, max(12, int(len(non_missing) * 0.08)))
    return "Category" if unique_count <= threshold else "Text"


def profile_dataset(dataframe: pd.DataFrame) -> dict:
    total_cells = max(1, int(dataframe.shape[0] * dataframe.shape[1]))
    missing_cells = int(dataframe.isna().sum().sum())
    columns = []

    for name in dataframe.columns:
        series = dataframe[name]
        kind = column_kind(series)
        unique_count = int(series.nunique(dropna=True))
        missing_count = int(series.isna().sum())
        is_recommended = not (
            kind == "Text"
            and unique_count > max(20, int(len(dataframe) * 0.5))
        )
        columns.append({
            "name": name,
            "kind": kind,
            "dtype": str(series.dtype),
            "missing": missing_count,
            "missing_percent": round(100 * missing_count / max(1, len(dataframe)), 2),
            "unique": unique_count,
            "recommended_feature": is_recommended,
        })

    return {
        "rows": int(dataframe.shape[0]),
        "columns_count": int(dataframe.shape[1]),
        "missing_cells": missing_cells,
        "missing_percent": round(100 * missing_cells / total_cells, 2),
        "duplicate_rows": int(dataframe.duplicated().sum()),
        "memory_bytes": int(dataframe.memory_usage(index=True, deep=True).sum()),
        "columns": columns,
    }


def recommended_feature_columns(dataframe: pd.DataFrame, target_column: str | None = None) -> list[str]:
    profile = profile_dataset(dataframe)
    return [
        column["name"]
        for column in profile["columns"]
        if column["name"] != target_column and column["recommended_feature"]
    ]


def _validate_analysis_setup(
    dataframe: pd.DataFrame,
    *,
    objective: str,
    algorithm_key: str,
    feature_columns: list[str],
    target_column: str | None,
    preprocessing: dict,
):
    if objective not in OBJECTIVE_LABELS:
        raise ValueError("Choose a supported analysis objective.")

    algorithm = ALGORITHM_CATALOG.get(algorithm_key)

    if not algorithm or algorithm["objective"] != objective:
        raise ValueError("The selected algorithm does not support this objective.")

    unique_features = list(dict.fromkeys(feature_columns or []))

    if not unique_features:
        raise ValueError("Select at least one feature column.")

    missing_features = [column for column in unique_features if column not in dataframe.columns]

    if missing_features:
        raise ValueError("One or more selected feature columns no longer exist.")

    if objective in SUPERVISED_OBJECTIVES:
        if not target_column or target_column not in dataframe.columns:
            raise ValueError("Select a target column for supervised learning.")
        if target_column in unique_features:
            raise ValueError("The target column cannot also be used as a feature.")

    selected = dataframe[unique_features]
    categorical_columns = [
        column
        for column in unique_features
        if not is_numeric_dtype(selected[column].dtype) or is_bool_dtype(selected[column].dtype)
    ]

    if selected.isna().any().any() and not preprocessing.get("impute_missing", True):
        raise ValueError("The selected features contain missing values. Enable imputation or remove those rows.")

    if categorical_columns and not preprocessing.get("encode_categories", True):
        raise ValueError("Categorical features require category encoding.")

    max_encoded = env_int("MAX_ANALYSIS_ENCODED_FEATURES", 500, maximum=5_000)
    estimated_features = len(unique_features) - len(categorical_columns)
    estimated_features += sum(
        min(max(1, int(selected[column].nunique(dropna=True))), 100)
        for column in categorical_columns
    )

    if estimated_features > max_encoded:
        raise ValueError(
            f"Categorical encoding would create approximately {estimated_features} features, "
            f"above the limit of {max_encoded}. Remove high-cardinality columns such as IDs or free text."
        )

    if len(dataframe) < 10:
        raise ValueError("At least 10 rows are required for analysis.")


def _make_preprocessor(dataframe: pd.DataFrame, feature_columns: list[str], preprocessing: dict):
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    numeric_columns = [
        column
        for column in feature_columns
        if is_numeric_dtype(dataframe[column].dtype) and not is_bool_dtype(dataframe[column].dtype)
    ]
    categorical_columns = [column for column in feature_columns if column not in numeric_columns]
    transformers = []

    if numeric_columns:
        numeric_steps = []

        if preprocessing.get("impute_missing", True):
            numeric_steps.append(("imputer", SimpleImputer(strategy="median", keep_empty_features=True)))

        if preprocessing.get("scale_numeric", True):
            numeric_steps.append(("scaler", StandardScaler()))

        numeric_transformer = Pipeline(numeric_steps) if numeric_steps else "passthrough"
        transformers.append(("numeric", numeric_transformer, numeric_columns))

    if categorical_columns:
        category_steps = []

        if preprocessing.get("impute_missing", True):
            category_steps.append(("imputer", SimpleImputer(strategy="most_frequent", keep_empty_features=True)))

        category_steps.append((
            "encoder",
            OneHotEncoder(
                handle_unknown="infrequent_if_exist",
                max_categories=100,
                sparse_output=False,
            ),
        ))
        transformers.append(("category", Pipeline(category_steps), categorical_columns))

    return ColumnTransformer(transformers, remainder="drop", verbose_feature_names_out=False)


def _build_estimator(algorithm_key: str, parameters: dict):
    if algorithm_key == "logistic_regression":
        from sklearn.linear_model import LogisticRegression
        return LogisticRegression(
            C=parameters["c"],
            max_iter=parameters["max_iter"],
            class_weight="balanced",
            random_state=42,
        )
    if algorithm_key == "random_forest_classifier":
        from sklearn.ensemble import RandomForestClassifier
        return RandomForestClassifier(
            n_estimators=parameters["n_estimators"],
            max_depth=parameters["max_depth"] or None,
            min_samples_leaf=parameters["min_samples_leaf"],
            class_weight="balanced",
            random_state=42,
            n_jobs=1,
        )
    if algorithm_key == "knn_classifier":
        from sklearn.neighbors import KNeighborsClassifier
        return KNeighborsClassifier(
            n_neighbors=parameters["n_neighbors"],
            weights=parameters["weights"],
            n_jobs=1,
        )
    if algorithm_key == "ridge_regression":
        from sklearn.linear_model import Ridge
        return Ridge(alpha=parameters["alpha"])
    if algorithm_key == "random_forest_regressor":
        from sklearn.ensemble import RandomForestRegressor
        return RandomForestRegressor(
            n_estimators=parameters["n_estimators"],
            max_depth=parameters["max_depth"] or None,
            min_samples_leaf=parameters["min_samples_leaf"],
            random_state=42,
            n_jobs=1,
        )
    if algorithm_key == "gradient_boosting_regressor":
        from sklearn.ensemble import GradientBoostingRegressor
        return GradientBoostingRegressor(
            n_estimators=parameters["n_estimators"],
            learning_rate=parameters["learning_rate"],
            max_depth=parameters["max_depth"],
            random_state=42,
        )
    if algorithm_key == "kmeans":
        from sklearn.cluster import KMeans
        return KMeans(n_clusters=parameters["n_clusters"], n_init="auto", random_state=42)
    if algorithm_key == "dbscan":
        from sklearn.cluster import DBSCAN
        return DBSCAN(eps=parameters["eps"], min_samples=parameters["min_samples"], n_jobs=1)
    if algorithm_key == "pca":
        from sklearn.decomposition import PCA
        return PCA(n_components=parameters["n_components"], random_state=42)
    if algorithm_key == "isolation_forest":
        from sklearn.ensemble import IsolationForest
        return IsolationForest(
            n_estimators=parameters["n_estimators"],
            contamination=parameters["contamination"],
            random_state=42,
            n_jobs=1,
        )

    raise ValueError("Unsupported analysis algorithm.")


def _json_number(value):
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _records(dataframe: pd.DataFrame, limit: int = 50) -> list[dict]:
    preview = dataframe.head(limit).copy()
    preview = preview.replace([np.inf, -np.inf], np.nan)
    return json.loads(preview.to_json(orient="records", date_format="iso"))


def _two_dimensional_projection(matrix) -> np.ndarray:
    from sklearn.decomposition import PCA

    values = np.asarray(matrix)

    if values.ndim != 2 or values.shape[1] == 0:
        raise ValueError("Preprocessing did not produce usable numeric features.")

    if values.shape[1] == 1:
        return np.column_stack([values[:, 0], np.zeros(values.shape[0])])

    return PCA(n_components=2, random_state=42).fit_transform(values)


def _permutation_feature_importance(pipeline, X_test, y_test, objective: str) -> list[dict]:
    from sklearn.inspection import permutation_importance

    if not len(X_test):
        return []

    sample_size = min(len(X_test), 1_000)
    sample = X_test.sample(n=sample_size, random_state=42) if len(X_test) > sample_size else X_test
    sample_target = y_test.loc[sample.index]
    scoring = "f1_weighted" if objective == "classification" else "r2"

    try:
        importance = permutation_importance(
            pipeline,
            sample,
            sample_target,
            scoring=scoring,
            n_repeats=2,
            random_state=42,
            n_jobs=1,
        )
    except Exception:
        return []

    rows = [
        {"feature": str(feature), "importance": _json_number(max(0.0, score))}
        for feature, score in zip(X_test.columns, importance.importances_mean)
    ]
    return sorted(rows, key=lambda row: row["importance"] or 0, reverse=True)[:10]


def _run_supervised(
    dataframe: pd.DataFrame,
    *,
    objective: str,
    algorithm_key: str,
    feature_columns: list[str],
    target_column: str,
    parameters: dict,
    preprocessing: dict,
    test_size: float,
) -> dict:
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        f1_score,
        mean_absolute_error,
        mean_squared_error,
        precision_score,
        r2_score,
        recall_score,
        roc_auc_score,
        roc_curve,
    )
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline

    working = dataframe[[*feature_columns, target_column]].copy()
    warnings = []

    if objective == "classification":
        working = working.loc[working[target_column].notna()].copy()
        working[target_column] = working[target_column].astype(str)
        class_counts = working[target_column].value_counts()

        if len(class_counts) < 2:
            raise ValueError("Classification requires at least two target classes.")
        if len(class_counts) > 20:
            raise ValueError("Classification supports at most 20 target classes in this workspace.")
    else:
        working[target_column] = pd.to_numeric(working[target_column], errors="coerce")
        dropped = int(working[target_column].isna().sum())
        working = working.loc[working[target_column].notna()].copy()

        if dropped:
            warnings.append(f"Excluded {dropped} rows with a missing or non-numeric target.")

    if len(working) < 10:
        raise ValueError("At least 10 rows with a valid target are required.")

    X = working[feature_columns]
    y = working[target_column]
    test_size = max(0.1, min(float(test_size), 0.4))
    stratify = None

    if objective == "classification":
        counts = y.value_counts()
        expected_test_rows = max(1, int(round(len(y) * test_size)))

        if int(counts.min()) >= 2 and expected_test_rows >= len(counts):
            stratify = y
        else:
            warnings.append("The target could not be stratified because one or more classes are too small.")

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=42,
        stratify=stratify,
    )
    parameters = dict(parameters)

    if algorithm_key == "knn_classifier" and parameters["n_neighbors"] > len(X_train):
        parameters["n_neighbors"] = max(1, len(X_train))
        warnings.append("Reduced the number of KNN neighbors to match the training set size.")

    pipeline = Pipeline([
        ("preprocessor", _make_preprocessor(X_train, feature_columns, preprocessing)),
        ("model", _build_estimator(algorithm_key, parameters)),
    ])
    pipeline.fit(X_train, y_train)
    predicted = pipeline.predict(X_test)
    predictions = pd.DataFrame({
        "Source row": X_test.index.astype(str),
        "Actual": y_test.to_numpy(),
        "Prediction": predicted,
    })
    charts = {}
    metrics = {}

    if objective == "classification":
        labels = sorted({str(value) for value in y})
        matrix = confusion_matrix(y_test.astype(str), pd.Series(predicted).astype(str), labels=labels)
        metrics = {
            "accuracy": _json_number(accuracy_score(y_test, predicted)),
            "precision": _json_number(precision_score(y_test, predicted, average="weighted", zero_division=0)),
            "recall": _json_number(recall_score(y_test, predicted, average="weighted", zero_division=0)),
            "f1": _json_number(f1_score(y_test, predicted, average="weighted", zero_division=0)),
        }
        charts["class_distribution"] = [
            {"label": str(label), "count": int(count)}
            for label, count in y.value_counts().sort_index().items()
        ]
        charts["confusion_matrix"] = {"labels": labels, "matrix": matrix.tolist()}

        model = pipeline.named_steps["model"]

        if (
            len(labels) == 2
            and y_test.astype(str).nunique() == 2
            and hasattr(model, "predict_proba")
        ):
            probabilities = pipeline.predict_proba(X_test)
            model_labels = [str(value) for value in model.classes_]
            positive_label = labels[-1]
            positive_index = model_labels.index(positive_label)
            positive_scores = probabilities[:, positive_index]
            binary_actual = (y_test.astype(str) == positive_label).astype(int)
            fpr, tpr, _ = roc_curve(binary_actual, positive_scores)
            auc_value = roc_auc_score(binary_actual, positive_scores)
            metrics["roc_auc"] = _json_number(auc_value)
            charts["roc_curve"] = {
                "fpr": [_json_number(value) for value in fpr],
                "tpr": [_json_number(value) for value in tpr],
                "auc": _json_number(auc_value),
                "positive_label": positive_label,
            }
            predictions["Confidence"] = probabilities.max(axis=1)
        elif len(labels) > 2 and hasattr(model, "predict_proba"):
            try:
                probabilities = pipeline.predict_proba(X_test)
                metrics["roc_auc"] = _json_number(
                    roc_auc_score(y_test, probabilities, multi_class="ovr", average="weighted", labels=model.classes_)
                )
                predictions["Confidence"] = probabilities.max(axis=1)
            except ValueError:
                pass
    else:
        actual = np.asarray(y_test, dtype=float)
        predicted_numeric = np.asarray(predicted, dtype=float)
        residuals = actual - predicted_numeric
        metrics = {
            "r2": _json_number(r2_score(actual, predicted_numeric)),
            "mae": _json_number(mean_absolute_error(actual, predicted_numeric)),
            "rmse": _json_number(math.sqrt(mean_squared_error(actual, predicted_numeric))),
        }
        limit = min(1_000, len(actual))
        charts["actual_vs_predicted"] = {
            "actual": [_json_number(value) for value in actual[:limit]],
            "predicted": [_json_number(value) for value in predicted_numeric[:limit]],
        }
        counts, edges = np.histogram(residuals, bins=min(20, max(5, int(math.sqrt(len(residuals))))))
        charts["residual_distribution"] = {
            "counts": counts.astype(int).tolist(),
            "edges": [_json_number(value) for value in edges],
        }
        predictions["Residual"] = residuals

    charts["feature_importance"] = _permutation_feature_importance(
        pipeline,
        X_test,
        y_test,
        objective,
    )
    return {
        "metrics": metrics,
        "charts": charts,
        "warnings": warnings,
        "predictions": predictions,
        "preview": _records(predictions),
        "test_rows": int(len(X_test)),
    }


def _run_unsupervised(
    dataframe: pd.DataFrame,
    *,
    objective: str,
    algorithm_key: str,
    feature_columns: list[str],
    parameters: dict,
    preprocessing: dict,
) -> dict:
    from sklearn.metrics import silhouette_score

    X = dataframe[feature_columns].copy()
    preprocessor = _make_preprocessor(X, feature_columns, preprocessing)
    encoded = np.asarray(preprocessor.fit_transform(X))

    if not np.isfinite(encoded).all():
        raise ValueError("Preprocessing produced non-finite values. Review missing and infinite values.")

    estimator = _build_estimator(algorithm_key, parameters)
    metrics = {}
    charts = {}
    warnings = []
    predictions = pd.DataFrame({"Source row": X.index.astype(str)})

    if objective == "clustering":
        if algorithm_key == "kmeans" and parameters["n_clusters"] >= len(X):
            raise ValueError("The number of clusters must be smaller than the number of rows.")

        labels = estimator.fit_predict(encoded)
        predictions["Cluster"] = labels
        unique_clusters = sorted(set(int(value) for value in labels if int(value) != -1))
        noise_count = int(np.sum(labels == -1))
        metrics["clusters"] = len(unique_clusters)
        metrics["noise_ratio"] = _json_number(noise_count / max(1, len(labels)))
        valid_mask = labels != -1

        if len(set(labels[valid_mask])) >= 2 and int(valid_mask.sum()) > len(set(labels[valid_mask])):
            try:
                metrics["silhouette"] = _json_number(
                    silhouette_score(encoded[valid_mask], labels[valid_mask], sample_size=min(5_000, int(valid_mask.sum())), random_state=42)
                )
            except ValueError:
                pass

        distribution = pd.Series(labels).value_counts().sort_index()
        charts["cluster_distribution"] = [
            {"label": "Noise" if int(label) == -1 else f"Cluster {int(label) + 1}", "count": int(count)}
            for label, count in distribution.items()
        ]
        projection = _two_dimensional_projection(encoded)
        limit = min(len(projection), 2_000)
        charts["cluster_scatter"] = {
            "x": [_json_number(value) for value in projection[:limit, 0]],
            "y": [_json_number(value) for value in projection[:limit, 1]],
            "labels": [int(value) for value in labels[:limit]],
        }
    elif objective == "dimensionality_reduction":
        component_count = min(parameters["n_components"], encoded.shape[0], encoded.shape[1])

        if component_count < 2:
            raise ValueError("PCA requires at least two usable rows and two encoded features.")

        estimator.set_params(n_components=component_count)
        components = estimator.fit_transform(encoded)

        for index in range(component_count):
            predictions[f"PC{index + 1}"] = components[:, index]

        explained = estimator.explained_variance_ratio_
        metrics["components"] = int(component_count)
        metrics["explained_variance"] = _json_number(explained.sum())
        charts["explained_variance"] = [
            {"label": f"PC{index + 1}", "value": _json_number(value)}
            for index, value in enumerate(explained)
        ]
        limit = min(len(components), 2_000)
        charts["pca_scatter"] = {
            "x": [_json_number(value) for value in components[:limit, 0]],
            "y": [_json_number(value) for value in components[:limit, 1]],
        }
    else:
        labels = estimator.fit_predict(encoded)
        scores = estimator.decision_function(encoded)
        friendly_labels = np.where(labels == -1, "Anomaly", "Normal")
        predictions["Prediction"] = friendly_labels
        predictions["Anomaly score"] = -scores
        anomaly_count = int(np.sum(labels == -1))
        metrics["anomalies"] = anomaly_count
        metrics["anomaly_ratio"] = _json_number(anomaly_count / max(1, len(labels)))
        charts["anomaly_distribution"] = [
            {"label": "Normal", "count": int(len(labels) - anomaly_count)},
            {"label": "Anomaly", "count": anomaly_count},
        ]
        counts, edges = np.histogram(-scores, bins=min(24, max(6, int(math.sqrt(len(scores))))))
        charts["score_distribution"] = {
            "counts": counts.astype(int).tolist(),
            "edges": [_json_number(value) for value in edges],
        }
        projection = _two_dimensional_projection(encoded)
        limit = min(len(projection), 2_000)
        charts["anomaly_scatter"] = {
            "x": [_json_number(value) for value in projection[:limit, 0]],
            "y": [_json_number(value) for value in projection[:limit, 1]],
            "labels": [str(value) for value in friendly_labels[:limit]],
        }

    return {
        "metrics": metrics,
        "charts": charts,
        "warnings": warnings,
        "predictions": predictions,
        "preview": _records(predictions),
        "test_rows": int(len(X)),
    }


def run_analysis(
    dataframe: pd.DataFrame,
    *,
    objective: str,
    algorithm_key: str,
    feature_columns: list[str],
    target_column: str | None = None,
    parameters: dict | None = None,
    preprocessing: dict | None = None,
    test_size: float = 0.2,
) -> dict:
    normalized_parameters = normalize_algorithm_parameters(algorithm_key, parameters)
    normalized_preprocessing = {
        "impute_missing": bool((preprocessing or {}).get("impute_missing", True)),
        "scale_numeric": bool((preprocessing or {}).get("scale_numeric", True)),
        "encode_categories": bool((preprocessing or {}).get("encode_categories", True)),
        "random_state": 42,
    }
    feature_columns = list(dict.fromkeys(feature_columns or []))
    _validate_analysis_setup(
        dataframe,
        objective=objective,
        algorithm_key=algorithm_key,
        feature_columns=feature_columns,
        target_column=target_column,
        preprocessing=normalized_preprocessing,
    )
    consume_rate_limit(
        "DataAnalysis",
        per_user_hour=env_int("ANALYSIS_RUNS_PER_USER_HOUR", 20, maximum=1_000),
        per_user_day=env_int("ANALYSIS_RUNS_PER_USER_DAY", 100, maximum=10_000),
        global_per_minute=env_int("ANALYSIS_GLOBAL_RUNS_PER_MINUTE", 15, maximum=1_000),
        global_per_day=env_int("ANALYSIS_GLOBAL_RUNS_PER_DAY", 1_000, maximum=100_000),
    )

    with concurrency_slot(
        "DataAnalysis",
        global_limit=env_int("ANALYSIS_MAX_CONCURRENT_RUNS", 2, maximum=64),
        lease_seconds=env_int("ANALYSIS_MAX_LEASE_SECONDS", 600, minimum=30, maximum=3_600),
    ):
        if objective in SUPERVISED_OBJECTIVES:
            outcome = _run_supervised(
                dataframe,
                objective=objective,
                algorithm_key=algorithm_key,
                feature_columns=feature_columns,
                target_column=str(target_column),
                parameters=normalized_parameters,
                preprocessing=normalized_preprocessing,
                test_size=test_size,
            )
        else:
            outcome = _run_unsupervised(
                dataframe,
                objective=objective,
                algorithm_key=algorithm_key,
                feature_columns=feature_columns,
                parameters=normalized_parameters,
                preprocessing=normalized_preprocessing,
            )

    outcome["objective"] = objective
    outcome["algorithm_key"] = algorithm_key
    outcome["algorithm_label"] = ALGORITHM_CATALOG[algorithm_key]["label"]
    outcome["parameters"] = normalized_parameters
    outcome["preprocessing"] = normalized_preprocessing
    outcome["feature_columns"] = feature_columns
    outcome["target_column"] = target_column
    return outcome


def serializable_analysis_result(outcome: dict) -> dict:
    return {
        "objective": outcome["objective"],
        "algorithm_key": outcome["algorithm_key"],
        "algorithm_label": outcome["algorithm_label"],
        "parameters": outcome["parameters"],
        "preprocessing": outcome["preprocessing"],
        "feature_columns": outcome["feature_columns"],
        "target_column": outcome.get("target_column"),
        "charts": outcome.get("charts", {}),
        "warnings": outcome.get("warnings", []),
        "preview": outcome.get("preview", []),
        "test_rows": outcome.get("test_rows", 0),
    }


def build_analysis_report(
    *,
    run_id: int,
    source_name: str,
    outcome: dict,
    row_count: int,
    column_count: int,
) -> str:
    metric_lines = "\n".join(
        f"- **{key.replace('_', ' ').title()}:** {value:.4f}" if isinstance(value, float) else f"- **{key.replace('_', ' ').title()}:** {value}"
        for key, value in outcome.get("metrics", {}).items()
        if value is not None
    ) or "- No metric was available."
    warnings = "\n".join(f"- {value}" for value in outcome.get("warnings", [])) or "- None"
    return (
        f"# Data Analysis Report — Run #{run_id}\n\n"
        f"## Dataset\n\n"
        f"- **Source:** {source_name}\n"
        f"- **Shape:** {row_count:,} rows × {column_count:,} columns\n\n"
        f"## Configuration\n\n"
        f"- **Objective:** {OBJECTIVE_LABELS[outcome['objective']]}\n"
        f"- **Algorithm:** {outcome['algorithm_label']}\n"
        f"- **Target:** {outcome.get('target_column') or 'Not required'}\n"
        f"- **Features:** {', '.join(outcome['feature_columns'])}\n"
        f"- **Parameters:** `{json.dumps(outcome['parameters'], ensure_ascii=False)}`\n"
        f"- **Preprocessing:** `{json.dumps(outcome['preprocessing'], ensure_ascii=False)}`\n"
        f"- **Random state:** 42\n\n"
        f"## Metrics\n\n{metric_lines}\n\n"
        f"## Warnings\n\n{warnings}\n"
    )


def get_analysis_storage_path() -> Path:
    storage = scoped_path(os.getenv("DATA_ANALYSIS_STORAGE_PATH", "data/analysis"))
    storage.mkdir(parents=True, exist_ok=True, mode=0o700)

    try:
        storage.chmod(0o700)
    except OSError:
        pass

    return storage


def _safe_analysis_path(path: str | Path) -> Path:
    root = get_analysis_storage_path().resolve()
    resolved = Path(path).expanduser().resolve()

    if resolved != root and root not in resolved.parents:
        raise ValueError("The requested file is outside the analysis storage area.")

    return resolved


def _safe_csv_value(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def predictions_csv_bytes(predictions: pd.DataFrame) -> bytes:
    safe = predictions.copy()

    for column in safe.columns:
        if is_string_dtype(safe[column].dtype) or safe[column].dtype == "object":
            safe[column] = safe[column].map(_safe_csv_value)

    return safe.to_csv(index=False).encode("utf-8-sig")


def save_analysis_artifacts(
    run_id: int,
    *,
    predictions: pd.DataFrame,
    report_markdown: str,
) -> dict:
    root = get_analysis_storage_path()
    predictions_bytes = predictions_csv_bytes(predictions)
    report_bytes = report_markdown.encode("utf-8")
    enforce_storage_quota(
        root,
        len(predictions_bytes) + len(report_bytes),
        quota_bytes=env_int("MAX_ANALYSIS_STORAGE_BYTES", 250 * 1024 * 1024, minimum=1024 * 1024),
        label="analysis",
        max_files=env_int("MAX_STORED_ANALYSIS_FILES", 1_000, maximum=10_000),
    )
    run_path = root / f"run-{int(run_id)}"
    run_path.mkdir(parents=True, exist_ok=True, mode=0o700)
    predictions_path = run_path / "predictions.csv"
    report_path = run_path / "report.md"
    predictions_path.write_bytes(predictions_bytes)
    report_path.write_bytes(report_bytes)

    for path in (predictions_path, report_path):
        try:
            path.chmod(0o600)
        except OSError:
            pass

    return {
        "predictions_file_path": str(predictions_path),
        "report_file_path": str(report_path),
    }


def read_analysis_artifact(path: str) -> bytes:
    safe_path = _safe_analysis_path(path)

    if not safe_path.is_file():
        raise FileNotFoundError("The stored analysis artifact could not be found.")

    return safe_path.read_bytes()
