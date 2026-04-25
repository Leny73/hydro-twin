# 🎨 HANDOFF — Frontend Dev

> **You** = Tatiana 🙌 (frontend lead).
> **Dimi** = lead dev / your point of contact for everything backend, AWS, deploys.
> **Pitch:** Sunday Apr 26, 15:00 at CASSINI Hackathon Bulgaria. **~24h left.**

---

## ⏰ Where things stand right now (Sat Apr 25)

- ✅ **You shipped the notification layer** — Discord + Telegram messages firing. Massive unblock 🚀
- 🔄 **Dimi is on AWS deploys** — Lambda + API Gateway + IAM + Vercel (LD-1 → LD-4). He needs ~2.5h heads-down.
- 🎯 **Your next slot is parallel-ready** — no AWS dep, no backend dep. Pure frontend.

---

## 🎯 Primary task: **LD-7 — "Subscribe to Alerts" UI**

Replace the current `window.alert()` stub in `AlertPanel.handleSubscribe()` with a real subscribe form that POSTs to `/subscribe`.

### 📂 File

`frontend/src/components/AlertPanel.jsx` → `handleSubscribe()` (the stub uses `window.alert(...)` — replace it).

### 🧱 What to build

1. **Inline form inside the panel** (not a modal — keeps the mobile bottom-sheet flow tight)
2. **Email input** + submit button
3. **Client-side email regex validation** (basic `/^\S+@\S+\.\S+$/` is fine)
4. **Loading state** while request is in-flight (disable button, small spinner or `…`)
5. **Success toast** — e.g. `✅ You're subscribed for {region.name}`
6. **Error toast** — for 400 invalid email and for network failure (different copy for each)
7. **API call:**

```js
const url = import.meta.env.VITE_API_ENDPOINT.replace('/assess', '/subscribe');
fetch(url, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, region_id: region.id }),
});
```

### ✅ Acceptance criteria

- [ ] Form opens inline when "Subscribe" is clicked, collapses on success/cancel
- [ ] Email validation runs before fetch (no wasted requests)
- [ ] Loading / success / error states are all visually distinct
- [ ] Touch targets ≥ 44×44 px (WCAG 2.5.5 — drivers use this on phones in the field)
- [ ] Responsive: works on **both** mobile bottom sheet (`<640px`, ~68vh) **and** desktop sidebar
- [ ] Visual style matches existing AlertPanel — mono font, dark UI, Tailwind utilities only

### 🚫 Hard boundaries — DO NOT TOUCH

- ❌ `App.jsx` — Dimi is wiring deploys here, would merge-conflict
- ❌ `STATUS_META` constants — shared schema across 3 files, breaking it cascades to backend + webhook colors
- ❌ Anything in `backend/**`
- ❌ No new dependencies — **don't add** `react-toastify`, `react-hook-form`, `zod`, etc. Tailwind + a small local component is enough
- ❌ Don't move existing files around — keep the diff small

### 🧰 Stack reminders

- **Tailwind CSS 3** (already configured, no theme changes please)
- **Mono font stack** — JetBrains Mono → Fira Code → system mono
- **React 18 + plain JSX** (no TypeScript)
- **Panel is responsive:** `<640px` = bottom sheet, `≥640px` = right sidebar
- **Status colors** to match: badge / button colors should pull from existing AlertPanel patterns, not new hex values

### 🧪 Testing without a real backend

The `/subscribe` endpoint doesn't exist yet — Dimi builds it as **LD-8** after the deploys land. While he's heads-down:

1. Run dev server: `cd frontend && npm run dev -- --host`
2. The POST will fail with network error → that's exactly what exercises your error-state UI ✅
3. To verify success path locally, **temporarily** mock the fetch with a 1.2s delay returning `{ ok: true }` — but **revert before committing**

---

## 🎨 Stretch (only if LD-7 lands fast): **LD-10 — Metrics sparkline**

Tiny SVG sparkline (precipitation or river level) inside the AlertPanel, above or beside the reasoning blockquote.

- 🎨 Pure inline SVG — **no chart library** (`recharts`, `chart.js`, `victory` all banned for hackathon — bundle bloat)
- 📐 Must not break panel layout at any breakpoint
- 📊 Backend extractor doesn't return historical arrays yet → mock 14 random data points for the demo, leave a `// TODO: real data from extractor` comment
- 🎨 Match the dark UI palette — soft accent line, no axes/labels needed, just a vibe

---

## 🌿 Branch + commit convention

```bash
git checkout -b 20260425-subscribe-ui
# make changes
git add frontend/src/components/AlertPanel.jsx
git commit -m "feat(frontend): wire subscribe form to /subscribe endpoint"
```

- Branch format: `YYYYMMDD-feature-name` (project rule)
- **Do NOT push to `main` directly**
- **Do NOT commit** any `.env`, `.env.local`, or AWS keys
- Open a PR against `main` for Dimi to review when ready

---

## 🙋 Got blocked? Got a question?

Ping Dimi directly — don't guess on:

- The `/subscribe` API contract (he owns it, may add fields)
- Anything that touches AWS / env vars / Mapbox tokens
- Whether to add a new component file vs. inline (default = inline, AlertPanel is already small)

Track open questions in `specs/05-cross-team-asks/01-questions-for-team.md` if Dimi is heads-down on AWS.

---

## 🎬 Why this matters for the pitch

The "Subscribe" CTA is the **call-to-action moment** in the 3-minute pitch. Angela will likely click it live. If the toast pops cleanly and the form feels polished, that's a 10/10 demo beat. If it's still a `window.alert()`, the pitch loses 30 seconds of credibility.

**You're shipping the moment of conversion. Make it tight.** 💧

---

**LFG. Pitch in 24h.** 🚀
