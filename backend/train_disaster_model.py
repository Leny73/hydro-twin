
"""
train_disaster_models.py — HydroTwin Maximalist Bulgaria Risk Classifiers
========================================================================

Trains three ordinal risk classifiers using the meteorology-expanded dataset:

1. flood_saturation_precursor
   X = t-1 saturation + synoptic + compound features
   y = flood_risk_level at t

2. flood_detection
   X = t current EO/weather/synoptic features
   y = flood_risk_level at t

3. drought
   X = t-1 vegetation/soil/heat/blocking features
   y = drought_risk_level at t

Run:
    python -m backend.train_disaster_models
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
    f1_score,
    mean_absolute_error,
)
from sklearn.utils.class_weight import compute_sample_weight
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
    "feature_t_minus_1_s1_vv_db",
    "feature_t_minus_1_s1_vh_db",
    "feature_t_minus_1_flood_extent_km2",
    "feature_t_minus_1_soil_moisture_pct",
    "feature_t_minus_1_soil_moisture_7d_delta",
    "feature_t_minus_1_precip_mm_24h",
    "feature_t_minus_1_precip_mm_48h",
    "feature_t_minus_1_precip_mm_72h",
    "feature_t_minus_1_precip_mm_7d",
    "feature_t_minus_1_precip_mm_30d",
    "feature_t_minus_1_forecast_precip_24h_mm",
    "feature_t_minus_1_forecast_precip_48h_mm",
    "feature_t_minus_1_forecast_precip_72h_mm",
    "feature_t_minus_1_precip_intensity_max_1h_mm",
    "feature_t_minus_1_temp_max_c",
    "feature_t_minus_1_temp_min_c",
    "feature_t_minus_1_temp_mean_c",
    "feature_t_minus_1_dew_point_max_c",
    "feature_t_minus_1_dewpoint_depression_min_c",
    "feature_t_minus_1_relative_humidity_mean_pct",
    "feature_t_minus_1_relative_humidity_max_pct",
    "feature_t_minus_1_pressure_mean_hpa",
    "feature_t_minus_1_pressure_min_hpa",
    "feature_t_minus_1_pressure_drop_24h_hpa",
    "feature_t_minus_1_pressure_drop_48h_hpa",
    "feature_t_minus_1_wind_speed_max_ms",
    "feature_t_minus_1_wind_gust_max_ms",
    "feature_t_minus_1_cloud_cover_mean_pct",
    "feature_t_minus_1_cloud_cover_max_pct",
    "feature_t_minus_1_uvi_max",
    "feature_t_minus_1_snow_mm_24h",
    "feature_t_minus_1_snow_mm_48h",
    "feature_t_minus_1_snowmelt_proxy",
    "feature_t_minus_1_drought_stress_index",
    "feature_t_minus_1_week_of_year",
    "feature_t_minus_1_month",
    "feature_t_minus_1_day_of_year",
    "feature_t_minus_1_is_spring",
    "feature_t_minus_1_is_summer",
    "feature_t_minus_1_is_autumn",
    "feature_t_minus_1_is_winter",
    "feature_t_minus_1_precip_7d_ratio_to_pleven_avg",
    "feature_t_minus_1_precip_30d_ratio_to_pleven_avg",
    "feature_t_minus_1_soil_moisture_ratio_to_pleven_avg",
    "feature_t_minus_1_ndvi_seasonal_anomaly_proxy",
    "feature_t_minus_1_heavy_rain_hours_24h",
    "feature_t_minus_1_heavy_rain_hours_48h",
    "feature_t_minus_1_thunderstorm_hours_48h",
    "feature_t_minus_1_convective_proxy",
    "feature_t_minus_1_ivt_proxy",
    "feature_t_minus_1_mediterranean_cyclone_proxy",
    "feature_t_minus_1_cutoff_low_proxy",
    "feature_t_minus_1_cyclogenesis_proxy",
    "feature_t_minus_1_blocking_heat_proxy",
    "feature_t_minus_1_synoptic_flood_score",
    "feature_t_minus_1_flash_flood_trigger",
    "feature_t_minus_1_soil_saturation_surge",
    "feature_t_minus_1_drought_to_flood_transition",
    "feature_t_minus_1_compound_drought_heat",
    "feature_t_minus_1_compound_flood_after_dry_spell",
    "feature_t_minus_1_flood_watch_threshold_count",
    "feature_t_minus_1_flood_warning_threshold_count",
    "feature_t_minus_1_drought_watch_threshold_count",
    "feature_t_minus_1_drought_warning_threshold_count",
    "feature_t_minus_1_alert_confidence",
]

FLOOD_SATURATION_PRECURSOR_FEATURES = [
    "feature_t_minus_1_soil_moisture_pct",
    "feature_t_minus_1_soil_moisture_7d_delta",
    "feature_t_minus_1_precip_mm_7d",
    "feature_t_minus_1_precip_mm_30d",
    "feature_t_minus_1_forecast_precip_24h_mm",
    "feature_t_minus_1_forecast_precip_48h_mm",
    "feature_t_minus_1_s1_moisture",
    "feature_t_minus_1_ndwi",
    "feature_t_minus_1_flood_extent_km2",
    "feature_t_minus_1_pressure_drop_24h_hpa",
    "feature_t_minus_1_pressure_drop_48h_hpa",
    "feature_t_minus_1_wind_gust_max_ms",
    "feature_t_minus_1_relative_humidity_mean_pct",
    "feature_t_minus_1_precip_7d_ratio_to_pleven_avg",
    "feature_t_minus_1_precip_30d_ratio_to_pleven_avg",
    "feature_t_minus_1_heavy_rain_hours_48h",
    "feature_t_minus_1_convective_proxy",
    "feature_t_minus_1_ivt_proxy",
    "feature_t_minus_1_mediterranean_cyclone_proxy",
    "feature_t_minus_1_cutoff_low_proxy",
    "feature_t_minus_1_cyclogenesis_proxy",
    "feature_t_minus_1_synoptic_flood_score",
    "feature_t_minus_1_flash_flood_trigger",
    "feature_t_minus_1_soil_saturation_surge",
    "feature_t_minus_1_drought_to_flood_transition",
    "feature_t_minus_1_compound_flood_after_dry_spell",
    "feature_t_minus_1_snowmelt_proxy",
    "feature_t_minus_1_flood_watch_threshold_count",
    "feature_t_minus_1_flood_warning_threshold_count",
    "feature_t_minus_1_is_spring",
    "feature_t_minus_1_is_summer",
    "feature_t_minus_1_is_autumn",
    "feature_t_minus_1_month",
    "feature_t_minus_1_week_of_year",
]

FLOOD_DETECTION_FEATURES = [
    "feature_t_minus_0_soil_moisture_pct",
    "feature_t_minus_0_soil_moisture_7d_delta",
    "feature_t_minus_0_precip_mm_24h",
    "feature_t_minus_0_precip_mm_48h",
    "feature_t_minus_0_precip_mm_72h",
    "feature_t_minus_0_precip_mm_7d",
    "feature_t_minus_0_precip_mm_30d",
    "feature_t_minus_0_forecast_precip_24h_mm",
    "feature_t_minus_0_forecast_precip_48h_mm",
    "feature_t_minus_0_forecast_precip_72h_mm",
    "feature_t_minus_0_precip_intensity_max_1h_mm",
    "feature_t_minus_0_s1_moisture",
    "feature_t_minus_0_ndwi",
    "feature_t_minus_0_flood_extent_km2",
    "feature_t_minus_0_pressure_min_hpa",
    "feature_t_minus_0_pressure_drop_24h_hpa",
    "feature_t_minus_0_pressure_drop_48h_hpa",
    "feature_t_minus_0_wind_gust_max_ms",
    "feature_t_minus_0_relative_humidity_mean_pct",
    "feature_t_minus_0_heavy_rain_hours_24h",
    "feature_t_minus_0_heavy_rain_hours_48h",
    "feature_t_minus_0_thunderstorm_hours_48h",
    "feature_t_minus_0_convective_proxy",
    "feature_t_minus_0_ivt_proxy",
    "feature_t_minus_0_mediterranean_cyclone_proxy",
    "feature_t_minus_0_cutoff_low_proxy",
    "feature_t_minus_0_cyclogenesis_proxy",
    "feature_t_minus_0_synoptic_flood_score",
    "feature_t_minus_0_flash_flood_trigger",
    "feature_t_minus_0_soil_saturation_surge",
    "feature_t_minus_0_drought_to_flood_transition",
    "feature_t_minus_0_compound_flood_after_dry_spell",
    "feature_t_minus_0_snowmelt_proxy",
    "feature_t_minus_0_flood_watch_threshold_count",
    "feature_t_minus_0_flood_warning_threshold_count",
    "feature_t_minus_0_is_spring",
    "feature_t_minus_0_is_summer",
    "feature_t_minus_0_is_autumn",
    "feature_t_minus_0_month",
    "feature_t_minus_0_week_of_year",
]

DROUGHT_FEATURES = [
    "feature_t_minus_1_ndvi",
    "feature_t_minus_1_ndvi_seasonal_anomaly_proxy",
    "feature_t_minus_1_soil_moisture_pct",
    "feature_t_minus_1_soil_moisture_7d_delta",
    "feature_t_minus_1_soil_moisture_ratio_to_pleven_avg",
    "feature_t_minus_1_precip_mm_30d",
    "feature_t_minus_1_precip_30d_ratio_to_pleven_avg",
    "feature_t_minus_1_temp_max_c",
    "feature_t_minus_1_temp_mean_c",
    "feature_t_minus_1_dew_point_max_c",
    "feature_t_minus_1_dewpoint_depression_min_c",
    "feature_t_minus_1_relative_humidity_mean_pct",
    "feature_t_minus_1_cloud_cover_mean_pct",
    "feature_t_minus_1_uvi_max",
    "feature_t_minus_1_wind_speed_max_ms",
    "feature_t_minus_1_drought_stress_index",
    "feature_t_minus_1_blocking_heat_proxy",
    "feature_t_minus_1_compound_drought_heat",
    "feature_t_minus_1_drought_watch_threshold_count",
    "feature_t_minus_1_drought_warning_threshold_count",
    "feature_t_minus_1_is_summer",
    "feature_t_minus_1_is_autumn",
    "feature_t_minus_1_month",
    "feature_t_minus_1_week_of_year",
]

MODEL_CONFIGS = [
    {
        "target_col": "flood_risk_level",
        "model_stem": "flood_saturation_precursor",
        "model_filename": "flood_saturation_precursor_xgboost.json",
        "feature_set": FLOOD_SATURATION_PRECURSOR_FEATURES,
        "description": "prior saturation + synoptic + compound proxies -> flood risk",
    },
    {
        "target_col": "flood_risk_level",
        "model_stem": "flood_detection",
        "model_filename": "flood_detection_xgboost.json",
        "feature_set": FLOOD_DETECTION_FEATURES,
        "description": "current EO/weather/synoptic observations -> flood risk",
    },
    {
        "target_col": "drought_risk_level",
        "model_stem": "drought",
        "model_filename": "drought_risk_xgboost.json",
        "feature_set": DROUGHT_FEATURES,
        "description": "prior vegetation + soil + heat/blocking proxies -> drought risk",
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

    # XGBoost can handle NaN, but very sparse columns should still be avoided.
    sparse_features = []
    for col in cleaned_features:
        non_null_ratio = model_df[col].notna().mean()
        if non_null_ratio >= 0.20:
            sparse_features.append(col)

    if not sparse_features:
        raise ValueError("All requested feature columns are too sparse.")

    X = model_df[sparse_features]
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

    if "target_date" in model_df.columns:
        order = model_df["target_date"].sort_values().index
        X = X.loc[order]
        y = y.loc[order]
        model_df = model_df.loc[order]

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
    train_classes = sorted(y_train_raw.dropna().astype(int).unique().tolist())
    mapping = {old: new for new, old in enumerate(train_classes)}
    inverse = {new: old for old, new in mapping.items()}

    y_train = y_train_raw.map(mapping).astype(int)
    y_test = y_test_raw.map(mapping)

    return y_train, y_test, mapping, inverse


def build_model(num_classes: int) -> XGBClassifier:
    return XGBClassifier(
        n_estimators=350,
        max_depth=3,
        learning_rate=0.035,
        subsample=0.88,
        colsample_bytree=0.88,
        min_child_weight=2,
        gamma=0.25,
        reg_alpha=0.8,
        reg_lambda=6.0,
        objective="multi:softprob",
        num_class=num_classes,
        random_state=42,
        n_jobs=-1,
        eval_metric="mlogloss",
        tree_method="hist",
        max_bin=128,
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


def save_confidence_calibration(model, X_test: pd.DataFrame, y_true_original: pd.Series, pred_original: np.ndarray, output_path: str) -> None:
    if not hasattr(model, "predict_proba"):
        return
    proba = model.predict_proba(X_test)
    confidence = proba.max(axis=1)
    calib = pd.DataFrame({
        "confidence": confidence,
        "correct": (y_true_original.values == pred_original).astype(int),
        "true_level": y_true_original.values,
        "pred_level": pred_original,
        "abs_error": np.abs(y_true_original.values - pred_original),
    })
    calib["confidence_bin"] = pd.cut(calib["confidence"], bins=[0, .2, .4, .6, .8, 1.0], include_lowest=True)
    summary = calib.groupby("confidence_bin", observed=True).agg(
        n=("correct", "size"),
        accuracy=("correct", "mean"),
        mean_abs_error=("abs_error", "mean"),
        mean_confidence=("confidence", "mean"),
    )
    summary.to_csv(output_path)


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
    sample_weight = compute_sample_weight(class_weight="balanced", y=y_train)
    model.fit(X_train, y_train, sample_weight=sample_weight)
    pred_mapped = model.predict(X_test_eval)

    pred_original = np.array([inverse_mapping[int(v)] for v in pred_mapped])
    baseline_original = np.array([inverse_mapping[int(v)] for v in baseline_pred_mapped])

    accuracy = accuracy_score(y_test_eval_original, pred_original)
    balanced_acc = balanced_accuracy_score(y_test_eval_original, pred_original)
    macro_f1 = f1_score(y_test_eval_original, pred_original, labels=[0, 1, 2, 3, 4], average="macro", zero_division=0)
    weighted_f1 = f1_score(y_test_eval_original, pred_original, labels=[0, 1, 2, 3, 4], average="weighted", zero_division=0)
    ordinal_mae = mean_absolute_error(y_test_eval_original, pred_original)

    baseline_accuracy = accuracy_score(y_test_eval_original, baseline_original)
    baseline_balanced_acc = balanced_accuracy_score(y_test_eval_original, baseline_original)
    baseline_macro_f1 = f1_score(y_test_eval_original, baseline_original, labels=[0, 1, 2, 3, 4], average="macro", zero_division=0)
    baseline_ordinal_mae = mean_absolute_error(y_test_eval_original, baseline_original)

    metrics = {
        "rows_total": int(len(X)),
        "rows_train": int(len(X_train)),
        "rows_test": int(len(X_test_eval)),
        "features": int(X.shape[1]),
        "accuracy": float(accuracy),
        "balanced_accuracy": float(balanced_acc),
        "macro_f1": float(macro_f1),
        "weighted_f1": float(weighted_f1),
        "ordinal_mae": float(ordinal_mae),
        "baseline_accuracy": float(baseline_accuracy),
        "baseline_balanced_accuracy": float(baseline_balanced_acc),
        "baseline_macro_f1": float(baseline_macro_f1),
        "baseline_ordinal_mae": float(baseline_ordinal_mae),
        "accuracy_improvement_vs_baseline": float(accuracy - baseline_accuracy),
        "balanced_accuracy_improvement_vs_baseline": float(balanced_acc - baseline_balanced_acc),
        "macro_f1_improvement_vs_baseline": float(macro_f1 - baseline_macro_f1),
        "ordinal_mae_improvement_vs_baseline": float(baseline_ordinal_mae - ordinal_mae),
        "class_mapping": mapping,
    }

    print("Baseline most-frequent classifier:")
    print(f"  accuracy          : {baseline_accuracy}")
    print(f"  balanced_accuracy : {baseline_balanced_acc}")
    print(f"  macro_f1          : {baseline_macro_f1}")
    print(f"  ordinal_mae       : {baseline_ordinal_mae}")
    print("XGBoost classifier:")
    for k, v in metrics.items():
        print(f"{k}: {v}")

    model_path = os.path.join(MODEL_DIR, model_filename)
    report_path = os.path.join(MODEL_DIR, f"{model_stem}_classification_report.csv")
    importance_path = os.path.join(MODEL_DIR, f"{model_stem}_feature_importance.csv")
    confusion_path = os.path.join(MODEL_DIR, f"{model_stem}_confusion_matrix.csv")
    calibration_path = os.path.join(MODEL_DIR, f"{model_stem}_confidence_calibration.csv")
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

    save_confidence_calibration(model, X_test_eval, y_test_eval_original, pred_original, calibration_path)

    save_prediction_plot(
        dates_test_eval,
        y_test_eval_original,
        pred_original,
        title=f"{model_stem}: predicted vs true risk class",
        output_path=plot_path,
    )

    print(f"Saved model       : {model_path}")
    print(f"Saved report      : {report_path}")
    print(f"Saved importance  : {importance_path}")
    print(f"Saved confusion   : {confusion_path}")
    print(f"Saved calibration : {calibration_path}")
    print(f"Saved plot        : {plot_path}")

    if metrics["balanced_accuracy_improvement_vs_baseline"] <= 0:
        print("WARNING: classifier did not beat baseline on balanced accuracy. Treat this target as not learned.")

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
        "drought_features": DROUGHT_FEATURES,
        "risk_labels": RISK_LABELS,
        "models": {
            "flood_saturation_precursor": "flood_saturation_precursor_xgboost.json",
            "flood_detection": "flood_detection_xgboost.json",
            "drought": "drought_risk_xgboost.json",
        },
        "notes": [
            "Use balanced_accuracy, macro_f1, and ordinal_mae as primary metrics.",
            "Plain accuracy can be misleading because SAFE/LOW_RISK classes often dominate.",
            "OpenWeather proxy features are intentionally physical proxies, not replacements for ECMWF/ERA5 diagnostics.",
        ],
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
