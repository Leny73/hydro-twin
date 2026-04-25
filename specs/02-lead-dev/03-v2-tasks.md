# 🚀 HydroTwin v2 — Sprint Task Spec

> **Owner:** Lead Dev (Dimi)
> **Status (2026-04-25 PM):** **All Lead Dev v2 work shipped.** Backend + frontend live in production. V2-1 (regions) shipped at 3 oblasts: Pleven + Yambol + Burgas. V2-2/V2-3/V2-6 shipped end-to-end. V2-4 still deferred (waiting on Alexandre). V2-5 owned by colleague.
> **Created:** 2026-04-25, post-pitch sprint

---

## 🎯 Overview

Post-MVP sprint: turn the click-to-assess prototype into a **continuously-monitoring multi-region dashboard** with at-a-glance status, scheduled real notifications, and source attribution — without breaking the demo fallbacks that kept v1 bullet-proof.

- **Owned by Lead Dev (Dimi):** V2-1, V2-2, V2-3, V2-4, V2-6
- **Owned by colleague (parallel work-stream):** V2-5 (time-travel UI + history table)

---

## 🏗️ Architecture decisions (locked 2026-04-25)

These five decisions were the rails for every task. **Don't re-litigate.**

| # | Concern | Decision | Rationale |
|---|---|---|---|
| 1 | 🗄️ DB for cached state | **Extend DynamoDB** — new table `HydroTwinStatus` (PK=`region_id`) | Same IAM role, same SDK, no new cloud surface. V2-5's history table is independent (PK=`region_id`, SK=`assessed_at`) |
| 2 | ⏱️ Cron mechanism | **EventBridge rule @ 30 min** → new Lambda `HydroTwinCron` | AWS-native, direct Lambda invoke, no Vercel function hop / second billing surface |
| 3 | 📢 Notification de-dup | **Fire webhook only on status-code transition.** No quiet hours v1 | First-ever run with non-SAFE status fires; same-status repeat skips; de-escalations (WARNING→WATCH) also fire |
| 4 | 📚 `/assess` sources contract | **Add `sources: string[]` to response.** Plumb existing extractor `source` field as `[source]` for now | Additive only — no extractor schema change. Future-ready when Alexandre adds structured citations |
| 5 | 🔍 V2-4 feasibility | **Defer until Alexandre confirms** sub-region drill-down is tractable at Sentinel-1/2 native resolution inside Lambda 15-min ceiling | Question to be logged in `specs/05-cross-team-asks/01-questions-for-team.md` |

### 🤝 V2-5 colleague coordination contract (live & ready)
- ✅ Lead Dev's cron runs on a public EventBridge rule the colleague can co-attach to: `arn:aws:events:us-east-1:640053196632:rule/HydroTwinCronSchedule`
- ✅ Snapshot table (`HydroTwinStatus`) is read-only from V2-5's side; their `HydroTwinHistory` (PK=`region_id`, SK=`assessed_at`) is independent
- ✅ Adding history-append is a **~5-line patch** in `backend/cron_handler.py` after `_write_snapshot()` — colleague can PR without touching snapshot logic
- ✅ Cron Lambda function name: `HydroTwinCron` (handler `cron_handler.lambda_handler`) — surfaced in `04-runbook.md` under "v2 Stack inventory"

---

## V2-1 — Add more monitored regions  ✅ Shipped (3 oblasts)
- **Priority:** 🟢 — originally deferred, but expanded during the v2 session
- **Status:** **DONE 2026-04-25 PM.** Three Bulgarian oblasts live in prod: **Pleven · Yambol · Burgas**. Cron iterates all three on every 30-min run.
- **Files (shipped):**
  - `backend/regions.py` — `REGIONS` (id → bbox), `REGION_NAMES` (id → display), `KNOWN_REGIONS` frozenset
  - `frontend/src/regions.geojson` — polygon features for all three
  - `frontend/src/App.jsx` — `REGIONS` array (id, bbox, lon/lat, color) for marker labels
  - `backend/subscribe_handler.py` — imports `KNOWN_REGIONS` from shared module (no inline list)
- **Acceptance criteria:**
  - [x] Region list confirmed: Pleven Oblast (Danube floodplain), Yambol Oblast (Tundzha basin), Burgas Oblast (Black Sea coast)
  - [x] Each region defined with: `id` (slug), display name, `bbox`, polygon GeoJSON, marker color
  - [x] `frontend/src/regions.geojson` polygons render on map
  - [x] `App.jsx REGIONS` array contains all three
  - [x] `subscribe_handler.KNOWN_REGIONS` synced via `from regions import KNOWN_REGIONS`
  - [x] Cron iterates over all three (verified `regions_total: 3, regions_succeeded: 3`)
  - [x] Subscribe E2E tested: `POST /subscribe {"region_id":"pleven|yambol|burgas"}` → 201
- **Time spent:** ~30 min (regions added by Dimi mid-session, code already region-agnostic)

---

## V2-2 — Pre-computed map state with legend  ✅ Shipped
- **Priority:** 🟡 → **shipped**
- **Status:** **DONE 2026-04-25 PM.** Map paints all polygons by current status on page load; legend top-left auto-updates "X min ago" every 60 s; stale-state badge wired (yellow if >1 h).
- **Files (shipped):**
  - `backend/status_handler.py` (NEW) — scans `HydroTwinStatus`, returns array, Decimal→native conversion
  - `backend/cron_handler.py` (NEW) — populates the table this reads (see V2-3)
  - `frontend/src/components/MapLegend.jsx` (NEW) — colour scale + freshness indicator
  - `frontend/src/App.jsx` — `/status` fetch on mount, `paintedRegions` `useMemo`, snapshot patch on `/assess` response
  - `specs/02-lead-dev/02-deployment/04-runbook.md` — v2 Stack inventory + multi-Lambda redeploy + manual cron section
- **Acceptance criteria:**
  - [x] DynamoDB table `HydroTwinStatus` created in `us-east-1` (PK=`region_id`, on-demand billing, TTL disabled)
  - [x] Lambda `HydroTwinStatus` deployed (Python 3.12, 128 MB, 10 s timeout) — scans table, returns array
  - [x] API Gateway route `GET /status` wired (route id `uh6wk3q`, integration id `9u6xkqr`)
  - [x] Response shape: `{ regions: [{region_id, status, confidence, reasoning, sources, assessed_at}], generated_at }`
  - [x] CORS preflight returns 200 with `Access-Control-Allow-*` headers
  - [x] Frontend on mount fetches `/status`, paints each polygon by `STATUS_COLORS[status]`
  - [x] **Map legend** mounted top-left under topbar — 5 status colours + label + "Updated X min ago"
  - [x] Stale-state UX: if newest `assessed_at` > 1 h, legend shows ⚠️ badge in yellow
  - [x] Click on region: **cache-first (changed 2026-04-25)** — render the `/status` snapshot instantly (no Bedrock spinner). Live `/assess` is the fallback when no snapshot exists for the region (initial-mount race, `/status` failure, or first-ever run). When `/assess` does run, its response patches into `regionStatuses` so the polygon repaints immediately.
  - [x] Demo fallback: `/status` failure → polygons render in neutral grey (`#64748B`) + console warn (no crash)
- **Live:** `https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/status`

---

## V2-3 — Scheduled background Lambda runs  ✅ Shipped
- **Priority:** 🟡 → **shipped**
- **Status:** **DONE 2026-04-25 PM.** Cron runs every 30 min, snapshots all 3 regions, fires Discord webhooks only on status transitions. De-dup verified: a no-change run produces `webhooks_fired: 0`.
- **Files (shipped):**
  - `backend/cron_handler.py` (NEW) — orchestrator (read prior → assess → write snapshot → de-dup webhook)
  - `backend/lambda_handler.py` — refactored: extracted `assess_region(region_id, bbox)` for cron reuse, added `sources` field to response, threaded `region_name` into Bedrock prompt
  - `backend/regions.py` (NEW) — single source of truth for `REGIONS` + `REGION_NAMES` + `KNOWN_REGIONS`
  - AWS Console / CLI: EventBridge rule `HydroTwinCronSchedule`, Lambda `HydroTwinCron`, IAM inline policy `HydroTwinStatusDynamoDB`
  - `specs/02-lead-dev/02-deployment/04-runbook.md` — manual cron invoke + pause/resume schedule + 6-row troubleshooting matrix
- **Acceptance criteria:**
  - [x] Lambda `HydroTwinCron` deployed (Python 3.12, 256 MB, **5 min timeout** — 3 regions × ~15 s each + buffer)
  - [x] EventBridge rule `HydroTwinCronSchedule` (`rate(30 minutes)`, ENABLED) → invokes `HydroTwinCron`
  - [x] IAM: `HydroTwinLambdaRole` (shared by all 4 Lambdas) gets inline policy `HydroTwinStatusDynamoDB` granting `dynamodb:GetItem/PutItem/UpdateItem/Scan/Query` on the new table. Bedrock + Sentinel access already attached on the role
  - [x] Iterates over `REGIONS` from `backend/regions.py` (single source of truth — same module imported by `subscribe_handler`, `cron_handler`, `status_handler`)
  - [x] Per region: extract → load rules → Bedrock → write snapshot → de-dup webhook decision
  - [x] **De-dup logic:** `_should_fire_webhook(prior, new_status)` — first run + non-SAFE fires; same-status repeat skips; transitions in either direction fire
  - [x] CloudWatch log group `/aws/lambda/HydroTwinCron` exists; each run logs region count, transitions list, error per region
  - [x] Demo fallback preserved: per-region try/except — one failure logs + skips, others continue (`regions_failed` counter exposed in summary)
  - [x] **First manual smoke test:** `aws lambda invoke` → 3 rows in `HydroTwinStatus`, 1 webhook (Pleven first-run DROUGHT_WATCH), Yambol/Burgas SAFE on first run quietly seeded
  - [x] **De-dup smoke test:** second invoke produced `webhooks_fired: 0` (statuses unchanged) — confirms no spam
- **Discovered + fixed during smoke test:**
  - Missing `python-dotenv` in zip caused `Unable to import module 'cron_handler'` on first invoke. Added to the install line in the runbook + zip rebuilt.

---

## V2-4 — Drill-down: per-region risk detail  🟠 Deferred
- **Priority:** 🟠 — feasibility unknown, deferred until data analyst greenlights
- **Status:** **BLOCKED** on Alexandre (Data Analyst). Question to be logged in `specs/05-cross-team-asks/01-questions-for-team.md`.
- **Question to Alexandre:**
  > Can `sentinel_extractor.get_eo_and_weather_data` return per-cell metrics for an N×N grid inside a region bbox without exceeding the Lambda 15-min ceiling, and what's the smallest N that gives meaningful spatial differentiation at Sentinel-1/2 native resolution?
- **Acceptance criteria:** ⏸️ Pending feasibility answer
- **Time estimate:** ⏸️ TBD post-spike (likely 1–2 days if feasible, descope if not)
- **Dependencies:** Alexandre's feasibility result

---

## V2-5 — Time-travel / replay  🚫 NOT YOURS
> **Owned by Dimi's colleague (parallel work-stream).** Lead Dev does NOT touch time-travel UI, history table, or replay logic. Coordination contract is in the **Architecture decisions** section above — schedule ARN + cron Lambda function name + ~5-line history-append patch site are all surfaced.

---

## V2-6 — Visualize data sources used in computations  ✅ Shipped
- **Priority:** 🟢 → **shipped**
- **Status:** **DONE 2026-04-25 PM.** `sources: string[]` flows from extractor → `/assess` response → `HydroTwinStatus` row → `/status` response → `AlertPanel`. Collapsible "📚 Data Sources (N)" section renders below the sparkline.
- **Files (shipped):**
  - `backend/lambda_handler.py` — `assess_region` wraps extractor `source` string into `sources: [source]`
  - `backend/cron_handler.py` — `_write_snapshot` persists `sources` attribute on every snapshot
  - `backend/status_handler.py` — passes `sources` through in `/status` response
  - `frontend/src/components/AlertPanel.jsx` — new "📚 Data Sources (N)" expandable section between sparkline + footer; `sourcesOpen` state resets per region
- **Acceptance criteria:**
  - [x] `/assess` response body includes `sources: string[]` (always present, `[]` if extractor returns nothing)
  - [x] `HydroTwinStatus` row includes `sources` attribute
  - [x] `/status` response includes `sources` per region
  - [x] AlertPanel renders **collapsed by default** "📚 Data Sources (N)" section if `sources.length > 0`; hides section entirely if empty
  - [x] Each source rendered as a bullet (`<li className="ml-1">`)
  - [x] Mobile + desktop layout unaffected (Vite build clean, no layout shift)
  - [x] Demo fallback: if response is missing `sources`, `Array.isArray` guard skips the whole section without crash
- **Notes:**
  - Currently every region returns the same single string: *"Sentinel Hub Statistical API (S2-L2A NDVI/NDWI) + OpenMeteo"* (the extractor's existing field). Structured citations (`{name, url, dataset_id}`) are a future upgrade — no UI changes needed when extractor gains them.

---

## 🛠️ Mid-sprint discovery — Bedrock prompt fix (not in original scope)

The first cron run revealed Bedrock was hallucinating "Pleven Oblast" in the reasoning text for Yambol and Burgas. Cause: `meteorology_rules.md` is Pleven-calibrated and mentions Pleven by name; without explicit region context in the prompt, Claude defaulted to that.

**Fix shipped same session:**
- `backend/regions.py` — added `REGION_NAMES` dict (id → human display)
- `backend/lambda_handler.py` — `call_bedrock_agent(data, rules, region_name)` now takes the region name as a third arg; prompt has a new `=== REGION UNDER ASSESSMENT ===` block + a writing rule forbidding Claude from naming a different oblast even if the rules file mentions one
- `assess_region` resolves `region_name = REGION_NAMES.get(region_id, region_id)` before invoking Bedrock
- All 4 Lambdas redeployed; cron re-invoked → snapshots refreshed → verified Pleven reasoning still names Pleven, Yambol/Burgas reasoning name themselves correctly (no cross-contamination)

---

## 📌 Cross-cutting concerns — RESOLVED

| Concern | Resolution |
|---|---|
| DB choice for cached state | ✅ DynamoDB → `HydroTwinStatus` table live |
| Cron mechanism | ✅ EventBridge rule `HydroTwinCronSchedule` @ 30 min, ARMED |
| Notification de-dup | ✅ Status-code transition only, no quiet hours v1 — verified `webhooks_fired: 0` on no-change run |
| `/assess` response contract | ✅ `sources: string[]` field plumbed end-to-end |
| Multi-region prompt accuracy | ✅ `region_name` threaded into Bedrock prompt, verified no cross-region naming |
| V2-4 feasibility | 🟠 Still deferred — pending Alexandre |

---

## 🚦 Execution order — RESULT (Pleven + Yambol + Burgas v2 scope)

1. ✅ **V2-1** (regions list) — expanded to 3 oblasts mid-session
2. ✅ **V2-3 + V2-2 together** — cron + table seeded data → `/status` + legend rendered it
3. ✅ **V2-6** — `sources` array shipped end-to-end
4. ✅ **Bedrock prompt fix** — discovered + shipped in the same session
5. 🟠 **V2-4** — still deferred (Alexandre's feasibility answer required)

V2-5 is colleague's parallel work-stream; not in this list.

---

## 🌐 Live infrastructure (snapshot 2026-04-25 PM)

| Layer | Resource | URL / ID |
|---|---|---|
| Frontend | Vercel project `hydrotwin` | https://hydrotwin.vercel.app |
| API Gateway | HTTP API `sdnatb43dl` | https://sdnatb43dl.execute-api.us-east-1.amazonaws.com |
| Lambda — assess | `HydroTwin` | `lambda_handler.lambda_handler` · 256 MB · 30 s |
| Lambda — subscribe | `HydroTwinSubscribe` | `subscribe_handler.lambda_handler` · 128 MB · 10 s |
| Lambda — cron | `HydroTwinCron` | `cron_handler.lambda_handler` · 256 MB · 5 min |
| Lambda — status reader | `HydroTwinStatus` | `status_handler.lambda_handler` · 128 MB · 10 s |
| EventBridge rule | `HydroTwinCronSchedule` | `rate(30 minutes)` · ENABLED |
| DynamoDB — subscriptions | `HydroTwinSubscriptions` | PK=`email`, SK=`region_id` |
| DynamoDB — snapshots | `HydroTwinStatus` | PK=`region_id` · 3 rows |
| IAM role | `HydroTwinLambdaRole` | Shared by all 4 Lambdas |
| Inline policy | `HydroTwinStatusDynamoDB` | Get/Put/Update/Scan/Query on `HydroTwinStatus` |

---

## 🔍 Verification — all green

**Backend / API:**
- [x] `GET /status` returns 200 + 3 regions with `sources` arrays + valid `assessed_at`
- [x] `POST /assess` returns 200 with `sources` field for all 3 regions
- [x] Cron manual invoke: `regions_total: 3, regions_succeeded: 3, regions_failed: 0`
- [x] De-dup verified: second invoke returned `webhooks_fired: 0` (statuses unchanged)
- [x] Bedrock multi-region naming: Pleven → "Pleven Oblast", Yambol → "Yambol Oblast", Burgas → "Burgas Oblast" (no cross-contamination)
- [x] Bedrock LIVE (no `[DEMO MODE]` in any reasoning string)

**Frontend:**
- [x] `https://hydrotwin.vercel.app` HTTP 200 (Age: 0 = fresh)
- [x] Build clean (Vite 5.4 builds in 17 s)

**Manual / human-eyes (still TODO before Dimi declares "done"):**
- [ ] Open public Vercel URL in **incognito** — verify all 3 polygons render coloured by status
- [ ] Verify map legend top-left shows colour scale + "Updated X min ago"
- [ ] Click each region → confirm reasoning + sources panel + sparkline render
- [ ] Subscribe form for Yambol or Burgas → confirm 201
- [ ] Phone via LAN — confirm mobile bottom-sheet + legend stack correctly

**Post-demo hygiene:**
- [ ] Rotate the Vercel deploy token (chat-pasted) at https://vercel.com/account/tokens
- [ ] Rotate Sentinel Hub OAuth client at https://shapps.sentinel-hub.com
- [ ] Rotate Discord webhook at Channel Settings → Integrations → Webhooks
- [ ] `npx vercel login` once so future `/deploy vercel` uses OS-stored auth

---

## 📝 How to expand a stub (legacy guidance — preserved for future v2+ tasks)

When picking up a future task:

1. Replace the **Stub** line with a real spec section (acceptance criteria as checkboxes)
2. Resolve the **Open questions** — either answer them inline or flag what you need from whom
3. Add a **Files** section listing exactly what changes
4. Add a **Time estimate** so the sprint is plannable
5. If the task spans multiple PRs, list the PR breakdown

Mirror the format of `01-tasks.md` — it's a known-good template.
