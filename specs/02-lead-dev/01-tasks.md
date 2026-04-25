# 👨‍💻 Lead Developer — Task Spec

> **Owner:** Lead Dev
> **Source:** `README.md` § Lead Developer task list
> **Roadmap:** [`../01-roadmap/01-hackathon-roadmap.md`](../01-roadmap/01-hackathon-roadmap.md)

10 tasks. 4 blockers (🔴), 4 important (🟡), 2 nice-to-have (🟢).

---

## 🔴 Tier 1 — Blockers (Friday evening → Saturday night)

### LD-1 — Deploy Lambda to AWS + create API Gateway HTTP endpoint
- **Priority:** 🔴 Blocker
- **Files:** `backend/lambda_handler.py` + AWS Console
- **What:** Package the backend as a Lambda zip, upload to AWS, create an API Gateway HTTP API in front of it with a `POST /assess` route.
- **Acceptance criteria:**
  - [ ] Lambda function `HydroTwin` exists in AWS (Runtime Python 3.10+, Handler `lambda_handler.lambda_handler`, Timeout 30s, Memory 256 MB)
  - [ ] API Gateway URL responds to `POST /assess` with a valid JSON body
  - [ ] CORS preflight (`OPTIONS`) returns 200 with `Access-Control-Allow-*` headers
  - [ ] `curl -X POST <gateway-url>/assess -d '{"region_id":"danube-basin","bbox":[8,42,30,52]}'` returns a 200 response
- **Dependencies:** AWS account access
- **Notes:** Build the zip with `pip install -r requirements.txt -t . && zip -r ../hydrotwin-backend.zip . --exclude ".venv/*" "local_server.py" ".env*"`

### LD-2 — Set Lambda environment variables
- **Priority:** 🔴 Blocker
- **Files:** AWS Console → Lambda → Configuration → Environment variables
- **What:** Set the three required env vars so the Lambda can call Bedrock and post to Discord.
- **Acceptance criteria:**
  - [ ] `WEBHOOK_URL` = real Discord webhook URL
  - [ ] `BEDROCK_MODEL_ID` = `anthropic.claude-3-sonnet-20240229-v1:0`
  - [ ] `BEDROCK_REGION` = a Bedrock-enabled region (default `us-east-1`)
- **Dependencies:** LD-1 (Lambda exists), LD-5 (Discord webhook URL ready)

### LD-3 — Add IAM policy `bedrock:InvokeModel` to Lambda execution role
- **Priority:** 🔴 Blocker
- **Files:** AWS IAM
- **What:** Without this policy, the Lambda will throw `AccessDeniedException` when calling `bedrock-runtime.invoke_model`. The demo fallback will hide it locally — but the real demo must hit Bedrock.
- **Acceptance criteria:**
  - [ ] Lambda execution role has an inline or attached policy allowing `bedrock:InvokeModel` on `arn:aws:bedrock:*::foundation-model/anthropic.claude-3-sonnet-*`
  - [ ] Test invocation returns a real Claude response (not the `[DEMO MODE — Bedrock unavailable]` fallback string)
- **Dependencies:** LD-1

### LD-4 — Deploy frontend to Vercel
- **Priority:** 🔴 Blocker
- **Files:** `frontend/`
- **What:** Push the Vite build to Vercel with `Root Directory = frontend` and the two required env vars.
- **Acceptance criteria:**
  - [ ] Public URL renders the map + all region markers
  - [ ] `VITE_MAPBOX_TOKEN` set in Vercel project settings (scoped to `styles:read, tiles:read`)
  - [ ] `VITE_API_ENDPOINT` set to the deployed API Gateway URL from LD-1
  - [ ] Clicking a region marker triggers a real network call to the Lambda (verify in DevTools Network tab)
- **Dependencies:** LD-1 (API Gateway URL ready), Mapbox token available
- **Command:** `cd frontend && npx vercel --prod`

---

## 🟡 Tier 2 — Important (Sunday morning)

### LD-5 — Create Discord channel + webhook
- **Priority:** 🟡 (Friday-evening prep, but blocking LD-2)
- **Files:** Discord server settings + `backend/lambda_handler.py` → `trigger_webhook()`
- **What:** Create a server channel (e.g. `#hydrotwin-alerts`), generate a webhook URL via Channel Settings → Integrations → Webhooks, paste it into `WEBHOOK_URL`. Alerts fire automatically on every `WATCH` or `WARNING` status (already wired in `lambda_handler.lambda_handler` line 272).
- **Acceptance criteria:**
  - [ ] Webhook URL works: `curl -X POST <webhook-url> -H "Content-Type: application/json" -d '{"content":"test"}'` → message appears in channel
  - [ ] URL pasted into Lambda env var `WEBHOOK_URL`

### LD-6 — End-to-end Discord alert test
- **Priority:** 🟡
- **Files:** `backend/local_server.py` (or deployed Lambda)
- **What:** Force a `FLOOD_WARNING` assessment and verify the Discord embed is rendered correctly.
- **Acceptance criteria:**
  - [ ] Discord embed shows: red colour (`0xEF4444`), 🔴 emoji prefix, status field = `FLOOD_WARNING`, confidence % rendered correctly, region_id field populated, reasoning text in description
  - [ ] Webhook delivery happens within 2s of API call
  - [ ] Lambda response returns to client even if webhook fails (non-fatal)
- **Dependencies:** LD-5
- **How to force:** Either temporarily hardcode the assessment dict in `lambda_handler.call_bedrock_agent()`, or send a curl payload that triggers thresholds Claude will assess as warning.

### LD-7 — Wire "Subscribe to Alerts" button to real `/subscribe` endpoint
- **Priority:** 🟡
- **Files:** `frontend/src/components/AlertPanel.jsx` → `handleSubscribe()`
- **What:** Replace the `window.alert()` stub with a real `fetch()` to a `/subscribe` endpoint. Form should collect at minimum an email or webhook handle.
- **Acceptance criteria:**
  - [ ] Subscribe button opens an inline form (or modal) with email field
  - [ ] On submit, posts to `${VITE_API_ENDPOINT.replace('/assess','/subscribe')}` with `{email, region_id}`
  - [ ] Shows success / error toast
- **Dependencies:** LD-8

### LD-8 — Add `/subscribe` Lambda + DynamoDB table
- **Priority:** 🟡
- **Files:** new `backend/subscribe_handler.py` + DynamoDB table `HydroTwinSubscriptions`
- **What:** New Lambda handler at `POST /subscribe` that writes `{email, region_id, created_at}` to a DynamoDB table.
- **Acceptance criteria:**
  - [ ] DynamoDB table `HydroTwinSubscriptions` exists (PK = `email`, SK = `region_id`)
  - [ ] Lambda has IAM permission `dynamodb:PutItem` on that table
  - [ ] API Gateway route `POST /subscribe` wired to the new Lambda
  - [ ] Returns 201 on success, 400 on invalid email
- **Dependencies:** LD-1 (API Gateway exists)

---

## 🟢 Tier 3 — Nice-to-have (only if everything else done)

### LD-9 — Add more monitored regions
- **Priority:** 🟢
- **Files:** `frontend/src/App.jsx` → `REGIONS` array
- **What:** Add Central Asia / Amazon basin / other regions. Each entry needs `id`, `name`, `description`, `longitude`, `latitude`, `bbox`, `color`.
- **Acceptance criteria:**
  - [ ] New marker(s) render on the map
  - [ ] Clicking each new region returns a valid assessment

### LD-10 — Add time-series sparkline in `AlertPanel`
- **Priority:** 🟢
- **Files:** `frontend/src/components/` (new component, e.g. `MetricsSparkline.jsx`)
- **What:** Render a small sparkline of recent sensor metrics (precipitation, river level) inside the assessment panel.
- **Acceptance criteria:**
  - [ ] Sparkline renders without breaking the panel layout on mobile or desktop
  - [ ] Library choice: prefer SVG-only solution (no heavy chart lib for hackathon)
- **Notes:** Requires the extractor to return historical arrays — coordinate with Data Analysts.

---

## 🔍 Verification before pitch

- [ ] Open public Vercel URL on a clean browser (incognito)
- [ ] Click each of the 5 region markers — each returns an assessment within 5s
- [ ] At least one region triggers a Discord alert during the demo dry-run
- [ ] Phone the public URL via LAN — confirm mobile view also works
- [ ] Backup screen recording captured (in case live demo dies)
