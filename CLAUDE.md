# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this workspace.

> 📖 **Read these first for full context:**
>
> - `specs/01-roadmap/01-hackathon-roadmap.md` — 40h timeline, tier ordering, dependency graph, demo script
> - `specs/02-lead-dev/01-tasks.md` — **Dimi's** 10 tasks (the only ones you should write code for)
> - `specs/05-cross-team-asks/01-questions-for-team.md` — what to ping teammates for, with answers tracked at the bottom
> - `initial_context.md` — full hackathon brief (audience positioning, pitch script, hard NOs)
> - `README.md` — architecture diagram, quick-start, original task lists per team
> - `backend/meteorology_rules.md` — authoritative threshold matrix injected into the Bedrock prompt
> - `data_science/README.md` — integration contract for the EO/weather data extractor

## 🎯 Project Overview

**HydroTwin** 💧 — a multi-region **flood & drought early-warning system** built for **CASSINI Hackathon Bulgaria 2026** (Sofia, 25–27 April). Pitch: **Sunday 27 April · 15:00**. Real-time Copernicus Sentinel EO data + OpenMeteo weather feeds → AWS Bedrock (Claude 3 Sonnet) → risk assessment → Discord webhook + map UI.

**Positioning** (per `initial_context.md`): *"NIMH delivers the warning. bg-ALERT delivers the alarm. HydroTwin delivers the decision."* — a decision-support layer between national meteorology and emergency activation, aimed at municipal authorities.

- **Phase (now):** Hackathon MVP — single AWS Lambda + Vite/React PWA, demo-ready end-to-end with a built-in fallback so the UI works even with no AWS creds
- **Status:** 🟢 Lead Dev scaffolding done. Waiting on **Data Analysts** (real EO extractor) + **Meteorologist** (validated thresholds + regional baselines)

## 👥 Team & Scope

| Member | Role | Owns |
|---|---|---|
| **Dimi (the user)** | Solo coder + architecture lead | Everything in `specs/02-lead-dev/01-tasks.md` (Lambda, frontend, deploys, Discord wiring, /subscribe endpoint) |
| Tatiana Dragu | Frontend lead (per brief) | TBD — currently Dimi is doing all frontend; coordinate scope |
| Alexandre Payen | Data / geospatial / ML | `backend/sentinel_extractor.py`, AOI polygons, evalscripts, replay backfill |
| Lyuben Branzalov | AI summary layer | Claude prompt engineering (may overlap with Dimi's Bedrock prompt — coordinate) |
| Elitsa Ilieva | Meteorologist (NIMH — domain expert) | `backend/meteorology_rules.md`, threshold calibration, replay event pick |
| Angela Nedyalkova | Project lead, pitch | Pitch script, 2-page summary |
| Val Stavrev | Space industry advisor | Pitch framing, EUSPA-grade language |

**Dimi codes solo with Claude Code.** Don't write or modify files owned by others (`backend/sentinel_extractor.py`, `backend/meteorology_rules.md`, `data_science/`) unless explicitly asked. If their work is needed to unblock Dimi's task, **flag what to ask them** via `specs/05-cross-team-asks/01-questions-for-team.md` rather than guessing.

## 📍 Current State (Updated 2026-04-25)

### What's Done

- ✅ **Monorepo scaffold** — `backend/` (Python Lambda) + `frontend/` (Vite + React 18) + `data_science/` (notebooks placeholder)
- ✅ **Lambda orchestrator** (`backend/lambda_handler.py`) — parses API Gateway event → calls extractor → loads rules file → invokes Bedrock → fires webhook on non-SAFE → returns CORS-friendly JSON. Handles `OPTIONS` preflight, has a **demo-mode fallback** that returns a realistic `FLOOD_WATCH` if Bedrock errors (NoCredentialsError, throttling, JSON parse, etc.) so the demo never 500s
- ✅ **Local dev server** (`backend/local_server.py`) — Flask wrapper around `lambda_handler` so the same code runs on `http://localhost:5050/assess` without AWS. Loads `.env.local` then `.env.example`
- ✅ **Discord/Telegram webhook** (`trigger_webhook`) — colour-coded embeds per status, non-fatal on failure (never blocks the Lambda response)
- ✅ **Bedrock prompt** — injects `meteorology_rules.md` verbatim as authoritative context, current sensor data as JSON, asks for strict JSON response (status / confidence / reasoning). `temperature=0.1`, `max_tokens=512`
- ✅ **Frontend map UI** (`frontend/src/App.jsx`) — Mapbox satellite map with 5 region markers (Mediterranean, Sahel, Danube, Po Valley, Nile Delta). Click → POST to `VITE_API_ENDPOINT` → render `AlertPanel`. **Built-in demo fallback** if API unreachable
- ✅ **AlertPanel** (`frontend/src/components/AlertPanel.jsx`) — responsive: bottom sheet on mobile (`<640px`, ~68vh), right sidebar on desktop. Status badge, AI confidence bar, reasoning blockquote, subscribe CTA stub
- ✅ **Mobile-first PWA shell** — `viewport-fit=cover`, `100dvh`, 44×44 px touch targets (WCAG 2.5.5), `apple-mobile-web-app-capable`, black-translucent status bar
- ✅ **`meteorology_rules.md` draft** — alert status definitions, flood + drought threshold tables, SAFE conditions, compound event rules (flash flood, drought-heat). Regional baselines are placeholders
- ✅ **`.env.example` files** for both backend + frontend, README documents every variable

### What's NOT Done Yet

- ❌ **`sentinel_extractor.py` is a STUB** — returns hardcoded dummy dict. Owned by Data Analysts. Must be replaced with real Copernicus + OpenMeteo API calls. **Schema must NOT change** (see Integration Contract below)
- ❌ **`meteorology_rules.md` regional baselines (Section 5)** — placeholder values, owned by Meteorologist. WMO 1991–2020 normals required before go-live
- ❌ **No tests** — `data_science/notebooks/` is empty, no `backend/tests/`
- ❌ **No data-freshness guard** in extractor — must reject observations > 24 h old
- ❌ **SMS delivery** — UI accepts a phone number but `notifications.send_sms()` is a demo-mode stub until AWS SNS sandbox approval (set `SMS_ENABLED=1` to flip)
- ❌ **Per-user Telegram** — needs bot DM UX before chat_id can be captured

### Subscribe pipeline (NEW · 2026-04-26)

- ✅ **Multi-channel `/subscribe` Lambda** — accepts `email` (required), `discord_webhook` (optional, validated), `phone` + `telegram_chat` (stored, not delivered yet). Stores in DynamoDB `HydroTwinSubscriptions` with PK=email + SK=region_id
- ✅ **Brevo welcome email** — fires on successful subscribe with current region status + deep link + HMAC-signed unsubscribe link. Falls through to demo-mode if `BREVO_API_KEY` unset
- ✅ **Per-user Discord welcome embed** — if subscriber provided a webhook URL, immediately POSTs a "you're subscribed" embed there too
- ✅ **Cron fan-out on transitions** — `cron_handler` queries subscribers for the transitioning oblast and sends each one an alert email + Discord embed. Bills only on transitions (not every 30-min cron run)
- ✅ **`/unsubscribe` Lambda + frontend page** — one-click HMAC-token-signed unsubscribe links in every email, lands on themed `/unsubscribe` page that POSTs to the API
- ✅ **Region URL deep-linking** — clicking a region updates `?region=<id>` in the URL; `/?region=burgas` opens that panel directly. Used by email links

### 🔒 Stack is locked — do NOT propose re-scaffolding

The brief in `initial_context.md` originally specified **Next.js 14 + Leaflet + Supabase + Anthropic-direct + Brevo**. Dimi (lead) decided on **2026-04-25** to keep the existing **Vite + Mapbox + Python Lambda + Bedrock + Discord** stack. This is final.

**Do NOT:**
- ❌ Suggest migrating to Next.js, Leaflet, Supabase, or Anthropic-direct
- ❌ Propose archiving / re-scaffolding the repo
- ❌ Re-litigate framework choices

**DO:**
- ✅ Adapt brief features (3 Bulgarian AOIs, replay button, anomaly detection, Claude summaries, AOI polygons, email alerts) onto the existing stack — only the framework choices were overridden, the product spec still applies
- ✅ Translate brief-stack-coupled features (e.g. "Supabase RLS") to equivalents on the current stack (e.g. DynamoDB IAM)
- ✅ Ask before assuming when a brief feature doesn't have an obvious mapping

### ⚠️ Brief vs README task list — known divergence

`README.md` task lists (the source of truth per lead call, mirrored into `specs/02-lead-dev/`, `specs/03-data-analysts/`, `specs/04-meteorologist/`) were authored against the **old prototype** (5 global regions, AWS Bedrock, Discord). The brief describes a **different product** (3 Bulgarian AOIs, Brevo email, replay button = pitch centerpiece). Per Dimi's lead call, follow the README task list. If a brief feature is critical and missing from the README list, surface it explicitly — don't silently re-shape work toward the brief.

### Quick Commands

```bash
# ── Backend (local Lambda dev) ────────────────────────────────────────────
pip3 install --user --break-system-packages flask flask-cors requests boto3 python-dotenv
python3 backend/local_server.py          # http://localhost:5050/assess

# ── Frontend (Vite dev server) ────────────────────────────────────────────
cd frontend
npm install
npm run dev -- --host                    # http://localhost:5173 + LAN URL

# ── Production builds ─────────────────────────────────────────────────────
cd frontend && npm run build             # → dist/
cd backend && pip install -r requirements.txt -t . && \
  zip -r ../hydrotwin-backend.zip . --exclude ".venv/*" "local_server.py" ".env*"
```

### Smoke test the backend

```bash
curl -X POST http://localhost:5050/assess \
     -H "Content-Type: application/json" \
     -d '{"region_id": "danube-basin", "bbox": [8.0, 42.0, 30.0, 52.0]}'
```

## 🛠️ Tech Stack (Source of Truth)

| Layer                  | Technology                                                  |
| ---------------------- | ----------------------------------------------------------- |
| Backend runtime        | **AWS Lambda (Python 3.10+)**, handler `lambda_handler.lambda_handler` |
| Local dev server       | Flask + flask-cors (port 5050)                              |
| AI / LLM               | **AWS Bedrock — `anthropic.claude-3-sonnet-20240229-v1:0`** |
| AWS SDK                | boto3 (pre-installed in Lambda runtime)                     |
| EO data sources        | Copernicus Sentinel-1 / -2 / -3, ECMWF ERA5, OpenMeteo      |
| Edge trigger           | API Gateway (HTTP API or REST API)                          |
| Frontend framework     | **React 18 + Vite 5**                                       |
| Styling                | **Tailwind CSS 3.4** (mono font stack: JetBrains Mono → Fira Code → system mono) |
| Map                    | **react-map-gl + mapbox-gl 3.4** (satellite-streets-v12 style with fog) |
| Frontend hosting       | Vercel (Root Directory = `frontend`)                        |
| Notifications (out)    | Discord webhook (default) or Telegram bot endpoint          |
| Notifications (in TBD) | Web Push, DynamoDB-backed `/subscribe` Lambda               |

## 📦 Repository Structure

```
hydro-twin/
├── backend/
│   ├── lambda_handler.py        ✅ Orchestrator — Bedrock call + webhook + CORS
│   ├── sentinel_extractor.py    🔧 STUB (Data Analysts) — dummy dict, schema locked
│   ├── meteorology_rules.md     🔧 DRAFT (Meteorologist) — injected verbatim into prompt
│   ├── local_server.py          ✅ Flask shim that mimics API Gateway → Lambda
│   ├── requirements.txt         ✅ requests, boto3 (+ flask, flask-cors, dotenv for local)
│   └── .env.example             ✅ WEBHOOK_URL, BEDROCK_MODEL_ID, BEDROCK_REGION
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx              ✅ Map + REGIONS array + fetch + demo fallback
│   │   ├── main.jsx             ✅ React 18 createRoot bootstrap
│   │   ├── index.css            ✅ Tailwind + dvh full-height + Mapbox dark overrides
│   │   └── components/
│   │       └── AlertPanel.jsx   ✅ Responsive panel (bottom sheet ⇄ sidebar)
│   ├── index.html               ✅ PWA meta tags, viewport-fit=cover, 💧 favicon
│   ├── package.json             ✅ react 18, react-map-gl 7, mapbox-gl 3, tailwind 3
│   ├── vite.config.js           ✅ envPrefix VITE_, sourcemaps on
│   ├── tailwind.config.js       ✅ Scans index.html + src/**/*.{js,jsx,ts,tsx}
│   └── .env.example             ✅ VITE_MAPBOX_TOKEN, VITE_API_ENDPOINT
│
└── data_science/
    ├── README.md                ✅ Integration contract — required dict keys
    └── notebooks/               🔧 Empty — analysts add EDA + extractor prototypes here
```

**Rule:** the **only** integration point between teams is the `get_eo_and_weather_data(bbox)` function signature and its return-dict schema. Cross-team boundaries are sacred — see Integration Contract below.

## 🚨 Critical Stack Rules (NON-NEGOTIABLE)

These guarantee the demo always works and team boundaries stay clean:

- ❌ **NEVER** rename or remove keys in the `get_eo_and_weather_data()` return dict — `lambda_handler.py` and the Bedrock prompt depend on the schema. Add new keys freely
- ❌ **NEVER** change the function signature `get_eo_and_weather_data(bbox: list) -> dict` — analysts and orchestrator are decoupled by this contract
- ❌ **NEVER** modify `meteorology_rules.md` thresholds without the Meteorologist's approval — they go straight into the Claude prompt as authoritative context
- ❌ **NEVER** remove the demo fallback in `lambda_handler.call_bedrock_agent()` — it's what keeps the hackathon demo bullet-proof when AWS creds / Bedrock access are flaky
- ❌ **NEVER** remove the demo fallback in `App.jsx` `fetchAssessment()` — same reason, frontside
- ❌ **NEVER** make `trigger_webhook` failures fatal — webhook delivery must not block the API response to the client
- ❌ **NEVER** commit `.env.local`, `.env`, or any file containing AWS keys / webhook URLs
- ❌ **NEVER** ship Mapbox tokens scoped beyond `styles:read, tiles:read` to the public bundle — they end up in the JS chunk
- ❌ **NEVER** break the Lambda response envelope (`statusCode`, `headers` with CORS, `body` as JSON string) — API Gateway requires this exact shape
- ✅ **ALWAYS** keep CORS headers on every response (including the `OPTIONS` preflight short-circuit)
- ✅ **ALWAYS** use low temperature (`0.1`) and request strict JSON in the Bedrock prompt — assessments must be deterministic and parseable
- ✅ **ALWAYS** preserve the 44×44 px minimum touch targets on map markers (WCAG 2.5.5) — drivers/responders use this on phones in the field
- ✅ **ALWAYS** keep `100dvh` (not `100vh`) on root elements so the map fills correctly when mobile browser chrome shows/hides

## 🤝 Team Ownership & Integration Contracts

One repo, three owners. Stay inside your boundary:

| Path                              | Owner                                    | Status      |
| --------------------------------- | ---------------------------------------- | ----------- |
| `frontend/`                       | Dimi (Lead Dev)                          | ✅ Ready    |
| `backend/lambda_handler.py`       | Dimi (Lead Dev)                          | ✅ Ready    |
| `backend/local_server.py`         | Dimi (Lead Dev)                          | ✅ Ready    |
| `backend/sentinel_extractor.py`   | Alexandre Payen (Data Analysts)          | 🔧 Stub     |
| `backend/meteorology_rules.md`    | Elitsa Ilieva (Meteorologist · NIMH)     | 🔧 Draft    |
| `data_science/`                   | Alexandre Payen (Data Analysts)          | 🔧 Empty    |
| `specs/02-lead-dev/`              | Dimi                                     | ✅ Ready    |
| `specs/03-data-analysts/`         | Read-only (context for Dimi)             | ✅ Ready    |
| `specs/04-meteorologist/`         | Read-only (context for Dimi)             | ✅ Ready    |
| `specs/05-cross-team-asks/`       | Dimi (track answers from teammates here) | ✅ Ready    |

### Extractor Contract (Data Analysts ↔ Lead Dev)

`lambda_handler.py` calls exactly one function:

```python
from sentinel_extractor import get_eo_and_weather_data
result = get_eo_and_weather_data(bbox=[lon_min, lat_min, lon_max, lat_max])
```

**Required dict keys** (units in docstring — do NOT rename):

| Key                 | Type  | Source                                      |
| ------------------- | ----- | ------------------------------------------- |
| `ndvi`              | float | Sentinel-2 B4/B8                            |
| `soil_moisture_pct` | float | Sentinel-1 SAR backscatter or ESA CCI       |
| `precip_mm_7d`      | float | OpenMeteo / ERA5                            |
| `precip_mm_30d`     | float | OpenMeteo / ERA5                            |
| `river_level_m`     | float | Sentinel-3 SRAL altimetry / in-situ gauge   |
| `flood_extent_km2`  | float | Sentinel-1 GRD + flood mapping              |
| `temp_max_c`        | float | OpenMeteo                                   |
| `drought_index`     | float | SPI-3 / PDSI from ERA5                      |
| `data_timestamp`    | str   | ISO-8601 UTC, observation-window end        |
| `source`            | str   | Human-readable dataset note / DQ warning    |

### Meteorology Rules Contract (Meteorologist ↔ Lead Dev)

`backend/meteorology_rules.md` is **loaded at runtime** by `lambda_handler.py` and **injected verbatim** into the Bedrock prompt under `=== METEOROLOGY RULES & THRESHOLDS ===`. The Markdown structure (sections 1–7, threshold tables) is the contract. Renaming a threshold or restructuring a table changes how Claude reasons about the data.

- The five status codes (`SAFE | DROUGHT_WATCH | DROUGHT_WARNING | FLOOD_WATCH | FLOOD_WARNING`) are **also** referenced by the frontend (`AlertPanel` `STATUS_META`) and the webhook colour map. Add or rename a code → update **all three** sites
- Compound rules ("if A and B → escalate to X") are interpreted by Claude — keep them in plain English, no pseudo-code

## 🗺️ Monitoring Regions

5 regions are hardcoded in `frontend/src/App.jsx` `REGIONS[]`. Adding a new region requires only an entry there (id, name, longitude, latitude, bbox, color). The backend is region-agnostic — it accepts any `bbox` from the request body.

| `region.id`          | bbox (lon_min, lat_min, lon_max, lat_max) | Risk profile                       |
| -------------------- | ----------------------------------------- | ---------------------------------- |
| `mediterranean-basin`| `-6.0, 30.0, 37.0, 47.0`                  | Drought (summer dry season)        |
| `sahel-region`       | `-17.0, 10.0, 40.0, 20.0`                 | Chronic drought                    |
| `danube-basin`       | `8.0, 42.0, 30.0, 52.0`                   | Spring snowmelt floods             |
| `po-valley`          | `6.5, 43.5, 14.5, 46.5`                   | Autumn flash floods                |
| `nile-delta`         | `25.0, 22.0, 37.0, 32.0`                  | Saltwater intrusion + Nile floods  |

## 🌐 Environment Variables

```bash
# ── backend/.env.local (Lambda env vars in AWS Console) ───────────────────
WEBHOOK_URL=https://discord.com/api/webhooks/...   # Discord or Telegram endpoint
BEDROCK_MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0
BEDROCK_REGION=us-east-1                            # Must be a Bedrock-enabled region
AWS_ACCESS_KEY_ID=...                               # Local dev only — Lambda uses IAM role
AWS_SECRET_ACCESS_KEY=...                           # Local dev only

# ── frontend/.env.local ───────────────────────────────────────────────────
VITE_MAPBOX_TOKEN=pk.eyJ1...                        # Scope: styles:read, tiles:read
VITE_API_ENDPOINT=https://<api-id>.execute-api.us-east-1.amazonaws.com/prod/assess
# Local dev: http://localhost:5050/assess
```

🔒 **Never commit any `.env` file.** Use `.env.example` as the template — both directories already have one.

## 💡 Demo-First Philosophy

This is a **hackathon project**. The single most important property is **"the demo never breaks"**:

- Both layers (Lambda + frontend) ship with a graceful fallback that returns a believable `FLOOD_WATCH` assessment if the upstream service is unreachable
- The frontend `console.warn`s and shows a yellow banner ("Live API unavailable — showing simulated assessment data") instead of dropping into an error state
- The Lambda catches **every** Bedrock exception (`NoCredentialsError`, `EndpointResolutionError`, throttling, JSON parse) — never returns 500
- The webhook trigger is wrapped in `try/except` — a failed webhook is logged and ignored

When making changes, **preserve these fallbacks**. Removing them to "clean up" the code will break the demo at the worst possible moment.

## 🔍 Post-Change Verification

Before declaring a change done:

1. **Backend** — run `python3 backend/local_server.py` and `curl` `/assess` with at least one region payload. Check the JSON envelope (`status`, `confidence`, `reasoning`)
2. **Frontend** — run `npm run dev -- --host`, click each region marker, verify the panel renders on both desktop (≥640 px) and mobile (DevTools device toolbar or real phone via LAN URL)
3. **CORS** — if you touch the response envelope, verify the `OPTIONS` preflight returns 200 with `Access-Control-Allow-*` headers
4. **Schema lock** — if you edited `sentinel_extractor.py`, verify all 10 required keys are still present (`ndvi`, `soil_moisture_pct`, `precip_mm_7d`, `precip_mm_30d`, `river_level_m`, `flood_extent_km2`, `temp_max_c`, `drought_index`, `data_timestamp`, `source`)
5. **Status codes alignment** — if you added a new status, grep for it in three files: `meteorology_rules.md`, `lambda_handler.py` `STATUS_META`, `frontend/src/components/AlertPanel.jsx` `STATUS_META`

**Confidence assessment** at the end of significant changes:

- 🟢 **95–100%** — Single file, fallback paths verified, no schema impact
- 🟡 **80–94%** — Multi-file, locally smoke-tested, no edge cases obviously missed
- 🟠 **60–79%** — Touches contracts (extractor schema, response envelope, status codes), needs end-to-end verification
- 🔴 **<60%** — High risk (auth, IAM, AWS infra), needs hands-on validation by the user

## 🚦 Hackathon Roadmap (Lead Dev priorities)

> Full per-team task lists live in `README.md`. Lead Dev's blockers:

| # | Priority | Task |
| - | -------- | ---- |
| 1 | 🔴 | Deploy Lambda to AWS + create API Gateway HTTP endpoint |
| 2 | 🔴 | Set Lambda env vars (`WEBHOOK_URL`, `BEDROCK_MODEL_ID`, `BEDROCK_REGION`) |
| 3 | 🔴 | Attach IAM `bedrock:InvokeModel` to the Lambda execution role |
| 4 | 🔴 | Deploy frontend to Vercel (Root = `frontend`) + set Mapbox + API env vars |
| 5 | 🟡 | Wire real Discord channel webhook → smoke test with forced `FLOOD_WARNING` payload |
| 6 | 🟡 | Build `/subscribe` Lambda + DynamoDB-backed subscription table |
| 7 | 🟢 | Add more regions (Central Asia, Amazon basin) to `REGIONS[]` |
| 8 | 🟢 | Add a sparkline of recent metrics in `AlertPanel` |

## 🚨 Git Rules

- **NEVER** commit, push, or make any git write operations unless the user **explicitly** says "commit" or "push"
- **NEVER** push to `main` directly — branch first
- **NEVER** commit secrets — `.env.local`, AWS keys, webhook URLs, Mapbox tokens

### Branch Naming

```
YYYYMMDD-feature-name
```

Examples: `20260425-real-extractor`, `20260425-deploy-lambda`, `20260426-subscribe-endpoint`

## 📋 Specs folder — the source of truth for tasks

```
specs/
├── 01-roadmap/01-hackathon-roadmap.md       — 40h timeline, tier ordering, dep graph, demo script
├── 02-lead-dev/01-tasks.md                  — Dimi's 10 tasks (LD-1 through LD-10)
├── 03-data-analysts/01-tasks.md             — Alexandre's 9 tasks (read-only context)
├── 04-meteorologist/01-tasks.md             — Elitsa's 8 tasks (read-only context)
└── 05-cross-team-asks/01-questions-for-team.md  — what Dimi needs to ping others for + answer log
```

**Spec naming convention** (parking-style):
- Folder: `specs/XX-topic-name/` (e.g. `specs/06-replay-feature/`)
- Files: `01-foo.md`, `02-bar.md`, numbered in creation order
- New feature/spec discussion → new numbered folder

## 📝 Keeping This File Updated

When making **significant changes** to architecture, contracts, or stack:

1. Update the **Current State** section (✅ done / ❌ pending)
2. Update the **Tech Stack** table if a library is added/removed
3. Update the **Integration Contracts** if `sentinel_extractor` keys, the Lambda response envelope, or status codes change
4. Update the **Monitoring Regions** table if `REGIONS[]` changes
5. Update the **Environment Variables** section if a new env var is introduced
6. Update the **Specs folder** section if a new spec folder is added
7. Update `specs/05-cross-team-asks/01-questions-for-team.md` answer log when teammates respond

This is a multi-team project — future Claude sessions (and the other teams) rely on this file being accurate.
