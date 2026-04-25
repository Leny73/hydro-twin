  # 🤝 HANDOFF-3 — Frontend + polish handoff

> **Audience:** Dimi's frontend collaborator (you 👋)
> **Author:** Dimi (lead dev, on AWS / backend / deploys)
> **Pitch:** Sun 27 Apr · 15:00, CASSINI Hackathon Bulgaria — Sofia. **~21h left.**
> **Repo:** https://github.com/Leny73/hydro-twin · branch off `dev`

---

## ⏰ Where we are right now

- 🟢 **Backend live** — `https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/assess` (Lambda + DynamoDB + `/subscribe` route all deployed)
- 🟢 **Frontend live** — `https://hydrotwin.vercel.app` (Vite + Mapbox, single Pleven Oblast zone — and that's intentional, we're staying with 1 zone for the pitch)
- 🟡 **One demo blocker** — Anthropic use-case form not yet submitted → Bedrock falls back to `[DEMO MODE]` text. Dimi is handling. Doesn't affect any of your tasks.
- 🔧 **Subscribe whitelist regression** — backend is being fixed by Dimi (one-line change to `KNOWN_REGIONS`). Don't touch.

---

## 🎯 Your tasks (in priority order)

### 🟡 **Task 1 — LD-10: SVG sparkline in AlertPanel**

Tiny chart of recent precipitation or river-level history inside the assessment panel. Pure SVG — **no chart library** (Recharts/Chart.js are overkill for hackathon).

**File:** new `frontend/src/components/MetricsSparkline.jsx`, mounted inside `AlertPanel.jsx` between the AI Reasoning blockquote and the Metadata Footer.

**Stub data is fine** — the real history arrays don't exist yet (extractor returns single values). Just hardcode a believable 14-day series for now, e.g.:

```js
const stubSeries = [12, 18, 22, 15, 30, 45, 60, 55, 48, 35, 28, 20, 15, 18];
```

**Acceptance criteria:**
- [ ] Renders without breaking the panel layout on **mobile** (`<640px` bottom sheet) or **desktop** (right sidebar)
- [ ] Uses the existing Tailwind palette (cyan/blue accents, gray-700 grid)
- [ ] No new npm deps — pure SVG `<path>` or `<polyline>`

**Time:** ~45 min

---

### 🟢 **Task 2 — Browser smoke test before pitch**

Open https://hydrotwin.vercel.app in incognito on **both** your phone and desktop, walk the demo end-to-end, screenshot anything weird:

- [ ] Map loads, Pleven polygon renders
- [ ] Tap/click the Pleven zone → AlertPanel opens within 5s
- [ ] Subscribe button → form opens → submit a real email → success toast
- [ ] Close panel → return to map cleanly
- [ ] Mobile: bottom sheet doesn't get clipped by the address bar (`100dvh` should handle this)
- [ ] Desktop: sidebar doesn't overlap the map nav

**Send Dimi a Loom / screen recording if anything breaks.**

**Time:** 15 min

---

### 🟢 **Task 3 — Backup demo recording (insurance for Sunday)**

30-second screen capture of the live demo working end-to-end, in case Bedrock / Discord / network die on stage. Use Loom, OBS, or built-in screen recorder. Hand the file to Dimi or Angela.

**Time:** 5 min

---

## 🛠️ Local dev setup (5 min)

```bash
# Clone + branch from dev
git checkout dev
git pull
git checkout -b 20260425-sparkline   # or your branch name

# Frontend
cd frontend
npm install
cp .env.example .env.local
# Edit .env.local — set VITE_MAPBOX_TOKEN (ask Dimi if you don't have one)
# VITE_API_ENDPOINT=https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/assess
npm run dev -- --host
# → opens http://localhost:5173 + LAN URL for phone testing
```

All your work is **frontend-only** — no backend setup needed. Hit the live API at `https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/assess` for testing.

---

## 🚫 Files to NOT touch (backend is Dimi's lane)

| File | Owner | Why |
|---|---|---|
| `backend/**` | Dimi / Alexandre / Elitsa | Lambda, extractor, meteorology rules — all separate workstreams |
| `data_science/**` | Alexandre | Notebook scratch space |
| `specs/02-lead-dev/02-deployment/**` | Dimi | Deploy logs / runbook |

Your scope is `frontend/src/components/` (new sparkline component + AlertPanel mount point).

---

## ✅ How to ship

1. Commit on your branch with a clear message (e.g. `feat(frontend): add SVG sparkline to AlertPanel`)
2. Push + open PR against `dev` (NOT `main`)
3. Tag Dimi for review
4. After merge → Dimi redeploys Lambda + Vercel from `dev`

---

## 📌 Hard rules

- ❌ Never commit `.env` / `.env.local` (gitignored — should be safe, but double-check `git status` before push)
- ❌ Never push to `main` directly
- ❌ No new heavy dependencies (chart libs, animation libs) — bundle size matters for mobile
- ✅ Keep 44×44px minimum touch targets on any new interactive elements (WCAG)
- ✅ Use `100dvh` not `100vh` on full-height elements (mobile browser chrome)

---

## 🎬 Pitch context (so you know what you're shipping into)

HydroTwin is a **flood + drought early-warning system** focused on **Pleven Oblast** (Danube floodplain — Vit, Osam & Iskur tributaries). Pitch is **15:00 Sunday at CASSINI Bulgaria 2026**, Sofia. The demo flow is:

1. Open `hydrotwin.vercel.app` on phone + projector
2. Tap the Pleven zone
3. AlertPanel slides up with AI risk assessment + reasoning
4. Tap 🔔 Subscribe → enter email → confirm
5. (Live) Discord channel pings with a colour-coded embed

The sparkline you're adding makes the AlertPanel feel **data-rich** instead of just static text — that's the visual anchor for "this is a real EO-driven product, not a slideware mockup."

---

**Questions? Ping Dimi on Discord. Good luck — see you Sunday.** 💧
