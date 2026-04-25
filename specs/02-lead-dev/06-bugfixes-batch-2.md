# 🐛 HydroTwin v3 — Bugfixes Batch #2

> **Owner:** Lead Dev (Dimi)
> **Status:** Captured 2026-04-25 PM after Batch #1 deploy + AWS reports infra went live.
> **Trigger:** Post-Batch#1 polish pass. UX detail work + first request for richer in-panel meteorology graphs.
> **Scope:** Frontend-only (chart improvements may add a small data fetch hook).

---

## BF2-1 — ✂️ Shorter map hint copy  🟢 Trivial

**Symptom:** The "Tap a region or municipality to view assessment" floating hint is still long enough to wrap on narrow viewports.
**Decision (locked):** Tighten to **"Tap a region to view assessment"**.
**Suspect files:**
- `frontend/src/pages/Overview.jsx` line ~631
**Acceptance:**
- [ ] Hint reads exactly `Tap a region to view assessment` — no oblast names, no "or municipality"

---

## BF2-2 — 📋 Recent reports UX overhaul  🟡 Important

**Symptoms:**
- (a) No way to **filter by region** — at scale the list is one long stream
- (b) Submitted **date** is shown only as a relative "37 min ago" — once reports get older that loses precision
- (c) **Coordinates overflow** the card — the metadata row crams region/time/email/coords on a single line and on narrow widths the lat/lng spills outside the card border
**Expected:**
- (a) Add a region filter — dropdown matching the submission form's region options (`All / Pleven / Yambol / Burgas / Other`)
- (b) Show both relative time **and** an absolute date stamp (e.g. `25 Apr 2026 · 17:42 UTC`). Relative bold, absolute muted next to it
- (c) Wrap or restructure the metadata row so on `<sm` it stacks gracefully — coordinates should never escape the card
**Suspect files:**
- `frontend/src/components/ReportsList.jsx`
**Acceptance:**
- [ ] Region filter visible above the list, defaults to `All`
- [ ] Filtering shows the count update (`3 reports` → `1 report` etc.)
- [ ] Each card shows both relative time + absolute timestamp
- [ ] Cards never overflow at 320 px → 1920 px
- [ ] Empty-state copy adapts when filter excludes all reports (e.g. "No reports for Pleven yet.")

---

## BF2-3 — 🕒 Promote "Last Updated" to a top-of-sidebar card  🟡 Important

**Symptom (image #6):** The freshness widget is currently a tiny two-line block pinned to the **bottom** of the sidebar where it's easy to miss.
**Inspiration (image #7):** A richer card with:
- Clock / refresh icon in a circular badge
- Big, bold time (HH:MM)
- Smaller "Today, {date}" caption
- Subtle right-arrow chevron (suggesting tappable / drilldown)
**Decision (locked):**
- Move the widget to the **top of the sidebar** (just under the brand row, above the nav links)
- Adopt the card style from image #7 — clock icon · large time · date caption
- Keep the same "stale > 60 min → yellow ⚠️" treatment
**Suspect files:**
- `frontend/src/components/Sidebar.jsx` (NavContent block)
**Acceptance:**
- [ ] Card appears above `Overview`/`Reports`/`Sources` nav links
- [ ] Bottom of the sidebar reclaims the freed space (or shows nothing — Dimi to confirm what to put there, see open question)
- [ ] Card shows: 🕒 icon · `HH:MM` time · `Today, DD MMM YYYY` (or `N min ago` style — see open question)
- [ ] Stale state still triggers ⚠️ + yellow accent
- [ ] Mobile drawer shows the same card (since `NavContent` is shared)

---

## BF2-4 — 📈 Better precipitation chart + (maybe) cyclone visualization  🟢 Nice-to-have, hackathon flair

**Symptom:** `MetricsSparkline` currently renders a **stubbed** 14-day series with no axes, no units shown on the curve, no date labels. Per the file's TODO comment it's been awaiting real data wiring.
**Teammate suggestion (verbatim):**
> "I suggested that we could include the visualisation of the cyclones in the said time the forecast is made. This could be taken from ECMWF or wetter3.de"
**Two pieces of work:**

### BF2-4a — Real precipitation chart with axes
- Replace stub series with **real OpenMeteo data** for the selected region (we already have `frontend/src/lib/openmeteo.js` doing replay fetches — extract a "current 14-day" helper)
- Add proper **X-axis** (date ticks every 2–3 days) and **Y-axis** (mm scale, max ≈ 1.2 × peak)
- Tooltip on hover with day + value
- Optional second series (temperature max) overlaid in a different colour
**Files:** `frontend/src/components/MetricsSparkline.jsx` (rewrite as a real chart), or replace with a new `PrecipitationChart.jsx`. Add helper to `lib/openmeteo.js`.

### BF2-4b — Cyclone / pressure visualization
- **Option A — wetter3.de embed (fastest):** add a `<CycloneChart />` component that renders an `<img>` pointing to wetter3.de's public Europe surface-pressure forecast (e.g. `https://www.wetter3.de/Bilder/dt00_3.gif` or similar). Static image, no auth, attribution beneath. Refreshes 4× daily on their side.
- **Option B — Build from OpenMeteo `surface_pressure`:** we render a 24/48 h pressure trend line with an annotation when a low-pressure system is forecast. Slower but ours.
- **Option C — Both:** wetter3.de panoramic image *plus* a local pressure trend line for the AOI.
**Files:** new `frontend/src/components/CycloneChart.jsx` + import into `AlertPanel.jsx` below the precipitation chart.
**Risk:** wetter3.de hotlinking policy unclear — if blocked we proxy through our Lambda or fall back to Option B.
**Acceptance:**
- [ ] Precipitation chart shows axes with date + mm labels
- [ ] At least one new visualization (cyclones or pressure trend) renders inside the AlertPanel
- [ ] Per-source attribution visible ("Source: wetter3.de · ECMWF Open Data" etc.)
- [ ] Falls back gracefully if upstream image fails to load (no broken-image icon)

---

## BF2-5 — 📌 Sticky AlertPanel header  🟡 Important

**Symptom (image #8):** Once you scroll down inside the panel (long reasoning, multiple sections), the **HydroTwin Alert / region name / status tag / close button** all scroll out of view. Users lose the ✕ button and the context of *which* region they're reading about.
**Expected:**
- The header block (region label + status tag + close button) **stays pinned to the top** of the panel as the body scrolls
- Solid / blurred background so reasoning text underneath doesn't bleed through
- Works on both **mobile bottom sheet** and **desktop right sidebar**
- The replay banner (when active) and the Current Status badge can either scroll with the body or join the sticky region — Dimi to call. Default: only the title row sticks.
**Suspect files:**
- `frontend/src/components/AlertPanel.jsx`
**Acceptance:**
- [ ] Scrolling the panel keeps the title + tag + close visible at all times
- [ ] No visible flash/seam where the sticky header meets the scrolled content
- [ ] Mobile drag-handle still rendered (above the sticky header on mobile)
- [ ] No layout shift when the header transitions from "in flow" to "sticky"

---

## BF2-6 — 🎨 Top severity counter mismatches map + legend  🔴 Critical

**Symptom:** The top-bar "Open alerts by severity" counter is using a **different vocabulary** from the rest of the UI:

| Surface | Codes used | Colours |
|---|---|---|
| Map polygons | `SAFE` · `DROUGHT_WATCH` · `DROUGHT_WARNING` · `FLOOD_WATCH` · `FLOOD_WARNING` | green · amber · orange · blue · red |
| Map legend | same 5 status codes | same 5 colours |
| **Top counter** | `NORMAL` · `WATCH` · `WARNING` · `CRITICAL` (4 collapsed tiers) | green · yellow · orange · red |

**Concrete failures:**
- (a) **Names diverge** — legend says "Drought Watch" / "Flood Watch", counter just says "WATCH"
- (b) **Colours diverge** — `FLOOD_WATCH` is **blue** on the map but rolls into yellow `WATCH` in the counter
- (c) **Count looks wrong to the user** — Dimi reports orange polygons visible on the map (= `DROUGHT_WARNING` = `WARNING` tier) while the counter shows `WARNING: 0`. Need to verify whether this is the same vocabulary problem (counter labelled differently) or a real wiring bug.

**Architecture decision required (locked → see option):**
- Original v3 spec (`04-v3-dashboard-redesign.md` row #4) deliberately collapsed 5 codes → 4 tiers in the *counter only*, keeping the per-status colours on the map. The hypothesis was that municipal ops want a 4-bucket overview ("how bad is it overall?"). Real-device testing shows this **fights** the rest of the UI rather than complementing it.
- **Decision (locked 2026-04-25 PM):** Drop the 4-tier collapse. The counter uses the **same 5 status codes, names, and colours as the legend**. Single vocabulary, single source of truth.

**Suspect files:**
- `frontend/src/components/SeverityCounter.jsx` — switch from `SEVERITY_ORDER` / `SEVERITY_META` to the 5 status codes
- `frontend/src/lib/severity.js` — keep the `severityOf` helper for any non-counter consumer (e.g. `StatusPill` already uses it), but add a **status-level** `STATUS_META` parallel to the legend's so we have one canonical source. Or import the legend's STATUSES list directly.
- `frontend/src/components/MapLegend.jsx` — reuse its `STATUSES` array as the canonical source if it's not already exported

**Acceptance:**
- [ ] Counter reads `Safe N · Drought Watch N · Drought Warning N · Flood Watch N · Flood Warning N` (or compact icon labels at narrow widths)
- [ ] Each label uses the **same colour swatch** as the legend
- [ ] An orange polygon on the map is reflected as `Drought Warning: 1` (or higher) in the counter — no hidden remappings
- [ ] On `<md` viewports the counter still fits — collapse to colored numbers only without the labels (e.g. `🟢 2 · 🟡 1 · 🟠 1 · 🔵 0 · 🔴 0`)
- [ ] Standalone `severityOf` helper still works for components that use it (StatusPill, etc.) — don't accidentally remove the export

**Verification path:**
- After fix, force a `DROUGHT_WARNING` for one region (e.g. via a manual `/cron-run`) and confirm the counter increments accordingly. If it doesn't, the wiring (not the vocabulary) is broken — open a separate spec entry.

---

## 🚦 Suggested fix order

1. **BF2-1** — 30-second copy change ✂️
2. **BF2-6** — top counter alignment (single source of truth) 🎨
3. **BF2-5** — sticky header (small CSS, big UX win) 📌
4. **BF2-2** — reports filter + date + coord wrap (single-component refactor) 📋
5. **BF2-3** — sidebar card (visual polish, single component) 🕒
6. **BF2-4a** — real precip chart with axes 📈
7. **BF2-4b** — cyclone/pressure visual *(after Dimi confirms option A vs B vs C)* 🌀

---

## ❓ Open questions for Dimi (block BF2-3 and BF2-4b)

- **BF2-3** — Should the card show the **time** (`14:23`) or **relative** time (`1 min ago`) as the primary big-text value? Mockup shows time, but project's running theme is relative ("3 min ago", "2 h ago").
- **BF2-3** — What goes at the **bottom** of the sidebar once the freshness card moves up? Options: nothing (clean), severity counter (mini), build version, or an "Open feedback" link.
- **BF2-4b** — Pick **A / B / C** for the cyclone visual. A is fastest (10 min), C is richest (~45 min).
- **BF2-4a** — Real-time precip data for the chart needs the region's centroid coordinates. Confirm we can hit OpenMeteo client-side from the frontend on every region click? (We already do for replay so this is mostly fine — just flagging the extra request.)
