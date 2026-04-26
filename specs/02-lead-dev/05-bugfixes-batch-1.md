# 🐛 HydroTwin v3 — Bugfixes Batch #1

> **Owner:** Lead Dev (Dimi)
> **Status:** Captured 2026-04-25 from real-device testing of v3 dashboard. Implementation pending.
> **Trigger:** Post-`825c604` smoke test on mobile + desktop revealed UI/UX regressions and a broken `/reports` submit.
> **Scope:** Frontend-only (no backend changes expected). Some moves are layout reshuffles, others are real bugs.

---

## 🎯 Theme

The v3 redesign shipped the right *structure* (sidebar / topbar / sources bar / panel) but the *density and hierarchy* are off — especially on mobile. The right-side panel re-states things that already live in the chrome (data sources, region name), the in-map UI elements eat half the viewport, and `/reports` doesn't actually submit. This batch is a UX consolidation pass + one functional fix.

---

## BF1-1 — 📱 Mobile navigation broken / hamburger invisible  🔴 Critical

**Symptom:** On mobile (`<640 px`) the sidebar nav is unreachable. Hamburger toggle is either missing or not visible against the map background.
**Repro:** Open `/` on a phone (or DevTools device mode at 375 × 667) → can't get to `Reports`.
**Expected:** Clear, high-contrast hamburger button in the top bar that opens a slide-out / overlay drawer with `Overview`, `Reports` (and the new `Sources` from BF1-3), plus the "Last updated" widget.
**Suspect files:**
- `frontend/src/components/Layout.jsx`
- `frontend/src/components/Sidebar.jsx`
- `frontend/src/components/TopBar.jsx`
**Acceptance:**
- [ ] Hamburger visible on `<768 px` against any map tile (use a solid bg / shadow, not pure transparent)
- [ ] Drawer opens, has a backdrop, and closes on link tap or backdrop tap
- [ ] No layout shift when opening (use `position: fixed` overlay, don't squeeze the map)
- [ ] 44 × 44 px touch target (WCAG 2.5.5 — already a project rule)

---

## BF1-2 — 🗺️ Legend takes too much space + "Awaiting first run…" stale text  🟡 Important

**Symptom (a):** `MapLegend` is permanently expanded and covers ~25% of the map on mobile.
**Symptom (b):** Legend shows the literal string **"Awaiting first run…"** which is a leftover from a pre-cron loading state and now reads as a bug to viewers.
**Decision (locked 2026-04-25):**
- Legend defaults to **open on every viewport** (mobile + desktop) but gets an explicit **collapse/expand toggle** so users can shrink it when it's in the way.
- Remove the "Awaiting first run…" copy entirely — the freshness widget in the sidebar already carries that information.
**Suspect files:**
- `frontend/src/components/MapLegend.jsx` — the offending text is at line ~89
**Acceptance:**
- [ ] Legend has a collapse/expand toggle (chevron / minus icon)
- [ ] Defaults to **open** on all breakpoints
- [ ] Collapsed state shrinks to a small chip (≤ 60 × 60 px) showing just the legend icon
- [ ] No reference to "Awaiting first run" anywhere in the codebase (`grep` clean)

---

## BF1-3 — 📚 Move "Data Sources" to its own nav page (Sources)  🟡 Important

**Symptom:** On mobile the bottom `DataSourcesBar` (Copernicus / Galileo / Rainfall / etc.) is unreadable — see BF1-8 below — and it's eating vertical space that should belong to the map. The sources are static reference info, not live state, so they don't need to be on every screen.
**Decision (locked 2026-04-25):**
- New route `/sources` with a new page `frontend/src/pages/Sources.jsx`
- Sidebar/drawer gets a third link: `Overview` · `Reports` · `Sources` (visible on mobile drawer, on desktop it can also be a sidebar link)
- **Mobile:** `DataSourcesBar` is hidden — sources reachable only via the new nav item
- **Desktop:** `DataSourcesBar` stays at the bottom as informational chrome (with proper overflow handling per BF1-8)
- Page lists each source with: logo, name, what it provides, refresh cadence, link to the upstream provider
**Suspect files:**
- `frontend/src/components/Sidebar.jsx` — add the link
- `frontend/src/components/Layout.jsx` — register the route
- `frontend/src/components/DataSourcesBar.jsx` — content moves into the new page
- `frontend/src/pages/Sources.jsx` (NEW)
**Acceptance:**
- [ ] `/sources` renders cleanly on mobile and desktop
- [ ] All source entries currently in `DataSourcesBar` are present on the page

---

## BF1-4 — 📊 AlertPanel: hide "Past Day" + lift "Current Status" to the top  🔴 Critical UX

**Symptom (image #1):** When a region/municipality is clicked the right panel opens with the **replay/past-day picker** and **"Jump to a known event" chips** at the top, taking the entire fold. The actually-important info — `Current Status: Drought Watch` — is buried at the very bottom. There are also repeated/redundant sections.
**Expected:**
- **Top of the panel = the assessment**: status badge, AI confidence, region name (no repetition with the topbar / map pill), short reasoning summary
- Replay date picker + curated event chips become a **collapsed section** lower in the panel (default closed). Label it `🕓 Replay & past events` with a chevron.
- Audit and **remove repeated sections** — region name, status, sources should each appear exactly once.
**Suspect files:**
- `frontend/src/components/AlertPanel.jsx`
- `frontend/src/components/HistoryPicker.jsx` (probably wraps the date picker + chips)
- `frontend/src/components/DatePicker.jsx`, `frontend/src/components/CuratedEventChips.jsx`
**Acceptance:**
- [ ] Opening the panel, **without scrolling**, shows: status badge, region name, AI confidence, top-line reasoning
- [ ] Replay UI is collapsed by default
- [ ] Each piece of info (region, status, confidence) appears exactly once

---

## BF1-5 — 🧹 Remove redundant "Data Sources" block from AlertPanel  🟡 Important

**Symptom:** Clicking a region opens the panel which **also** lists every data source — duplicating what was in the bottom `DataSourcesBar` and (after BF1-3) what lives on `/sources`. Users don't need a global source list per click.
**Decision (locked 2026-04-25):**
- **Remove the sources block entirely** from `AlertPanel`. No per-assessment caption — sources live on `/sources` (mobile) and `DataSourcesBar` (desktop) only.
**Suspect files:**
- `frontend/src/components/AlertPanel.jsx`
**Acceptance:**
- [ ] No static "Data Sources" / logo strip inside the panel
- [ ] No per-assessment source caption either — clean removal

---

## BF1-6 — 🏷️ In-map region cards too big (cover entire region)  🟡 Important

**Symptom (image #2):** `StatusPill` cards (Pleven Oblast WATCH, Burgas Oblast NORMAL) sit on top of the polygons and at desktop zoom levels they're as big as the region itself — obscures the geography.
**Decision (locked 2026-04-25 — Dimi delegated):**
- Strip the pill down to **colored dot + status text only** (drop the region name). The panel and the future hover tooltip carry the name.
- Tighter padding, smaller font (≈ 11–12 px), single-line.
- Pill anchored to the region centroid but never larger than ~96 × 24 px.
**Suspect files:**
- `frontend/src/components/StatusPill.jsx`
- `frontend/src/pages/Overview.jsx` (where the pills are mounted on the map)
**Acceptance:**
- [ ] At default desktop zoom (Bulgaria-fit), no pill covers more than ~10% of its region polygon
- [ ] Still legible at mobile zoom (text ≥ 11 px, contrast ratio ≥ 4.5:1)

---

## BF1-7 — 💬 Hallucinated/random hint text "Tap a region label or a Pleven municipality…"  🟡 Important

**Symptom (image #3):** A floating hint reads:
> "Tap a region label or a **Pleven** municipality to view assessment"
The "Pleven" is not contextual — it's hardcoded copy that looks like an LLM hallucination to the viewer.
**Decision (locked 2026-04-25):**
- Use the **generic copy**: `"Tap a region or municipality to view assessment"`. Single source of truth, no contextual logic.
**Suspect files:**
- `frontend/src/pages/Overview.jsx` (line ~631 has the literal string)
**Acceptance:**
- [ ] Hint text contains no hardcoded oblast name unless the map view is actually focused on that oblast
- [ ] Hint hides as soon as a region is selected

---

## BF1-8 — 📐 Bottom data-sources bar wraps to a horizontal mess  🟡 Important

**Symptom (image #4):** `DataSourcesBar` overflows on mobile — labels and logos line-break into a tangled horizontal strip with stray dividers.
**Decision:** With BF1-3 moving sources to their own page, the simplest fix is to **hide `DataSourcesBar` on `<768 px`** entirely (link the `/sources` page instead). On desktop it can stay but needs proper overflow handling.
**Expected:**
- `<768 px`: `DataSourcesBar` is hidden; user reaches sources via the new nav link
- `≥ 768 px`: bar uses `flex-wrap` or horizontal scroll with a fade mask, no broken dividers
**Suspect files:**
- `frontend/src/components/DataSourcesBar.jsx`
**Acceptance:**
- [ ] No layout breakage at any width from 320 px to 1920 px
- [ ] Bar hidden on mobile (or alternative: collapsed into a single "Data sources →" link)

---

## BF1-9 — *(skipped by user — slot reserved for next round)*

---

## BF1-10 — 📝 `/reports` form not submitting + remove AI-seeded test reports  🔴 Critical

**Symptom (image #5):**
- (a) Clicking `SUBMIT REPORT` flashes a red error toast: "Submission failed. Please try again." Network tab shows the request payload going out — so the failure is server-side or response-handling.
- (b) "Recent reports" section shows three obviously-fake demo reports (`Pleven Oblast — 37 min ago — m***@example.com`, etc.) seeded by the frontend itself for demo purposes.
**Expected:**
- (a) Submit succeeds → success toast → form resets → new report appears at top of the list
- (b) Demo reports removed entirely. If the list is empty, show a friendly empty state ("No reports yet. Be the first to report an incident.")
**Investigation findings (2026-04-25):**
- ✅ **Frontend code is correct.** `frontend/src/components/ReportForm.jsx` → calls `submitReport()` in `frontend/src/lib/reports-api.js` → POSTs to `${VITE_API_ENDPOINT}` rewritten from `/assess` to `/reports`. Payload shape matches what the backend expects (`email`, `region_id`, `description`, `lat`, `lng`).
- ✅ **Backend Lambda code exists and looks correct.** `backend/reports_handler.py` is a complete, well-validated POST/GET handler with CORS + DynamoDB persistence + 503 fallback.
- ✅ **Local dev server wires it up.** `backend/local_server.py:93` routes `/reports` → `reports_handler`. So `npm run dev` against `http://localhost:5050` should work end-to-end if AWS creds + a local DynamoDB are configured (or against the real AWS DynamoDB).
- 🔴 **Root cause: AWS infrastructure for `/reports` was never provisioned.** `specs/02-lead-dev/02-deployment/04-runbook.md` documents this as **pending first-time setup** in the section *"🆕 v3 first-time setup — Reports table + Lambda + API routes"*:
  - DynamoDB table `HydroTwinReports` — not yet created (`aws dynamodb create-table …`)
  - Lambda function `HydroTwinReports` — not yet created (`aws lambda create-function …`)
  - API Gateway routes `POST /reports`, `GET /reports`, `OPTIONS /reports` — not yet added to API `sdnatb43dl`
  - IAM policy patch for `dynamodb:PutItem` + `dynamodb:Scan` on `HydroTwinReports` — not yet applied
- 📌 **The three "demo" reports the user saw are NOT in DynamoDB.** They're a frontend fallback in `ReportsList.jsx` lines 20–48 (`DEMO_REPORTS` constant) that kicks in when `GET /reports` fails. With the backend down, the user always sees them.
**Confirmation needed from Dimi:**
- Open DevTools → Network tab → click Submit → share the **HTTP status code** of the failing `POST /reports` request. Expected: **404 Not Found** (no API Gateway route) or **403 Forbidden** (route exists but Lambda permission missing). Either confirms the diagnosis above.
**Fix path (split into 2 deliverables):**
- 🔧 **(BF1-10a — frontend cleanup, can ship today):**
  - Remove `DEMO_REPORTS` constant + `demoMode` state + "Demo data" badge from `ReportsList.jsx`
  - When `GET /reports` fails, render an empty state with a small error caption ("Couldn't load reports — try again later") instead of fake data
  - This is **safe to do before the backend is up** — empty state is now the honest UX
- 🔧 **(BF1-10b — AWS provisioning, owned by Dimi):**
  - Run section *"🆕 v3 first-time setup — Reports table + Lambda + API routes"* of `04-runbook.md` end-to-end (table + Lambda + IAM patch + API routes + smoke `curl`)
  - Verification: the curl smoke test in the runbook returns `200` with a `report_id`
**Suspect files:**
- `frontend/src/components/ReportForm.jsx` — submit logic, endpoint, error-handling
- `frontend/src/components/ReportsList.jsx` — lines 22–40 hardcode the three demo reports; line ~72 has `demoMode` flag and "Demo data" badge
- `backend/lambda_handler.py` (or a separate reports Lambda) — verify the endpoint exists and accepts the payload shape `{ email, description, lat, lng, region_id }`
**Acceptance:**
- [ ] No demo reports rendered on a clean DB
- [ ] Submitting a valid report returns 2xx, list refreshes, form clears
- [ ] Submitting an invalid report (missing required field) shows a clear inline validation error, not the generic toast
- [ ] No `demo-1` / `demo-2` / `demo-3` strings left in `ReportsList.jsx`

---

## 🚦 Suggested fix order

1. **BF1-10** — broken submit is the only functional regression; everything else is UX polish 🔴
2. **BF1-1** — mobile nav unblocks demos on phones 🔴
3. **BF1-4** — biggest user-perceived UX win (panel hierarchy) 🔴
4. **BF1-2 + BF1-7** — quick string/visual cleanups (low risk, high polish) 🟡
5. **BF1-6** — pill resize, isolated component 🟡
6. **BF1-3 + BF1-5 + BF1-8** — sources consolidation (these three move together: new `/sources` page + remove from panel + hide bar on mobile) 🟡

---

## 📋 Notes

- All bugs were captured from a single test session on 2026-04-25 PM after merging `825c604` (v3 dashboard) and `483a6c8` (replay fixes).
- Screenshots referenced (panel-replay-on-top, oversized-pills, hardcoded-Pleven-hint, sources-bar-mess, reports-submit-fail) live in the conversation thread, not committed to the repo.
- No backend contract changes expected — if BF1-10 turns out to need a new Lambda or DynamoDB table, split it into its own spec file (`06-reports-backend.md`) before starting.
