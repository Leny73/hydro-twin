# 📊 Data Analysts — Task Spec

> **Owner:** Data Analysts team
> **Source:** `README.md` § Data Analysts task list
> **Roadmap:** [`../01-roadmap/01-hackathon-roadmap.md`](../01-roadmap/01-hackathon-roadmap.md)
> **Integration contract:** [`../../data_science/README.md`](../../data_science/README.md)

9 tasks. 3 blockers (🔴), 4 important (🟡), 2 nice-to-have (🟢).

---

## 🔒 Integration contract — DO NOT BREAK

`backend/lambda_handler.py` calls **one** function:

```python
from sentinel_extractor import get_eo_and_weather_data
result = get_eo_and_weather_data(bbox=[lon_min, lat_min, lon_max, lat_max])
```

The return dict **must** contain these 10 keys (units in the docstring):

| Key | Type | Source |
|-----|------|--------|
| `ndvi` | float | Sentinel-2 B4/B8 |
| `soil_moisture_pct` | float | Sentinel-1 SAR backscatter or ESA CCI |
| `precip_mm_7d` | float | OpenMeteo / ERA5 |
| `precip_mm_30d` | float | OpenMeteo / ERA5 |
| `river_level_m` | float | Sentinel-3 SRAL altimetry / in-situ gauge |
| `flood_extent_km2` | float | Sentinel-1 GRD + flood mapping |
| `temp_max_c` | float | OpenMeteo |
| `drought_index` | float | SPI-3 / PDSI from ERA5 |
| `data_timestamp` | str | ISO-8601 UTC |
| `source` | str | Human-readable dataset / DQ note |

**You may add extra keys freely.** The Bedrock prompt forwards everything in the dict, so additional keys help Claude reason. **Never rename or remove keys** — `lambda_handler.py` and the prompt depend on them.

---

## 🔴 Tier 1 — Blockers (Saturday morning)

### DA-1 — Replace dummy `get_eo_and_weather_data()` with real API calls
- **Priority:** 🔴 Blocker
- **File:** `backend/sentinel_extractor.py`
- **What:** The function currently returns a hardcoded dict with fake values (line 83). Replace with real Copernicus + Open-Meteo calls.
- **Acceptance criteria:**
  - [ ] All 10 required keys are still present
  - [ ] `source` field reflects the real datasets used (no `DUMMY` string)
  - [ ] Function works for any of the 5 region bboxes in `frontend/src/App.jsx` `REGIONS[]`
  - [ ] Returns within 10s (Lambda timeout is 30s, leave headroom for Bedrock call)
- **Order of attack (suggested):** Open-Meteo first (free, no auth, validates the pipeline), then Sentinel Hub Statistical API.

### DA-2 — Validate dict-key schema preservation
- **Priority:** 🔴 Blocker
- **File:** `backend/sentinel_extractor.py`
- **What:** Add a runtime assertion (or unit test) that the returned dict contains all 10 required keys before returning. Catches schema drift early.
- **Acceptance criteria:**
  - [ ] An assertion or schema check runs at the end of `get_eo_and_weather_data()`
  - [ ] Raising on missing keys is OK (Lambda will fall back to demo mode); a clear error message is required
- **Suggestion:**
  ```python
  REQUIRED_KEYS = {"ndvi", "soil_moisture_pct", "precip_mm_7d", "precip_mm_30d",
                   "river_level_m", "flood_extent_km2", "temp_max_c",
                   "drought_index", "data_timestamp", "source"}
  missing = REQUIRED_KEYS - result.keys()
  assert not missing, f"Extractor schema violation — missing keys: {missing}"
  ```

### DA-3 — Data-freshness guard (>24h rejection)
- **Priority:** 🔴 Blocker
- **File:** `backend/sentinel_extractor.py`
- **What:** If the observation timestamp is older than 24 hours, either raise an error OR populate `source` with a clear staleness warning so Claude downgrades confidence.
- **Acceptance criteria:**
  - [ ] Timestamp comparison uses UTC (no timezone confusion)
  - [ ] Stale data path is testable (mock `data_timestamp = (now - 48h).isoformat()`)
  - [ ] Behaviour documented in the function docstring

---

## 🟡 Tier 2 — Important (Saturday afternoon → Sunday morning)

### DA-4 — Sentinel-2 NDVI calculation
- **Priority:** 🟡
- **File:** `backend/sentinel_extractor.py`
- **What:** Implement NDVI = (NIR − Red) / (NIR + Red) using Sentinel-2 Bands 8 (NIR) + 4 (Red) for the given bbox. Use Sentinel Hub Process or Statistical API.
- **Acceptance criteria:**
  - [ ] Returns a single float NDVI (mean across the bbox) for the most recent cloud-free image (≤7 days old preferred)
  - [ ] Range checked: −1 to +1
  - [ ] Falls back to last known value (or `None`) if no recent cloud-free image is available
- **Recommended endpoint:** Sentinel Hub Statistical API — returns aggregated stats without downloading rasters

### DA-5 — Sentinel-1 SAR-based flood extent mapping
- **Priority:** 🟡
- **File:** `backend/sentinel_extractor.py`
- **What:** Compute open-water pixel count from VV polarization → convert to km².
- **Acceptance criteria:**
  - [ ] Returns `flood_extent_km2` as a non-negative float
  - [ ] Threshold for "open water" pixels is documented in code comment (typical: VV < −18 dB)
  - [ ] Returns `0.0` when no flooding is detected (not `None`)

### DA-6 — Open-Meteo precipitation totals
- **Priority:** 🟡
- **File:** `backend/sentinel_extractor.py`
- **What:** Pull 7-day and 30-day precipitation totals from Open-Meteo (https://open-meteo.com/, free, no API key).
- **Acceptance criteria:**
  - [ ] `precip_mm_7d` and `precip_mm_30d` populated for the bbox centroid
  - [ ] Source endpoint documented in code comment (likely `/v1/era5` or `/v1/forecast`)
- **Note:** This is the easiest external call — start here on Saturday morning to validate the whole pipeline.

### DA-7 — SPI-3 drought index from ERA5
- **Priority:** 🟡
- **File:** `backend/sentinel_extractor.py`
- **What:** Compute the 3-month Standardized Precipitation Index from ERA5 monthly precipitation, fitting a gamma distribution to the historical record for the bbox centroid.
- **Acceptance criteria:**
  - [ ] Returns `drought_index` as a float (typical range −3 to +3)
  - [ ] Negative values = drier than normal, positive = wetter
  - [ ] Uses at least 30 years of historical ERA5 data for distribution fitting (cache the fitted parameters per region — don't refit every call)

---

## 🟢 Tier 3 — Nice-to-have

### DA-8 — Unit tests with mocked API responses
- **Priority:** 🟢
- **Files:** new `backend/tests/test_sentinel_extractor.py` OR `data_science/notebooks/`
- **What:** pytest tests that mock Open-Meteo + Sentinel Hub responses and assert the dict schema contract.
- **Acceptance criteria:**
  - [ ] At least one test per data source (Open-Meteo, Sentinel-2, Sentinel-1, ERA5)
  - [ ] Schema assertion test (all 10 required keys present)
  - [ ] Stale-data test (`data_timestamp > 24h ago` triggers expected behaviour)

### DA-9 — EDA notebook
- **Priority:** 🟢
- **Files:** `data_science/notebooks/01-historical-events-eda.ipynb`
- **What:** Exploratory analysis of historical flood/drought events per region — informs threshold validation.
- **Acceptance criteria:**
  - [ ] One notebook per region (or one combined notebook with per-region sections)
  - [ ] Plots: precipitation history, NDVI seasonal pattern, known event annotations

---

## 🔍 Verification before handoff

- [ ] Run `python3 -c "from backend.sentinel_extractor import get_eo_and_weather_data; print(get_eo_and_weather_data([8,42,30,52]))"` from repo root
- [ ] All 10 keys printed, no `None` for required floats (use 0.0 if truly zero)
- [ ] `source` field names every dataset used
- [ ] Total response time < 10s
