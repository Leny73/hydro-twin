"""
classify_scenarios.py — Run hand-crafted test scenarios through all 3 XGBoost models.
Prints the predicted class and confidence for each scenario.
"""
import csv
import json
import os
import sys

import numpy as np
import pandas as pd
from xgboost import XGBClassifier

BASE = '/mnt/c/Users/lyube/Desktop/projects/hydro-twin/data/models'

RISK_LABELS = {0: "SAFE", 1: "LOW_RISK", 2: "MODERATE_RISK", 3: "HIGH_RISK", 4: "VERY_HIGH_RISK"}

# ── Load models and extract actual feature names from the booster ────────────
def load(stem):
    m = XGBClassifier()
    m.load_model(os.path.join(BASE, f'{stem}_xgboost.json'))
    return m

flood_precursor_model  = load('flood_saturation_precursor')
flood_detection_model  = load('flood_detection')
drought_model          = load('drought_risk')

# Use the feature names the model was actually trained on (from the booster)
FLOOD_PRECURSOR_COLS = flood_precursor_model.get_booster().feature_names
FLOOD_DETECTION_COLS = flood_detection_model.get_booster().feature_names
DROUGHT_COLS         = drought_model.get_booster().feature_names

print(f"Flood Precursor features ({len(FLOOD_PRECURSOR_COLS)}): {FLOOD_PRECURSOR_COLS}")
print(f"Flood Detection features ({len(FLOOD_DETECTION_COLS)}): {FLOOD_DETECTION_COLS}")
print(f"Drought features         ({len(DROUGHT_COLS)}): {DROUGHT_COLS}")

# ── Print top feature importances ─────────────────────────────────────────────
def top_features(stem, n=8):
    rows = list(csv.DictReader(open(os.path.join(BASE, f'{stem}_feature_importance.csv'))))
    rows.sort(key=lambda r: float(r['importance']), reverse=True)
    return [(r['feature'], float(r['importance'])) for r in rows[:n]]

print("=" * 72)
print("  TOP FEATURE IMPORTANCES")
print("=" * 72)
for stem, label in [
    ('flood_saturation_precursor', 'Flood Precursor'),
    ('flood_detection',            'Flood Detection'),
    ('drought',                    'Drought'),
]:
    print(f"\n  {label}:")
    for feat, imp in top_features(stem):
        short = feat.replace('feature_t_minus_1_', 't-1:').replace('feature_t_minus_0_', 't-0:')
        print(f"    {imp:.4f}  {short}")

# ── Predict helper ────────────────────────────────────────────────────────────
def predict(model, feature_cols, values: dict):
    # feature_cols already have the lag prefix (e.g. feature_t_minus_1_soil_moisture_pct)
    # Strip the lag prefix to find the raw key, then map back
    row = {}
    for col in feature_cols:
        # Remove known prefixes to get raw feature name
        raw = col
        for prefix in ('feature_t_minus_1_', 'feature_t_minus_0_'):
            if col.startswith(prefix):
                raw = col[len(prefix):]
                break
        row[col] = values.get(raw, np.nan)
    X = pd.DataFrame([row])[feature_cols]
    pred = int(model.predict(X)[0])
    proba = model.predict_proba(X)[0]
    return pred, float(max(proba)), list(proba)

# ── Test scenarios ────────────────────────────────────────────────────────────
# Each scenario is a flat dict of raw feature names (without the lag prefix).
# We test the same snapshot against all 3 models.

SCENARIOS = [
    {
        "name": "Dry Bulgarian summer — no rain, high heat",
        "expected_flood": "SAFE",
        "expected_drought": "MODERATE_RISK or higher",
        "features": dict(
            # EO
            ndvi=0.25, ndwi=-0.15, s1_moisture=0.22, flood_extent_km2=0.0,
            # precip — very low
            precip_mm_24h=0.0, precip_mm_48h=0.0, precip_mm_72h=0.0,
            precip_mm_7d=1.0, precip_mm_30d=8.0,
            forecast_precip_24h_mm=0.0, forecast_precip_48h_mm=0.0, forecast_precip_72h_mm=0.0,
            precip_intensity_max_1h_mm=0.0,
            # soil
            soil_moisture_pct=12.0, soil_moisture_7d_delta=-8.0,
            # weather
            temp_max_c=38.5, temp_min_c=22.0, temp_mean_c=30.0,
            relative_humidity_mean_pct=28.0, dew_point_max_c=10.0, dewpoint_depression_min_c=20.0,
            pressure_mean_hpa=1016.0, pressure_min_hpa=1014.0,
            pressure_drop_24h_hpa=0.2, pressure_drop_48h_hpa=0.4,
            wind_speed_max_ms=3.0, wind_gust_max_ms=5.0,
            cloud_cover_mean_pct=5.0, uvi_max=9.5,
            snow_mm_24h=0.0, snow_mm_48h=0.0, snowmelt_proxy=0.0,
            # synoptic
            heavy_rain_hours_24h=0, heavy_rain_hours_48h=0, thunderstorm_hours_48h=0,
            convective_proxy=0.0, ivt_proxy=0.05,
            mediterranean_cyclone_proxy=0.0, cutoff_low_proxy=0.0,
            cyclogenesis_proxy=0.0, blocking_heat_proxy=0.85, synoptic_flood_score=0.01,
            # compound
            flash_flood_trigger=0, soil_saturation_surge=0,
            drought_to_flood_transition=0, compound_drought_heat=1,
            compound_flood_after_dry_spell=0,
            # derived
            drought_stress_index=0.72, drought_index=None,
            precip_7d_ratio_to_pleven_avg=0.09, precip_30d_ratio_to_pleven_avg=0.18,
            soil_moisture_ratio_to_pleven_avg=0.40, ndvi_seasonal_anomaly_proxy=-0.35,
            # threshold counts
            flood_watch_threshold_count=0, flood_warning_threshold_count=0,
            drought_watch_threshold_count=3, drought_warning_threshold_count=2,
            alert_confidence=0.70,
            # time
            is_spring=0, is_summer=1, is_autumn=0, is_winter=0,
            month=7, week_of_year=28, day_of_year=196,
        ),
    },
    {
        "name": "Spring Danube saturation — heavy rain on wet soil",
        "expected_flood": "LOW_RISK or MODERATE_RISK",
        "expected_drought": "SAFE",
        "features": dict(
            ndvi=0.52, ndwi=0.12, s1_moisture=0.72, flood_extent_km2=8.5,
            precip_mm_24h=22.0, precip_mm_48h=38.0, precip_mm_72h=55.0,
            precip_mm_7d=68.0, precip_mm_30d=95.0,
            forecast_precip_24h_mm=25.0, forecast_precip_48h_mm=42.0, forecast_precip_72h_mm=60.0,
            precip_intensity_max_1h_mm=12.0,
            soil_moisture_pct=82.0, soil_moisture_7d_delta=18.0,
            temp_max_c=14.0, temp_min_c=6.0, temp_mean_c=10.0,
            relative_humidity_mean_pct=88.0, dew_point_max_c=11.0, dewpoint_depression_min_c=2.0,
            pressure_mean_hpa=1002.0, pressure_min_hpa=998.0,
            pressure_drop_24h_hpa=4.5, pressure_drop_48h_hpa=7.2,
            wind_speed_max_ms=9.0, wind_gust_max_ms=14.0,
            cloud_cover_mean_pct=92.0, uvi_max=2.1,
            snow_mm_24h=0.0, snow_mm_48h=0.0, snowmelt_proxy=0.08,
            heavy_rain_hours_24h=3, heavy_rain_hours_48h=7, thunderstorm_hours_48h=0,
            convective_proxy=0.18, ivt_proxy=0.55,
            mediterranean_cyclone_proxy=0.52, cutoff_low_proxy=0.30,
            cyclogenesis_proxy=0.48, blocking_heat_proxy=0.0, synoptic_flood_score=0.42,
            flash_flood_trigger=0, soil_saturation_surge=1,
            drought_to_flood_transition=0, compound_drought_heat=0,
            compound_flood_after_dry_spell=0,
            drought_stress_index=0.08, drought_index=None,
            precip_7d_ratio_to_pleven_avg=6.18, precip_30d_ratio_to_pleven_avg=2.11,
            soil_moisture_ratio_to_pleven_avg=2.73, ndvi_seasonal_anomaly_proxy=0.02,
            flood_watch_threshold_count=3, flood_warning_threshold_count=1,
            drought_watch_threshold_count=0, drought_warning_threshold_count=0,
            alert_confidence=0.75,
            is_spring=1, is_summer=0, is_autumn=0, is_winter=0,
            month=4, week_of_year=16, day_of_year=110,
        ),
    },
    {
        "name": "Extreme flash flood scenario — saturated soil + intense convection",
        "expected_flood": "HIGH_RISK or VERY_HIGH_RISK",
        "expected_drought": "SAFE",
        "features": dict(
            ndvi=0.48, ndwi=0.32, s1_moisture=0.91, flood_extent_km2=28.0,
            precip_mm_24h=55.0, precip_mm_48h=88.0, precip_mm_72h=110.0,
            precip_mm_7d=145.0, precip_mm_30d=180.0,
            forecast_precip_24h_mm=65.0, forecast_precip_48h_mm=95.0, forecast_precip_72h_mm=120.0,
            precip_intensity_max_1h_mm=32.0,
            soil_moisture_pct=92.0, soil_moisture_7d_delta=28.0,
            temp_max_c=19.0, temp_min_c=11.0, temp_mean_c=15.0,
            relative_humidity_mean_pct=94.0, dew_point_max_c=17.0, dewpoint_depression_min_c=1.0,
            pressure_mean_hpa=996.0, pressure_min_hpa=990.0,
            pressure_drop_24h_hpa=8.0, pressure_drop_48h_hpa=12.0,
            wind_speed_max_ms=16.0, wind_gust_max_ms=24.0,
            cloud_cover_mean_pct=98.0, uvi_max=1.2,
            snow_mm_24h=0.0, snow_mm_48h=0.0, snowmelt_proxy=0.0,
            heavy_rain_hours_24h=9, heavy_rain_hours_48h=15, thunderstorm_hours_48h=6,
            convective_proxy=0.88, ivt_proxy=0.82,
            mediterranean_cyclone_proxy=0.78, cutoff_low_proxy=0.71,
            cyclogenesis_proxy=0.85, blocking_heat_proxy=0.0, synoptic_flood_score=0.90,
            flash_flood_trigger=1, soil_saturation_surge=1,
            drought_to_flood_transition=0, compound_drought_heat=0,
            compound_flood_after_dry_spell=0,
            drought_stress_index=0.02, drought_index=None,
            precip_7d_ratio_to_pleven_avg=13.2, precip_30d_ratio_to_pleven_avg=4.0,
            soil_moisture_ratio_to_pleven_avg=3.07, ndvi_seasonal_anomaly_proxy=0.0,
            flood_watch_threshold_count=5, flood_warning_threshold_count=4,
            drought_watch_threshold_count=0, drought_warning_threshold_count=0,
            alert_confidence=0.90,
            is_spring=1, is_summer=0, is_autumn=0, is_winter=0,
            month=5, week_of_year=20, day_of_year=135,
        ),
    },
    {
        "name": "Normal autumn — moderate rain, average conditions",
        "expected_flood": "SAFE",
        "expected_drought": "SAFE",
        "features": dict(
            ndvi=0.42, ndwi=-0.05, s1_moisture=0.38, flood_extent_km2=0.0,
            precip_mm_24h=4.0, precip_mm_48h=7.0, precip_mm_72h=10.0,
            precip_mm_7d=18.0, precip_mm_30d=48.0,
            forecast_precip_24h_mm=5.0, forecast_precip_48h_mm=8.0, forecast_precip_72h_mm=12.0,
            precip_intensity_max_1h_mm=2.5,
            soil_moisture_pct=35.0, soil_moisture_7d_delta=3.0,
            temp_max_c=18.0, temp_min_c=8.0, temp_mean_c=13.0,
            relative_humidity_mean_pct=68.0, dew_point_max_c=11.0, dewpoint_depression_min_c=7.0,
            pressure_mean_hpa=1012.0, pressure_min_hpa=1008.0,
            pressure_drop_24h_hpa=1.0, pressure_drop_48h_hpa=2.0,
            wind_speed_max_ms=5.5, wind_gust_max_ms=9.0,
            cloud_cover_mean_pct=55.0, uvi_max=3.2,
            snow_mm_24h=0.0, snow_mm_48h=0.0, snowmelt_proxy=0.0,
            heavy_rain_hours_24h=0, heavy_rain_hours_48h=1, thunderstorm_hours_48h=0,
            convective_proxy=0.05, ivt_proxy=0.22,
            mediterranean_cyclone_proxy=0.12, cutoff_low_proxy=0.08,
            cyclogenesis_proxy=0.14, blocking_heat_proxy=0.0, synoptic_flood_score=0.10,
            flash_flood_trigger=0, soil_saturation_surge=0,
            drought_to_flood_transition=0, compound_drought_heat=0,
            compound_flood_after_dry_spell=0,
            drought_stress_index=0.28, drought_index=None,
            precip_7d_ratio_to_pleven_avg=1.64, precip_30d_ratio_to_pleven_avg=1.07,
            soil_moisture_ratio_to_pleven_avg=1.17, ndvi_seasonal_anomaly_proxy=-0.08,
            flood_watch_threshold_count=0, flood_warning_threshold_count=0,
            drought_watch_threshold_count=0, drought_warning_threshold_count=0,
            alert_confidence=0.80,
            is_spring=0, is_summer=0, is_autumn=1, is_winter=0,
            month=10, week_of_year=41, day_of_year=285,
        ),
    },
    {
        "name": "Drought-to-flood transition — parched soil, sudden downpour",
        "expected_flood": "MODERATE_RISK or higher (runoff on hardened soil)",
        "expected_drought": "LOW_RISK (was in drought)",
        "features": dict(
            ndvi=0.20, ndwi=-0.08, s1_moisture=0.19, flood_extent_km2=2.0,
            precip_mm_24h=62.0, precip_mm_48h=70.0, precip_mm_72h=72.0,
            precip_mm_7d=65.0, precip_mm_30d=12.0,
            forecast_precip_24h_mm=68.0, forecast_precip_48h_mm=72.0, forecast_precip_72h_mm=75.0,
            precip_intensity_max_1h_mm=18.0,
            soil_moisture_pct=11.0, soil_moisture_7d_delta=9.0,
            temp_max_c=32.0, temp_min_c=18.0, temp_mean_c=25.0,
            relative_humidity_mean_pct=52.0, dew_point_max_c=20.0, dewpoint_depression_min_c=5.0,
            pressure_mean_hpa=1003.0, pressure_min_hpa=999.0,
            pressure_drop_24h_hpa=5.0, pressure_drop_48h_hpa=6.5,
            wind_speed_max_ms=11.0, wind_gust_max_ms=18.0,
            cloud_cover_mean_pct=75.0, uvi_max=5.8,
            snow_mm_24h=0.0, snow_mm_48h=0.0, snowmelt_proxy=0.0,
            heavy_rain_hours_24h=5, heavy_rain_hours_48h=6, thunderstorm_hours_48h=3,
            convective_proxy=0.62, ivt_proxy=0.48,
            mediterranean_cyclone_proxy=0.38, cutoff_low_proxy=0.55,
            cyclogenesis_proxy=0.60, blocking_heat_proxy=0.10, synoptic_flood_score=0.48,
            flash_flood_trigger=1, soil_saturation_surge=0,
            drought_to_flood_transition=1, compound_drought_heat=0,
            compound_flood_after_dry_spell=1,
            drought_stress_index=0.65, drought_index=None,
            precip_7d_ratio_to_pleven_avg=5.91, precip_30d_ratio_to_pleven_avg=0.27,
            soil_moisture_ratio_to_pleven_avg=0.37, ndvi_seasonal_anomaly_proxy=-0.40,
            flood_watch_threshold_count=2, flood_warning_threshold_count=2,
            drought_watch_threshold_count=2, drought_warning_threshold_count=0,
            alert_confidence=0.65,
            is_spring=0, is_summer=1, is_autumn=0, is_winter=0,
            month=8, week_of_year=32, day_of_year=220,
        ),
    },
]

# ── Run predictions ───────────────────────────────────────────────────────────
print("\n" + "=" * 72)
print("  SCENARIO CLASSIFICATION RESULTS")
print("=" * 72)

for sc in SCENARIOS:
    name = sc["name"]
    feats = sc["features"]

    fp_pred, fp_conf, fp_proba = predict(flood_precursor_model, FLOOD_PRECURSOR_COLS, feats)
    fd_pred, fd_conf, fd_proba = predict(flood_detection_model, FLOOD_DETECTION_COLS, feats)
    dr_pred, dr_conf, dr_proba = predict(drought_model,         DROUGHT_COLS,         feats)

    print(f"\n  Scenario: {name}")
    print(f"  Expected flood  : {sc['expected_flood']}")
    print(f"  Expected drought: {sc['expected_drought']}")
    print()

    def fmt_proba(proba, pred):
        parts = []
        for i, p in enumerate(proba):
            label = RISK_LABELS.get(i, str(i))
            marker = " <-- predicted" if i == pred else ""
            parts.append(f"    {label:<16}: {p:.3f}{marker}")
        return "\n".join(parts)

    print(f"  [Flood Precursor]  pred={RISK_LABELS[fp_pred]}  conf={fp_conf:.3f}")
    print(fmt_proba(fp_proba, fp_pred))
    print(f"  [Flood Detection]  pred={RISK_LABELS[fd_pred]}  conf={fd_conf:.3f}")
    print(fmt_proba(fd_proba, fd_pred))
    print(f"  [Drought Model]    pred={RISK_LABELS[dr_pred]}  conf={dr_conf:.3f}")
    print(fmt_proba(dr_proba, dr_pred))

    # Quick pass/fail
    flood_label_used = RISK_LABELS[fd_pred] or RISK_LABELS[fp_pred]
    drought_label_used = RISK_LABELS[dr_pred]
    print(f"\n  --> Flood signal  : {flood_label_used} | Drought signal: {drought_label_used}")
    print("  " + "-" * 68)

print("\nDone.")
