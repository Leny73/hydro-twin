"""Dataset sufficiency review for HydroTwin ML models."""
import csv
import json
import os
import collections

BASE = '/mnt/c/Users/lyube/Desktop/projects/hydro-twin/data'

# ── 1. File inventory ─────────────────────────────────────────────────────────
print("=" * 68)
print("  FILE INVENTORY")
print("=" * 68)
for root, dirs, files in os.walk(BASE):
    dirs.sort()
    for f in sorted(files):
        p = os.path.join(root, f)
        rel = p.replace(BASE, '')
        size = os.path.getsize(p)
        print(f"  {size:>10,} B  {rel}")

# ── 2. Main dataset stats ─────────────────────────────────────────────────────
ml_path = os.path.join(BASE, 'ml', 'supervised_disaster_dataset.csv')
if os.path.exists(ml_path):
    with open(ml_path, newline='') as f:
        rows = list(csv.DictReader(f))

    print()
    print("=" * 68)
    print("  SUPERVISED DATASET  (supervised_disaster_dataset.csv)")
    print("=" * 68)
    print(f"  Total rows   : {len(rows)}")
    print(f"  Total columns: {len(rows[0]) if rows else 0}")

    # Class distributions
    for target in ['flood_risk_level', 'drought_risk_level']:
        if target in rows[0]:
            counts = collections.Counter(r[target] for r in rows)
            print(f"\n  {target} distribution:")
            labels = {0: 'SAFE', 1: 'LOW_RISK', 2: 'MODERATE_RISK', 3: 'HIGH_RISK', 4: 'VERY_HIGH_RISK'}
            for cls in sorted(counts.keys(), key=lambda x: int(float(x)) if x not in ('', None) else -1):
                pct = counts[cls] / len(rows) * 100
                label = labels.get(int(float(cls)), cls) if cls not in ('', None) else 'N/A'
                bar = '#' * int(pct / 2)
                print(f"    class {cls} ({label:>15}): {counts[cls]:>4}  ({pct:5.1f}%)  {bar}")

    # AOI coverage
    if 'aoi_name' in rows[0]:
        aoi_counts = collections.Counter(r['aoi_name'] for r in rows)
        print(f"\n  Rows per AOI:")
        for aoi, cnt in sorted(aoi_counts.items()):
            print(f"    {aoi:<40} {cnt:>4} rows")

    # Date range
    date_col = next((c for c in ['target_date', 'feature_date', 'end_date'] if c in rows[0]), None)
    if date_col:
        dates = sorted(r[date_col] for r in rows if r[date_col])
        print(f"\n  Date range   : {dates[0]} → {dates[-1]}")
        print(f"  Unique dates : {len(set(dates))}")

    # Null / missing check on key feature columns
    key_cols = [
        'feature_t_minus_1_soil_moisture_pct',
        'feature_t_minus_1_precip_mm_7d',
        'feature_t_minus_1_precip_mm_30d',
        'feature_t_minus_1_ndvi',
        'feature_t_minus_1_flood_extent_km2',
        'feature_t_minus_1_drought_stress_index',
        'feature_t_minus_0_soil_moisture_pct',
        'feature_t_minus_0_precip_mm_7d',
    ]
    print(f"\n  Missing value rates (key features):")
    for col in key_cols:
        if col in rows[0]:
            missing = sum(1 for r in rows if not r[col] or r[col] in ('', 'None', 'nan'))
            pct = missing / len(rows) * 100
            flag = '  ⚠' if pct > 20 else ''
            print(f"    {col:<50} {missing:>4}/{len(rows)}  ({pct:5.1f}%){flag}")

# ── 3. Processed time-series ──────────────────────────────────────────────────
proc_path = os.path.join(BASE, 'processed', 'eo_weather_timeseries.csv')
if os.path.exists(proc_path):
    with open(proc_path, newline='') as f:
        ts_rows = list(csv.DictReader(f))
    print()
    print("=" * 68)
    print("  RAW TIME-SERIES  (eo_weather_timeseries.csv)")
    print("=" * 68)
    print(f"  Total rows   : {len(ts_rows)}")
    if ts_rows:
        if 'aoi_name' in ts_rows[0]:
            aoi_counts = collections.Counter(r['aoi_name'] for r in ts_rows)
            print(f"  Rows per AOI:")
            for aoi, cnt in sorted(aoi_counts.items()):
                print(f"    {aoi:<40} {cnt:>4} rows")
        date_col = next((c for c in ['end_date', 'data_timestamp', 'start_date'] if c in ts_rows[0]), None)
        if date_col:
            dates = sorted(r[date_col] for r in ts_rows if r[date_col])
            print(f"  Date range   : {dates[0]} → {dates[-1]}")
        # Check for real EO vs simulated
        ndvi_vals = [r.get('ndvi') for r in ts_rows if r.get('ndvi') not in ('', 'None', 'nan', None)]
        print(f"  Non-null NDVI: {len(ndvi_vals)} / {len(ts_rows)} rows")
        s1_vals = [r.get('s1_moisture') for r in ts_rows if r.get('s1_moisture') not in ('', 'None', 'nan', None)]
        print(f"  Non-null S1   : {len(s1_vals)} / {len(ts_rows)} rows")
else:
    print("\n  ⚠  eo_weather_timeseries.csv NOT FOUND")

# ── 4. Training summary quick recap ──────────────────────────────────────────
summary_path = os.path.join(BASE, 'models', 'training_summary.json')
if os.path.exists(summary_path):
    with open(summary_path) as f:
        summary = json.load(f)
    print()
    print("=" * 68)
    print("  MODEL TRAINING SUMMARY")
    print("=" * 68)
    for entry in summary:
        m = entry.get('metrics', {})
        print(f"  {entry['model_stem']:<45}  acc={m.get('accuracy', 0):.3f}  bal_acc={m.get('balanced_accuracy', 0):.3f}  rows={m.get('rows_total')}")

print("\nDone.")
