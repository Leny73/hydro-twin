# HydroTwin — Data Sources: What We Actually Use vs. What We Claim

**Status as of 2026-04-26** — quick reference for the team before the pitch.

> TL;DR: our Sources page lists 7 feeds. Only **3** are wired into live API calls. The rest are aspirational, indirect, or marketing.

---

## ✅ Actually called in the code

| Source | Where it's called | What we extract |
|---|---|---|
| **Sentinel-2 L2A** (Copernicus) | `backend/sentinel_extractor.py` → Sentinel Hub Statistical API | NDVI (B4/B8) for vegetation health, NDWI (B3/B8) for water extent → drives `ndvi`, `ndwi`, `flood_extent_km2` |
| **OpenMeteo Forecast API** | `backend/sentinel_extractor.py` | precipitation 7d/30d, soil moisture, max temp, 24h precip forecast |
| **OpenMeteo Archive API** (ERA5-backed) | `frontend/src/lib/openmeteo.js` | History replay — past dates pull ERA5 reanalysis through OpenMeteo |
| **AWS Bedrock — Claude Sonnet 4.6** | `backend/lambda_handler.py`, `backend/chat_handler.py` | risk assessment + chat (the LLM, not a data source) |
| **GADM v4.1** boundary data | bundled `gadm41_BGR_1.json`, `gadm41_BGR_2.json` | Bulgaria oblast + 29 municipality polygons |
| **Mapbox satellite-streets-v12** | basemap | tiles only |

---

## ❌ Listed on the Sources page but NOT actually called

These appear in `frontend/src/pages/Sources.jsx` and `DataSourcesBar.jsx`:

| Claimed source | Reality | Risk if a judge asks |
|---|---|---|
| **Sentinel-1 SAR** (flood extent, soil moisture from backscatter) | No SAR evalscript exists. We only query `sentinel-2-l2a`. | 🔴 High — S-1 is Copernicus's flood-mapping workhorse, this is the most likely "show me" question |
| **Sentinel-3 SRAL altimetry** (river levels) | `river_level_m` is hardcoded as `None` in `sentinel_extractor.py:367` with a TODO. Zero S-3 calls. | 🟡 Medium — clicking into a flood alert shows the empty field |
| **Galileo GNSS** | **Zero code uses it.** The card is decorative. `initial_context.md:92` even says *"Galileo/EGNOS (challenge is EO-centric) → don't force it"* | 🟢 Low — CASSINI is EO-centric, judges unlikely to probe |
| **ECMWF ERA5 (direct)** | We don't call ECMWF directly. ERA5 comes via OpenMeteo's archive API. Listing it separately double-counts. | 🟢 Low — technically true via OpenMeteo |
| **NIMH Bulgaria** | No API call. Indirect — `meteorology_rules.md` thresholds were informed by NIMH expertise (Elitsa) | 🟢 Low — defensible as "domain consultation" |
| **Copernicus GloFAS** | TODO in code comments for `river_level_m`. Not integrated. | 🟢 Low — not on Sources page yet |

---

## 🎯 Pitch defence lines (if pressed)

- **"How do you use Galileo?"** → *"Galileo is part of the broader EU space programme our pipeline aligns with — we use the GNSS-derived geolocation embedded in every Copernicus acquisition, but we don't call a Galileo API directly."* Defensible. Don't claim first-class Galileo use.
- **"Where's your Sentinel-1 flood mapping?"** → Honest answer: *"Sentinel-2 NDWI is our v1 water-extent proxy; SAR-based extent is on the v2 roadmap."*
- **"Show me a river level"** → flood-watch regions show `river_level_m = null`. Either don't click into one during the demo, or implement Sentinel-3 / GloFAS before Sunday.

---

## 💡 Recommended cleanup before the pitch

1. **Soften `Sources.jsx`** — mark Sentinel-1, Sentinel-3, Galileo as **Planned / Roadmap** rather than active.
   *OR*
2. **Add a "✓ Live" / "○ Planned" badge** per source card so the page is transparent without removing the EU programme attribution.

Either fix takes ~5 minutes and removes the *"is this actually real?"* attack surface.

---

## 📂 Source-of-truth files

- `backend/sentinel_extractor.py` — the only file that talks to satellite/weather APIs
- `frontend/src/lib/openmeteo.js` — replay-mode historical fetch
- `frontend/src/pages/Sources.jsx` — what we claim to users
- `frontend/src/components/DataSourcesBar.jsx` — bottom-bar attribution (desktop only)
