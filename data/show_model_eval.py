"""Print confusion matrices, classification reports, and calibration for all three models."""
import csv
import json
import os

BASE = os.path.join(os.path.dirname(__file__), "models")

MODELS = [
    ("Flood Saturation Precursor", "flood_saturation_precursor"),
    ("Flood Detection",            "flood_detection"),
    ("Drought",                    "drought"),
]

RISK_LABELS = {0: "SAFE", 1: "LOW_RISK", 2: "MODERATE_RISK", 3: "HIGH_RISK", 4: "VERY_HIGH_RISK"}


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def read_csv_matrix(path):
    with open(path, newline="") as f:
        return list(csv.reader(f))


with open(os.path.join(BASE, "training_summary.json")) as f:
    summary_list = json.load(f)

# Build lookup by model_stem
summary = {entry["model_stem"]: entry["metrics"] for entry in summary_list}

for name, prefix in MODELS:
    print()
    print("=" * 68)
    print(f"  MODEL: {name}")
    print("=" * 68)

    # ── Confusion matrix ──────────────────────────────────────────────────
    cm = read_csv_matrix(os.path.join(BASE, f"{prefix}_confusion_matrix.csv"))
    print("\nConfusion Matrix  (rows = Actual class, cols = Predicted class)")
    col_w = 15
    for row in cm:
        print("  " + "".join(str(c).rjust(col_w) for c in row))

    # ── Classification report ─────────────────────────────────────────────
    cr = read_csv(os.path.join(BASE, f"{prefix}_classification_report.csv"))
    if cr:
        print("\nClassification Report:")
        headers = list(cr[0].keys())
        print("  " + "".join(h.rjust(15) for h in headers))
        for row in cr:
            print("  " + "".join(str(row[h])[:14].rjust(15) for h in headers))

    # ── Confidence calibration ────────────────────────────────────────────
    cal = read_csv(os.path.join(BASE, f"{prefix}_confidence_calibration.csv"))
    if cal:
        print("\nConfidence Calibration  (mean predicted probability per true class):")
        headers = list(cal[0].keys())
        print("  " + "".join(h.rjust(15) for h in headers))
        for row in cal:
            print("  " + "".join(str(row[h])[:14].rjust(15) for h in headers))

    # ── Training summary ──────────────────────────────────────────────────
    s = summary.get(prefix, {})
    if s:
        print()
        print(f"  Accuracy        : {s.get('accuracy', 'N/A'):.4f}  (baseline: {s.get('baseline_accuracy','N/A'):.4f}  Δ {s.get('accuracy_improvement_vs_baseline',0):+.4f})")
        print(f"  Balanced acc.   : {s.get('balanced_accuracy', 'N/A'):.4f}  (baseline: {s.get('baseline_balanced_accuracy','N/A'):.4f}  Δ {s.get('balanced_accuracy_improvement_vs_baseline',0):+.4f})")
        print(f"  Macro F1        : {s.get('macro_f1', 'N/A'):.4f}  (baseline: {s.get('baseline_macro_f1','N/A'):.4f}  Δ {s.get('macro_f1_improvement_vs_baseline',0):+.4f})")
        print(f"  Weighted F1     : {s.get('weighted_f1', 'N/A'):.4f}")
        print(f"  Ordinal MAE     : {s.get('ordinal_mae', 'N/A'):.4f}  (baseline: {s.get('baseline_ordinal_mae','N/A'):.4f}  Δ {s.get('ordinal_mae_improvement_vs_baseline',0):+.4f})")
        print(f"  Train/Test rows : {s.get('rows_train','N/A')} / {s.get('rows_test','N/A')}  (total {s.get('rows_total','N/A')})")
        print(f"  Features used   : {s.get('features', 'N/A')}")
        cm_map = s.get("class_mapping", {})
        if cm_map:
            print("  Class mapping   : " + "  ".join(f"{v}={RISK_LABELS.get(v,k)}" for k,v in cm_map.items()))

print("\nDone.")
