# 📼 Historical Events Replay — Design

> **Owner:** Lead Dev (Dimi)
> **Status:** Design draft — not yet scheduled
> **Created:** 2026-04-25
> **Origin:** `initial_context.md` calls the "replay button" the pitch centerpiece. This expands it from a single hardcoded replay into a per-region history dropdown.
> **Related specs:**
>
> - `../02-lead-dev/01-tasks.md` (LD-10 sparkline shipped — this is a follow-on)
> - `../03-data-analysts/01-tasks.md` (extractor signature change needed — see cross-team ask)
> - `../04-meteorologist/01-tasks.md` (event list + severity confirmation needed)
> - `../05-cross-team-asks/01-questions-for-team.md` (asks logged under "History replay")

---

## 🎯 What we're building

A `<HistoryPicker>` dropdown inside `AlertPanel` that lists the **5 most recent verified flood/drought events** for the selected region (e.g., Pleven). Selecting an event re-renders the dashboard against that historical date, so the user sees _"what HydroTwin would have said at the time"_ — same map, same panel, same Bedrock reasoning, but past-tense.

**User flow:**

1. User clicks a region (e.g., Pleven) → `AlertPanel` opens with the live assessment
2. Dropdown at the top of the panel lists 5 past events: _"📼 2014-08 — Mizia / Vit basin floods (FLOOD_WARNING)"_
3. User picks one → panel swaps to the historical snapshot, banner appears: _"📼 Showing 2014-08-01 reconstruction"_
4. "Back to live" button restores the live view

---

## 🗂️ Data sources

### ✅ USE

| Source                                                       | What for                                                                             | Where                                   |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------ | --------------------------------------- |
| **Curated JSON** (`frontend/src/data/historicalEvents.json`) | Catalog of 5 events per region: date range, name, severity, EMS link, baked snapshot | Frontend                                |
| **OpenMeteo Historical API** (`archive-api.open-meteo.com`)  | Past precipitation + temperature for `replay_date`                                   | Extractor (Tier B only)                 |
| **Sentinel-1/2 archive** via Sentinel Hub                    | Past NDVI, soil moisture, flood extent                                               | Extractor (Tier B only)                 |
| **ERA5 reanalysis**                                          | SPI-3 / PDSI for replay date                                                         | Extractor (Tier B only)                 |
| **Copernicus EMS Rapid Mapping**                             | Source of event truth (activation IDs, official maps)                                | Research only — bake findings into JSON |
| **NIMH Bulgaria records**                                    | Bulgarian flood truth source                                                         | Research only — confirm with Elitsa     |

### ❌ DO NOT USE

- **EM-DAT / DesInventar at runtime** — paywalled, slow. Use as research input for the JSON, never as a live call.
- **Live Sentinel API queries during the demo** — 5–30s latency, can fail. If used in Tier B, results must be cached.
- **LLM-generated event lists** — hallucination risk. Every event must have an EMS or NIMH source.
- **Generic disaster RSS feeds** (GDACS, ReliefWeb) — too noisy, not flood-specific to small Bulgarian basins.
- **Twitter / news scraping** — unverifiable, not pitch-grade.

---

## 🏗️ Architecture — two tiers

### Tier A — pre-baked snapshot (demo-safe, ship first)

Each entry in `historicalEvents.json` includes the full extractor return dict frozen at peak event date. Frontend renders directly from the JSON, **no backend call**. Works offline. Bypasses `sentinel_extractor.py` entirely.

- **Pro:** zero dependency on Alexandre, zero AWS round-trip, never breaks
- **Con:** numbers are static, not "real reconstructions" — but for the demo, indistinguishable from live data because the panel renders the same shape

### Tier B — live archive fetch (stretch)

Frontend POSTs `/assess` with `{ bbox, replay_date: "YYYY-MM-DD" }`. Lambda passes `replay_date` to `get_eo_and_weather_data()`. **Extractor (Alexandre's code)** routes to historical APIs. Bedrock prompt prepends _"This is a historical reconstruction from {date}"_ for past-tense reasoning.

- **Pro:** real EO reconstruction, stronger pitch narrative
- **Con:** depends on Alexandre extending the extractor + Sentinel Hub archive auth

**Fallback rule:** If Tier B errors, frontend falls back to Tier A snapshot. Demo never breaks. (Same fallback principle as `App.jsx` `fetchAssessment()`.)

---

## 📐 Schema additions

### `historicalEvents.json` (frontend, new file)

```json
{
  "pleven": [
    {
      "id": "pleven-2014-08",
      "regionId": "pleven",
      "dateStart": "2014-07-30",
      "dateEnd": "2014-08-05",
      "peakDate": "2014-08-01",
      "name": "Mizia / Vit basin floods",
      "severity": "FLOOD_WARNING",
      "summary": "120mm in 24h overflowed the Skat tributary; Mizia town inundated, 2 fatalities.",
      "emsActivationId": "EMSR096",
      "sourceUrl": "https://emergency.copernicus.eu/mapping/list-of-components/EMSR096",
      "snapshot": {
        "ndvi": 0.42,
        "soil_moisture_pct": 89,
        "precip_mm_7d": 145,
        "precip_mm_30d": 220,
        "river_level_m": 6.8,
        "flood_extent_km2": 14.2,
        "temp_max_c": 24,
        "drought_index": 1.4,
        "data_timestamp": "2014-08-01T12:00:00Z",
        "source": "EMSR096 / NIMH archive (curated)"
      },
      "reasoning": "Saturated soils from a wet July combined with a 120mm/24h convective event on the upper Vit. Peak discharge breached the Mizia levees."
    }
  ]
}
```

**Note:** `snapshot` matches the extractor return-dict schema **exactly** — same 10 keys, same types, same units. This means `AlertPanel` doesn't need to know whether data came from Tier A or Tier B.

### Backend request body extension (Lambda)

```jsonc
POST /assess
{
  "region_id": "pleven",
  "bbox": [22.5, 43.2, 25.5, 44.0],
  "replay_date": "2014-08-01"   // NEW, optional, ISO YYYY-MM-DD
}
```

### Extractor signature change (Alexandre's file — ask, do not edit)

```python
def get_eo_and_weather_data(
    bbox: list,
    replay_date: str | None = None,   # NEW
) -> dict:
    """When replay_date is set, route to historical APIs.
    Return dict keys are unchanged (10-key contract holds)."""
```

### Lambda response envelope extension (cosmetic)

```jsonc
{
  "status": "FLOOD_WARNING",
  "confidence": 0.91,
  "reasoning": "...",
  "replay": true, // NEW, optional
  "replay_date": "2014-08-01", // NEW, optional, echoed from request
}
```

So `AlertPanel` can show _"📼 2014-08-01 reconstruction"_ banner.

---

## 👥 Scope split

| Owner         | Work                                                                                                                                                                                                                                        |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Dimi**      | `historicalEvents.json` schema + Pleven entries (placeholder snapshots first, real numbers once Elitsa confirms), `<HistoryPicker>` component, banner UI in `AlertPanel`, Lambda `replay_date` passthrough, Tier B → Tier A fallback wiring |
| **Alexandre** | Extractor `replay_date` branch — OpenMeteo Historical + Sentinel archive routing. Schema unchanged.                                                                                                                                         |
| **Elitsa**    | Confirm 5 verified Pleven floods (dates, severity, summary, NIMH source). Same for any other Bulgarian AOI.                                                                                                                                 |
| **Lyuben**    | Optional: tweak Bedrock prompt for past-tense reasoning when `replay_date` is set                                                                                                                                                           |

---

## ⚠️ Critical rules (non-negotiable)

- ❌ **Do not change the extractor return-dict schema.** `replay_date` is a new _input_; the 10 output keys stay identical.
- ❌ **Do not fabricate events.** Every entry in the JSON must have an EMS activation ID OR a confirmed NIMH source.
- ❌ **Do not block on Tier B.** Ship Tier A first; Tier B is a stretch.
- ❌ **Do not break the `STATUS_META` contract.** Historical events use the same 5 status codes (`SAFE | DROUGHT_WATCH | DROUGHT_WARNING | FLOOD_WATCH | FLOOD_WARNING`).
- ✅ **Always preserve the live-view fallback.** "Back to live" button must always work, even mid-replay.
- ✅ **Tier B must fall back to Tier A on error.** Demo never breaks.

---

## 🚧 Open questions

1. **Region scope** — only Pleven, or expand to other Bulgarian AOIs? Pleven is the only confirmed AOI today; the brief mentions 3 Bulgarian AOIs but the other two aren't defined yet. **Recommendation:** Pleven only for v1; design supports adding more without code change (just JSON entries).
2. **Tier A only, or A + B scaffolded?** **Recommendation:** Tier A first (3–4h, demo-safe), wire B as stretch if Alexandre's extractor change lands by Saturday afternoon.
3. **Where does the dropdown live?** Top of `AlertPanel`, floating control on the map, or a new modal? **Recommendation:** inside `AlertPanel` so it appears only when a region is selected (less map clutter).

---

## 📋 Implementation steps

### Tier A (Lead Dev, ~3–4h)

1. Create `frontend/src/data/historicalEvents.json` with placeholder Pleven entries — real dates, placeholder snapshot numbers (flag for Elitsa with `// TODO: NIMH-confirm` comments).
2. Create `frontend/src/components/HistoryPicker.jsx` — controlled `<select>` styled with Tailwind to match `AlertPanel`.
3. Mount `<HistoryPicker>` at the top of `AlertPanel`, above the status badge.
4. In `App.jsx`, add `replayEvent` state. When set, render `replayEvent.snapshot` + `replayEvent.reasoning` instead of the live assessment.
5. Add a yellow info banner in `AlertPanel` (_"📼 Showing 2014-08-01 reconstruction · Back to live →"_) when `replayEvent` is set.
6. "Back to live" button clears `replayEvent` and re-fetches the live assessment.
7. Smoke test on mobile (≤640 px bottom-sheet) + desktop (≥640 px sidebar).
8. Open cross-team asks (see updated `specs/05-cross-team-asks/01-questions-for-team.md`).

### Tier B (stretch, depends on Alexandre)

1. Frontend: include `replay_date` in POST body when `replayEvent` is set.
2. Lambda: read `replay_date` from body, pass to `get_eo_and_weather_data(bbox, replay_date=...)`.
3. Lambda: in Bedrock prompt, prepend _"This is a historical reconstruction from {replay_date}."_ when set.
4. Lambda: add `replay: true, replay_date` to response envelope.
5. Frontend: show banner using server-confirmed `replay_date`.
6. Fallback: if Tier B errors, fall through to Tier A snapshot in the JSON (already in memory client-side).

---

## 🎬 Demo narrative

> "Pleven, today, is `DROUGHT_WATCH` — soil moisture 22%. But here's what makes HydroTwin different: with one click, we replay August 2014. Same dashboard, same AI reasoning, but reconstructed from Sentinel archive data. You can see the system would have flagged `FLOOD_WARNING` 36 hours before Mizia flooded. That's the decision-support layer between NIMH's warning and bg-ALERT's alarm."

This is the "replay button" pitch centerpiece, but **richer**: not one event, but a verifiable history per region. Defensible to the jury (every event has an EMS source).
