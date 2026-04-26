# HydroTwin — Complete Pitch Brief & System Description

> **Handoff document.** This file describes the entire HydroTwin system in enough detail that another Claude Code instance (or any LLM) can read it and produce diagrams, slides, presenter notes, or visualizations from it without needing to read the codebase. Every component, flow, contract, and fallback is described in prose. Where diagrams would help, the section is labeled `[DIAGRAM HINT]` with the recommended diagram type and what it should contain.

---

## 0. Project Identity

- **Name:** HydroTwin
- **Tagline:** _"NIMH delivers the warning. bg-ALERT delivers the alarm. **HydroTwin delivers the decision.**"_
- **Event:** CASSINI Hackathon Bulgaria 2026, Sofia, 25–27 April 2026. Pitch slot: Sunday 27 April at 15:00.
- **One-line description:** A multi-region flood and drought early-warning system that combines real-time Copernicus Sentinel Earth Observation data with OpenMeteo weather feeds, runs an AWS Bedrock (Claude 3 Sonnet) reasoning step against Bulgaria-calibrated meteorological thresholds, and fans out email + Discord alerts to subscribed municipal authorities the moment any of 32 Bulgarian regions transitions out of a SAFE state.
- **Audience:** Bulgarian municipal authorities — civil-protection officers, mayors, emergency-response coordinators. Not meteorologists. Not the general public.
- **Positioning:** Decision-support layer between national meteorology (NIMH) and emergency activation (bg-ALERT).

---

## 1. High-Level Architecture (the whole picture)

The system has four physical zones:

1. **The user's browser.** A React/Vite single-page application served from Vercel. Renders a Mapbox satellite map with clickable region overlays (3 oblasts as polygons + 29 municipalities). Talks to the backend over HTTPS + JSON.
2. **AWS, the API tier.** API Gateway (HTTP API) routes incoming requests to one of eight AWS Lambda functions written in Python 3.10+.
3. **AWS, the data + AI tier.** Three DynamoDB tables hold subscriptions, cached region status snapshots, and citizen incident reports. AWS Bedrock hosts Claude 3 Sonnet, which all assessment requests run through.
4. **External services.** Copernicus Sentinel Hub Statistical API (Earth Observation), OpenMeteo (free weather), Brevo (transactional email), Discord (channel webhooks + per-user webhooks).

[DIAGRAM HINT — top-level architecture]
- Type: flowchart, top-down or left-to-right
- Boxes: User → Browser (Vercel/Vite/React/Mapbox) → API Gateway → 8 Lambdas (group: assess, cron, subscribe, unsubscribe, status, chat-alert, dams, reports) → DynamoDB (3 tables) and Bedrock (Claude 3 Sonnet); plus external arrows from Lambdas out to Sentinel Hub, OpenMeteo, Brevo, Discord
- Group boxes: cluster the 8 Lambdas inside an "AWS" cluster; cluster the 4 external services inside an "External" cluster
- Show that browser ↔ API Gateway is HTTPS+JSON and that cron is triggered by EventBridge (a clock icon) rather than by the user

---

## 2. The 8 AWS Lambda Functions

Every Lambda is written in Python, returns API Gateway-compatible JSON envelopes (`statusCode`, `headers` with CORS, `body` as JSON string), and handles the `OPTIONS` preflight. They share helper modules: `notifications.py` (Brevo + Discord + HMAC), `regions.py` (3 oblasts + 29 municipalities), `sentinel_extractor.py` (live EO + weather).

### 2.1 `/assess` — risk assessment for a single region
- **File:** `backend/lambda_handler.py`
- **Trigger:** API Gateway POST.
- **Input JSON:** `{ "region_id": "pleven", "bbox": [lon_min, lat_min, lon_max, lat_max] }`.
- **What it does:** fetches live Earth Observation + weather data for the bbox, loads the meteorology rules file from disk, builds a structured prompt, calls Claude on Bedrock at temperature 0.1 with max_tokens 1200, parses the strict-JSON response, and returns a structured assessment.
- **Returns:** `{ region_id, status, confidence, reasoning, reasoning_structured, sources }`.
- **Status values:** `SAFE`, `DROUGHT_WATCH`, `DROUGHT_WARNING`, `FLOOD_WATCH`, `FLOOD_WARNING`.
- **Confidence:** float 0.0–1.0.
- **Reasoning structured:** four keys — `whats_happening` (plain summary), `why_it_matters` (the actual numbers, bolded), `current_context` (seasonal trend), `next_step` (concrete action for a mayor today).
- **Latency in practice:** ~3–5 seconds end to end.

### 2.2 `cron` — autonomous re-assessment + transition fan-out
- **File:** `backend/cron_handler.py`
- **Trigger:** EventBridge Schedule, `rate(30 minutes)`.
- **Timeout:** 15 minutes (was 5; bumped when municipalities were added).
- **What it does:** iterates all 32 regions (3 oblasts + 29 municipalities). For each one, reads the prior status from `HydroTwinStatus`, runs the same assessment pipeline as `/assess`, writes the new snapshot back, and decides whether to fire alerts.
- **Transition logic:** alerts fire only when the status code _changes_ between runs. SAFE → SAFE is silent. Any non-trivial transition (SAFE → non-SAFE, non-SAFE → SAFE, between non-SAFE tiers) fires.
- **Fan-out:** on transition, posts to the shared Discord/Telegram operations channel, then scans `HydroTwinSubscriptions` for matching subscribers and sends each one a personalized email (Brevo) plus a per-user Discord webhook embed (if they configured one).
- **Returns a summary dict** with counts: `regions_succeeded`, `webhooks_fired`, `subscriber_emails_sent`, `subscriber_discord_sent`, `transitions` array.

### 2.3 `/subscribe` — multi-channel subscription
- **File:** `backend/subscribe_handler.py`
- **Trigger:** API Gateway POST.
- **Input JSON:** `{ email, region_id, discord_webhook?, phone?, telegram_chat? }`.
- **Validation:** email regex, region must be in known set, Discord webhook shape-checked against `^https://(...)\.discord(app)?\.com/api/webhooks/\d+/[\w-]+$`, phone in E.164.
- **Municipality roll-up:** if user subscribes to a municipality (e.g. `BGR.13.6_1`), the row is saved against the parent oblast (`pleven`). One subscription per oblast, not per municipality.
- **DynamoDB write:** `PutItem` with `ConditionExpression: attribute_not_exists(email) AND attribute_not_exists(region_id)`. Returns 409 on duplicate.
- **Welcome fan-out (immediate):** Brevo HTML email with current region status + AI reasoning + HMAC unsubscribe link, plus a Discord welcome embed posted to the user-supplied webhook (if any).
- **Returns:** 201 with `{ message, email, region_id, region_name, created_at, delivered: { email, discord }, rolled_up_to, requested_region_id }`.

### 2.4 `/unsubscribe` — HMAC-signed one-click
- **File:** `backend/unsubscribe_handler.py`
- **Trigger:** API Gateway GET (querystring) or POST (JSON body).
- **Input:** `{ e: email, r: region_id, t: token }`.
- **Token:** 16 hex characters of `HMAC-SHA256(UNSUBSCRIBE_SECRET, "email|region_id")`.
- **Verification:** constant-time comparison via `hmac.compare_digest()` to prevent timing oracles.
- **Action:** idempotent `DeleteItem` keyed on `(email, region_id)`. Clicking twice does not error.
- **Returns:** 200 with `{ message: "unsubscribed", email, region_id }`, or 400 on invalid/expired token.

### 2.5 `/status` — pre-computed snapshots
- **File:** `backend/status_handler.py`
- **Trigger:** API Gateway GET.
- **What it does:** scans the `HydroTwinStatus` table (small N — one row per region) and returns the latest snapshot for every region in one payload.
- **Used by:** the frontend on initial load, so the map can paint every region's status badge instantly without making 32 individual `/assess` calls.
- **Returns:** `{ regions: [...], generated_at }`. On scan failure: empty `regions` array plus `demo_mode: true` so the frontend renders neutral grey polygons.

### 2.6 `/chat-alert` — context-scoped Q&A assistant
- **File:** `backend/chat_handler.py`
- **Trigger:** API Gateway POST.
- **Persona:** "HydroSentry" — a deliberately scoped assistant for Bulgarian Civil Defense. Hard-capped at 3 sentences per reply. No free-form chat.
- **Input JSON:** `{ user_message, alert_context: { region_id, region_name, status, confidence, reasoning, eo_data: { ndvi, soil_moisture_pct, precip_mm_7d } } }`.
- **Bedrock call:** Claude 3 Sonnet, temperature 0.2, max_tokens 300.
- **Returns:** `{ reply }`. Falls back to a deterministic demo reply if Bedrock fails.

### 2.7 `/dams` — Bulgarian dam monitoring
- **File:** `backend/dams_handler.py`
- **Trigger:** API Gateway GET.
- **Monitored dams:** Kardzhali (Язовир Кърджали), Studen Kladenets (Язовир Студен Кладенец), Ivaylovgrad (Язовир Ивайловград).
- **Pipeline:** parses fill-percentage XLS files (historical), derives LOW/HIGH thresholds at the 25th/75th percentile, fetches live NDWI from Sentinel Hub for the past 14 days at each dam location, correlates NDWI on historical high-fill vs. low-fill dates to derive live NDWI thresholds, then assigns each dam an alert level: `WATER_REGIME`, `STABLE`, or `OPEN_GATES`.
- **Side effect:** fires the same Discord/Telegram channels as the region assessment system if any dam is non-STABLE.
- **Returns:** `{ dams: [{ id, name, lat, lon, fill_pct, volume_mln_m3, ndwi, alert_level, thresholds }], generated_at }`.

### 2.8 `/reports` — citizen incident submissions
- **File:** `backend/reports_handler.py`
- **Trigger:** API Gateway POST (citizen submits) or GET (operations team reads triage feed).
- **POST validation:** email regex, `region_id` ∈ {pleven, yambol, burgas, other}, description 10–500 chars.
- **POST returns:** 201 with the new `report_id` (UUID v4).
- **GET returns:** array of reports newest-first. On scan failure: empty array + `demo_mode: true`.

[DIAGRAM HINT — Lambda inventory]
- Type: simple two-column "service catalog" table or a fan-out diagram showing API Gateway pointing to all 8 Lambdas
- For each Lambda, a one-line "what it does" caption
- Visually distinguish the cron Lambda (clock icon, no API Gateway path) from the seven HTTP Lambdas

---

## 3. DynamoDB Schema (3 tables)

### 3.1 `HydroTwinStatus` — live snapshot per region
- **Partition key:** `region_id` (string). Examples: `pleven`, `yambol`, `burgas`, `BGR.13.6_1`.
- **No sort key** — exactly one row per region.
- **Attributes:**
  - `status` (string) — one of the five status codes.
  - `confidence` (Decimal, 0.0–1.0).
  - `reasoning` (string, markdown blob).
  - `reasoning_structured` (map) with the four keys described above.
  - `sources` (list of strings) — e.g. `["Sentinel Hub Statistical API + OpenMeteo"]`.
  - `assessed_at` (string, ISO-8601 UTC).
- **Written by:** the cron Lambda every 30 minutes.
- **Read by:** `/status` (instant map paint), `/assess` (cache-first fallback), the cron Lambda (to read prior status for transition detection).

### 3.2 `HydroTwinSubscriptions` — multi-channel subscribers
- **Partition key:** `email` (string).
- **Sort key:** `region_id` (string).
- **Composite key rationale:** the same email can subscribe to multiple oblasts cleanly (one row per email × region pair).
- **Attributes:**
  - `created_at` (string, ISO-8601 UTC).
  - `discord_webhook` (string, optional) — only stored if the user enabled it.
  - `phone` (string, optional) — E.164 format. Currently stored but SMS delivery is gated on AWS SNS sandbox approval.
  - `telegram_chat` (string, optional) — stored, not yet delivered (needs bot DM UX).
- **Written by:** `/subscribe`. Deleted by `/unsubscribe`.
- **Read by:** the cron Lambda on transition (filter scan by `region_id`).
- **No GSI** at hackathon scale — full-table scan with `region_id` filter is acceptable; would add a GSI on `region_id` if N grows.

### 3.3 `HydroTwinReports` — citizen incident reports
- **Partition key:** `report_id` (string, UUID v4).
- **Attributes:** `email`, `region_id`, `description` (10–500 chars), `lat` (Decimal), `lng` (Decimal), `submitted_at` (ISO-8601).
- **Written by:** `/reports` POST. Read by `/reports` GET (newest-first scan).
- **No GSI** at hackathon scale.

[DIAGRAM HINT — ER diagram of the 3 tables]
- Type: entity-relationship diagram, three boxes side by side
- Each box lists the attributes with type prefixes (string, decimal, map, list) and PK/SK markers
- Add a note next to `HydroTwinSubscriptions` saying "PK + SK lets one email subscribe to multiple oblasts"
- Add a note next to `HydroTwinStatus` saying "1 row per region, upserted by cron every 30 min"

---

## 4. Real Data Sources (the EO + weather pipeline)

The function `get_eo_and_weather_data(bbox: list) -> dict` in `backend/sentinel_extractor.py` is the sole integration point between the data tier and the assessment tier. Its return-dict schema is locked — `lambda_handler.py` and the Bedrock prompt depend on these exact keys.

### 4.1 Sentinel Hub Statistical API
- **Provider:** Copernicus Data Space Ecosystem.
- **Auth:** OAuth2 client credentials. Token endpoint: `https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token`. Stats endpoint: `https://sh.dataspace.copernicus.eu/statistics/v1`.
- **Bands fetched:**
  - **NDVI** from Sentinel-2 L2A (B4 red, B8 NIR). Range −1 to 1. Healthy vegetation 0.4–0.9, stressed 0.1–0.3.
  - **NDWI** from Sentinel-2 L2A (McFeeters 1996, B3/B8). Range −1 to 1. Open water > 0; flooded land 0.0–0.3.
- **Window:** 14 days rolling.
- **Cloud filter:** evalscript keeps only Scene Classification Layer values 4 (vegetation) and 5 (not-vegetated), discarding clouds and shadows.
- **Mosaicking:** `leastCC` (least-cloud-cover composite).
- **Resolution:** 0.01° ≈ 814 m at 43°N latitude.
- **Aggregation:** daily buckets (P1D).
- **Fallback:** if `SH_CLIENT_ID` or `SH_CLIENT_SECRET` is missing, the extractor skips Sentinel Hub entirely and uses OpenMeteo only. The `source` field in the output dict notes this.

### 4.2 OpenMeteo
- **Provider:** OpenMeteo (free, no API key).
- **Endpoint:** `https://api.open-meteo.com/v1/forecast`.
- **Window:** 30 days historical + 2 days forecast.
- **Metrics fetched:**
  - `precipitation_sum` (daily) → aggregated to last 7 days and last 30 days.
  - `temperature_2m_max` (daily) → 7-day maximum.
  - `soil_moisture_0_to_7cm` (hourly) → current percentage and 7-day delta.
  - `precipitation` next 24 h (forecast).

### 4.3 Output schema (LOCKED — do not rename keys)
The merged dict that flows into the Bedrock prompt:
- `ndvi` (float)
- `soil_moisture_pct` (float)
- `precip_mm_7d` (float)
- `precip_mm_30d` (float)
- `river_level_m` (float, currently None — TODO Copernicus GloFAS or in-situ gauge)
- `flood_extent_km2` (float, derived from NDWI thresholding)
- `temp_max_c` (float)
- `drought_index` (float, currently None — TODO ERA5-derived SPI-3)
- `data_timestamp` (string, ISO-8601 UTC, end of observation window)
- `source` (string, human-readable attribution + DQ warning)
- `ndwi` (float, anomaly enrichment)
- `soil_moisture_7d_delta` (float, anomaly enrichment)
- `forecast_precip_24h_mm` (float, anomaly enrichment)

[DIAGRAM HINT — data pipeline]
- Type: left-to-right flowchart
- Three nodes feeding into the extractor function: "Sentinel-2 L2A NDVI/NDWI · 14-day · cloud-filtered", "OpenMeteo precip/temp/soil/forecast · 30-day window"
- Extractor box: "sentinel_extractor.py — get_eo_and_weather_data(bbox)"
- Output box on the right: "Locked output schema" with the 10–13 key names listed
- Add a small dotted line back from the output to "lambda_handler.py" indicating it's the integration contract

---

## 5. The AI Layer (Bedrock + Claude 3 Sonnet)

### 5.1 Model
- **Service:** AWS Bedrock.
- **Model ID:** `anthropic.claude-3-sonnet-20240229-v1:0` (env var `BEDROCK_MODEL_ID`).
- **Region:** `us-east-1` by default (env `BEDROCK_REGION`).
- **API:** Bedrock Messages API, `anthropic_version: bedrock-2023-05-31`.
- **Parameters:** `temperature: 0.1` (deterministic), `max_tokens: 1200`.

### 5.2 Prompt construction (three layers)
The Bedrock user prompt is assembled at runtime by `call_bedrock_agent()` in `lambda_handler.py`:

1. **Audience framing.** The prompt opens with: _"You are advising municipal authorities in Bulgaria — civil-protection officers, mayors, emergency-response coordinators."_ This anchors the response style. Claude writes for non-experts who need to take action TODAY, not for meteorologists.
2. **Authoritative rules — `meteorology_rules.md` injected verbatim.** This file (owned by the meteorologist) contains the five status code definitions, threshold tables for floods (precipitation, soil moisture, river level), threshold tables for droughts (NDVI, drought index, soil moisture), SAFE conditions, and compound rules (e.g. "if A and B then escalate to X"). It's loaded from the Lambda package at runtime and dropped in under a `=== METEOROLOGY RULES & THRESHOLDS ===` heading.
3. **Live sensor data as JSON.** The output of `get_eo_and_weather_data(bbox)` is JSON-formatted under a `=== CURRENT OBSERVATIONS ===` heading.

The prompt then closes with **writing rules**: no jargon, translate NDVI/SPI/SAR/NDWI into plain language, lead with a headline (no numbers), put numbers in `why_it_matters` with bold formatting, situate against seasonal norms, end with a concrete action.

### 5.3 Response shape (strict JSON)
Claude is told to return:
```
{
  "status": "SAFE | DROUGHT_WATCH | DROUGHT_WARNING | FLOOD_WATCH | FLOOD_WARNING",
  "confidence": 0.0-1.0,
  "reasoning": "<markdown, 2-4 short paragraphs, under 600 chars>",
  "reasoning_structured": {
    "whats_happening": "<1-2 sentences, plain summary>",
    "why_it_matters": "<1-3 short bullets or sentences with numbers in **bold**>",
    "current_context": "<1-2 sentences, seasonal trend>",
    "next_step": "<1-2 sentences, concrete action for a mayor TODAY>"
  }
}
```

### 5.4 Demo-mode fallback (the demo never breaks)
If anything goes wrong on the Bedrock side — `NoCredentialsError`, `EndpointResolutionError`, throttling, JSON parse failure — the Lambda catches the exception and returns a hardcoded `FLOOD_WATCH` with confidence 0.78, generic flood-safety guidance in all four structured sections, and a marker `_(Demo mode — live AI temporarily offline: <ExceptionName>)_` so the frontend can display a subtle hint. The Lambda **never returns 500** to API Gateway.

[DIAGRAM HINT — AI layer]
- Type: flowchart showing prompt construction
- Three input boxes feeding into "Claude 3 Sonnet (temp 0.1, 1200 tokens, strict JSON)": "(1) Audience framing", "(2) meteorology_rules.md injected verbatim", "(3) Live sensor data as JSON"
- Single output box on the right showing the four reasoning_structured keys + status + confidence
- Add a side-branch labeled "If Bedrock fails → hardcoded FLOOD_WATCH demo response" pointing to a dimmed fallback box

---

## 6. User Click Flow (the 3-second magic)

This is the core demo moment. When a user clicks a region marker:

1. **Click handler** (`pages/Overview.jsx`, `handleRegionClick`) sets the React state to the selected region and pushes the URL to `/?region=<region_id>` so the click is shareable and bookmarkable.
2. **Cache-first paint.** The frontend already has the latest snapshot from `/status` cached at page load. It renders the AlertPanel _instantly_ from that cached data.
3. **Background fetch.** In parallel, a `POST /assess` call is fired with `{ region_id, bbox }`.
4. **Lambda `/assess`** runs:
   - In parallel: pulls Sentinel-2 NDVI + NDWI from Sentinel Hub, and pulls precipitation + soil moisture + temp + forecast from OpenMeteo.
   - Loads `meteorology_rules.md` from the Lambda package.
   - Sends the assembled prompt to Bedrock.
   - Parses the strict-JSON response.
   - Optionally upserts the snapshot to `HydroTwinStatus`.
   - Returns the assessment.
5. **AlertPanel re-renders** with the fresh assessment. If the live result differs from the cached snapshot, the user sees a smooth update.
6. **If the network call fails**, the frontend catches the error and calls `buildDemoResponse(region)` to render a hardcoded `FLOOD_WATCH` with a yellow "simulated data" banner. The demo never shows a broken state.

What appears in the AlertPanel:
- Color-coded status badge (SAFE green, WATCH yellow, WARNING red).
- Confidence bar.
- Four reasoning sections (`whats_happening`, `why_it_matters`, `current_context`, `next_step`).
- Precipitation chart (last 7 days).
- Forecast outlook (next 24 h).
- Synoptic chart (cyclone/pressure context).
- Citizen incident reports list for that region.
- Subscribe call-to-action (email + optional Discord webhook).

[DIAGRAM HINT — user click flow]
- Type: sequence diagram (UML style)
- Lifelines: User, Frontend, API Gateway, /assess Lambda, Sentinel Hub, OpenMeteo, Bedrock, HydroTwinStatus
- Steps in order: click → URL update → cache-first paint (note over Frontend) → POST /assess → invoke Lambda → parallel arrows to Sentinel Hub and OpenMeteo → load rules → invoke Bedrock → return JSON → optional snapshot upsert → 200 response → AlertPanel renders
- Use a `par` block for the parallel SH + OM calls

---

## 7. Subscribe Flow

When a user submits the subscribe form (email required; Discord webhook, phone, telegram chat optional):

1. **Frontend** posts `{ email, region_id, discord_webhook?, phone?, telegram_chat? }` to `/subscribe`.
2. **`/subscribe` Lambda** validates inputs (email regex, region in known set, Discord webhook shape regex, phone E.164).
3. **Municipality roll-up.** If `region_id` is a municipality (e.g. `BGR.13.6_1`), `parent_oblast(region_id)` returns the parent oblast (`pleven`). The subscription is stored against the oblast.
4. **DynamoDB `PutItem`** with `ConditionExpression: attribute_not_exists(email) AND attribute_not_exists(region_id)`. If the row already exists, the conditional check fails and the Lambda returns 409.
5. **Read current snapshot** for the region from `HydroTwinStatus` so the welcome message can include up-to-date status + reasoning.
6. **Welcome fan-out (parallel):**
   - **Brevo email.** `notifications.send_email()` posts to the Brevo Transactional API (`https://api.brevo.com/v3/smtp/email`) with a dark-themed HTML template. Subject: `✅ Subscribed: HydroTwin alerts for {region_name}`. Body includes status badge, AI reasoning, deep link to the region (`/?region=<id>`), and an HMAC-signed unsubscribe link.
   - **Discord welcome embed.** If the user supplied a webhook URL, an embed titled `✅ Subscribed — {region_name}` is posted there with the current status, confidence, and reasoning.
7. **Response 201** with `{ delivered: { email: true|false, discord: true|false } }` so the UI can show what actually went out.

If the DynamoDB table is missing, the Lambda still returns 201 with `demo_mode: true` and a warning, so the demo doesn't break.

[DIAGRAM HINT — subscribe flow]
- Type: sequence diagram
- Lifelines: User, Frontend, /subscribe Lambda, HydroTwinSubscriptions, HydroTwinStatus, Brevo, Discord
- Show the conditional branch: "Already exists → 409" vs. "New → save → fetch snapshot → parallel welcome (Brevo + Discord) → 201"
- Use an `alt` block for the existing-vs-new branch and a `par` block for the email + Discord fan-out

---

## 8. Cron Transition Alerts (the autonomous brain)

This is the biggest differentiator vs. a static dashboard — it runs while everyone sleeps.

- **Trigger:** EventBridge Schedule with `rate(30 minutes)`.
- **Scope:** all 32 regions (3 oblasts: pleven, yambol, burgas; 29 municipalities by GADM GID_2 codes).
- **Per-region pipeline:**
  1. Read prior status from `HydroTwinStatus` (`GetItem` by `region_id`).
  2. Run the same `assess_region(region_id, bbox)` pipeline as `/assess`.
  3. Write the new snapshot back to `HydroTwinStatus` (DynamoDB Decimal conversion for floats).
  4. Compare prior status to new status → fire-decision.
  5. If a transition is detected and the region is an oblast (not a sub-municipality), fire alerts.

### 8.1 Transition matrix
| Prior status         | New status        | Action                          |
|----------------------|-------------------|---------------------------------|
| _none_ (first run)   | `SAFE`            | silent (no fire)                |
| _none_ (first run)   | non-SAFE          | fire (initial alert)            |
| `SAFE`               | `SAFE`            | silent                          |
| `SAFE`               | any non-SAFE      | fire (escalation)               |
| non-SAFE             | `SAFE`            | fire (recovery / all-clear)     |
| non-SAFE             | different non-SAFE| fire (re-grade up or down)      |

### 8.2 Fan-out on transition
1. **Operations channel.** Post to the comma-separated list of Discord webhooks (and Telegram bot, if configured) defined in `WEBHOOK_URL` env. Same colour-coded embed as the manual `/assess` flow.
2. **Subscribers.** Scan `HydroTwinSubscriptions` filtered by `region_id`. For each row:
   - Build a personalized alert email via `notifications.render_alert_email()` — subject like `🌊 Flood Watch — Pleven Oblast`, intro line `"Status just changed from SAFE to FLOOD_WATCH"`, body with the AI reasoning and an HMAC unsubscribe link.
   - Send via Brevo.
   - If the row has a `discord_webhook`, also post a per-user Discord embed.
3. **Failures are non-fatal.** Each channel is wrapped in try/except. One dead webhook does not break the email batch.

### 8.3 Why this matters commercially
Notifications + Bedrock costs are billed only on _state changes_, not every cron run. A subscriber for `pleven` gets exactly one email when conditions deteriorate, not 48 emails per day.

[DIAGRAM HINT — cron flow]
- Type: flowchart, top-down
- Start node: "EventBridge cron rate(30 min)"
- Loop node: "For each of 32 regions"
- Sequential boxes: read prior status → run assess_region → write new snapshot → decision diamond "Status changed?"
- Decision branches: "SAFE → SAFE → silent" (gray dead-end) and "any transition → fire"
- Fire branch fans out: "Discord ops channel" + "Scan subscribers WHERE region_id" → "Per subscriber: email + per-user Discord webhook"
- Color the silent branch grey/muted and the fire branch red/active

---

## 9. Unsubscribe Flow (HMAC-signed, one-click)

Every email footer contains a link of the form:
```
https://hydrotwin.vercel.app/unsubscribe?e={url-encoded-email}&r={region_id}&t={hmac_token}
```

### 9.1 Token construction
- Message: `"{email}|{region_id}".encode()`.
- Algorithm: `HMAC-SHA256(UNSUBSCRIBE_SECRET, message).hexdigest()[:16]`.
- Length: 16 hex chars (64 bits) — unguessable in practice without the secret.
- Secret: `UNSUBSCRIBE_SECRET` env var. Default development value must be overridden in production.

### 9.2 Click-through flow
1. User clicks the link in their email.
2. The frontend `/unsubscribe` page parses the querystring, then POSTs `{ e, r, t }` to the `/unsubscribe` Lambda.
3. The Lambda recomputes the expected token and compares with `hmac.compare_digest()` — constant-time, no timing oracle.
4. If valid, `DeleteItem` keyed on `(email, region_id)`. Idempotent — a second click is a no-op delete.
5. Returns 200 with `{ message: "unsubscribed", email, region_id }`.
6. Page renders "✅ You're unsubscribed from {region_name} alerts."

[DIAGRAM HINT — unsubscribe flow]
- Type: sequence diagram
- Lifelines: Email (alert), User, /unsubscribe page, /unsubscribe Lambda, HydroTwinSubscriptions
- Add a note at the top describing the link format
- Show the verification branch (`alt` block): valid token → DeleteItem → 200; invalid token → 400

---

## 10. Frontend Routes

The frontend is a React Router single-page app served from Vercel.

| Route               | Component        | Purpose                                                        | Layout |
|---------------------|------------------|----------------------------------------------------------------|--------|
| `/`                 | `Overview.jsx`   | Mapbox satellite map + AlertPanel (the operational dashboard)  | yes (sidebar) |
| `/incidents`        | `Incidents.jsx`  | Read-only triage list of citizen reports (GET `/reports`)      | yes |
| `/sources`          | `Sources.jsx`    | Data source documentation and status                           | yes |
| `/dams`             | `Dams.jsx`       | Bulgarian dam monitoring dashboard (GET `/dams`)               | yes |
| `/submit`           | `Submit.jsx`     | Public citizen incident submission form (POST `/reports`)      | no  |
| `/unsubscribe`      | `Unsubscribe.jsx`| HMAC-token landing page (POST `/unsubscribe`)                  | no  |
| `*`                 | `NotFound.jsx`   | 404 catch-all                                                  | no  |

### Deep-link patterns
- `/?region=pleven` — open the map with Pleven Oblast pre-selected and AlertPanel open.
- `/?region=BGR.13.9_1` — open with a specific municipality (Nikopol, in this case).
- `/unsubscribe?e=...&r=...&t=...` — one-click email unsubscribe (HMAC-verified).

[DIAGRAM HINT — route map]
- Type: small flowchart, left-to-right
- Two clusters: "Inside Layout (sidebar)" containing `/`, `/incidents`, `/sources`, `/dams`; and "Public (no layout)" containing `/submit`, `/unsubscribe`, `*` 404
- Add a small note below listing the deep-link patterns

---

## 11. Demo-Mode Fallbacks (the secret weapon)

Both backend and frontend degrade gracefully when AWS or external services are unavailable. **The demo never crashes — by design.**

### 11.1 Backend fallbacks
- **Bedrock unavailable** (no creds, throttle, parse error) → Lambda returns hardcoded `FLOOD_WATCH` with 0.78 confidence + generic flood-safety guidance in all four structured sections + `_(Demo mode — live AI temporarily offline: <ExceptionName>)_` marker.
- **Sentinel Hub credentials missing** → extractor skips Sentinel Hub, uses OpenMeteo only, notes it in `source: "OpenMeteo only (Sentinel Hub credentials not set — NDVI/NDWI are estimated)"`.
- **Brevo not configured** → `notifications.send_email()` returns False, logs `[email demo-mode] Would have sent to ...`, the calling Lambda still returns success.
- **DynamoDB table missing** → `/subscribe` returns 201 with `demo_mode: true`; `/status` returns empty `regions: []` with `demo_mode: true`; `/reports` GET returns empty array with `demo_mode: true`.
- **Webhook delivery failure** → caught and logged; never blocks the API response.

### 11.2 Frontend fallbacks
- **`/assess` unreachable** → `fetchAssessment` catch block calls `buildDemoResponse(region)` and renders a hardcoded `FLOOD_WATCH` plus a yellow banner: _"Live API unavailable — showing simulated assessment data."_
- **`/status` empty or unreachable** → all region polygons paint in neutral grey (#64748B). Clicking a region still works (falls through to live `/assess` then `buildDemoResponse`).
- **Mapbox token missing** → page still loads, just without the satellite basemap.

[DIAGRAM HINT — fallbacks]
- Type: two-column flowchart with red "fail" boxes on the left and green "recovery" boxes on the right
- Pairs (each red → green):
  - "Bedrock fails" → "Hardcoded FLOOD_WATCH + Demo mode tag"
  - "Sentinel Hub creds missing" → "OpenMeteo only + note in source"
  - "Brevo unset" → "Log demo-mode, still return success"
  - "DynamoDB missing" → "/subscribe 201 + demo_mode flag"
  - "/assess unreachable" → "buildDemoResponse + yellow banner"
  - "/status empty" → "Neutral grey polygons"
- Title the diagram: "The demo never breaks — by design"

---

## 12. Tech Stack Reference

| Layer                | Technology                                                                |
|----------------------|---------------------------------------------------------------------------|
| Backend runtime      | AWS Lambda (Python 3.10+); handler `lambda_handler.lambda_handler`        |
| Local dev server     | Flask + flask-cors on port 5050 (`backend/local_server.py`)               |
| AI / LLM             | AWS Bedrock — `anthropic.claude-3-sonnet-20240229-v1:0`                  |
| AWS SDK              | boto3                                                                     |
| EO data              | Copernicus Sentinel-1 / -2 / -3, ECMWF ERA5, OpenMeteo                    |
| Edge trigger         | API Gateway (HTTP API), EventBridge Schedule                              |
| Storage              | DynamoDB (3 tables)                                                       |
| Frontend framework   | React 18 + Vite 5                                                         |
| Styling              | Tailwind CSS 3.4 (mono font: JetBrains Mono → Fira Code → system mono)    |
| Map                  | react-map-gl + mapbox-gl 3.4 (style: satellite-streets-v12 with fog)      |
| Frontend hosting     | Vercel (Root Directory = `frontend`)                                      |
| Email                | Brevo Transactional API                                                   |
| Channel notifications| Discord webhooks (channel + per-user); Telegram bot (channel only)        |
| Auth on frontend     | None (public read; subscribe is open)                                     |
| Auth on unsubscribe  | HMAC-SHA256 token (no login needed)                                       |

### Environment variables
- **Backend:** `WEBHOOK_URL` (Discord/Telegram), `BEDROCK_MODEL_ID`, `BEDROCK_REGION`, `SH_CLIENT_ID`, `SH_CLIENT_SECRET`, `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, `UNSUBSCRIBE_SECRET`, `FRONTEND_BASE_URL`, `SUBSCRIPTIONS_TABLE`.
- **Frontend:** `VITE_MAPBOX_TOKEN` (scoped `styles:read, tiles:read`), `VITE_API_ENDPOINT`.

---

## 13. The Monitored Regions

3 oblasts (top-level Bulgarian administrative units) plus 29 municipalities (GADM GID_2 codes nested under those oblasts) = 32 regions total.

| Oblast    | Risk profile                                  | Municipalities (count) |
|-----------|-----------------------------------------------|------------------------|
| Pleven    | Spring snowmelt floods on the Danube tributaries | ~11 (e.g. Nikopol, Belene, Pleven city) |
| Yambol    | Mixed flood + drought (Tundzha river basin)   | ~5                     |
| Burgas    | Flash floods, coastal flooding, occasional drought | ~13               |

The frontend renders these as polygons (GADM GeoJSON) over a Mapbox satellite basemap. The backend is region-agnostic — every Lambda accepts any `bbox` from the request body, so adding a new region is a single-row entry in `frontend/src/data/regions.js` (or wherever the canonical list lives) plus a row in `backend/regions.py`.

[DIAGRAM HINT — regions map]
- Type: stylized map of Bulgaria with three colored oblast polygons (Pleven north, Yambol southeast, Burgas east coast) and a count badge on each ("11 municipalities", etc.)
- Or simpler: a single row of three colored chips labeled "Pleven · 11 municipalities", "Yambol · 5 municipalities", "Burgas · 13 municipalities"

---

## 14. Demo Walkthrough (8 steps for the live pitch)

| # | Action                                       | Talking point                                                                                       |
|---|----------------------------------------------|-----------------------------------------------------------------------------------------------------|
| 1 | Open the map                                 | "3 oblasts + 29 municipalities, Mapbox satellite, click anywhere."                                  |
| 2 | Click **Pleven Oblast**                      | "Cache-first paint — instant. Then in the background, /assess hits Sentinel + OpenMeteo + Bedrock." |
| 3 | Show AlertPanel                              | "4 plain-language sections. No NDVI jargon — what's happening, why it matters, context, next step." |
| 4 | Click a municipality (e.g. Nikopol)          | "GADM GID_2 codes, 29 of them — same backend, smaller bbox."                                        |
| 5 | Subscribe with email                         | "201 → welcome email lands → Discord embed fires."                                                  |
| 6 | Open `/dams`                                 | "3 dams correlated with Sentinel NDWI — alert levels: WATER_REGIME, STABLE, OPEN_GATES."            |
| 7 | Open `/incidents`                            | "Citizens close the loop — POST /reports, triage feed for civil protection."                       |
| 8 | Mention cron                                 | "30-min EventBridge → 32 regions → only fire on transitions → emails + per-user Discord."          |

---

## 15. The 30-Second Pitch Sentence

> _"Click any region in Bulgaria → in 3 seconds we pull live Sentinel-2 NDVI, NDWI, and OpenMeteo weather, feed Bulgaria-calibrated meteorological thresholds and the live numbers to **Claude on Bedrock**, and return a structured assessment a mayor can act on. Subscribe, and you'll get an email + Discord alert the moment your oblast transitions out of SAFE — and we run that check **every 30 minutes, automatically, for all 32 regions**."_

---

## 16. Hard NOs (preserve these in any redesign)

- ❌ Never rename keys in `get_eo_and_weather_data()` return dict — the Bedrock prompt depends on them.
- ❌ Never change the function signature `get_eo_and_weather_data(bbox: list) -> dict`.
- ❌ Never modify `meteorology_rules.md` thresholds without the meteorologist's approval.
- ❌ Never remove the demo fallback in `lambda_handler.call_bedrock_agent()`.
- ❌ Never remove the demo fallback in `App.jsx` `fetchAssessment()`.
- ❌ Never make `trigger_webhook` failures fatal.
- ❌ Never break the Lambda response envelope (`statusCode`, `headers` with CORS, `body` as JSON string).
- ✅ Always keep CORS headers on every response (including `OPTIONS` preflight).
- ✅ Always use temperature 0.1 and request strict JSON in the Bedrock prompt.
- ✅ Always preserve 44×44 px minimum touch targets on map markers (WCAG 2.5.5).
- ✅ Always use `100dvh` on root elements so mobile browser chrome doesn't clip the map.

---

## 17. File Map (for reference)

| Path                                          | Purpose                                                          |
|-----------------------------------------------|------------------------------------------------------------------|
| `backend/lambda_handler.py`                   | `/assess` orchestrator + Bedrock + webhook + CORS               |
| `backend/cron_handler.py`                     | EventBridge 30-min fan-out                                      |
| `backend/subscribe_handler.py`                | `/subscribe` Lambda                                             |
| `backend/unsubscribe_handler.py`              | `/unsubscribe` Lambda                                           |
| `backend/status_handler.py`                   | `/status` snapshot reader                                       |
| `backend/chat_handler.py`                     | `/chat-alert` HydroSentry assistant                             |
| `backend/dams_handler.py`                     | `/dams` monitoring                                              |
| `backend/reports_handler.py`                  | `/reports` citizen submissions                                  |
| `backend/sentinel_extractor.py`               | Live Sentinel Hub + OpenMeteo extractor                         |
| `backend/notifications.py`                    | Brevo + Discord + HMAC token helpers                            |
| `backend/regions.py`                          | 3 oblasts + 29 municipalities + parent_oblast() roll-up         |
| `backend/meteorology_rules.md`                | Authoritative thresholds, injected verbatim into Bedrock prompt |
| `backend/local_server.py`                     | Flask wrapper that mimics API Gateway → Lambda for local dev    |
| `frontend/src/App.jsx`                        | React Router setup                                              |
| `frontend/src/pages/Overview.jsx`             | Map + AlertPanel host                                           |
| `frontend/src/components/AlertPanel.jsx`      | Status panel + subscribe CTA                                    |
| `frontend/src/pages/Unsubscribe.jsx`          | HMAC unsubscribe landing                                        |
| `frontend/src/pages/Dams.jsx`                 | Dam dashboard                                                   |
| `frontend/src/pages/Incidents.jsx`            | Citizen triage feed                                             |
| `frontend/src/pages/Submit.jsx`               | Citizen incident submission form                                |

---

## 18. What this document is for

This file is a self-contained briefing. Hand it to another Claude Code instance (or any LLM) and ask for any of:

- **Diagrams.** Each `[DIAGRAM HINT]` block above describes the diagram type, what should be in it, and what to label. Generate Mermaid, draw.io XML, ExcalidrawLib JSON, or static images from those hints.
- **Slide deck.** Sections 1, 5, 6, 8, 11, 14, 15 map directly to a 7-slide deck. Section 14 is the live demo script. Section 15 is the closing line.
- **Speaker notes.** Each section has enough detail to write 30–60 seconds of narration.
- **One-pager / two-pager handout.** Sections 0, 1, 5, 8, 14, 15 condensed.
- **Architecture review document.** Sections 2, 3, 4, 5, 7, 8, 9, 11 in full.
- **Investor / EUSPA-grade summary.** Sections 0, 1, 8 (cron commercial argument), 11 (resilience), 15.

_HydroTwin · CASSINI Hackathon Bulgaria 2026 · Sofia · 25–27 April_
