# 🎨 HydroTwin v3 — Dashboard Redesign Spec

> **Owner:** Lead Dev (Dimi)
> **Status:** Architecture decisions locked 2026-04-25 PM. Implementation in progress.
> **Created:** 2026-04-25, post-v2 sprint
> **Trigger:** Mockup-driven UI overhaul + new `/reports` route for citizen-submitted incident reports.

---

## 🎯 Overview

Turn the current click-only map into a **proper operational dashboard**:

1. **Persistent chrome** — left sidebar (nav + freshness), top bar (severity counts), bottom bar (data-source provenance)
2. **Map at full height** with Bulgaria outline, higher polygon opacity, in-map status pills
3. **Structured AlertPanel** — replace the single markdown blob with 4 explicit sections (what / why / context / next)
4. **New `/reports` page** — public form for citizens to report incidents, public list view (no auth for demo)

The v2 cron + DynamoDB snapshot stack stays as-is. This is a UX redesign on top of the same data.

---

## 🏗️ Architecture decisions (locked 2026-04-25)

| # | Concern | Decision | Rationale |
|---|---|---|---|
| 1 | Structured reasoning shape | **Bedrock returns `reasoning_structured: {whats_happening, why_it_matters, current_context, next_step}` alongside existing `reasoning` markdown** | Additive — doesn't break v2 consumers. Frontend prefers structured when present, falls back to markdown for safety |
| 2 | Routing | **Add `react-router-dom@6`** with two routes: `/` (Overview) and `/reports` | Lightweight, well-known, zero learning cost. Wouter would shave ~3 kB but isn't worth the unfamiliarity tax |
| 3 | Report geometry input | **Pinpoint marker (lat/lng) + region dropdown** (`pleven` / `yambol` / `burgas` / `other`) | Polygon drawing is a UX rabbit hole. Pinpoint + region tag gives admins enough spatial info for triage |
| 4 | Severity grouping | Map status codes → severity tiers for the top counter & legend: `SAFE→NORMAL`, `*_WATCH→WATCH`, `DROUGHT_WARNING→WARNING`, `FLOOD_WARNING→CRITICAL`. Polygon paint stays per-status (preserves flood vs drought visual signal) | Mockup-faithful counter without losing flood/drought distinction on the map itself |
| 5 | Reports auth | **None for demo.** Anyone can POST a report; anyone can GET the list. Production hardening = separate concern, flagged in cross-team-asks | Per Dimi: "everyone will be able to see for a demo" |

### 🔁 Backwards compatibility contract

- `/assess` and `/status` responses **add** `reasoning_structured` — they don't remove anything. Old frontends keep working.
- DynamoDB `HydroTwinStatus` rows gain a `reasoning_structured` attribute. DynamoDB is schemaless; existing rows without it are fine until the next cron run.
- Status codes (5 of them) are untouched. Severity grouping is a frontend-only derivation.

---

## V3-1 — Layout shell + routing  🟡 Important

**Goal:** Replace the single-screen `App.jsx` with a proper dashboard chrome.

- **Files:**
  - `frontend/package.json` — add `react-router-dom@^6`
  - `frontend/src/App.jsx` — becomes the `<BrowserRouter>` root with `<Routes>`
  - `frontend/src/pages/Overview.jsx` (NEW) — current map + AlertPanel logic moves here
  - `frontend/src/pages/Reports.jsx` (NEW, stub for V3-4)
  - `frontend/src/components/Layout.jsx` (NEW) — flex grid: sidebar | main | (right panel slot)
  - `frontend/src/components/Sidebar.jsx` (NEW) — logo, nav links, "Last Updated" widget
  - `frontend/src/components/TopBar.jsx` (NEW) — page title + `SeverityCounter`
  - `frontend/src/components/SeverityCounter.jsx` (NEW) — derives from `regionStatuses`
  - `frontend/src/components/DataSourcesBar.jsx` (NEW) — Copernicus / Galileo / Rainfall logos & labels
  - `frontend/src/components/MapLegend.jsx` — keep for now, but shown inside the map (top-right)
  - `frontend/src/lib/severity.js` (NEW) — `STATUS_TO_SEVERITY`, `SEVERITY_META`
- **Acceptance criteria:**
  - [ ] `/` and `/reports` both render with sidebar visible
  - [ ] Sidebar fixed at 200 px wide, dark, with: 💧 logo, `Overview` link, `Reports` link, "Last updated X min ago" widget at bottom
  - [ ] Top bar fixed at 64 px tall: page title left, severity counter centered/right
  - [ ] Severity counter shows 5 colored dots + count: NORMAL · WATCH · WARNING · CRITICAL · INFO
  - [ ] Bottom bar fixed at 56 px tall with data-source attribution (Copernicus, Galileo, Rainfall)
  - [ ] Map fills the remaining vertical space (no "Alerts by area" table — never existed, just confirming nothing leaks in)
  - [ ] Active nav link highlights cyan
  - [ ] Layout works at ≥1024 px desktop (mobile collapse is out of scope for v3 — flag for later sprint if user objects)
- **Time estimate:** 2.5 h
- **Dependencies:** none. Unblocks V3-2 / V3-3.

---

## V3-2 — Map polish  🟡 Important

**Goal:** Bulgaria stands out, polygons are clearly visible, status reads at a glance.

- **Files:**
  - `frontend/src/pages/Overview.jsx` — add Bulgaria outline `<Source>` + `<Layer>`, bump polygon opacity, swap text labels for `<StatusPill>` markers
  - `frontend/src/components/StatusPill.jsx` (NEW) — region name + status badge
  - `frontend/src/lib/bulgaria-outline.js` (NEW) — country boundary GeoJSON (simplified)
- **Acceptance criteria:**
  - [ ] Bulgaria country boundary rendered as a thin cyan outline (1.5 px, 0.6 opacity)
  - [ ] Region polygon fill opacity raised from 0.18 → 0.42 (hover stays at 0.55)
  - [ ] Region labels replaced with `StatusPill`: region name + colored status badge (NORMAL/WATCH/WARNING/CRITICAL) on a dark rounded background
  - [ ] Status pills remain ≥44 px tall (WCAG touch target)
  - [ ] Map legend (existing `MapLegend.jsx`) repositioned to top-right inside the map; shows the 5-tier severity scale
- **Time estimate:** 1.5 h
- **Dependencies:** V3-1 (Overview page exists)

---

## V3-3 — Structured AlertPanel  🟡 Important

**Goal:** Replace the single markdown blob with 4 icon-prefixed sections matching the mockup.

- **Files:**
  - `backend/lambda_handler.py` — Bedrock prompt asks for `reasoning_structured` in addition to existing `reasoning`. Result merged into assessment dict.
  - `backend/cron_handler.py` — `_write_snapshot` includes `reasoning_structured` if present (no-op if missing)
  - `backend/status_handler.py` — passes through unchanged (already returns full row)
  - `frontend/src/components/AlertPanel.jsx` — render 4 sections with icons (📈 What's happening, 💧 Why it matters, 🌱 Current context, 📋 Suggested next step). Fall back to markdown blob if `reasoning_structured` missing.
- **Acceptance criteria:**
  - [ ] Bedrock prompt instructs strict JSON with `reasoning_structured: { whats_happening, why_it_matters, current_context, next_step }` (each: short markdown string, 1–3 sentences)
  - [ ] Demo fallback in `call_bedrock_agent` includes a populated `reasoning_structured` so the panel doesn't render half-empty when Bedrock is offline
  - [ ] DynamoDB snapshot row includes `reasoning_structured` after next cron run
  - [ ] AlertPanel renders 4 sections in order: What's happening · Why it matters · Current context · Next step
  - [ ] Each section: icon + label + content. Markdown allowed inside content.
  - [ ] If `reasoning_structured` is absent (legacy row, partial Bedrock response), panel shows the existing markdown blob and a small "Legacy reasoning" note
  - [ ] Status badge + confidence bar + sources block + subscribe CTA all preserved (no regressions)
- **Time estimate:** 3 h
- **Dependencies:** V3-1

---

## V3-4 — `/reports` page  🟢 Nice-to-have

**Goal:** Public incident-report form + public list view.

- **Files:**
  - `backend/reports_handler.py` (NEW) — single Lambda handles `POST /reports` (submit) and `GET /reports` (list)
  - DynamoDB table `HydroTwinReports` (PK=`report_id` UUID, attributes: email, region_id, lat, lng, description, status, submitted_at)
  - `frontend/src/pages/Reports.jsx` — list view + form
  - `frontend/src/components/ReportForm.jsx` (NEW) — email, region dropdown, pinpoint mini-map, description textarea
  - `frontend/src/components/ReportsList.jsx` (NEW) — card list of submitted reports
  - `frontend/src/lib/reports-api.js` (NEW) — `submitReport()`, `listReports()`
  - `specs/02-lead-dev/02-deployment/04-runbook.md` — append deploy steps for new table + Lambda + API Gateway routes
- **Acceptance criteria:**
  - [ ] DynamoDB table `HydroTwinReports` created (on-demand billing, TTL disabled, GSI not required for demo)
  - [ ] Lambda `HydroTwinReports` deployed (Python 3.12, 256 MB, 10 s timeout)
  - [ ] API Gateway routes: `POST /reports` and `GET /reports` (CORS enabled)
  - [ ] POST validates email format + required fields, returns 400 on invalid input, 200 on success with new `report_id`
  - [ ] GET returns `{ reports: [...], generated_at }`, sorted newest-first
  - [ ] `/reports` page shows form on top, list below
  - [ ] Form fields: email · region dropdown · description (textarea) · "Pin location on map" mini-map (click to place marker) · submit button
  - [ ] List shows: timestamp · region · description (truncated) · email (masked: `j***@example.com`) · "View on map" link (highlights the pin on a mini-map preview)
  - [ ] Submit success toast + form reset
  - [ ] Submit error toast on validation/network failure
  - [ ] Demo fallback: if API unreachable, show seeded mock reports + console warn
- **Time estimate:** 5 h (3 h backend + 2 h frontend)
- **Dependencies:** V3-1 (router exists, Reports.jsx mounted)

---

## 🚦 Execution order

1. **V3-1** — Layout shell. Unblocks everything.
2. **V3-2** — Map polish. Pure frontend, safe to ship in same PR as V3-1.
3. **V3-3** — Structured AlertPanel. Backend prompt change + frontend rewrite.
4. **V3-4** — `/reports` page. Largest scope; ship last.
5. **Build verification** — `npm run build`. **No deploy** — user reviews everything first.

PR shape: **one big v3 PR** since V3-1/V3-2/V3-3 are tightly coupled and V3-4 reuses the layout chrome. If review surfaces a need to split, V3-4 is the natural cut point.

---

## 📌 Cross-cutting concerns

| Concern | Resolution |
|---|---|
| Mobile breakpoints | **Deferred.** v3 targets desktop ≥1024 px. Mobile reflow = future sprint |
| Reports admin auth | **None for demo.** Production = Cognito or similar; flagged in cross-team-asks |
| Bulgaria GeoJSON source | Hand-simplified outline shipped in `lib/bulgaria-outline.js` (sub-2 kB). Avoids runtime fetch / CDN dependency |
| Severity vs status semantics | Polygons paint by **status** (preserves flood/drought color signal). Counter & legend group by **severity** (mockup-faithful). Both layers cohabit cleanly via the `lib/severity.js` map |
| Status code "INFO" in mockup | Reserved — no current status maps to it. Counter shows 0. Documented for future use (e.g. data-quality warnings, system events) |

---

## 📝 Open follow-ups (not in v3 scope)

- Mobile reflow of the dashboard chrome (sidebar collapses to bottom nav)
- Reports admin authentication
- Reports email verification (currently no double opt-in)
- Reports moderation tooling (delete spam, mark as resolved)
- Wire severity counter to be clickable → filters AlertPanel previews per tier
