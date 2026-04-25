# HydroTwin — Bulgaria Adaptation Layer

> **STATUS: EXTENDED — Bulgaria-specific regionalization and threshold adaptation added on top of validated global model.**
> **Region:** Bulgaria
> **Last updated:** 2026-04-25

---

## 1. National Climate Zoning (BBOX Layer)

### 1.1 Danubian Plain (North Bulgaria)
- Continental climate
- Strong spring snowmelt contribution
- Summer drought tendency

**Primary Risks:**
- Flood: Mar–May
- Drought: Jul–Sep

---

### 1.2 Thracian Lowland (South Bulgaria)
- Transitional-continental climate
- High summer temperatures

**Primary Risks:**
- Drought: Jun–Sep (dominant)
- Localized flash floods (convective storms)

---

### 1.3 Black Sea Coast
- Maritime influence
- High-intensity autumn precipitation

**Primary Risks:**
- Flash floods: Sep–Dec (critical)
- Compound coastal flooding (precipitation + storm surge)

---

### 1.4 Mountain Regions (Rila, Pirin, Balkan Range)
- Snow-dominated hydrology
- Rapid runoff response

**Primary Risks:**
- Snowmelt floods: Mar–Jun
- Flash floods: summer convective storms

---

## 2. Flood Thresholds (Bulgaria-Calibrated)

| Metric | FLOOD_WATCH | FLOOD_WARNING | Notes |
|--------|------------|---------------|------|
| Precipitation 7d | > 40 mm | > 80 mm | Lower than EU average due to regional response |
| Precipitation 24h | > 50 mm | > 80 mm | Critical for flash flood triggering |
| Soil moisture | > 75% | > 85% | Slightly reduced threshold |
| River level rise (7d) | > 0.4 m | > 0.8 m | Includes Danube and internal rivers |

---

## 3. Drought Thresholds

| Metric | DROUGHT_WATCH | DROUGHT_WARNING |
|--------|--------------|-----------------|
| SPI-3 | < −1.0 | < −1.5 |
| Soil moisture | < 20% | < 10% |
| Precipitation (30d) | < 30% | < 10% |
| Temperature | > 33°C | > 38°C |

---

## 4. Seasonality Modifiers (Bulgaria)

### Spring (Mar–May)
- Snowmelt + precipitation

**Adjustments:**
- River thresholds × 0.8
- Increased flood sensitivity

---

### Summer (Jun–Aug)
- Drought + convective storms

**Adjustments:**
- Increase drought sensitivity
- Flash flood trigger:
```
precip_24h > 60 mm → FLOOD_WARNING
```

---

### Autumn (Sep–Nov)
- Peak flood season

**Adjustments:**
- Precipitation thresholds × 0.8
- Black Sea coast × 0.7

---

### Winter (Dec–Feb)
- Low precipitation
- Ice processes in rivers

**Add:**
- Ice-jam risk (Danube)

---

## 5. Compound Event Rules (Bulgaria)

### 5.1 Flash Flood
```
IF precip_mm_24h > 70 mm
AND soil_moisture > 80%
→ FLOOD_WARNING
```

---

### 5.2 Drought-to-Flood Transition
```
IF SPI < −1.5 (preceding 2–3 months)
AND precip_24h > 60 mm
→ FLASH_FLOOD_PARADOX
```

---

### 5.3 Compound Drought-Heat
```
IF SPI < −1.2
AND temp > 37°C (≥5 days)
→ DROUGHT_WARNING
```

---

## 6. Micro-Climate Adjustments

### Mountain Zones
- Reduced reliance on soil moisture
```
precip_24h > 50 mm → FLOOD_WATCH
```

---

### Black Sea Coast
- Highest flood risk zone

**Adjustments:**
- Precipitation thresholds −20%
- Add storm surge interaction

---

### Dobruja Region
- High drought susceptibility

**Adjustment:**
- DROUGHT_WATCH at SPI < −0.8

---

### Danube System
- Strong upstream control

**Weighting:**
- River level: 70%
- Local precipitation: 30%

---

## 7. Data Sources (Operational)

### Satellite
- Copernicus EDO/GDO
- Sentinel-1 SAR
- fAPAR anomaly (preferred over NDVI)

### Models
- ECMWF (ENS)
- ERA5 reanalysis

### National
- NIMH (precipitation, river gauges)
- Basin Directorates

---

## 8. Confidence Rules (Simplified)

| Condition | Action |
|----------|--------|
| < 3 stations | LOW_CONFIDENCE |
| Missing SAR | Ignore flood_extent |
| Conflicting indicators | Downgrade alert |

---

## 9. Minimal Operational Algorithm

```
1. Apply seasonality multiplier
2. Apply regional modifier
3. Evaluate thresholds
4. Evaluate compound rules
5. Apply confidence modifiers
6. Output alert
```

---

## 10. Key Insights for Bulgaria

- Primary hazard: Flash floods (summer + autumn)
- Critical mechanism: Drought-to-flood transition
- Key metric: 24h precipitation + soil moisture
- Danube system: controlled by upstream hydrology

---

### 11 Synoptic Weather Patterns & Cyclone Integration

**Objective:** Incorporate large-scale synoptic drivers (Mediterranean cyclones, cut-off lows, blocking patterns) into flood and compound event triggering.

#### A) Mediterranean Cyclone Trigger (Vb-like tracks)
```
IF MSLP_min < 1005 hPa
AND cyclone_track intersects (Aegean → Black Sea → Danube corridor)
AND precip_forecast_72h > 60 mm
→ PRE-FLOOD_WATCH
```

**Enhancements:**
- Increase weight for Danube basin and Black Sea coast
- Apply +20% sensitivity if soil_moisture > 70%

---

#### B) Cut-off Low (Cold Core) Detection
```
IF 500hPa geopotential anomaly < −2σ
AND system is quasi-stationary (>48h)
AND convective_available_potential_energy (CAPE) > 800 J/kg 
→ FLASH_FLOOD_RISK_HIGH
```

**Notes:**
- Critical for South Bulgaria and mountain regions
- Strong linkage to localized extreme precipitation

---

#### C) Atmospheric River / Moisture Transport Proxy
```
IF IVT (Integrated Vapor Transport) > 250 kg m−1 s−1
AND low-level jet present (850 hPa wind > 12 m/s)
→ ENHANCED_PRECIP_EFFICIENCY
```

**Effect:**
- Reduce precipitation thresholds by 10–20%

---

#### D) Blocking & Heat Dome (Drought Reinforcement)
```
IF 500hPa ridge persists > 5 days
AND temperature anomaly > +5°C
→ DROUGHT_INTENSIFICATION
```

**Effect:**
- Accelerate soil moisture depletion
- Lower SPI thresholds by ~0.2

---

#### E) Frontal System Acceleration (Rapid Cyclogenesis)
```
IF d(MSLP)/dt < −5 hPa / 24h
AND frontal passage expected
→ EXTREME_EVENT_POTENTIAL
```

**Effect:**
- Trigger early WATCH level (T+3–5 days)

---

#### F) Composite Synoptic Risk Score

Define a synoptic index:
```
SYNOPTIC_SCORE = w1*cyclone + w2*cutoff + w3*IVT + w4*blocking + w5*cyclogenesis
```

**Operational Use:**
- If SYNOPTIC_SCORE > 0.7 → allow early escalation of alerts
- If > 0.85 → override local thresholds (extreme mode)

---

#### G) Data Inputs

- ECMWF (ENS/IFS): MSLP, geopotential (500 hPa), IVT
- ERA5: anomaly baselines
- Satellite: cloud top temperature (for convective systems)

---

#### H) Integration into Pipeline

```
1. Detect synoptic pattern
2. Compute SYNOPTIC_SCORE
3. Modify thresholds dynamically
4. Pass to main hazard engine
```

---

**Key Insight:**
In Bulgaria, the most destructive flood events are rarely purely local — they are strongly linked to Mediterranean cyclones and slow-moving upper-level systems. Integrating synoptic dynamics significantly increases early warning skill (lead time +2–4 days).

