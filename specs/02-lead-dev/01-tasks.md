# 👨‍💻 Lead Developer — Task Spec

> **Owner:** Lead Dev
> **Source:** `README.md` § Lead Developer task list
> **Roadmap:** [`../01-roadmap/01-hackathon-roadmap.md`](../01-roadmap/01-hackathon-roadmap.md)

10 tasks. 4 blockers (🔴), 4 important (🟡), 2 nice-to-have (🟢).

**Status (updated 2026-04-25 ~13:50):** LD-1, LD-2, LD-3, LD-4, LD-5, LD-7, LD-8 ✅ Done. LD-6 🟢 Implicitly verified (Discord HTTP 204 confirmed in CloudWatch on FLOOD_WATCH path; explicit FLOOD_WARNING red-embed test still pending). LD-9 scope changed to Bulgarian AOIs (1 of 3 done — `pleven` only). LD-10 not started.

**🟡 External blockers in flight:**
- **Anthropic use-case form** — submitted ~13:45 via AWS Console (Bedrock Playground prompt). Propagation up to ~15 min. Until then `/assess` returns canned `[DEMO MODE]` text. Re-test by curling `/assess` and confirming `reasoning` no longer starts with `[DEMO MODE`.
- **Sentinel Hub credentials** (`SH_CLIENT_ID` / `SH_CLIENT_SECRET`) — without these the new `sentinel_extractor.py` skips real EO calls and returns empty data → Bedrock has no signal → falls back. Get from https://shapps.sentinel-hub.com.

**✅ Regression fixed 2026-04-25 ~13:48:**
- `backend/subscribe_handler.py` `KNOWN_REGIONS` whitelist updated from the old 5 global IDs to `{"pleven"}` — matches `frontend/src/regions.geojson`. Deployed to both Lambdas. Verified live: `POST /subscribe {"region_id":"pleven"}` → HTTP 201, `{"region_id":"atlantis"}` → HTTP 400, legacy `{"region_id":"danube-basin"}` → HTTP 400 (intentionally — frontend no longer sends them).

---

## 🔴 Tier 1 — Blockers (Friday evening → Saturday night)

### LD-1 — Deploy Lambda to AWS + create API Gateway HTTP endpoint  ✅ Done
- **Priority:** 🔴 Blocker
- **Files:** `backend/lambda_handler.py` + AWS Console
- **What:** Package the backend as a Lambda zip, upload to AWS, create an API Gateway HTTP API in front of it with a `POST /assess` route.
- **Acceptance criteria:**
  - [x] Lambda function `HydroTwin` exists in AWS (Runtime Python 3.12, Handler `lambda_handler.lambda_handler`, Timeout 30s, Memory 256 MB)
  - [x] API Gateway URL responds to `POST /assess` with a valid JSON body
  - [x] CORS preflight (`OPTIONS`) returns 200 with `Access-Control-Allow-*` headers
  - [x] `curl -X POST` returns a 200 response
- **Live:** `https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/assess`
- **Re-deployed 2026-04-25 PM** with merged backend (new `lambda_handler.py` + bundled `python-dotenv`). Verified HTTP 200.

### LD-2 — Set Lambda environment variables  ✅ Done
- **Priority:** 🔴 Blocker
- **Files:** AWS Console → Lambda → Configuration → Environment variables
- **Acceptance criteria:**
  - [x] `DISCORD_WEBHOOK_URL` = real Discord webhook URL (set 2026-04-25 PM, swapped to final URL ~13:25)
  - [x] `BEDROCK_MODEL_ID` = `us.anthropic.claude-sonnet-4-6` (cross-region inference profile — required for current-gen models)
  - [x] `BEDROCK_REGION` = `us-east-1`
  - [ ] `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — optional, currently unset → Telegram delivery is skipped cleanly
- **Note:** legacy `WEBHOOK_URL` was dropped in the env update — new code reads `DISCORD_WEBHOOK_URL`.

### LD-3 — Add IAM policy `bedrock:InvokeModel` to Lambda execution role  ✅ Done
- **Priority:** 🔴 Blocker
- **Acceptance criteria:**
  - [x] `HydroTwinLambdaRole` has `BedrockInvokeAccess` (broad `anthropic.*` + inference profiles)
  - [x] `HydroTwinLambdaRole` has `HydroTwinSubscribeDynamoDB` (added today for LD-8)
  - [ ] Test invocation returns a real Claude response (not the `[DEMO MODE]` string) — **blocked by Anthropic use-case form**, NOT by IAM. The form is the only thing standing between us and live Bedrock.

### LD-4 — Deploy frontend to Vercel  ✅ Done
- **Priority:** 🔴 Blocker
- **Acceptance criteria:**
  - [x] Public URL renders the map + Pleven polygon overlay: https://hydrotwin.vercel.app
  - [x] `VITE_MAPBOX_TOKEN` set in Vercel project settings
  - [x] `VITE_API_ENDPOINT` set to the deployed API Gateway URL
  - [x] Clicking the Pleven zone triggers a real network call to the Lambda
- **Re-deployed 2026-04-25 PM** with Tatiana's Subscribe UI bundle. Alias serves fresh build (HTTP 200, Age: 0).

---

## 🟡 Tier 2 — Important (Sunday morning)

### LD-5 — Create Discord channel + webhook  ✅ Done
- **Priority:** 🟡 (Friday-evening prep, but blocking LD-2)
- **Acceptance criteria:**
  - [x] Webhook URL works — verified via CloudWatch log: `Discord webhook delivered: HTTP 204` (2026-04-25 ~11:22 UTC)
  - [x] URL pasted into Lambda env var `DISCORD_WEBHOOK_URL`

### LD-6 — End-to-end Discord alert test  🟢 Mostly verified
- **Priority:** 🟡
- **What:** Force a `FLOOD_WARNING` assessment and verify the Discord embed is rendered correctly.
- **Verified so far:**
  - [x] Webhook delivery is non-fatal (delivery happened in <0.3s, but Lambda also handles HTTP errors via `try/except` per `lambda_handler.py`)
  - [x] Webhook delivery happens within 2s of API call (measured ~270ms)
  - [x] Lambda response returns to client even if webhook fails (verified by code review — `requests.RequestException` caught and logged)
  - [x] Embed renders blue (`0x3B82F6`) 🌊 emoji + status field = `FLOOD_WATCH`, region_id field, reasoning text — all confirmed in the channel during smoke test
- **Still pending:**
  - [ ] **Force a real `FLOOD_WARNING` (not `FLOOD_WATCH`) to verify red colour (`0xEF4444`) + 🔴 emoji prefix path.** Easiest after Anthropic form approves — synthesize a payload that breaches multiple flood thresholds at once. Or temporarily hardcode `status: "FLOOD_WARNING"` in `call_bedrock_agent()` for one curl, then revert.

### LD-7 — Wire "Subscribe to Alerts" button to real `/subscribe` endpoint  ✅ Done
- **Priority:** 🟡
- **Files:** `frontend/src/components/AlertPanel.jsx` (Tatiana's PR — merged into `dev` 2026-04-25 PM)
- **Acceptance criteria:**
  - [x] Subscribe button opens an inline form with email field
  - [x] On submit, posts to `${VITE_API_ENDPOINT.replace('/assess','/subscribe')}` with `{email, region_id}` — contract verified against backend
  - [x] Shows success / error toast (handles 400 + 409 + success states)
- **Note:** UI lives at https://hydrotwin.vercel.app — open Pleven zone → click 🔔 Subscribe → enter email. ✅ Backend whitelist now includes `pleven` (fixed + redeployed 2026-04-25 ~13:48), full E2E flow works.

### LD-8 — Add `/subscribe` Lambda + DynamoDB table  ✅ Done
- **Priority:** 🟡
- **Files:** `backend/subscribe_handler.py` + DynamoDB table `HydroTwinSubscriptions`
- **Acceptance criteria:**
  - [x] DynamoDB table `HydroTwinSubscriptions` exists in us-east-1 (PK = `email`, SK = `region_id`, on-demand billing)
  - [x] Lambda `HydroTwinSubscribe` has IAM permission `dynamodb:PutItem` on that table (inline policy `HydroTwinSubscribeDynamoDB` on `HydroTwinLambdaRole`)
  - [x] API Gateway route `POST /subscribe` wired (route id `0udae0r`, integration id `0c1lvs9`)
  - [x] Returns 201 on success, 400 on invalid email / unknown region, 409 on duplicate
- **Live:** `https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/subscribe`
- ✅ Region whitelist synced to frontend regions (`pleven`), redeployed 2026-04-25 ~13:48.

---

## 🟢 Tier 3 — Nice-to-have (only if everything else done)

### LD-9 — Add more Bulgarian AOIs (scope changed)  🟡 1 of 3 done
- **Priority:** 🟢
- **Files:** `frontend/src/regions.geojson` + `frontend/src/App.jsx` `REGIONS` array + `backend/subscribe_handler.py` `KNOWN_REGIONS` whitelist
- **What (revised):** the brief calls for **3 Bulgarian AOIs**. The merged work added **Pleven Oblast** as the first. Add 2 more to match the brief — likely candidates: Sofia Oblast (urban flash flood), Plovdiv (Maritsa River basin), or Burgas (coastal + river-mouth).
- **Acceptance criteria:**
  - [x] Pleven Oblast renders as polygon overlay (not a marker dot)
  - [ ] 2 more Bulgarian regions added with polygon geometry in `regions.geojson`
  - [ ] Each new `id` added to `subscribe_handler.KNOWN_REGIONS` whitelist
  - [ ] Each region returns a valid assessment (Lambda is bbox-driven, so just needs a sensible bbox)
- **Coordinate with:** Angela (pitch narrative — does the pitch reference 3 regions?), Elitsa (regional baselines for new AOIs in `meteorology_rules.md`).

### LD-10 — Add time-series sparkline in `AlertPanel`  ⏳ Not started
- **Priority:** 🟢
- **Files:** `frontend/src/components/` (new component, e.g. `MetricsSparkline.jsx`)
- **What:** Render a small SVG sparkline of recent sensor metrics (precipitation, river level) inside the assessment panel.
- **Notes:** Requires the extractor to return historical arrays — `sentinel_extractor.py` currently returns single scalar values. Coordinate with Alexandre if needed.

---

## 🔍 Findings & Follow-ups (added 2026-04-25 PM)

### ✅ [FIXED 2026-04-25 ~13:48] Subscribe whitelist out of sync with frontend regions
- **Was:** `POST /subscribe {"region_id":"pleven"}` returned 400 because `subscribe_handler.KNOWN_REGIONS` still listed the old 5 global IDs.
- **Fix shipped:** `KNOWN_REGIONS = frozenset({"pleven"})`. Deployed to both Lambdas. Verified live: pleven → 201, atlantis → 400, danube-basin → 400.
- **Going forward:** when LD-9 adds 2 more Bulgarian regions, update both `frontend/src/regions.geojson` AND `backend/subscribe_handler.py KNOWN_REGIONS` together (the contract).

### 🟡 Bedrock returns demo fallback (Anthropic use-case form — submitted, awaiting propagation)
- **Symptom:** every `/assess` call has `[DEMO MODE — Bedrock unavailable]` in the `reasoning` text. CloudWatch shows `ResourceNotFoundException: Model use case details have not been submitted`.
- **Status 2026-04-25 ~13:45:** form submitted via Bedrock Playground (us-east-1 → click an Anthropic model → form pops up → fill + submit). AWS docs say up to 15 min for propagation.
- **Verify:** `curl -X POST https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/assess -H 'Content-Type: application/json' -d '{"region_id":"pleven","bbox":[23.9,43.15,25.2,43.7]}'` — `reasoning` should no longer start with `[DEMO MODE`.
- **Console retired:** "Model access" page is deprecated as of 2026 — serverless foundation models are auto-enabled per region; only Anthropic still requires the use-case form, triggered first time you select an Anthropic model in the Playground.

### 🟡 Sentinel Hub credentials unset
- **Symptom:** CloudWatch shows `SH_CLIENT_ID / SH_CLIENT_SECRET not set — skipping Sentinel Hub calls`. Real EO data is empty.
- **Fix:** get OAuth client at https://shapps.sentinel-hub.com → User Settings → OAuth Clients → set on Lambda env: `SH_CLIENT_ID`, `SH_CLIENT_SECRET`. No code change needed.
- **Impact:** even after Anthropic form approves, Bedrock will reason on empty sensor data → likely SAFE assessments. Real demo punch needs both.

### 🟡 Telegram unset (optional)
- **Symptom:** `Telegram delivery skipped — TELEGRAM_BOT_TOKEN/CHAT_ID not set`.
- **Fix:** if multi-channel notification is wanted, get a bot token from `@BotFather` and a chat ID from `@userinfobot`. Set both on Lambda env. No code change.

### 🟢 Vercel auth — recommended cleanup post-pitch
- The current deploy uses an inline `vcp_*` token (in chat history). Recommend running `npx vercel login` once after the demo so future `/deploy vercel` runs use OS-stored auth instead. Then revoke the chat-leaked token at https://vercel.com/account/tokens.

### 🟢 `/deploy` slash command available
- Project-local at `.claude/commands/deploy.md`. Usage: `/deploy lambda`, `/deploy vercel`, `/deploy all` (default). Handles zip rebuild, parallel push to both Lambdas, env-var drift detection, smoke tests, and Vercel prod deploy. `.claude/` is gitignored so the command stays on Dimi's machine only.

---

## 🔍 Verification before pitch

- [ ] Open public Vercel URL on a clean browser (incognito) — verify Pleven zone renders + clickable
- [ ] Click Pleven zone → assessment returns within 5s
- [ ] Trigger an alert during dry-run → Discord embed appears in channel
- [ ] Subscribe form submits successfully (requires whitelist fix above)
- [ ] Phone the public URL via LAN — confirm mobile view also works
- [ ] Backup screen recording captured (in case live demo dies)
- [ ] Anthropic form submitted + Bedrock returns real Claude response (no `[DEMO MODE]` text)
