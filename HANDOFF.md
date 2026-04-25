# 🤝 HANDOFF — Next Claude Session

> **You** = a fresh Claude Code session.
> **Dimi** = the user, the only human you're working with.
> **Goal of this file:** get you operational in 2 minutes so Dimi doesn't have to re-explain context.

---

## ⏰ Right now (the immediate situation)

- **Today is Saturday Apr 25, 2026** — build day at CASSINI Hackathon Bulgaria 2026.
- **Pitch is tomorrow (Sunday) at 15:00.** ~24 hours of work left.
- **Dimi just got AWS access from his lead** — moments before opening you. He's ready to start the deploy tasks.
- **Friday's setup window was lost** waiting for AWS access → all of Friday's tasks (LD-1 through LD-5) need to happen today, on top of Saturday's tasks.
- **Dimi is the sole coder.** No one else writes code on this team. He's working with you (Claude Code).

---

## 📚 Read these files in this order (then come back)

1. **`CLAUDE.md`** (root) — project state, stack rules, team, integration contracts
2. **`specs/02-lead-dev/01-tasks.md`** — Dimi's 10 tasks (LD-1 → LD-10) with acceptance criteria
3. **`specs/01-roadmap/01-hackathon-roadmap.md`** — timeline + dependency graph + demo script
4. **`specs/05-cross-team-asks/01-questions-for-team.md`** — what's blocking, with answer log
5. **`initial_context.md`** — full hackathon brief (positioning, hard NOs, replay feature) — read but DO NOT propose its framework choices
6. *(skim only)* `specs/03-data-analysts/01-tasks.md` + `specs/04-meteorologist/01-tasks.md` — context for what other teammates produce, not your work

**Don't read** `data_science/` or `backend/sentinel_extractor.py` deeply — they're owned by Alexandre, not Dimi.

---

## 🎯 The very first thing to do with Dimi

**Before** Dimi touches AWS Console, walk him through these in order:

1. ✅ **Bedrock model access request** (AWS Console → Bedrock → Model access → request `anthropic.claude-3-sonnet-20240229-v1:0`). This can take **hours to approve**. If not done yet, this is action #1 — even before LD-1.
2. ✅ **Confirm answers from Alexandre** on the two architectural questions:
   - **Q1 — pip packages?** If he's using `rasterio` / `GDAL` / large libs → Lambda zip approach changes (need Lambda Layers or container image instead of plain zip)
   - **Q2 — Sentinel Hub OAuth env var names?** Set them in LD-2 in one shot, not twice
3. ✅ If Alexandre hasn't answered yet → start **LD-5** (Discord webhook, 10 min, zero deps) while waiting

---

## 🚦 Saturday execution order

| # | Task | Time | Dep |
|---|------|------|-----|
| 1 | **LD-5** — Discord channel + webhook | 10 min | none |
| 2 | **LD-1** — Lambda + API Gateway | 60 min | ⚠️ Decision point: zip vs Layer vs container per Alexandre Q1 |
| 3 | **LD-3** — IAM `bedrock:InvokeModel` policy | 15 min | LD-1 |
| 4 | **LD-2** — Lambda env vars | 10 min | LD-1, LD-5, Alexandre Q2 |
| 5 | **LD-4** — Vercel deploy | 30 min | LD-1 (need API Gateway URL) |
| 6 | 🧪 **Smoke test** — click region on Vercel URL → see Discord alert | 15 min | all above |
| 7 | **LD-6** — e2e test with real Bedrock + real extractor | 30 min | Alexandre's real extractor |
| 8 | **LD-7 + LD-8** — Subscribe button + `/subscribe` Lambda + DynamoDB | 2–3h | none |
| 9 | 💤 sleep 6–7h |  |  |
| 10 | Sunday: polish, rehearsals, 15:00 submit |  |  |

---

## 🔒 STACK IS LOCKED — do not propose alternatives

- **Stack:** Vite + plain React 18 + Mapbox GL + Python AWS Lambda + AWS Bedrock + Discord webhook
- **Lead decision** by Dimi on 2026-04-25
- The brief in `initial_context.md` originally specified Next.js 14 + Leaflet + Supabase + Anthropic-direct + Brevo — **IGNORE those framework choices**
- ❌ Do not suggest migrating frameworks
- ❌ Do not suggest archiving / re-scaffolding the repo
- ❌ Do not re-litigate this — it's saved in memory and CLAUDE.md
- ✅ DO adapt brief *product* features (3 Bulgarian AOIs, replay button, anomaly detection, AOI polygons, email-style alerts) onto the current stack — but only if Dimi asks for them

---

## ⚠️ Critical "watch out for"

| Risk | Mitigation |
|---|---|
| **Bedrock model access takes hours to approve** | Request it the moment AWS Console opens — before any other AWS work |
| **Lambda 250 MB unzipped limit** | If Alexandre's pip packages are heavy → switch to Lambda Layers or container image. Decide BEFORE running `pip install -r requirements.txt -t .` |
| **Mapbox token in public bundle** | Vite inlines `VITE_*` at build time. Token MUST be scoped `styles:read, tiles:read` only — anyone who views the JS source can extract it |
| **Lambda timeout = 30 s** | Alexandre's real extractor may push it over. If you hear his Sentinel Hub call takes ~25s, bump Lambda timeout to 60s in LD-1 |
| **Lambda cold start during demo** | Hit `/assess` once right before Dimi (or Angela) goes on stage — warm the function |
| **Discord webhook URL in git** | Never paste it into source files — Lambda env var only. `.env.local` is the only acceptable local home |
| **CORS on `OPTIONS` preflight** | Already handled in `lambda_handler.py:236`. If you change the response envelope, preserve it |
| **Demo fallbacks are load-bearing** | `lambda_handler.call_bedrock_agent()` and `App.jsx fetchAssessment()` both have try/except → demo fallback. **Never remove these** — they're what guarantees the pitch never shows a 500 |

---

## 👤 How Dimi wants you to behave

- **Decisive copilot, not a re-planner.** Time is short. Don't propose 3 options when one is obviously right.
- **Short, emoji-heavy responses.** Use ✅ ❌ ⚠️ 🔴 🟡 🟢 liberally. End every response with a status indicator (✅ Success / ❌ Failure / ⚠️ Warning).
- **He knows TS/React/C# well.** Currently working in Python (Lambda) + JS (Vite/React) — don't talk down. He's a senior dev.
- **When he makes a call, execute it.** Don't re-argue. If he says "we're keeping X," X stays.
- **Flag teammate dependencies early.** If a task needs info from Alexandre / Elitsa / Lyuben, log it in `specs/05-cross-team-asks/01-questions-for-team.md` and tell Dimi to ping — don't guess.
- **Don't create new spec docs unless he asks.** No "decision logs," no "summary files." The specs that exist are enough.
- **No commits / pushes unless he explicitly says** "commit" or "push." Even with hours to deadline.

---

## 📁 What Dimi owns vs doesn't

| Owns (edit freely) | Does NOT own (read-only) |
|---|---|
| `frontend/**` | `backend/sentinel_extractor.py` (Alexandre) |
| `backend/lambda_handler.py` | `backend/meteorology_rules.md` (Elitsa) |
| `backend/local_server.py` | `data_science/**` (Alexandre) |
| `backend/requirements.txt` | `specs/03-data-analysts/` (read-only context) |
| `specs/01-roadmap/` | `specs/04-meteorologist/` (read-only context) |
| `specs/02-lead-dev/` | |
| `specs/05-cross-team-asks/` (track answers here) | |
| `CLAUDE.md` (update on significant changes) | |

If a Lead Dev task requires touching one of the read-only files (e.g. need to add a new alert status, which means editing both `lambda_handler.py` `STATUS_META` and the shared list of codes in `meteorology_rules.md`), **stop and ask Dimi to coordinate with the owner** — don't edit the file unilaterally.

---

## 🙋 Open questions waiting on teammates (as of handoff time)

> Update this section as answers come in. Mirror to `specs/05-cross-team-asks/01-questions-for-team.md` answer log at the bottom.

### Alexandre Payen (Data Analysts)
- ⏳ **Q1 — Pip packages?** (heavy → need Lambda Layers / container)
- ⏳ **Q2 — Sentinel Hub OAuth env var names?**
- ⏳ Q3 — Realistic extractor latency? (might force Lambda timeout bump)
- ⏳ Q4 — Who owns the data-freshness guard? (you or him)
- ⏳ Q5 — Adding any new keys to the return dict? (informational)

### Elitsa Ilieva (Meteorologist)
- ⏳ Q1 — ETA for filling regional baselines (Section 5)?
- ⏳ Q2 — Adding any new alert status codes? (would force edits to 3 files)
- ⏳ Q3 — Confirm the 5 region IDs are unchanged?

### Lyuben Branzalov (AI summary layer)
- ⏳ Q1 — Editing the existing Bedrock prompt in `lambda_handler.py`, or building a separate `/summarize` endpoint?

---

## ✅ End-of-Saturday gate

The demo is "Tier 1 done" when **all** of the following hold:

- [ ] `https://<vercel-url>` loads, map renders, all region markers clickable
- [ ] Clicking a region triggers a real `/assess` call to the deployed Lambda (not local Flask)
- [ ] The Lambda returns a real Bedrock-generated assessment (not the `[DEMO MODE — Bedrock unavailable]` fallback string)
- [ ] At least one region produces a `WATCH` or `WARNING` status that fires a Discord alert
- [ ] The Discord embed shows correct status, confidence %, reasoning, and region ID
- [ ] `meteorology_rules.md` Section 5 (regional baselines) is filled with real values (Elitsa's deliverable)
- [ ] All 5 regions return real data, no `DUMMY` source string (Alexandre's deliverable)

If Alexandre + Elitsa deliverables are late, the frontend's built-in demo fallback still gives Dimi a working live pitch. Don't panic — just record a backup screen capture Sunday morning.

---

## 🎬 The pitch (3 minutes — Sunday 15:00)

| Time | Segment | Owner |
|------|---------|-------|
| 0:00–0:20 | Hook — real flood photo, human cost | TBD (probably Angela) |
| 0:20–0:40 | Gap — decision-support layer is missing | TBD |
| 0:40–1:20 | Product — HydroTwin live, click region, show AI assessment | TBD |
| 1:20–2:20 | Discord alert firing live | TBD |
| 2:20–2:50 | Ask — pilot / call to action | TBD |
| 2:50–3:00 | Close — one-liner | TBD |

**One thing to confirm with Dimi:** the README task list (which he's executing) is built around the **old global-regions / Discord prototype**. The brief in `initial_context.md` describes a **different product** (3 Bulgarian AOIs, Brevo email, replay button = pitch centerpiece). If Angela's pitch follows the brief's narrative, Dimi's tasks won't match her demo flow. Worth a 5-minute Angela sync — but only flag this once. Per Dimi's lead call, the README task list wins.

---

## 🚀 Start here

When Dimi sends his first message after reading this handoff:

1. Greet him briefly: "Saw the handoff. AWS access in hand — let's start. First: have you requested Bedrock model access yet?"
2. Confirm Bedrock model access status
3. Confirm Alexandre's Q1 + Q2 answers status
4. If both green → start LD-5 (Discord webhook)
5. If waiting → start LD-5 anyway (zero deps), then LD-1 with the deploy method to-be-decided

End response with `✅` and the next concrete action.

---

**Good luck. Pitch is tomorrow. Let's ship.** 💧
