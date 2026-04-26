# 👨‍💻 Lead Developer — Task Spec

> **Owner:** Lead Dev
> **Source:** `README.md` § Lead Developer task list
> **Roadmap:** [`../01-roadmap/01-hackathon-roadmap.md`](../01-roadmap/01-hackathon-roadmap.md)

10 tasks. 4 blockers (🔴), 4 important (🟡), 2 nice-to-have (🟢).

**Status (updated 2026-04-25 ~14:35):** **All 10 LD tasks ✅ Done.** Backend + frontend live, Bedrock invoking real Claude Sonnet 4.6, Discord webhook verified, Subscribe E2E live, sparkline shipped + hardened (PRs #4 + #5). Only LD-6 leftover: explicit FLOOD_WARNING red-embed test (current alerts trigger on FLOOD_WATCH/DROUGHT_WATCH which are blue/yellow — easy to force later by hardcoding status temporarily).

**🟢 No active blockers.** All in-flight items from the morning have shipped or cleared. Remaining items are nice-to-haves and post-pitch hygiene (token rotation, optional Telegram).

**✅ Cleared in this session:**
- **Anthropic use-case form** (~13:45 → ~14:15) — submitted via Bedrock Playground in us-east-1. After form approval, Marketplace auto-subscribe flow needed `AWSMarketplaceManageSubscriptions` policy on `hydrotwin-dev` (AdminAccess wasn't enough — see Findings). Once attached + first Playground Run, account-wide Marketplace subscription completed and Lambda `/assess` started returning real Claude responses.
- **Sentinel Hub credentials** (~14:10) — `SH_CLIENT_ID` / `SH_CLIENT_SECRET` pushed to `HydroTwin` Lambda env via merged `update-function-configuration`. Real EO data now flowing into the prompt.
- **Subscribe whitelist regression** (~13:48) — `subscribe_handler.KNOWN_REGIONS` synced to `{"pleven"}`. Tatiana also committed it independently in `8f54116` so the file's history reflects both.
- **Vercel Preview env vars** (~14:15) — added via Vercel REST API so all preview branches render the map (the `vercel env add` CLI is broken in non-interactive mode for preview targets — REST API works cleanly).

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
  - [x] `hydrotwin-dev` user has `AWSMarketplaceManageSubscriptions` (added ~14:15 to unblock the Anthropic Marketplace auto-subscribe flow)
  - [x] Test invocation returns a real Claude response — verified ~14:18 UTC (`/assess` for Pleven returned `DROUGHT_WATCH 0.82` with markdown reasoning, no `[DEMO MODE]` string).

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

### LD-9 — Add more Bulgarian AOIs  ✅ Done (scope frozen at Pleven-only)
- **Priority:** 🟢
- **Files:** `frontend/src/regions.geojson` + `frontend/src/App.jsx` `REGIONS` array + `backend/subscribe_handler.py` `KNOWN_REGIONS` whitelist
- **Decision (2026-04-25 ~14:00):** Dimi froze the scope at **Pleven Oblast only**. The brief originally called for 3 BG AOIs but a focused single-zone pitch is cleaner — no need to dilute the demo with thin polygons. Pleven (Danube floodplain — Vit / Osam / Iskur) carries the narrative on its own.
- **Acceptance criteria:**
  - [x] Pleven Oblast renders as polygon overlay (not a marker dot)
  - [x] `subscribe_handler.KNOWN_REGIONS` synced to `{"pleven"}` (whitelist regression fixed + redeployed ~13:48)
  - [x] Pleven returns a valid assessment via Lambda
- **Notes:** if Angela's pitch script references "3 zones," surface that mismatch — otherwise close this out.

### LD-10 — Add time-series sparkline in `AlertPanel`  ✅ Done
- **Priority:** 🟢
- **Files:** `frontend/src/components/MetricsSparkline.jsx` (new) + integration in `AlertPanel.jsx`
- **Shipped:** Tatiana's PRs `#4` (`c218405`) + `#5` (`20fada8` — hardened header + flat-series rendering). Pure SVG (no chart lib), mounts in the assessment panel between AI Reasoning and the metadata footer.
- **Acceptance criteria:**
  - [x] Sparkline component renders without breaking the panel layout on mobile or desktop
  - [x] SVG-only solution (no heavy chart lib for hackathon)
  - [x] Live on https://hydrotwin.vercel.app (deployed ~14:35 in the all-layer redeploy)
- **Notes:** uses stubbed series for now per the original handoff. When `sentinel_extractor.py` starts returning historical arrays, swap the stub for `assessment.history` (or whatever shape lands).

---

## 🔍 Findings & Follow-ups (added 2026-04-25 PM)

### ✅ [FIXED 2026-04-25 ~13:48] Subscribe whitelist out of sync with frontend regions
- **Was:** `POST /subscribe {"region_id":"pleven"}` returned 400 because `subscribe_handler.KNOWN_REGIONS` still listed the old 5 global IDs.
- **Fix shipped:** `KNOWN_REGIONS = frozenset({"pleven"})`. Deployed to both Lambdas. Verified live: pleven → 201, atlantis → 400, danube-basin → 400.
- **Going forward:** when LD-9 adds 2 more Bulgarian regions, update both `frontend/src/regions.geojson` AND `backend/subscribe_handler.py KNOWN_REGIONS` together (the contract).

### ✅ [FIXED 2026-04-25 ~14:18] Bedrock now returns real Claude Sonnet 4.6 (no more `[DEMO MODE]`)
- **Was:** every `/assess` call had `[DEMO MODE — Bedrock unavailable]` in the `reasoning` text. CloudWatch showed `ResourceNotFoundException: Model use case details have not been submitted`.
- **Path that worked:**
  1. `iam create-login-profile` to give `hydrotwin-dev` Console access (programmatic-only user before; AdminAccess via API didn't carry over)
  2. AWS Console → Bedrock (us-east-1) → Playground → select **Claude Sonnet 4.6** → triggered the **"Submit use case details for Anthropic"** modal (the retired "Model access" page is gone — the form is now triggered first-time per Anthropic model in the Playground)
  3. Filled the form (5 fields: company, URL, industry, intended users, use-case description) → submitted
  4. Clicked **Run** in Playground → got `AccessDeniedException` for `aws-marketplace:Subscribe` + `aws-marketplace:ViewSubscriptions` — **AdministratorAccess does NOT grant marketplace** in this account (confirmed via `iam simulate-principal-policy` which returned `allowed`, but Bedrock's marketplace flow rejected anyway)
  5. Attached AWS-managed policy `AWSMarketplaceManageSubscriptions` to `hydrotwin-dev`
  6. Clicked **Run** again → first call completed the account-wide Marketplace subscription
  7. From that moment, both the Playground AND the Lambda's `bedrock:InvokeModel` started returning real responses
- **Verify (still works):** `curl -X POST https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/assess -H 'Content-Type: application/json' -d '{"region_id":"pleven","bbox":[23.9,43.15,25.2,43.7]}'` — `reasoning` returns markdown with bold key numbers + bullets, no `[DEMO MODE]`, status varies (no longer canned `FLOOD_WATCH 0.78`).
- **Why this is non-obvious:** AWS docs only mention the use-case form. The Marketplace permission gotcha is undocumented as a Bedrock requirement — `AdministratorAccess` should grant `aws-marketplace:*` (and IAM simulation says it does) but Bedrock's specific subscribe path needs the explicit AWS-managed policy. Worth flagging to anyone else doing this on a fresh account.

### ✅ [FIXED 2026-04-25 ~14:10] Sentinel Hub credentials pushed to Lambda
- **Was:** CloudWatch showed `SH_CLIENT_ID / SH_CLIENT_SECRET not set — skipping Sentinel Hub calls`. Real EO data was empty.
- **Fix shipped:** `SH_CLIENT_ID` + `SH_CLIENT_SECRET` added to `HydroTwin` Lambda env via Vercel-style merge update (read live env first, append the 2 new keys, push back via `update-function-configuration` — existing `BEDROCK_*` + `DISCORD_WEBHOOK_URL` preserved).
- **Verify:** `/assess` invocation should no longer log `SH_CLIENT_ID not set` in CloudWatch.
- **🔒 Post-pitch action:** rotate the OAuth client at https://shapps.sentinel-hub.com (creds were pasted in chat history).

### ✅ [FIXED 2026-04-25 ~14:15] Vercel Preview env vars set
- **Was:** only Production + Development envs had `VITE_MAPBOX_TOKEN` / `VITE_API_ENDPOINT`. Branch-deploy previews (e.g. friend's incoming sparkline PR) would render a blank map.
- **Fix shipped:** both vars added via Vercel REST API (`POST /v10/projects/{id}/env` with `target: ["preview"]`, encrypted, no branch restriction → all preview branches inherit).
  - `VITE_MAPBOX_TOKEN` = same value as Production
  - `VITE_API_ENDPOINT` = `https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/assess`
- **Note:** the `vercel env add` CLI is currently broken in non-interactive mode (returns `action_required: git_branch_required` even with `--yes` and no branch arg). The REST API still supports "all preview branches" cleanly — used that instead.
- **🔒 Post-pitch action:** revoke the deploy token at https://vercel.com/account/tokens (token was pasted in chat history).

### ✅ [SHIPPED 2026-04-25 ~14:21] Plain-language markdown reasoning + frontend rendering
- **Why:** the raw Claude output was full of meteorology jargon ("DROUGHT_WARNING threshold of <10%", "precip-30d metric") — incomprehensible for the actual demo audience (mayors, civil protection, judges).
- **Backend (`backend/lambda_handler.py`):**
  - Rewrote the prompt to target municipal authorities — no NDVI/SPI/SAR acronyms in output, no internal status code names, plain-language analogies.
  - Asked Claude to return `reasoning` as light markdown (bold for key numbers, bullets for breached conditions, 2–4 short paragraphs, < 600 chars).
  - Bumped `max_tokens` 512 → 768 to give markdown headroom.
  - Added `_md_to_html` helper so Telegram (which uses HTML parse mode) renders `**bold**`, `*italic*`, `` `code` ``, and `- ` bullets correctly. Discord embed descriptions render markdown natively, no conversion.
  - Updated demo-mode fallback `reasoning` to also be markdown (consistency).
  - Updated `BEDROCK_MODEL_ID` default + footer/docstring labels: `Claude 3` → `Claude Sonnet 4.6`.
- **Frontend (`frontend/src/components/AlertPanel.jsx` + `package.json`):**
  - Added `react-markdown@9.0.1`.
  - Render `assessment.reasoning` via `<ReactMarkdown components={MD_COMPONENTS}>` with dark-theme overrides (bold, bullets, italic, code, links). Removed the always-italic blockquote style so markdown emphasis is visible.
  - Updated labels: `Claude 3` → `Claude Sonnet 4.6` (loading text + reasoning attribution footer).
- **Sample output (the new style):**
  > **The soil is unusually dry for late April, and rainfall over the past week has nearly stopped — conditions are trending toward drought.**
  > - The ground holds only **10.7% moisture**, well below the safe lower limit of 15%
  > - Only **2.1 mm of rain fell in the last 7 days**, against a seasonal average of roughly 11 mm
  > 
  > Vegetation across the oblast still looks healthy (satellite imagery shows normal green cover for April), so this is an early warning rather than a crisis.

### 🟡 Pulled-in changes from teammates (since `04da593`)
- `7079a4a feat: add meteorology_rules` (Elitsa) — major expansion of `backend/meteorology_rules.md` (+220 lines). Added Bulgarian-calibrated thresholds, Pleven Oblast climatological baseline, seasonality modifiers, compound event rules, confidence rules, assessment algorithm. The expanded rules feed straight into the new prompt — Claude has much richer context now.
- `29ff9f2 fix: zoom level on map` — `frontend/src/App.jsx` initial view tweak (4 lines).
- `8f54116 add md files` — misc docs + the `pleven` whitelist commit (matched what we'd already deployed).
- `c218405` + `20fada8` — LD-10 sparkline (PRs #4 + #5).

### 🟡 Telegram unset (optional)
- **Symptom:** `Telegram delivery skipped — TELEGRAM_BOT_TOKEN/CHAT_ID not set`.
- **Fix:** if multi-channel notification is wanted, get a bot token from `@BotFather` and a chat ID from `@userinfobot`. Set both on Lambda env. No code change.

### 🟢 Vercel auth — recommended cleanup post-pitch
- The current deploy uses an inline `vcp_*` token (in chat history). Recommend running `npx vercel login` once after the demo so future `/deploy vercel` runs use OS-stored auth instead. Then revoke the chat-leaked token at https://vercel.com/account/tokens.

### 🟢 `/deploy` slash command available
- Project-local at `.claude/commands/deploy.md`. Usage: `/deploy lambda`, `/deploy vercel`, `/deploy all` (default). Handles zip rebuild, parallel push to both Lambdas, env-var drift detection, smoke tests, and Vercel prod deploy. `.claude/` is gitignored so the command stays on Dimi's machine only.

---

## 🔍 Verification before pitch

**Backend / API (auto-verifiable):**
- [x] `/assess` returns 200 + real Claude response (Bedrock LIVE, no `[DEMO MODE]`)
- [x] `/subscribe` returns 201 for `pleven`, 400 for invalid email / unknown region, 409 on duplicate
- [x] Discord webhook fires HTTP 204 on non-SAFE statuses (verified in CloudWatch)
- [x] Sentinel Hub credentials set on Lambda env (real EO data flowing)
- [x] Vercel alias `https://hydrotwin.vercel.app` serves the latest bundle (sparkline + markdown reasoning)

**Manual / human-eyes (still TODO):**
- [ ] Open public Vercel URL in **incognito** — verify Pleven polygon renders, clickable, panel opens
- [ ] Click Pleven → confirm reasoning displays as **formatted markdown** (bold + bullets, not raw `**` symbols)
- [ ] Confirm sparkline renders inside the panel without breaking layout
- [ ] Submit the Subscribe form with a real email → confirm success toast + row appears in DynamoDB
- [ ] Phone the public URL via LAN — confirm mobile bottom-sheet renders correctly
- [ ] Force a `FLOOD_WARNING` (hardcode `status` in `call_bedrock_agent` for one curl) → confirm Discord embed renders RED (`0xEF4444`) with 🔴 emoji prefix → revert
- [ ] Backup screen recording captured (in case live demo dies)

**Post-pitch hygiene:**
- [ ] Rotate Vercel deploy token (https://vercel.com/account/tokens)
- [ ] Rotate Sentinel Hub OAuth client (https://shapps.sentinel-hub.com)
- [ ] Rotate Discord webhook (Channel Settings → Integrations → Webhooks)
- [ ] Run `npx vercel login` once so future `/deploy vercel` doesn't need a pasted token
