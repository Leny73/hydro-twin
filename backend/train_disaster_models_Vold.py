"""
train_disaster_models.py — HydroTwin Risk Classifiers
=====================================================

Trains three ordinal risk-classification models:

1. flood_saturation_precursor
   X = prior saturation/wetness features from t-1
   y = flood_risk_level at t

2. flood_detection
   X = current flood-relevant observations at t
   y = flood_risk_level at t

3. drought
   X = generic prior EO/weather features from t-1
   y = drought_risk_level at t

Risk classes:
    0 = SAFE
    1 = LOW_RISK
    2 = MODERATE_RISK
    3 = HIGH_RISK
    4 = VERY_HIGH_RISK

Run from project root:
    python -m backend.train_disaster_models

Expected input:
    data/ml/supervised_disaster_dataset.csv

Outputs:
    data/models/flood_saturation_precursor_xgboost.json
    data/models/flood_detection_xgboost.json
    data/models/drought_risk_xgboost.json
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
)
from xgboost import XGBClassifier


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATASET_PATH = os.path.join(PROJECT_ROOT, "data", "ml", "supervised_disaster_dataset.csv")
MODEL_DIR = os.path.join(PROJECT_ROOT, "data", "models")
PLOT_DIR = os.path.join(PROJECT_ROOT, "data", "plots")

os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(PLOT_DIR, exist_ok=True)

RISK_LABELS = {
    0: "SAFE",
    1: "LOW_RISK",
    2: "MODERATE_RISK",
    3: "HIGH_RISK",
    4: "VERY_HIGH_RISK",
}

GENERIC_LAG1_FEATURES = [
    "feature_t_minus_1_ndvi",
    "feature_t_minus_1_ndwi",
    "feature_t_minus_1_s1_moisture",
    "feature_t_minus_1_soil_moisture_pct",
    "feature_t_minus_1_soil_moisture_7d_delta",
    "feature_t_minus_1_precip_mm_7d",
    "feature_t_minus_1_precip_mm_30d",
    "feature_t_minus_1_forecast_precip_24h_mm",
    "feature_t_minus_1_temp_max_c",
    "feature_t_minus_1_drought_index",
    "feature_t_minus_1_flood_extent_km2",
    "feature_t_minus_1_week_of_year",
]

# Main hypothesis: prior saturation/wetness state -> future/current flood risk.
FLOOD_SATURATION_PRECURSOR_FEATURES = [
    "feature_t_minus_1_soil_moisture_pct",
    "feature_t_minus_1_soil_moisture_7d_delta",
    "feature_t_minus_1_precip_mm_7d",
    "feature_t_minus_1_precip_mm_30d",
    "feature_t_minus_1_s1_moisture",
    "feature_t_minus_1_ndwi",
    "feature_t_minus_1_flood_extent_km2",
    "feature_t_minus_1_week_of_year",
]

# Runtime-compatible detection model: today/current observations -> today's flood risk.
FLOOD_DETECTION_FEATURES = [
    "feature_t_minus_0_soil_moisture_pct",
    "feature_t_minus_0_soil_moisture_7d_delta",
    "feature_t_minus_0_precip_mm_7d",
    "feature_t_minus_0_precip_mm_30d",
    "feature_t_minus_0_forecast_precip_24h_mm",
    "feature_t_minus_0_s1_moisture",
    "feature_t_minus_0_ndwi",
    "feature_t_minus_0_flood_extent_km2",
    "feature_t_minus_0_week_of_year",
]

MODEL_CONFIGS = [
    {
        "target_col": "flood_risk_level",
        "model_stem": "flood_saturation_precursor",
        "model_filename": "flood_saturation_precursor_xgboost.json",
        "feature_set": FLOOD_SATURATION_PRECURSOR_FEATURES,
        "description": "prior saturation/wetness -> flood risk",
    },
    {
        "target_col": "flood_risk_level",
        "model_stem": "flood_detection",
        "model_filename": "flood_detection_xgboost.json",
        "feature_set": FLOOD_DETECTION_FEATURES,
        "description": "current observations -> flood risk",
    },
    {
        "target_col": "drought_risk_level",
        "model_stem": "drought",
        "model_filename": "drought_risk_xgboost.json",
        "feature_set": GENERIC_LAG1_FEATURES,
        "description": "prior EO/weather -> drought risk",
    },
]


@dataclass
class TrainResult:
    target_name: str
    model_stem: str
    model_path: str
    report_path: str
    importance_path: str
    confusion_path: str
    plot_path: str
    metrics: dict[str, Any]


def load_dataset(path: str = DATASET_PATH) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Dataset not found: {path}\n"
            "Run first: python -m backend.sentinel_extractor"
        )

    df = pd.read_csv(path)

    if "target_date" in df.columns:
        df["target_date"] = pd.to_datetime(df["target_date"], errors="coerce")
        sort_cols = [c for c in ["aoi_name", "target_date"] if c in df.columns]
        df = df.sort_values(sort_cols).reset_index(drop=True)

    return df


def make_xy(
    df: pd.DataFrame,
    target_col: str,
    feature_set: list[str],
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    if target_col not in df.columns:
        raise ValueError(f"Missing target column: {target_col}")

    feature_cols = [c for c in feature_set if c in df.columns]
    missing = [c for c in feature_set if c not in df.columns]

    if missing:
        print("Missing requested features:")
        for col in missing:
            print(f"  - {col}")

    if not feature_cols:
        raise ValueError("No requested feature columns found in dataset.")

    keep_cols = ["target_date", target_col] + feature_cols
    if "aoi_name" in df.columns:
        keep_cols.insert(0, "aoi_name")

    model_df = df[keep_cols].copy()

    for col in feature_cols:
        model_df[col] = pd.to_numeric(model_df[col], errors="coerce")

    model_df[target_col] = pd.to_numeric(model_df[target_col], errors="coerce")
    model_df = model_df.dropna(subset=[target_col])
    model_df[target_col] = model_df[target_col].astype(int).clip(0, 4)

    cleaned_features = []
    for col in feature_cols:
        if model_df[col].isna().all():
            continue
        if model_df[col].nunique(dropna=True) <= 1:
            continue
        cleaned_features.append(col)

    if not cleaned_features:
        raise ValueError("All requested feature columns are empty or constant.")

    X = model_df[cleaned_features]
    y = model_df[target_col]

    return X, y, model_df


def temporal_train_test_split(
    X: pd.DataFrame,
    y: pd.Series,
    model_df: pd.DataFrame,
    train_fraction: float = 0.8,
):
    if len(X) < 10:
        raise ValueError(f"Dataset too small: {len(X)} rows")

    split_idx = int(len(X) * train_fraction)
    split_idx = max(1, min(split_idx, len(X) - 1))

    X_train = X.iloc[:split_idx]
    X_test = X.iloc[split_idx:]
    y_train = y.iloc[:split_idx]
    y_test = y.iloc[split_idx:]
    dates_test = model_df["target_date"].iloc[split_idx:] if "target_date" in model_df.columns else None

    return X_train, X_test, y_train, y_test, dates_test


def remap_classes(
    y_train_raw: pd.Series,
    y_test_raw: pd.Series,
) -> tuple[pd.Series, pd.Series, dict[int, int], dict[int, int]]:
    """
    XGBoost requires contiguous classes 0..K-1 in training.
    This maps observed train classes to contiguous ids.
    Test rows with unseen classes are excluded from evaluation.
    """
    train_classes = sorted(y_train_raw.dropna().astype(int).unique().tolist())
    mapping = {old: new for new, old in enumerate(train_classes)}
    inverse = {new: old for old, new in mapping.items()}

    y_train = y_train_raw.map(mapping).astype(int)
    y_test = y_test_raw.map(mapping)

    return y_train, y_test, mapping, inverse


def build_model(num_classes: int) -> XGBClassifier:
    return XGBClassifier(
        n_estimators=100,
        max_depth=2,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        min_child_weight=3,
        reg_alpha=1.0,
        reg_lambda=8.0,
        objective="multi:softprob",
        num_class=num_classes,
        random_state=42,
        n_jobs=-1,
        eval_metric="mlogloss",
    )


def save_prediction_plot(
    dates,
    y_true: pd.Series,
    y_pred: np.ndarray,
    title: str,
    output_path: str,
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed; skipping prediction plot.")
        return

    plt.figure(figsize=(12, 5))
    x_axis = dates if dates is not None else range(len(y_true))
    plt.plot(x_axis, y_true.values, label="True risk level", linewidth=2)
    plt.plot(x_axis, y_pred, label="Predicted risk level", linewidth=2, linestyle="--")
    plt.yticks(list(RISK_LABELS.keys()), [RISK_LABELS[i] for i in RISK_LABELS])
    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel("Risk class")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=160)
    plt.close()


def train_one_model(df: pd.DataFrame, config: dict[str, Any]) -> TrainResult:
    target_col = config["target_col"]
    model_stem = config["model_stem"]
    feature_set = config["feature_set"]
    model_filename = config["model_filename"]
    description = config.get("description", "")

    print("\n───────────────────────────────────────────────────────")
    print(f"Training model : {model_stem}")
    print(f"Target         : {target_col}")
    print(f"Task           : {description}")
    print("───────────────────────────────────────────────────────")

    X, y, model_df = make_xy(df, target_col, feature_set)
    X_train, X_test, y_train_raw, y_test_raw, dates_test = temporal_train_test_split(X, y, model_df)

    y_train, y_test_mapped, mapping, inverse_mapping = remap_classes(y_train_raw, y_test_raw)
    valid_test_mask = y_test_mapped.notna()

    X_test_eval = X_test.loc[valid_test_mask]
    y_test_eval_mapped = y_test_mapped.loc[valid_test_mask].astype(int)
    y_test_eval_original = y_test_raw.loc[valid_test_mask].astype(int)
    dates_test_eval = dates_test.loc[valid_test_mask] if dates_test is not None else None

    print(f"Rows total : {len(X)}")
    print(f"Rows train : {len(X_train)}")
    print(f"Rows test  : {len(X_test_eval)}")
    print(f"Features   : {X.shape[1]}")
    print(f"Class mapping: {mapping}")
    print("Target distribution total:")
    print(y.value_counts().sort_index().to_string())
    print("Target distribution train:")
    print(y_train_raw.value_counts().sort_index().to_string())
    print("Target distribution test:")
    print(y_test_eval_original.value_counts().sort_index().to_string())
    print("Selected features:")
    for col in X.columns:
        print(f"  - {col}")

    if y_train.nunique() < 2:
        raise ValueError(f"Only one class present in training data for {model_stem}. Cannot train classifier.")

    if len(X_test_eval) == 0:
        raise ValueError(f"No valid test rows for {model_stem}; test set contains unseen classes only.")

    baseline = DummyClassifier(strategy="most_frequent")
    baseline.fit(X_train, y_train)
    baseline_pred_mapped = baseline.predict(X_test_eval)

    model = build_model(num_classes=y_train.nunique())
    model.fit(X_train, y_train)
    pred_mapped = model.predict(X_test_eval)

    pred_original = np.array([inverse_mapping[int(v)] for v in pred_mapped])
    baseline_original = np.array([inverse_mapping[int(v)] for v in baseline_pred_mapped])

    accuracy = accuracy_score(y_test_eval_original, pred_original)
    balanced_acc = balanced_accuracy_score(y_test_eval_original, pred_original)
    baseline_accuracy = accuracy_score(y_test_eval_original, baseline_original)
    baseline_balanced_acc = balanced_accuracy_score(y_test_eval_original, baseline_original)

    metrics = {
        "rows_total": int(len(X)),
        "rows_train": int(len(X_train)),
        "rows_test": int(len(X_test_eval)),
        "features": int(X.shape[1]),
        "accuracy": float(accuracy),
        "balanced_accuracy": float(balanced_acc),
        "baseline_accuracy": float(baseline_accuracy),
        "baseline_balanced_accuracy": float(baseline_balanced_acc),
        "accuracy_improvement_vs_baseline": float(accuracy - baseline_accuracy),
        "balanced_accuracy_improvement_vs_baseline": float(balanced_acc - baseline_balanced_acc),
        "class_mapping": mapping,
    }

    print("Baseline most-frequent classifier:")
    print(f"  accuracy          : {baseline_accuracy}")
    print(f"  balanced_accuracy : {baseline_balanced_acc}")
    print("XGBoost classifier:")
    for k, v in metrics.items():
        print(f"{k}: {v}")

    model_path = os.path.join(MODEL_DIR, model_filename)
    report_path = os.path.join(MODEL_DIR, f"{model_stem}_classification_report.csv")
    importance_path = os.path.join(MODEL_DIR, f"{model_stem}_feature_importance.csv")
    confusion_path = os.path.join(MODEL_DIR, f"{model_stem}_confusion_matrix.csv")
    plot_path = os.path.join(PLOT_DIR, f"model_{model_stem}_prediction.png")

    model.save_model(model_path)

    report = classification_report(
        y_test_eval_original,
        pred_original,
        labels=[0, 1, 2, 3, 4],
        target_names=[RISK_LABELS[i] for i in range(5)],
        output_dict=True,
        zero_division=0,
    )
    pd.DataFrame(report).transpose().to_csv(report_path)

    importance = pd.DataFrame({
        "feature": X.columns,
        "importance": model.feature_importances_,
    }).sort_values("importance", ascending=False)
    importance.to_csv(importance_path, index=False)

    confusion = confusion_matrix(y_test_eval_original, pred_original, labels=[0, 1, 2, 3, 4])
    pd.DataFrame(
        confusion,
        index=[RISK_LABELS[i] for i in range(5)],
        columns=[RISK_LABELS[i] for i in range(5)],
    ).to_csv(confusion_path)

    save_prediction_plot(
        dates_test_eval,
        y_test_eval_original,
        pred_original,
        title=f"{model_stem}: predicted vs true risk class",
        output_path=plot_path,
    )

    print(f"Saved model      : {model_path}")
    print(f"Saved report     : {report_path}")
    print(f"Saved importance : {importance_path}")
    print(f"Saved confusion  : {confusion_path}")
    print(f"Saved plot       : {plot_path}")

    if metrics["balanced_accuracy_improvement_vs_baseline"] <= 0:
        print("WARNING: classifier did not beat baseline. Treat this target as not learned.")

    return TrainResult(
        target_name=target_col,
        model_stem=model_stem,
        model_path=model_path,
        report_path=report_path,
        importance_path=importance_path,
        confusion_path=confusion_path,
        plot_path=plot_path,
        metrics=metrics,
    )


def save_feature_manifest() -> str:
    path = os.path.join(MODEL_DIR, "model_features.json")
    manifest = {
        "generic_lag1_features": GENERIC_LAG1_FEATURES,
        "flood_saturation_precursor_features": FLOOD_SATURATION_PRECURSOR_FEATURES,
        "flood_detection_features": FLOOD_DETECTION_FEATURES,
        "risk_labels": RISK_LABELS,
        "models": {
            "flood_saturation_precursor": "flood_saturation_precursor_xgboost.json",
            "flood_detection": "flood_detection_xgboost.json",
            "drought": "drought_risk_xgboost.json",
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return path


def main() -> None:
    print("Loading supervised dataset...")
    print(f"Dataset: {DATASET_PATH}")
    df = load_dataset(DATASET_PATH)
    print(f"Shape: {df.shape}")

    results = []
    for config in MODEL_CONFIGS:
        try:
            results.append(train_one_model(df, config))
        except Exception as exc:
            print(f"Training skipped/failed for {config['model_stem']}: {exc}")

    feature_manifest_path = save_feature_manifest()

    summary_path = os.path.join(MODEL_DIR, "training_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "target_name": r.target_name,
                    "model_stem": r.model_stem,
                    "model_path": r.model_path,
                    "report_path": r.report_path,
                    "importance_path": r.importance_path,
                    "confusion_path": r.confusion_path,
                    "plot_path": r.plot_path,
                    "metrics": r.metrics,
                }
                for r in results
            ],
            f,
            indent=2,
        )

    print("\n───────────────────────────────────────────────────────")
    print("DONE")
    print("───────────────────────────────────────────────────────")
    print(f"Training summary : {summary_path}")
    print(f"Feature manifest : {feature_manifest_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Training failed: {exc}")
        sys.exit(1)
