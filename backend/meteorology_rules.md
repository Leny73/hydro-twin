# HydroTwin — Meteorology Threshold Matrix
# Bulgaria / Pleven Oblast Edition

> **STATUS: ACTIVE — Bulgaria-calibrated thresholds merged from adaptation layer.**
> **Owner:** @meteorologist  
> **Last updated:** 2026-04-25
> **Region:** Pleven Oblast, Bulgaria (Danubian Plain)

This file is loaded at runtime by `lambda_handler.py` and injected verbatim into
the AWS Bedrock (Claude 3) prompt. Claude will reason against these thresholds to
determine the alert status for each region.

**Available sensor fields:** `ndvi`, `ndwi`, `soil_moisture_pct`, `soil_moisture_7d_delta`,
`precip_mm_7d`, `precip_mm_30d`, `forecast_precip_24h_mm`, `temp_max_c`,
`flood_extent_km2`, `river_level_m` (None — not yet integrated),
`drought_index` (None — not yet integrated)

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

## 2. Flood Thresholds (Bulgaria-Calibrated)

> Thresholds are lower than EU average — Bulgarian soils respond faster to precipitation.

| Metric | FLOOD_WATCH | FLOOD_WARNING | Notes |
|--------|------------|---------------|-------|
| Precipitation 7d (`precip_mm_7d`) | > 40 mm | > 80 mm | Lower than EU average due to fast regional response |
| Precipitation 24h (`forecast_precip_24h_mm`) | > 50 mm | > 80 mm | Critical flash flood trigger |
| Soil moisture (`soil_moisture_pct`) | > 75 % | > 85 % | Slightly reduced from global threshold |
| River level rise 7d (`river_level_m`) | > 0.4 m | > 0.8 m | Danube + internal rivers (Vit, Osam, Iskur) |
| NDWI (`ndwi`) | > 0.1 | > 0.25 | Open water proxy from Sentinel-2 |
| SAR flood extent (`flood_extent_km2`) | > 5 km² | > 20 km² | Open-water extent estimate |

**Escalation rule:** If ANY two or more FLOOD_WATCH thresholds are simultaneously
exceeded → escalate automatically to `FLOOD_WARNING`.

---

## 3. Drought Thresholds (Bulgaria-Calibrated)

| Metric | DROUGHT_WATCH | DROUGHT_WARNING | Notes |
|--------|--------------|-----------------|-------|
| SPI-3 (`drought_index`) | < −1.0 | < −1.5 | Standardised Precipitation Index |
| NDVI | < 0.25 (Apr–Sep) | < 0.15 | Vegetation stress — compare to seasonal norm |
| Soil moisture (`soil_moisture_pct`) | < 20 % | < 10 % | Volumetric % |
| Precipitation 30d (`precip_mm_30d`) | < 30 % of avg | < 10 % of avg | Pleven avg: ~45 mm/30d |
| Max temperature (`temp_max_c`) | > 33 °C sustained 7d | > 38 °C sustained 7d | Heat amplifier |

---

## 4. SAFE Conditions

All of the following must hold:
- No FLOOD_WATCH or FLOOD_WARNING threshold exceeded
- `drought_index` > −1.0 (or null — ignore if not available)
- `soil_moisture_pct` between 15 % and 75 %
- `precip_mm_7d` within ±50 % of seasonal average
- `ndvi` > 0.25 during growing season (Apr–Sep)

---

## 5. Regional Climatological Baseline — Pleven Oblast

| Metric | Value | Source | Notes |
|--------|-------|--------|-------|
| Avg precip 30d | ~45 mm | ERA5 1991–2020 | Spring peak Apr–May |
| Avg precip 7d | ~11 mm | ERA5 1991–2020 | |
| Avg NDVI (Apr) | ~0.45–0.55 | Sentinel-2 historical | Active vegetation growth |
| Avg NDVI (Jul) | ~0.55–0.65 | Sentinel-2 historical | Peak season |
| Avg soil moisture | ~30 % | ERA5 | Spring higher, summer lower |
| Primary flood season | Mar–May | NIMH | Snowmelt + spring rain |
| Secondary flood season | Sep–Nov | NIMH | Convective storms |
| Drought season | Jun–Sep | NIMH | Continental summer |

---

## 6. Seasonality Modifiers

### Spring (Mar–May) — Snowmelt + Precipitation
- River thresholds × 0.8 (higher background flow)
- Increased flood sensitivity
- NDVI rising rapidly — low values not drought signal yet

### Summer (Jun–Aug) — Drought + Convective Storms
- Increase drought sensitivity
- Flash flood trigger: `forecast_precip_24h_mm` > 60 mm → `FLOOD_WARNING`
- NDVI above 0.4 expected — below = drought stress signal

### Autumn (Sep–Nov) — Peak Flood Season
- Precipitation thresholds × 0.8
- Soil already partially saturated from summer storms
- Highest compound flood risk window

### Winter (Dec–Feb) — Low Precipitation / Ice
- Low base precipitation
- Ice-jam risk on Danube (elevates effective river level)
- NDVI naturally low — not a drought signal

---

## 7. Compound Event Rules

### 7.1 Flash Flood
```
IF forecast_precip_24h_mm > 70 mm
AND soil_moisture_pct > 80 %
→ FLOOD_WARNING (regardless of river level)
```

### 7.2 Drought-to-Flood Transition (most dangerous pattern in Bulgaria)
```
IF drought_index < −1.5 (preceding 2–3 months)
AND forecast_precip_24h_mm > 60 mm
→ FLOOD_WARNING — hardened soil cannot absorb water
```

### 7.3 Compound Drought-Heat
```
IF drought_index < −1.2
AND temp_max_c > 37 °C (≥ 5 days)
→ DROUGHT_WARNING
```

### 7.4 Soil Saturation Surge
```
IF soil_moisture_7d_delta > +20 %
AND precip_mm_7d > 35 mm
→ FLOOD_WATCH — rapid saturation trajectory
```

---

## 8. Confidence Rules

| Condition | Action |
|-----------|--------|
| `river_level_m` is None | Downgrade flood confidence — note data gap |
| `drought_index` is None | Rely on NDVI + soil moisture for drought signal |
| `ndwi` is None or NaN | Ignore flood extent estimate |
| Conflicting indicators (e.g. high precip + low soil moisture) | Downgrade alert, flag anomaly |

---

## 9. Assessment Algorithm (Claude should follow this order)

```
1. Determine current season from data_timestamp
2. Apply seasonality modifier to thresholds
3. Check compound event rules first (highest priority)
4. Evaluate flood thresholds — count how many are exceeded
5. Evaluate drought thresholds
6. Apply confidence modifiers based on data gaps
7. Output: status, confidence (0–1), reasoning
```

---

## 10. Key Insights for Pleven Oblast

- **Primary hazard:** Flash floods (summer convective) + spring snowmelt
- **Most dangerous pattern:** Drought-to-flood transition (hardened soil + sudden rain)
- **Key metrics:** `forecast_precip_24h_mm` + `soil_moisture_pct` (best predictors)
- **Danube influence:** Upstream hydrology controls Nikopol area — `river_level_m` critical when available
- **NDVI context:** April value ~0.45–0.55 is normal. Below 0.25 = drought stress. Above 0.65 = good season.

---

<!-- ============================================================
## 11. Synoptic Weather Patterns & Cyclone Integration
     STATUS: COMMENTED OUT — data fields not yet in pipeline
     TODO: Activate once ECMWF forecast fields are added to
           sentinel_extractor.py (MSLP, 500hPa geopotential, IVT, CAPE)

### A) Mediterranean Cyclone Trigger (Vb-like tracks)
IF MSLP_min < 1005 hPa
AND cyclone_track intersects (Aegean → Black Sea → Danube corridor)
AND precip_forecast_72h > 60 mm
→ PRE-FLOOD_WATCH
Enhancement: +20% sensitivity if soil_moisture > 70%

### B) Cut-off Low (Cold Core) Detection
IF 500hPa geopotential anomaly < −2σ
AND system is quasi-stationary (>48h)
AND CAPE > 800 J/kg
→ FLASH_FLOOD_RISK_HIGH (critical for South Bulgaria + mountains)

### C) Atmospheric River / Moisture Transport Proxy
IF IVT > 250 kg m−1 s−1
AND low-level jet present (850 hPa wind > 12 m/s)
→ ENHANCED_PRECIP_EFFICIENCY — reduce precip thresholds 10–20%

### D) Blocking & Heat Dome (Drought Reinforcement)
IF 500hPa ridge persists > 5 days
AND temperature anomaly > +5°C
→ DROUGHT_INTENSIFICATION — lower SPI thresholds by ~0.2

### E) Frontal System Rapid Cyclogenesis
IF d(MSLP)/dt < −5 hPa / 24h
AND frontal passage expected
→ EXTREME_EVENT_POTENTIAL — trigger early WATCH (T+3–5 days)

### F) Composite Synoptic Risk Score
SYNOPTIC_SCORE = w1*cyclone + w2*cutoff + w3*IVT + w4*blocking + w5*cyclogenesis
If SYNOPTIC_SCORE > 0.7 → early escalation
If SYNOPTIC_SCORE > 0.85 → override local thresholds (extreme mode)

Key insight: Bulgarian destructive floods are strongly linked to Mediterranean
cyclones and slow-moving upper-level systems. Synoptic integration adds +2–4
days lead time.
============================================================ -->

---

## 12. Pending Tasks

- [ ] Validate thresholds against NIMH historical event catalogue (2000–2025)
- [ ] Add Pleven WMO 1991–2020 precipitation normals (monthly resolution)
- [ ] Integrate `river_level_m` via Copernicus GloFAS API
- [ ] Integrate `drought_index` (SPI-3) via ERA5 reanalysis baseline
- [ ] Activate Section 11 (synoptic) once ECMWF fields added to pipeline

