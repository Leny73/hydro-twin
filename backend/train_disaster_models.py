"""
train_disaster_models.py

Train and save flood/drought XGBoost models from the supervised dataset.

Run from project root:
    python backend/train_disaster_models.py

Inputs:
    data/ml/supervised_disaster_dataset.csv

Outputs:
    data/models/flood_xgboost.json
    data/models/drought_xgboost.json
    data/models/flood_metrics.csv
    data/models/drought_metrics.csv
    data/models/flood_feature_importance.csv
    data/models/drought_feature_importance.csv
    data/plots/model_flood_prediction.png
    data/plots/model_drought_prediction.png

Install:
    pip install pandas numpy scikit-learn xgboost matplotlib
"""

import os
import sys
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATASET_PATH = os.path.join(PROJECT_ROOT, "data", "ml", "supervised_disaster_dataset.csv")
MODEL_DIR = os.path.join(PROJECT_ROOT, "data", "models")
PLOT_DIR = os.path.join(PROJECT_ROOT, "data", "plots")

os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(PLOT_DIR, exist_ok=True)


@dataclass
class TrainResult:
    target_name: str
    model_path: str
    metrics_path: str
    importance_path: str
    plot_path: str
    metrics: dict


def load_dataset(path: str = DATASET_PATH) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Dataset not found: {path}\n"
            "Run first: python backend/sentinel_extractor.py"
        )

    df = pd.read_csv(path)

    if "target_date" in df.columns:
        df["target_date"] = pd.to_datetime(df["target_date"], errors="coerce")
        df = df.sort_values("target_date").reset_index(drop=True)

    return df


def make_xy(df: pd.DataFrame, target_col: str) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    if target_col not in df.columns:
        raise ValueError(f"Missing target column: {target_col}")

    # Anything not prefixed feature_t_minus is excluded to avoid leakage.
    feature_cols = [c for c in df.columns if c.startswith("feature_t_minus_")]
    if not feature_cols:
        raise ValueError("No feature_t_minus_* columns found. Rebuild supervised dataset.")

    model_df = df[["target_date", target_col] + feature_cols].copy()

    # Convert all feature columns to numeric. Bad strings become NaN.
    for col in feature_cols:
        model_df[col] = pd.to_numeric(model_df[col], errors="coerce")

    model_df[target_col] = pd.to_numeric(model_df[target_col], errors="coerce")

    # Drop rows without target. Keep features only if enough values exist.
    model_df = model_df.dropna(subset=[target_col])

    # XGBoost can handle NaN, but remove completely empty columns.
    feature_cols = [c for c in feature_cols if not model_df[c].isna().all()]
    if not feature_cols:
        raise ValueError("All feature columns are empty after cleaning.")

    X = model_df[feature_cols]
    y = model_df[target_col]

    return X, y, model_df


def temporal_train_test_split(
    X: pd.DataFrame,
    y: pd.Series,
    model_df: pd.DataFrame,
    train_fraction: float = 0.8,
):
    if len(X) < 10:
        raise ValueError(f"Dataset too small for train/test split: {len(X)} rows")

    split_idx = int(len(X) * train_fraction)
    split_idx = max(1, min(split_idx, len(X) - 1))

    X_train = X.iloc[:split_idx]
    X_test = X.iloc[split_idx:]
    y_train = y.iloc[:split_idx]
    y_test = y.iloc[split_idx:]
    dates_test = model_df["target_date"].iloc[split_idx:] if "target_date" in model_df.columns else None

    return X_train, X_test, y_train, y_test, dates_test


def build_model() -> XGBRegressor:
    return XGBRegressor(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.04,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_weight=2,
        reg_alpha=0.1,
        reg_lambda=1.0,
        objective="reg:squarederror",
        random_state=42,
        n_jobs=-1,
    )


def evaluate(y_true: pd.Series, y_pred: np.ndarray) -> dict:
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae = float(mean_absolute_error(y_true, y_pred))

    # R2 can be unstable on tiny test sets or nearly constant targets.
    try:
        r2 = float(r2_score(y_true, y_pred))
    except Exception:
        r2 = float("nan")

    return {
        "rows_test": int(len(y_true)),
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
        "target_mean_test": float(np.mean(y_true)),
        "target_std_test": float(np.std(y_true)),
    }


def save_prediction_plot(
    dates,
    y_true: pd.Series,
    y_pred: np.ndarray,
    target_name: str,
    output_path: str,
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed; skipping prediction plot.")
        return

    plt.figure(figsize=(12, 5))

    x_axis = dates if dates is not None else range(len(y_true))
    plt.plot(x_axis, y_true.values, label="True", linewidth=2)
    plt.plot(x_axis, y_pred, label="Predicted", linewidth=2, linestyle="--")

    plt.title(f"{target_name} — prediction vs target")
    plt.xlabel("Date")
    plt.ylabel(target_name)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=160)
    plt.close()


def train_one_target(df: pd.DataFrame, target_col: str, model_stem: str) -> TrainResult:
    print(f"\n───────────────────────────────────────────────────────")
    print(f"Training target: {target_col}")
    print(f"───────────────────────────────────────────────────────")

    X, y, model_df = make_xy(df, target_col)
    X_train, X_test, y_train, y_test, dates_test = temporal_train_test_split(X, y, model_df)

    print(f"Rows total : {len(X)}")
    print(f"Rows train : {len(X_train)}")
    print(f"Rows test  : {len(X_test)}")
    print(f"Features   : {X.shape[1]}")

    model = build_model()
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    metrics = evaluate(y_test, y_pred)

    for key, value in metrics.items():
        print(f"{key}: {value}")

    model_path = os.path.join(MODEL_DIR, f"{model_stem}_xgboost.json")
    metrics_path = os.path.join(MODEL_DIR, f"{model_stem}_metrics.csv")
    importance_path = os.path.join(MODEL_DIR, f"{model_stem}_feature_importance.csv")
    plot_path = os.path.join(PLOT_DIR, f"model_{model_stem}_prediction.png")

    model.save_model(model_path)

    pd.DataFrame([metrics]).to_csv(metrics_path, index=False)

    importance = pd.DataFrame({
        "feature": X.columns,
        "importance": model.feature_importances_,
    }).sort_values("importance", ascending=False)
    importance.to_csv(importance_path, index=False)

    save_prediction_plot(
        dates=dates_test,
        y_true=y_test,
        y_pred=y_pred,
        target_name=target_col,
        output_path=plot_path,
    )

    print(f"Saved model      : {model_path}")
    print(f"Saved metrics    : {metrics_path}")
    print(f"Saved importance : {importance_path}")
    print(f"Saved plot       : {plot_path}")

    return TrainResult(
        target_name=target_col,
        model_path=model_path,
        metrics_path=metrics_path,
        importance_path=importance_path,
        plot_path=plot_path,
        metrics=metrics,
    )


def main() -> None:
    print("Loading supervised dataset...")
    print(f"Dataset: {DATASET_PATH}")

    df = load_dataset(DATASET_PATH)
    print(f"Shape: {df.shape}")

    targets = [
        ("final_flood_score_log", "flood"),
        ("final_drought_score_log", "drought"),
    ]

    results = []
    for target_col, model_stem in targets:
        if target_col not in df.columns:
            print(f"Skipping missing target: {target_col}")
            continue
        results.append(train_one_target(df, target_col, model_stem))

    summary_path = os.path.join(MODEL_DIR, "training_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "target_name": r.target_name,
                    "model_path": r.model_path,
                    "metrics_path": r.metrics_path,
                    "importance_path": r.importance_path,
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
    print(f"Training summary: {summary_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Training failed: {exc}")
        sys.exit(1)
