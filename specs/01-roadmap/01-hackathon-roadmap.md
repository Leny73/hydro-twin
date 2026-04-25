# 🗺️ HydroTwin — Hackathon Roadmap

> **CASSINI Hackathon Bulgaria 2026 · Sofia · 25–27 April**
> Pitch: **Sunday 27 April · 15:00**
> Total build window: ~40 active hours

This roadmap sequences the per-team task lists in `02-lead-dev/`, `03-data-analysts/`, `04-meteorologist/`. Source-of-truth tasks come from `README.md`.

---

## 🎯 Tier ordering (priority across all teams)

| Tier | Definition | Status |
|------|------------|--------|
| 🔴 **Blocker** (Tier 1) | Must ship by **Saturday night** or the demo dies | ⏳ In progress |
| 🟡 **Important** (Tier 2) | Demo target by **Sunday morning** | ⏳ Pending |
| 🟢 **Nice-to-have** (Tier 3) | Only if Tier 1+2 are rock solid | ⏳ Pending |

> **Rule:** if Saturday night arrives without Tier 1 done across all 3 teams, cut Tier 2/3 features immediately. Don't try to ship both.

---

## 📅 Timeline (40 hours)

### Friday Apr 25 — Setup (~4h active)

| Time | Owner | Task |
|------|-------|------|
| Evening | Lead Dev | Create AWS account access, set up Lambda + API Gateway shell, get IAM `bedrock:InvokeModel` policy attached |
| Evening | Lead Dev | Set Lambda env vars (`WEBHOOK_URL`, `BEDROCK_MODEL_ID`, `BEDROCK_REGION`) |
| Evening | Lead Dev | Create Discord channel + webhook → paste URL into `WEBHOOK_URL` |
| Evening | Lead Dev | Deploy frontend skeleton to Vercel (Root Directory = `frontend`) → public URL alive |
| Evening | Data Analysts | Set up CDSE / Sentinel Hub OAuth credentials, test one Statistical API call |
| Evening | Meteorologist | Lock the 3 monitoring regions + draft initial threshold review |

**Friday end-of-day goal:** clickable demo deployed to Vercel with a working `/assess` endpoint (even on dummy data). Everyone has access to the public URL.

---

### Saturday Apr 26 — Build Tier 1 (~14h active)

#### Morning block (4h)
- 🔴 **Data Analysts:** Replace dummy `get_eo_and_weather_data()` with real Open-Meteo precipitation calls (start here — free API, no auth, validates the pipeline)
- 🔴 **Lead Dev:** Verify e2e: real extractor → Lambda → Bedrock → Discord webhook fires on `WATCH`/`WARNING` status

#### Midday block (3h)
- 🔴 **Data Analysts:** Add real Sentinel-2 NDVI calculation via Sentinel Hub Statistical API
- 🔴 **Data Analysts:** Add 7-day & 30-day precipitation totals from Open-Meteo
- 🔴 **Data Analysts:** Add data-freshness guard (reject observations >24h old)

#### Afternoon block (4h)
- 🔴 **Meteorologist:** Validate all flood + drought thresholds in `meteorology_rules.md` Sections 2 & 3
- 🔴 **Meteorologist:** Fill the **Regional Climatological Baselines** table (Section 5) with WMO 1991–2020 normals
- 🔴 **Meteorologist:** Confirm or revise compound event rules (flash flood, drought-heat) in Section 6

#### Evening block (3h)
- 🟡 **Lead Dev:** Run end-to-end Discord alert test with forced `FLOOD_WARNING` payload (verify embed colour, confidence %, reasoning text)
- 🟡 **Data Analysts:** Add Sentinel-1 SAR-based flood extent mapping
- 🟡 **Data Analysts:** Compute SPI-3 drought index from ERA5 precipitation

**Saturday night gate:** every 🔴 task across all teams must be ✅ done. Sleep 6–7 hours.

---

### Sunday Apr 27 — Polish + Submit (~6h active, until 15:00)

#### Morning (3h)
- 🟡 **Lead Dev:** Wire Subscribe button to a real `/subscribe` Lambda endpoint
- 🟡 **Lead Dev:** Add `/subscribe` Lambda + DynamoDB table for user webhook handles
- 🟡 **Meteorologist:** Add seasonality multipliers (summer/winter baseline adjustments)
- 🟡 **Meteorologist:** Document ENSO/NAO teleconnection adjustments for Sahel + Mediterranean

#### Late morning (2h)
- 🟢 **Lead Dev:** Add more monitored regions (Central Asia / Amazon basin) if time
- 🟢 **Lead Dev:** Add sparkline chart for sensor metrics in `AlertPanel`
- 🟢 **Data Analysts:** Write unit tests with mocked API responses
- 🟢 **Data Analysts:** EDA notebook for historical flood/drought events

#### 13:00 — Code freeze
- Final pitch rehearsal × 1
- Backup screen recording (always assume the live demo will fail)

#### 15:00 — Submit

---

## 🔗 Cross-team dependency graph

```
                    ┌─ Meteorologist Task 1+2+3 (validated thresholds + baselines)
                    │       │
                    │       ▼
                    │   Lead Dev demo can claim "scientifically validated"
                    │
Data Analyst Task 1 (real extractor)
        │
        ▼
Lead Dev Task 6 (e2e Discord test)
        │
        ▼
Lead Dev Task 4 (Vercel deploy with real data)
        │
        ▼
Lead Dev Task 7+8 (Subscribe button → /subscribe Lambda)  ← Sunday
```

**Critical path:** Data Analyst Task 1 unblocks Lead Dev's e2e validation. Start it Saturday morning sharp.

---

## ✅ Tier 1 acceptance criteria (Saturday night gate)

The demo is "Tier 1 done" when **all** of the following hold:

- [ ] `https://<vercel-url>` loads, map renders, all region markers clickable
- [ ] Clicking a region triggers a real `/assess` call to the deployed Lambda (not local Flask)
- [ ] The Lambda returns a real Bedrock-generated assessment (not the demo fallback)
- [ ] At least one region produces a `WATCH` or `WARNING` status that fires a Discord alert
- [ ] The Discord embed shows correct status, confidence %, reasoning, and region ID
- [ ] `meteorology_rules.md` Section 5 (regional baselines) is filled with real values, not placeholders
- [ ] All 5 regions return data (no null fields, no `DUMMY` source string)

---

## 🎬 Demo script (3 minutes — Sunday 15:00)

| Time | Segment | Owner |
|------|---------|-------|
| 0:00–0:20 | **Hook** — real flood photo, human cost | TBD |
| 0:20–0:40 | **Gap** — Copernicus data exists, warnings exist, but the decision-support layer in between is missing | TBD |
| 0:40–1:20 | **Product** — HydroTwin live, click a region, show AI assessment + confidence + reasoning | TBD |
| 1:20–2:20 | **Discord alert** — show the live webhook firing into a Discord channel | TBD |
| 2:20–2:50 | **Ask** — call to action / pilot ask | TBD |
| 2:50–3:00 | **Close** — one-liner | TBD |

---

## 📋 Per-team task lists

- 👨‍💻 [`02-lead-dev/01-tasks.md`](../02-lead-dev/01-tasks.md) — 10 tasks
- 📊 [`03-data-analysts/01-tasks.md`](../03-data-analysts/01-tasks.md) — 9 tasks
- 🌦️ [`04-meteorologist/01-tasks.md`](../04-meteorologist/01-tasks.md) — 8 tasks

---

## 🚨 Risk register

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| AWS Bedrock access denied / region unavailable | Medium | Demo fallback in `lambda_handler.py` already returns realistic `FLOOD_WATCH` if Bedrock errors |
| Vercel deploy breaks live | Low | Keep `npm run dev -- --host` as backup; phone hotspot if conference Wi-Fi dies |
| Discord webhook URL leaks in commit | Low | `.env.local` already in `.gitignore`-equivalent path; never paste into source |
| Sentinel Hub API quota exceeded mid-demo | Medium | Cache the last successful response; fall back to dummy data |
| Lambda cold-start delays > 5s on demo click | Low | Hit `/assess` once before going on stage to warm it up |
| Live API totally unreachable during pitch | Medium | The frontend's built-in demo fallback covers this — the pitch still works |

---

## 📝 Status log

| Date | Status |
|------|--------|
| 2026-04-25 | Roadmap created. Repo scaffold complete (Lambda + frontend). Awaiting Friday-evening setup tasks. |
