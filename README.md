# HydroTwin 💧

**Multi-region Flood & Drought Early Warning System**  

---

## Architecture

```
Copernicus EO / OpenMeteo
          │
          ▼
  sentinel_extractor.py          ← Data Analysts own this
          │
          ▼
  lambda_handler.py              ← Orchestrates everything
     │         │
     │         ▼
     │   meteorology_rules.md    ← Meteorologist owns this
     │
     ▼
 AWS Bedrock (Claude 3 Sonnet)
     │
     ├──► Discord / Telegram Webhook  (on WATCH / WARNING)
     │
     ▼
 API Gateway (HTTPS)
     │
     ▼
 React / Vite (Vercel)           ← Mapbox map + AlertPanel
```

---

## Monorepo Structure

```
hydro-twin/
├── backend/
│   ├── lambda_handler.py        ✅ Orchestrator + Bedrock + Webhook
│   ├── sentinel_extractor.py    🔧 STUB — Data Analysts fill this
│   ├── meteorology_rules.md     🔧 DRAFT — Meteorologist fills this
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx              ✅ Map + region markers + state
│   │   ├── main.jsx
│   │   ├── index.css
│   │   └── components/
│   │       └── AlertPanel.jsx   ✅ Status / Reasoning / Subscribe panel
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   └── .env.example
│
└── data_science/
    ├── README.md                ← Integration contract for analysts
    └── notebooks/
```

---

## Team Ownership

| Path | Owner | Status |
|------|-------|--------|
| `frontend/` | Lead Dev | ✅ Ready |
| `backend/lambda_handler.py` | Lead Dev | ✅ Ready |
| `backend/sentinel_extractor.py` | Data Analysts | 🔧 Stub |
| `backend/meteorology_rules.md` | Meteorologist | 🔧 Draft |
| `data_science/` | Data Analysts | 🔧 In progress |

---

## Quick Start — Run locally in 3 steps

> **Prerequisites (one-time install)**
> - [Node.js LTS](https://nodejs.org) ≥ 20  — or install via `nvm` inside WSL: `nvm install --lts`
> - Python 3.10+  — available as `python3` in WSL/Ubuntu out of the box

---

### Step 1 — Install frontend dependencies

```bash
cd frontend
npm install
```

### Step 2 — Configure environment variables

```bash
# Frontend
cp frontend/.env.example frontend/.env.local
# Edit frontend/.env.local — add your Mapbox token:
#   VITE_MAPBOX_TOKEN=pk.eyJ1...
#   VITE_API_ENDPOINT=http://localhost:5050/assess

# Backend
cp backend/.env.example backend/.env.local
# Edit backend/.env.local — add AWS credentials when ready:
#   AWS_ACCESS_KEY_ID=...
#   AWS_SECRET_ACCESS_KEY=...
```

### Step 3 — Start both servers (two separate terminals)

**Terminal A — Backend (Flask wrapper around the Lambda)**
```bash
# Install Python deps (once)
pip3 install --user --break-system-packages flask flask-cors requests boto3 python-dotenv

# Start on http://localhost:5050
python3 backend/local_server.py
```

**Terminal B — Frontend (Vite dev server)**
```bash
cd frontend

# Start on http://localhost:5173
npm run dev -- --host
```

Open **http://localhost:5173** in your browser (or on your phone via the Network URL printed by Vite, e.g. `http://192.168.x.x:5173`).

> **No AWS credentials yet?** That's fine. The frontend has a built-in **demo fallback** — clicking any region marker will show a simulated `FLOOD_WATCH` assessment so the full UI is always demonstrable.

---

## Mobile / Responsive Design

The app is **mobile-first** and designed as the primary interface for phones.

| Feature | Mobile | Desktop |
|---------|--------|---------|
| Assessment panel | Slides up as a **bottom sheet** (covers ~65% of screen) | Fixed right sidebar (320px) |
| Region markers | 44 × 44 px touch targets (WCAG 2.5.5) | Same |
| Close panel | ✕ button → returns to full map | ✕ button |
| Viewport | `100dvh` — respects mobile browser chrome show/hide | Same |
| iOS safe area | `viewport-fit=cover` — clears notch & home bar | N/A |
| Status bar | Black translucent (PWA fullscreen mode) | N/A |

**To test on your phone:**
1. Make sure your laptop and phone are on the same Wi-Fi.
2. Start the frontend with `npm run dev -- --host`.
3. Vite will print a **Network** URL like `http://192.168.1.42:5173` — open that on your phone.

---

## Deploy to Production

### Backend → AWS Lambda

```bash
cd backend
pip install -r requirements.txt -t .
zip -r ../hydrotwin-backend.zip . --exclude ".venv/*" "local_server.py" ".env*"
aws lambda update-function-code \
    --function-name HydroTwin \
    --zip-file fileb://../hydrotwin-backend.zip
```

Lambda settings: Runtime `Python 3.10` · Handler `lambda_handler.lambda_handler` · Timeout 30 s · Memory 256 MB · IAM role needs `bedrock:InvokeModel`.

### Frontend → Vercel

```bash
cd frontend
npx vercel --prod
# Set "Root Directory" = frontend in Vercel project settings
# Add VITE_MAPBOX_TOKEN and VITE_API_ENDPOINT as Environment Variables
```

---

## Environment Variables Reference

| Scope | Variable | Example value |
|-------|----------|---------------|
| Frontend | `VITE_MAPBOX_TOKEN` | `pk.eyJ1...` |
| Frontend | `VITE_API_ENDPOINT` | `https://abc.execute-api.us-east-1.amazonaws.com/prod/assess` |
| Backend | `WEBHOOK_URL` | `https://discord.com/api/webhooks/...` |
| Backend | `BEDROCK_MODEL_ID` | `anthropic.claude-3-sonnet-20240229-v1:0` |
| Backend | `BEDROCK_REGION` | `us-east-1` |
| Backend (local) | `AWS_ACCESS_KEY_ID` | — |
| Backend (local) | `AWS_SECRET_ACCESS_KEY` | — |

---

## Hackathon Roadmap

> Priority order: 🔴 Blocker → 🟡 Important → 🟢 Nice to have

---

### 👨‍💻 Lead Developer

| # | Priority | Task | File(s) |
|---|----------|------|---------|
| 1 | 🔴 | Deploy Lambda to AWS + create API Gateway HTTP endpoint | `backend/lambda_handler.py` |
| 2 | 🔴 | Set Lambda env vars (`WEBHOOK_URL`, `BEDROCK_MODEL_ID`, `BEDROCK_REGION`) | AWS Console |
| 3 | 🔴 | Add IAM policy `bedrock:InvokeModel` to the Lambda execution role | AWS IAM |
| 4 | 🔴 | Deploy frontend to Vercel; set `VITE_MAPBOX_TOKEN` + `VITE_API_ENDPOINT` | `frontend/` |
| 5 | � | **Discord alerts** — create a server channel, generate a Webhook URL (Channel Settings → Integrations → Webhooks), paste it into `WEBHOOK_URL`. Alerts fire automatically on every `WATCH` or `WARNING` status. | `backend/lambda_handler.py` → `trigger_webhook()` |
| 6 | 🟡 | Test end-to-end Discord alert: call `/assess` with a forced `FLOOD_WARNING` payload and confirm the embed arrives with the correct colour, confidence %, and reasoning text | `backend/local_server.py` |
| 7 | 🟡 | Wire the "Subscribe to Alerts" button to a real `/subscribe` Lambda endpoint | `frontend/src/components/AlertPanel.jsx` |
| 8 | 🟡 | Add a `/subscribe` Lambda + DynamoDB table to store user webhook handles | new: `backend/subscribe_handler.py` |
| 9 | 🟢 | Add more monitored regions (Central Asia, Amazon basin) to the map | `frontend/src/App.jsx` → `REGIONS` array |
| 10 | 🟢 | Add a time-series sparkline chart for the sensor metrics in `AlertPanel` | `frontend/src/components/` |

---

### 📊 Data Analysts

| # | Priority | Task | File(s) |
|---|----------|------|---------|
| 1 | 🔴 | Replace the dummy `return` dict in `get_eo_and_weather_data()` with real Copernicus + OpenMeteo API calls | `backend/sentinel_extractor.py` |
| 2 | 🔴 | Validate all **required dict keys** are present and match the schema in the docstring — do not rename or remove any key | `backend/sentinel_extractor.py` |
| 3 | 🔴 | Add a data-freshness guard: raise an error (or return a warning in `source`) if the observation timestamp is > 24 h old | `backend/sentinel_extractor.py` |
| 4 | 🟡 | Implement Sentinel-2 NDVI calculation for the given `bbox` using the Sentinel Hub Process API | `backend/sentinel_extractor.py` |
| 5 | 🟡 | Implement Sentinel-1 SAR-based flood extent mapping (open-water pixel count → km²) | `backend/sentinel_extractor.py` |
| 6 | 🟡 | Pull 7-day and 30-day precipitation totals from [OpenMeteo](https://open-meteo.com/) (free, no API key) | `backend/sentinel_extractor.py` |
| 7 | 🟡 | Compute SPI-3 drought index from ERA5 reanalysis precipitation data | `backend/sentinel_extractor.py` |
| 8 | 🟢 | Write unit tests with mocked API responses | `data_science/notebooks/` or new `backend/tests/` |
| 9 | 🟢 | Add an EDA notebook exploring historical flood/drought events per region | `data_science/notebooks/` |

---

### 🌦️ Meteorologist

| # | Priority | Task | File(s) |
|---|----------|------|---------|
| 1 | 🔴 | Review and validate all threshold values in Sections 2 & 3 against peer-reviewed literature or WMO standards | `backend/meteorology_rules.md` |
| 2 | 🔴 | Fill in the **Regional Climatological Baselines** table (Section 5) with validated WMO 1991–2020 normals for all five regions | `backend/meteorology_rules.md` |
| 3 | 🔴 | Confirm or revise the compound event rules in Section 6 (flash flood, drought-heat) | `backend/meteorology_rules.md` |
| 4 | 🟡 | Add seasonality multipliers — e.g. Mediterranean summer dry-season adjustments to precipitation thresholds | `backend/meteorology_rules.md` |
| 5 | 🟡 | Define sub-regional micro-climate zones within each bounding box where thresholds differ significantly | `backend/meteorology_rules.md` |
| 6 | 🟡 | Document ENSO / NAO teleconnection adjustments for the Sahel and Mediterranean regions | `backend/meteorology_rules.md` |
| 7 | 🟢 | Add confidence-modifier rules — conditions under which Claude should lower confidence (e.g. sparse sensor coverage) | `backend/meteorology_rules.md` |
| 8 | 🟢 | Cross-validate thresholds against the ESA Copernicus Emergency Management Service historical event catalogue | `data_science/notebooks/` |


