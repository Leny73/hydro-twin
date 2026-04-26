# HydroTwin — Project Brief

> CASSINI Hackathon Bulgaria 2026 · Sofia · 25–27 April
> Challenge #3 — Disaster & Flood Risk Monitoring
> Built in ~40 hours. Pitches Sunday 15:00.

---

## The one-liner (memorize this)

**NIMH delivers the warning. bg-ALERT delivers the alarm. HydroTwin delivers the _decision_.**

We are the layer between national meteorology and emergency activation. We help mayors and regional governors understand whether their specific area is genuinely at risk, why, and how confident the signal is — before they pull the trigger on bg-ALERT.

## The product, in one paragraph

HydroTwin is a municipal decision-support dashboard and alert service for Bulgarian local authorities. It ingests Copernicus Earth Observation data (Sentinel-1, Sentinel-2), rainfall forecasts (Open-Meteo), and historical baselines for a small set of high-priority Bulgarian Areas of Interest (AOIs) — floodplains, reservoirs, catchments. When indicators deviate from baseline, it pushes a plain-language email alert to the registered authority with an AOI-specific risk score, confidence level, and a link to a dashboard that explains _why_. The MVP demonstrates this on three Bulgarian AOIs and includes a "replay" feature that shows what HydroTwin would have flagged before a known past flood event.

## What HydroTwin is NOT

This list matters more than the previous one. Don't drift.

- **Not a forecaster.** We don't compete with NIMH/EFAS/GloFAS. We synthesize their outputs and observational data into a decision signal.
- **Not a digital twin of Earth's water.** That framing is too broad and was deliberately abandoned. HydroTwin is narrower: a municipal alert layer.
- **Not a citizen-facing app.** Audience = municipal/regional authorities. No public sign-up flow needed.
- **Not a replacement for ISME-HYDRO or any pro tool.** We sit on top of pro platforms as the public-facing decision surface.
- **Not real-time.** Daily-refresh is fine. Don't burn time on streaming.
- **Not Bulgaria-wide.** 3 AOIs. That's it. Coverage breadth is not a hackathon objective.
- **Not multi-language UI.** English only for the demo.
- **Not mobile-first.** Desktop demo. Mayor's office, not field.

---

## Strategic positioning (don't let UI copy drift from this)

When generating any user-facing text — landing copy, email subject lines, alert body, dashboard labels — align with these framings:

**Audience phrasing:** "local authorities," "municipal decision-makers," "civil protection teams," "basin directorates," "regional governors," "the mayor's office." NOT "everyone," NOT "the public," NOT "citizens."

**Action phrasing:** "decision support," "early warning," "anomaly detection," "risk trend," "rising risk," "confidence-scored." NOT "we predict floods 1 week ahead" — that overclaims and puts us in direct comparison with EFAS.

**Safe lead-time phrasings:**

- "Up to 7 days of lead time by combining forecast and observation signals."
- "Flag rising risk before traditional thresholds are crossed."
- "Compress Copernicus' 10-day forecast horizon into a single actionable alert per AOI."

**Confidence honesty.** Every alert surfaces uncertainty. Example email line: _"Confidence: Medium. This alert is based on 2 of 4 indicators deviating from baseline."_ Burying uncertainty is what professional forecast systems do — surfacing it is part of our differentiation.

---

## The team

| Member            | Role                                           | Notes                                                                  |
| ----------------- | ---------------------------------------------- | ---------------------------------------------------------------------- |
| Angela Nedyalkova | Project lead / pitch / strategy                | Owns the pitch, owns the 2-page summary                                |
| Tatiana Dragu     | Full-stack dev / prototype lead                | Frontend lead — dashboard UI, map, charts                              |
| Dimi (me)         | Full-stack & AI prototype dev                  | Architecture, Sentinel Hub integration, anomaly logic, Supabase schema |
| Alexandre Payen   | Data / geospatial / ML                         | AOI polygons, evalscripts, historical backfill for replay              |
| Lyuben Branzalov  | AI / intelligent systems                       | AI summary layer — Claude API, prompt engineering                      |
| Elitsa Ilieva     | Meteorology & climate (NIMH Forecast division) | Domain expert. UX spec, threshold calibration, replay event selection  |
| Val Stavrev       | Space industry advisor (Visign Space)          | Pitch framing, EUSPA-grade language for the 2-page summary             |

**Elitsa is unfair-advantage territory.** She works inside NIMH. Anything domain-specific (which AOIs, what thresholds, which past event to replay, how a mayor reads a warning) — she calls it.

---

## Tech stack (committed)

```
Frontend:    Next.js 14 (App Router) + Tailwind + shadcn/ui
Map:         Leaflet + react-leaflet (CartoDB Positron tiles)
Charts:      Recharts
Backend:     Supabase (Postgres + PostGIS + Auth + Storage)
EO data:     Sentinel Hub Statistical API (via Copernicus Data Space Ecosystem)
Rainfall:    Open-Meteo (free, no API key)
AI summary:  Anthropic API · claude-sonnet-4-5
Email:       Brevo (transactional API — already familiar)
Deploy:      Vercel (frontend) + Supabase cloud (backend)
Scaffolding: Lovable (burn 100 free credits in first 30 min)
```

### Why Statistical API, not raster downloads

Sentinel Hub's Statistical API takes an AOI polygon + date range + an evalscript and returns JSON with mean/stddev of indices like NDWI, NDMI, NDVI. **No GDAL, no rasterio, no tile processing.** This is what makes a 40-hour timeline feasible. If we find ourselves writing tile-stitching code, we have taken a wrong turn.

### What we explicitly do NOT use

- Mapbox (paid token, billing friction) → Leaflet
- Custom-trained ML models (out of scope) → rule-based z-score anomaly detection
- Python data pipelines (slow to ship) → server-side Next.js API routes calling Sentinel Hub
- Galileo/EGNOS (challenge is EO-centric) → don't force it
- Raw Sentinel SAFE downloads → Statistical API only

---

## Database schema (Supabase / PostGIS)

```sql
-- AOIs we monitor
create table aois (
  id uuid primary key default gen_random_uuid(),
  name text not null,                    -- e.g. "Iskar floodplain — Sofia"
  region text,                           -- e.g. "Sofia-Capital"
  polygon geometry(Polygon, 4326) not null,
  created_at timestamptz default now()
);

-- Time-series indicator readings per AOI
create table readings (
  id uuid primary key default gen_random_uuid(),
  aoi_id uuid references aois(id) on delete cascade,
  date date not null,
  ndwi numeric,                          -- water index (Sentinel-2)
  ndmi numeric,                          -- moisture index (Sentinel-2)
  rainfall_mm numeric,                   -- Open-Meteo
  rainfall_forecast_7d_mm numeric,       -- Open-Meteo forecast sum
  source text,                           -- 'sentinel-hub' | 'open-meteo' | etc.
  unique (aoi_id, date, source)
);

-- Computed risk states (derived from readings)
create table risk_states (
  id uuid primary key default gen_random_uuid(),
  aoi_id uuid references aois(id) on delete cascade,
  date date not null,
  status text check (status in ('normal','elevated','high')) not null,
  score numeric,                         -- 0..1
  confidence text check (confidence in ('low','medium','high')),
  contributing_indicators jsonb,         -- which indicators triggered
  unique (aoi_id, date)
);

-- Plain-language summaries (Claude-generated, cached)
create table summaries (
  id uuid primary key default gen_random_uuid(),
  aoi_id uuid references aois(id) on delete cascade,
  date date not null,
  summary text not null,                 -- 2-3 sentence natural-language explanation
  generated_at timestamptz default now()
);

-- Subscribers (authority email registrations)
create table subscriptions (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  organization text,                     -- e.g. "Karlovo Municipality"
  aoi_ids uuid[] not null,
  created_at timestamptz default now()
);
```

Keep it this small. Don't add fields we won't use in the demo.

---

## MVP scope — three tiers, ship in order

### Tier 1 — Minimum shippable (must be done by Saturday night)

3 Bulgarian AOIs, statically pre-selected with Elitsa:

1. Iskar floodplain near Sofia
2. A Danube segment (Vidin/Ruse — agriculture stakeholder relevance)
3. Maritsa around Plovdiv

Dashboard surfaces:

- Map with 3 AOI polygons colored by status chip (Normal / Elevated / High)
- AOI list (sidebar or right pane), each row clickable
- AOI detail view: 14-day NDWI line + rainfall bars, stacked
- Status chip per AOI with timestamp "Last updated [date]"
- One single landing page, no auth flow, no marketing

Backend:

- Sentinel Hub Statistical API ingestion, daily for 90 days backfill
- Open-Meteo rainfall ingestion, daily for 90 days backfill
- Anomaly logic: z-score vs 30-day rolling baseline. Threshold values come from Elitsa.

**If we hit Saturday night without this, cut features from Tier 2/3 immediately.**

### Tier 2 — Demo target (Sunday morning)

- Claude-generated summary per AOI ("what changed in the last 14 days")
- The replay button (see next section — this is the pitch)
- Polished landing copy
- Email subscription form (collects email → AOI → triggers a fake "you would receive: [preview]" — don't actually wire up Brevo unless time permits)

### Tier 3 — Reach (only if everything else is rock solid)

- 4th and 5th AOI
- SAR-based flood mask overlay (Sentinel-1)
- GloFAS discharge integration
- PDF report export
- Real Brevo email sends on subscribe

---

## Data sources — integrate in this order

1. **Open-Meteo rainfall** (hour 1) — validates the whole pipeline end-to-end. Free, no API key, ERA5-based historical + forecast.
2. **Sentinel Hub Statistical API** (hours 2–6) — NDWI from Sentinel-2 for one AOI / one index / one date first. Then expand.
3. **Sentinel-1 SAR water detection** (only if ahead of schedule) — flood mask via threshold on VV polarization. Trickier evalscript. Elitsa decides if worth the time.
4. **GloFAS discharge** (Sunday morning reach goal) — Copernicus Emergency Management Service.

CDSE auth flow: OAuth2 client credentials. Set up the account Friday evening, test a single Statistical API request before you sleep.

---

## The replay demo (this is the pitch's centerpiece)

Most hackathon dashboards die in the live demo because nothing interesting is happening today. Counter-move: a **Replay** button on the dashboard that animates the timeline forward through a known past Bulgarian flood event.

**Demo script:**

> "Here's HydroTwin showing Bulgarian AOIs as of today — all Normal. Now let me show you what it would have shown in [event date], ten days before [the event]. [click Replay] On day 7, NDWI in [AOI] crosses the anomaly threshold. Day 9, rainfall forecast pushes us to High. _That_ is the window where authorities could have pre-positioned."

**Event candidates** (Elitsa picks final one):

- Karlovo, September 2022
- Tsarevo, September 2023

**Implementation:** the replay is just a date-slider over the same `risk_states` table. Backfill the data for the chosen event window during build. The "live" view and "replay" view share UI — only the data window changes. No special replay-only code paths.

**This sells the product.** Three things at once: validates the method on a real event everyone in the room remembers, sidesteps the boring-live-data problem, tells a story. Practice it live at least 4 times before Sunday — it's the thing most likely to break on stage.

---

## The five differentiators (use in Q&A)

1. **Audience — last-mile, not national.** EFAS is for ~116 national hydro services. Municipal authorities don't have credentials. Even if they did, EFAS is built for hydrologists, not mayors. We have access to warnings but no decision-support layer for them — that's where we live.

2. **Synthesis, not forecast.** We fuse Copernicus EO + rainfall forecast + anomaly baseline + (optionally) NIMH bulletins into a single local risk signal. EFAS only forecasts. We synthesize.

3. **Observational anomaly detection as a leading indicator.** NIMH's interactive map shows what's currently warned. It does not show "soil moisture has been climbing anomalously for 18 days." We surface the why behind the warning, with historical baseline context.

4. **AOI granularity & explainability.** EFAS is 5km grid; NIMH warnings are typically regional. The mayor of Karlovo doesn't need a Plovdiv-region alert — they need a Karlovo-floodplain risk score with plain-language reasoning.

5. **Decision support, not just delivery.** Email is the channel. The differentiator is what's _in_ the email — confidence-scored, AOI-specific, with reasoning. Not just a redirect to another portal.

## Q&A playbook (when "how is this different from X" comes up)

| If asked about | Answer                                                                                                                                                                                                  |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **NIMH**       | "NIMH issues warnings at a regional level. We translate those into municipality-specific decision support, with historical context and confidence reasoning a mayor needs to act."                      |
| **bg-ALERT**   | "bg-ALERT is the activation channel — sirens, cell broadcast — once a mayor has decided something is happening. We're the layer _before_ that decision, helping them know whether to pull the trigger." |
| **EFAS**       | "EFAS is for national hydrologists at NIMH's level. We're for the mayor's office on Monday morning — same data lineage, totally different audience."                                                    |
| **ISME-HYDRO** | "Professional analysis platform for water management authorities. We're the public-facing decision surface that consumes platforms like ISME-HYDRO and translates them for municipal officials."        |

---

## Pitch structure — 3 minutes, 33% of the score

| Time      | Segment                                                                                                                     | Owner                  |
| --------- | --------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| 0:00–0:20 | **Hook** — real Bulgarian flood photo, human cost                                                                           | Angela                 |
| 0:20–0:40 | **Gap** — Copernicus data exists, NIMH issues warnings, bg-ALERT is the alarm. The decision layer in between is undefended. | Angela                 |
| 0:40–1:20 | **Product** — HydroTwin live, one screen, three AOIs, click into one                                                        | Angela / Tatiana on UI |
| 1:20–2:20 | **Replay** — the centerpiece. The known past event. The would-have-been alert.                                              | Angela                 |
| 2:20–2:50 | **Ask** — complementary to ISME-HYDRO, pilot with [named municipality], path to deployment                                  | Angela                 |
| 2:50–3:00 | **Close** — one-line value prop                                                                                             | Angela                 |

**The Elitsa moment** — drop in if there's room: _"We asked a meteorology specialist who works inside NIMH itself how a flood warning gets from her desk to a field action. She said — quote — 'I don't know how it goes truly.' If the forecaster doesn't know, the mayor receiving it is even more in the dark. HydroTwin makes that handoff legible."_ (Get her permission to quote first.)

---

## Hard NOs — don't build these, don't suggest these

- Auth / user accounts (skip — subscription form fakes it)
- Real-time streaming data (daily refresh is fine)
- Bulgaria-wide coverage (3 AOIs, that's it)
- Custom-trained ML models (rule-based z-score is the spec)
- Multi-language UI (English only)
- Mobile-responsive polish (desktop demo)
- A native mobile app (zero relevance)
- Hardware (zero relevance)
- Beautiful onboarding flows (no auth, no flow)
- A landing page with marketing sections (one screen, the dashboard, that's it)
- Dark mode (not worth the time)
- E2E tests (not worth the time)
- Form validation libraries (native HTML validation only)
- A blog, news section, "about us," team page (no)

If a feature isn't on screen during the 3-minute pitch, it doesn't exist for hackathon purposes.

---

## File / repo conventions

```
hydrotwin/
  app/                       # Next.js 14 App Router
    page.tsx                 # The dashboard (single page)
    api/
      ingest/route.ts        # Triggered by cron / manual: pulls from Sentinel Hub + Open-Meteo
      summarize/route.ts     # Calls Claude API, caches to Supabase
      subscribe/route.ts     # Email subscription (fake or real)
      replay/route.ts        # Returns historical risk states for a given event
  components/
    Map.tsx                  # Leaflet map with AOI polygons
    AOIList.tsx              # Sidebar list with status chips
    AOIDetail.tsx            # Detail pane: chart + summary + indicators
    StatusChip.tsx           # Normal / Elevated / High pill
    ReplayControls.tsx       # The replay button + date slider
  lib/
    sentinel-hub.ts          # CDSE OAuth + Statistical API client
    open-meteo.ts            # Rainfall fetch
    anomaly.ts               # z-score logic, threshold rules
    supabase.ts              # Supabase client (server + browser)
    claude.ts                # Anthropic API client for summaries
  spec/                      # External memory (per Dimi's convention)
    SPEC.md                  # Living spec
    EVALSCRIPTS.md           # NDWI, NDMI, SAR water mask evalscripts
    AOI_DEFINITIONS.md       # Polygon coordinates, named per Elitsa
    REPLAY_EVENT.md          # The chosen past event, dates, expected behavior
  CLAUDE.md                  # This file
```

---

## Timeline — 40 hours, broken down

### Friday evening (Apr 25, ~4h active)

- Kickoff, mentor office hours
- **Ask mentors:** scope of the pre-made Copernicus data cube (geographical coverage, temporal window, format)
- **Lock with Elitsa:** the 3 AOIs and the replay event (must happen Friday night, not Saturday)
- Set up: CDSE account + Sentinel Hub OAuth, Supabase project, Vercel project, Brevo account, Anthropic API key
- Lovable scaffold the dashboard shell (burn ~50 of the 100 credits here)
- Push stub to production URL — everyone has access to a working but empty deploy
- **End-of-day goal:** clickable skeleton with fake data; we know everyone's tools work

### Saturday (Apr 26, ~14h active)

- **Morning (4h):** Open-Meteo integration end-to-end. One Sentinel Hub Statistical API call returning real NDWI for one AOI on one date. Schema deployed.
- **Midday (3h):** All 3 AOIs, 90 days backfilled in `readings` table. Anomaly logic written and tested against the replay event window.
- **Afternoon (4h):** Frontend wired — map renders polygons, list shows status chips reading real `risk_states`, AOI detail pane shows real chart.
- **Evening (3h):** Claude summary endpoint working. First end-to-end vertical slice complete.
- **Saturday night must have Tier 1 done.** Sleep 6–7 hours.

### Sunday (Apr 27, until 15:00, ~6h active)

- **Morning (3h):** Replay feature implemented and rehearsed live. UI polish. First full pitch rehearsal.
- **Late morning (2h):** 2-page summary finalized (Angela + Val). Backup screen recording (always assume the live demo will fail).
- **13:00:** Code freeze. Third pitch rehearsal.
- **15:00:** Submit.

---

## Open questions — bring Elitsa's answers back before coding

1. ~~Does NIMH push targeted warnings or bulletin-style?~~ Answered.
2. ~~How does NIMH → municipality → field handoff work?~~ Answered (incompletely, which is itself the insight).
3. **Which past Bulgarian flood event is the replay?** Karlovo 2022 vs Tsarevo 2023 — Elitsa picks the one with the cleanest "knowable in advance" story.
4. **What goes on the 1-screen dashboard for a mayor?** UX spec from a forecaster's perspective. Build whatever she says.
5. **Specific cases where observational data would have helped but wasn't in the warning pipeline?** Real ground-truth examples that justify the anomaly-detection angle.

---

## Copy / branding notes

- Product name: **HydroTwin** (one word, capital H, capital T). Logo can be the lowercase serif "h\*" or a water-droplet glyph if anyone has time. Don't burn time on logos.
- Tagline (use sparingly): _The decision layer between meteorology and emergency._
- Email subject template: `HydroTwin · [AOI name] · Risk elevated`
- Status colors: Normal = teal, Elevated = amber, High = red. Chip background should be the lightest stop, text the darkest.
- No emoji in alert content. No exclamation marks. Authoritative, calm tone.
- Confidence wording: "Confidence: Low / Medium / High" — never "% confidence."

---

## When in doubt

- If a decision is technical, **default to the choice that ships fastest.**
- If a decision is product, **default to what makes the 3-minute pitch clearer.**
- If a decision is positioning, **default to the framings in this doc** — they were chosen to defend against jury questions.
- If you can't decide, ask Dimi or Elitsa.
