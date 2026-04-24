# HydroTwin — Meteorology Threshold Matrix

> **STATUS: DRAFT — Must be reviewed and completed by the Meteorology Team before go-live.**
> **Owner:** @meteorologist  
> **Last updated:** _[INSERT DATE]_

This file is loaded at runtime by `lambda_handler.py` and injected verbatim into
the AWS Bedrock (Claude 3) prompt. Claude will reason against these thresholds to
determine the alert status for each region.

---

## 1. Alert Status Definitions

| Status | Meaning |
|--------|---------|
| `SAFE` | All metrics within seasonal norms. No action required. |
| `DROUGHT_WATCH` | Conditions trending toward drought. Monitor closely. |
| `DROUGHT_WARNING` | Active drought confirmed. Authorities should prepare response. |
| `FLOOD_WATCH` | Conditions conducive to flooding. Elevated readiness. |
| `FLOOD_WARNING` | Imminent or ongoing flooding. Activate emergency response. |

---

## 2. Flood Thresholds

| Metric | FLOOD_WATCH | FLOOD_WARNING | Notes |
|--------|------------|---------------|-------|
| River level rise (7-day) | > 0.5 m | > 1.0 m | Above seasonal baseline |
| Soil saturation (`soil_moisture_pct`) | > 80 % | > 90 % | Saturated soil accelerates runoff |
| Precipitation — 7 days (`precip_mm_7d`) | > 50 mm | > 100 mm | Cumulative total |
| Precipitation — 30 days (`precip_mm_30d`) | > 120 mm | > 200 mm | Long-term saturation proxy |
| SAR flood extent (`flood_extent_km2`) | > 5 km² | > 20 km² | Open-water pixels from Sentinel-1 |

**Rule:** If ANY two or more FLOOD_WATCH thresholds are simultaneously exceeded,
escalate automatically to `FLOOD_WARNING`.

---

## 3. Drought Thresholds

| Metric | DROUGHT_WATCH | DROUGHT_WARNING | Notes |
|--------|--------------|-----------------|-------|
| SPI-3 index (`drought_index`) | < −1.0 | < −1.5 | Standardised Precipitation Index |
| NDVI departure from baseline | < −0.15 | < −0.25 | Vegetation stress indicator |
| Precipitation — 30 days | < 30 % of climatological avg | < 10 % of climatological avg | |
| Soil moisture | < 20 % | < 10 % | Volumetric % |
| Max temperature (`temp_max_c`) | > 35 °C (sustained 7d) | > 40 °C (sustained 7d) | Heat amplifier |

---

## 4. SAFE Conditions

All of the following must hold:
- No FLOOD_WATCH or FLOOD_WARNING threshold exceeded.
- `drought_index` > −1.0
- `soil_moisture_pct` between 15 % and 80 %
- `precip_mm_7d` within ±50 % of seasonal average

---

## 5. Regional Climatological Baselines

> **TODO (Meteorologist):** Replace the placeholder values below with validated
> climatological normals (WMO 1991–2020 baseline recommended) for each region.

| Region ID | Avg precip 30d (mm) | Avg river level (m) | Notes |
|-----------|--------------------|--------------------|-------|
| `mediterranean-basin` | 35 mm | 2.1 m | Summer dry season Jun–Sep |
| `sahel-region` | 8 mm | 1.4 m | Sahel wet season Jul–Sep only |
| `danube-basin` | 65 mm | 4.0 m | Spring snowmelt peak Mar–May |
| `po-valley` | 70 mm | 3.5 m | Autumn peak Oct–Nov |
| `nile-delta` | 5 mm | 5.2 m | Nile flood season Jul–Sep |

---

## 6. Compound Event Rules

> **TODO (Meteorologist):** Define compound event logic (e.g. drought followed by
> flash flood) and ENSO / NAO teleconnection adjustments.

- **Flash Flood Risk:** `precip_mm_7d` > 80 mm AND `soil_moisture_pct` > 85 %
  → Escalate directly to `FLOOD_WARNING` regardless of river level.
- **Compound Drought-Heat:** `drought_index` < −1.2 AND `temp_max_c` > 38 °C
  → Escalate directly to `DROUGHT_WARNING`.

---

## 7. Pending Tasks

- [ ] Validate thresholds against historical ESA Copernicus event catalogue
- [ ] Add seasonality multipliers (winter vs summer baselines)
- [ ] Integrate ECMWF medium-range forecast confidence intervals
- [ ] Define sub-regional micro-climate zones within each bbox
