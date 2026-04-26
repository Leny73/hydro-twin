# 🙋 Questions to Ask the Team

> **Audience:** Dimi (Lead Dev — sole coder)
> **Purpose:** Things you need answered/delivered by teammates before *your* code can ship. Ping early — don't be the bottleneck on Sunday.

---

## 📊 For the Data Analysts (Alexandre Payen + team)

> They own `backend/sentinel_extractor.py`. Your Lambda imports it. Their work blocks your e2e Discord test (LD-6) and your "real demo, not fallback" goal (LD-3 verification).

### 🔴 Ask now (Friday evening)

| # | Question | Why you need it |
|---|----------|-----------------|
| 1 | **What's your ETA for replacing the dummy `get_eo_and_weather_data()` with real API calls?** | LD-6 (e2e Discord test) is blocked until you have real data. If their ETA is Saturday afternoon, plan your day around that. |
| 2 | **Are you adding any new pip packages?** (e.g. `sentinelhub-py`, `openmeteo-requests`, `xarray`, `rasterio`) | You package them into the Lambda zip via `pip install -r requirements.txt -t .`. Some packages (rasterio, GDAL) are huge and may bust Lambda's 250MB unzipped limit — flag early so you can decide between Lambda Layers vs container image. |
| 3 | **Will you need Sentinel Hub OAuth credentials in Lambda env vars?** | If yes, you need to add `SH_CLIENT_ID` + `SH_CLIENT_SECRET` to the Lambda env (LD-2) and to `.env.example`. Get the credential names locked. |
| 4 | **Realistic latency of the real extractor?** | Lambda timeout is 30s and Bedrock takes ~3–8s. If their extractor takes >20s, you'll need to bump Lambda timeout to 60s in LD-1, or run extraction async. |
| 5 | **Are you handling DA-3 (data-freshness guard) yourself, or do you want me to do it in the Lambda layer?** | Avoid double-implementing. Their docstring says they own it; just confirm. |

### 🟡 Ask Saturday morning

| # | Question | Why you need it |
|---|----------|-----------------|
| 6 | **Are you adding any new keys to the return dict?** | The Bedrock prompt forwards everything in the dict, so new keys = better Claude reasoning. No code change needed on your side, but worth knowing for the demo narrative. |
| 7 | **Which regions will have real data by Saturday night?** | If only 2 of the 5 regions return real data, decide whether the other 3 stay on dummy values, get hidden, or get a "data unavailable" badge in the UI. |
| 8 | **Will any region's bbox change?** | Currently locked in `frontend/src/App.jsx` `REGIONS[]`. If they want different bboxes (e.g. tighter coverage of Sentinel-2 tile boundaries), update both files in sync. |

### 🟢 Nice-to-know

| # | Question | Why you need it |
|---|----------|-----------------|
| 9 | **For LD-10 (sparkline) — can you return historical arrays too?** | Sparkline needs `precip_history_30d: float[]` etc. Only worth it if Tier 1+2 are done. |

### 📼 History replay (added 2026-04-25 — see `../06-history-replay/01-design.md`)

| # | Question | Why you need it |
|---|----------|-----------------|
| 10 | **Can `get_eo_and_weather_data(bbox, replay_date: str \| None = None)` accept an optional ISO date?** When set, route to OpenMeteo Historical API + Sentinel archive instead of live endpoints. **Return-dict schema must stay identical** (10 keys). | This unlocks Tier B of the history-replay feature (real EO reconstruction of past floods). Without it, we ship Tier A only — pre-baked snapshots in a frontend JSON. |
| 11 | **Does Sentinel Hub OAuth allow archive queries with arbitrary `time` ranges**, or do we need a different credential scope? | If credentials are forecast-only, we drop Tier B entirely. Lock this before I waste time on the Lambda passthrough. |
| 12 | **Realistic latency of a `replay_date` extraction?** (archive S1 GRD + OpenMeteo Historical) | If >25s, replay needs to be async or pre-cached. If <15s, fits in current 30s Lambda timeout. |

---

## 🌦️ For the Meteorologist (Elitsa Ilieva)

> She owns `backend/meteorology_rules.md`. The Lambda injects this verbatim into Claude's prompt. Her edits = production behavior changes, no code change required on your side.

### 🔴 Ask now (Friday evening)

| # | Question | Why you need it |
|---|----------|-----------------|
| 1 | **What's your ETA for filling Section 5 (Regional Climatological Baselines)?** | Right now it has placeholder values. Claude will technically work without real values but the demo narrative will be weak when the jury asks "where do these baselines come from?" |
| 2 | **Will you introduce any new alert status codes** beyond the current 5 (`SAFE`, `DROUGHT_WATCH`, `DROUGHT_WARNING`, `FLOOD_WATCH`, `FLOOD_WARNING`)? | You have to update **3 files** in lockstep if she adds one: `backend/lambda_handler.py` `STATUS_META`, `frontend/src/components/AlertPanel.jsx` `STATUS_META`, and the Discord embed colour map. Easier to lock the list now. |
| 3 | **Are the 5 region IDs in Section 5 correct?** (`mediterranean-basin`, `sahel-region`, `danube-basin`, `po-valley`, `nile-delta`) | These IDs must match `frontend/src/App.jsx` `REGIONS[]` exactly. If she renames one, you update the frontend. |

### 🟡 Ask Saturday morning

| # | Question | Why you need it |
|---|----------|-----------------|
| 4 | **Confirm she understands the file is injected verbatim into the LLM prompt** — no front-matter, no HTML, plain Markdown only. | Friendly check — if she pastes in something from Word it might wreck the prompt. |
| 5 | **Format check:** the file is loaded with `open(RULES_FILE, "r", encoding="utf-8")`. Any non-UTF-8 chars (smart quotes, em dashes from Word) might display weirdly to Claude. | Cosmetic but worth a heads-up. |

### 📼 History replay (added 2026-04-25 — see `../06-history-replay/01-design.md`)

| # | Question | Why you need it |
|---|----------|-----------------|
| 6 | **Can you confirm the 5 most significant verified flood/drought events for the Pleven AOI** (date range, severity using our 5 status codes, 1-line summary, NIMH or EMS source)? Candidates I'm pre-filling: 2014-08 Mizia/Vit floods, 2005 Danube floods, 2010 spring floods — please confirm/correct/replace. | Drives the dropdown content. Without verified events, the demo replay isn't defensible to the jury. |
| 7 | **Are there other Bulgarian AOIs (Sofia? Varna?) we should add** beyond Pleven, and what are their canonical past events? | Brief mentions 3 Bulgarian AOIs. Pleven is the only confirmed one today. |
| 8 | **For each event: what would the threshold matrix have classified it as at peak** (`FLOOD_WATCH` vs `FLOOD_WARNING`)? | The pre-baked snapshot's `severity` field has to match what the rules would output, otherwise the replay narrative is internally inconsistent. |

---

## 🤖 For Lyuben (AI summary layer — if applicable)

> The brief mentions an "AI summary layer — Claude API, prompt engineering" owned by Lyuben. You're already doing the Claude call in `lambda_handler.call_bedrock_agent()`.

### 🟡 Ask Saturday morning (if relevant to scope)

| # | Question | Why you need it |
|---|----------|-----------------|
| 1 | **Are you doing prompt engineering on the existing Bedrock call, or building a separate summary endpoint?** | Avoid two people editing the same prompt. If he's iterating on the prompt in `lambda_handler.call_bedrock_agent()`, give him the file and stay out. If it's a separate `/summarize` endpoint, you'll need a new route. |
| 2 | **Is `claude-3-sonnet-20240229-v1:0` (current model) fine, or does he want a different model?** | Bedrock model swap = 1-line env var change. Anthropic-direct = bigger refactor (probably out of scope per stack lock). |

---

## 🎯 For Angela (pitch / 2-page summary)

> She's writing the pitch. You're not the speaker, but the demo flow needs to match her script.

### 🟡 Ask Saturday afternoon

| # | Question | Why you need it |
|---|----------|-----------------|
| 1 | **Which region will she click during the live demo?** | You should warm that region's Lambda invocation right before she goes on stage to avoid cold-start delay. |
| 2 | **Does she want the Discord webhook firing live during the demo,** or pre-recorded? | If live, pre-create the Discord channel + invite the jury (or share-screen the channel). If pre-recorded, capture a clean screenshot. |
| 3 | **Backup screen recording — does she want you to record it,** or is someone else? | Sunday morning, do a clean run-through and screen-record it. Always assume the live demo will fail. |

---

## 🚦 Decision matrix — when to ping vs when to wait

| Situation | Action |
|-----------|--------|
| Their work blocks your Tier 1 (🔴) task | Ping immediately, even Friday night |
| Their work blocks your Tier 2 (🟡) task | Ping Saturday morning |
| Their work would just be nice for your Tier 3 (🟢) | Don't ping — work on Tier 1+2 first |
| You're guessing at a contract (key names, status codes, region IDs) | Always ping — guesses become bugs |
| You're tempted to "just do it yourself" because waiting is slow | Stop. The contract matters more than the speed. Ping. |

---

## 📝 Track answers here

> When you get answers, write them in this section so future Claude sessions and you-in-12-hours have the context.

### Data Analysts answers
- _(blank — fill in as you get them)_

### Meteorologist answers
- _(blank)_

### Lyuben answers
- _(blank)_

### Angela answers
- _(blank)_
