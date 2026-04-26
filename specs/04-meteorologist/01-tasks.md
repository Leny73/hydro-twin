# 🌦️ Meteorologist — Task Spec

> **Owner:** Meteorology team
> **Source:** `README.md` § Meteorologist task list
> **Source-of-truth file:** [`../../backend/meteorology_rules.md`](../../backend/meteorology_rules.md)

8 tasks. 3 blockers (🔴), 3 important (🟡), 2 nice-to-have (🟢).

---

## 📜 Why this matters

`backend/meteorology_rules.md` is **loaded at runtime** by the Lambda and **injected verbatim** into the AWS Bedrock (Claude 3) prompt as authoritative context. Claude reasons against these thresholds to determine each region's alert status. The Markdown structure (sections 1–7, threshold tables) is the contract — preserve it.

**Renaming a threshold or restructuring a table changes how Claude assesses risk.** Treat this as production code.

---

## 🔴 Tier 1 — Blockers (Saturday afternoon)

### MET-1 — Validate flood + drought thresholds (Sections 2 & 3)
- **Priority:** 🔴 Blocker
- **File:** `backend/meteorology_rules.md` Sections 2 & 3
- **What:** Review every threshold value and confirm against peer-reviewed literature or WMO standards. Adjust as needed.
- **Acceptance criteria:**
  - [ ] Each threshold in Section 2 (Flood) has a citation or expert-judgement note added in the "Notes" column
  - [ ] Each threshold in Section 3 (Drought) has the same
  - [ ] If any threshold is region-dependent, mark it explicitly (handled in detail by MET-5)
- **Current values to review:**
  - Flood: River level rise (>0.5m/>1.0m), soil saturation (>80%/>90%), 7d precip (>50mm/>100mm), 30d precip (>120mm/>200mm), SAR flood extent (>5km²/>20km²)
  - Drought: SPI-3 (<−1.0/<−1.5), NDVI departure (<−0.15/<−0.25), 30d precip (<30%/<10% of climatological avg), soil moisture (<20%/<10%), max temp (>35°C/>40°C sustained 7d)

### MET-2 — Fill **Regional Climatological Baselines** (Section 5)
- **Priority:** 🔴 Blocker
- **File:** `backend/meteorology_rules.md` Section 5
- **What:** Replace the placeholder values in the "Regional Climatological Baselines" table with validated WMO 1991–2020 normals for all 5 regions.
- **Acceptance criteria:**
  - [ ] Each of the 5 regions (`mediterranean-basin`, `sahel-region`, `danube-basin`, `po-valley`, `nile-delta`) has real values for `Avg precip 30d (mm)` and `Avg river level (m)`
  - [ ] Source documented (WMO Climate Atlas, ERA5 climatology, etc.)
  - [ ] Notes column includes the dominant seasonal pattern (already drafted — verify)

### MET-3 — Confirm or revise compound event rules (Section 6)
- **Priority:** 🔴 Blocker
- **File:** `backend/meteorology_rules.md` Section 6
- **What:** Validate the two compound event escalation rules currently drafted; revise wording if needed and add any missing rules.
- **Acceptance criteria:**
  - [ ] **Flash Flood Risk** rule (`precip_mm_7d > 80 mm AND soil_moisture_pct > 85%` → `FLOOD_WARNING`) — confirm or adjust thresholds
  - [ ] **Compound Drought-Heat** rule (`drought_index < −1.2 AND temp_max_c > 38°C` → `DROUGHT_WARNING`) — confirm or adjust
  - [ ] Any additional compound rules added in plain English (Claude reads this directly — no pseudo-code)

---

## 🟡 Tier 2 — Important (Sunday morning)

### MET-4 — Add seasonality multipliers
- **Priority:** 🟡
- **File:** `backend/meteorology_rules.md` (new section or extend Section 2/3)
- **What:** Define how thresholds adjust by season. Example: Mediterranean summer dry-season raises the precipitation threshold for "anomalously wet"; winter lowers it.
- **Acceptance criteria:**
  - [ ] At least one multiplier per season (DJF / MAM / JJA / SON) for at least the Mediterranean region
  - [ ] Wording is unambiguous so Claude can apply them ("In summer (JJA), multiply the FLOOD_WATCH precipitation threshold by 1.5x for `mediterranean-basin`")

### MET-5 — Define sub-regional micro-climate zones
- **Priority:** 🟡
- **File:** `backend/meteorology_rules.md` (new section)
- **What:** Within each bounding box, identify zones where thresholds differ significantly (e.g. mountain vs coastal in `mediterranean-basin`).
- **Acceptance criteria:**
  - [ ] At least one micro-climate zone documented per region with distinct thresholds
  - [ ] Zone boundaries described in lat/lon or by named geography (Claude doesn't have a GIS layer — text only)

### MET-6 — ENSO / NAO teleconnection adjustments
- **Priority:** 🟡
- **File:** `backend/meteorology_rules.md` (new section)
- **What:** Document how El Niño / NAO phases shift baseline expectations for the Sahel and Mediterranean regions.
- **Acceptance criteria:**
  - [ ] At least one ENSO adjustment for `sahel-region`
  - [ ] At least one NAO adjustment for `mediterranean-basin`
  - [ ] Phase determination is testable (e.g. "if NOAA ONI ≥ +0.5 → El Niño phase")

---

## 🟢 Tier 3 — Nice-to-have

### MET-7 — Confidence-modifier rules
- **Priority:** 🟢
- **File:** `backend/meteorology_rules.md` (new section)
- **What:** Define conditions under which Claude should *lower* its confidence score (e.g. sparse sensor coverage, single-source data, recent satellite gaps).
- **Acceptance criteria:**
  - [ ] At least 3 confidence-downgrade rules documented
  - [ ] Each rule references a sensor field (e.g. `source` containing "DUMMY" or "stale")

### MET-8 — Cross-validate against ESA Copernicus event catalogue
- **Priority:** 🟢
- **File:** `data_science/notebooks/02-threshold-validation.ipynb` (with Data Analysts)
- **What:** For ≥3 known historical flood/drought events from the ESA Copernicus Emergency Management Service catalogue, replay the rules against contemporaneous data and verify the correct alert status fires.
- **Acceptance criteria:**
  - [ ] At least 3 events tested
  - [ ] True-positive rate documented (does the rule trigger on real events?)
  - [ ] False-positive rate documented (does it stay quiet on non-event days?)

---

## 🚨 Critical formatting rules (DO NOT BREAK)

The Lambda injects this file **verbatim** into Claude's prompt. Do not:

- ❌ Rename the 5 alert status codes (`SAFE`, `DROUGHT_WATCH`, `DROUGHT_WARNING`, `FLOOD_WATCH`, `FLOOD_WARNING`) — they're referenced in 3 other places (`lambda_handler.py` `STATUS_META`, `frontend/src/components/AlertPanel.jsx` `STATUS_META`, Discord embed colour map). If you absolutely must add a new status, coordinate with Lead Dev to update all 3 sites in lockstep
- ❌ Restructure sections 1–7 (the section numbering is part of the contract)
- ❌ Use HTML or non-Markdown formatting — Claude reads the raw text, plain Markdown only
- ❌ Add front-matter (YAML / TOML) — the file is read raw

You CAN:

- ✅ Add new tables / sections as long as section numbering stays consistent
- ✅ Refine threshold values in existing tables
- ✅ Add citation footnotes
- ✅ Add per-region overrides

---

## 🔍 Verification before handoff

- [ ] `meteorology_rules.md` opens cleanly in any Markdown viewer
- [ ] All 5 status codes still present and unchanged
- [ ] All 5 region IDs in Section 5 match `frontend/src/App.jsx` `REGIONS[]` exactly: `mediterranean-basin`, `sahel-region`, `danube-basin`, `po-valley`, `nile-delta`
- [ ] No placeholder text (`[INSERT DATE]`, `TODO`, `_…_`) remaining in Sections 1–6 (Section 7 is the working backlog — placeholders OK there)
- [ ] Update the `Last updated:` line at the top
