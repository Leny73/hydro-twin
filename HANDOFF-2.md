# 🤝 HANDOFF-2 — Sat Apr 25, afternoon

> **You** = a fresh Claude Code session, picking up after the AWS + Vercel deploys are done.
> **Dimi** = the user, the only human who'll talk to you. He's doing all the coding.
> **Pitch:** Sun Apr 26 · 15:00 at CASSINI Hackathon Bulgaria. **~21h left.**

---

## ⏰ The situation right now

- 🟢 **Backend is live** — Lambda `HydroTwin` + API Gateway `https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/assess` (us-east-1). Deployed via `python -m awscli` from this machine.
- 🟢 **Frontend is live** — `https://hydrotwin.vercel.app`. Project: `demetrios-projects-24fffdd4/hydrotwin`. Both env vars baked into the bundle.
- 🟡 **Two soft blockers** — Anthropic use case form (Bedrock returns demo fallback) + placeholder Discord webhook URL. Demo fallback hides both, pitch still works.
- 🎨 **Tatiana is on the frontend** — building the Subscribe-to-Alerts UI in parallel. Don't touch her files.

---

## 📚 Read these first (in order)

1. **`specs/02-lead-dev/02-deployment/README.md`** — what was deployed, URLs, IDs (3 KB)
2. **`specs/02-lead-dev/02-deployment/03-blockers.md`** — the 2 active blockers + how to clear them
3. **`specs/02-lead-dev/02-deployment/04-runbook.md`** — copy-paste redeploy commands for Lambda + Vercel
4. **`specs/02-lead-dev/01-tasks.md`** — Dimi's 10 tasks (LD-1 → LD-10), with LD-1/2/3/4 ✅ done
5. **`HANDOFF-FRONTEND.md`** — what Tatiana is building (LD-7 + maybe LD-10)
6. **`CLAUDE.md`** (root) — stack rules, integration contracts, hard NOs
7. *(skip unless needed)* `HANDOFF.md` — stale, written before the deploys

**Skim only:** `01-aws-deployment.md`, `02-vercel-deployment.md` — full forensic detail, useful when debugging.

---

## ✅ What got shipped this morning

| Task | State |
|---|---|
| **LD-1** Lambda + API Gateway | ✅ Live |
| **LD-2** Lambda env vars (`BEDROCK_MODEL_ID`, `BEDROCK_REGION`, `WEBHOOK_URL`) | ✅ Set |
| **LD-3** IAM role + Bedrock invoke policy | ✅ Attached |
| **LD-4** Frontend on Vercel | ✅ Live at https://hydrotwin.vercel.app |
| **LD-5** Discord/Telegram notification code | ✅ Tatiana shipped earlier |
| Smoke test (HTTP 200, JSON envelope, CORS) | ✅ Verified |

### 🤖 Bedrock model decision

Switched from `anthropic.claude-3-sonnet-20240229-v1:0` (LEGACY, refuses to invoke) to **`us.anthropic.claude-sonnet-4-6`**. Newer Claude models on Bedrock require:

- The `us.` prefix (cross-region inference profile, NOT plain foundation-model invoke)
- Account-level Anthropic use case form submitted (one-time)

If Dimi mentions changing the model, alternates that work in this account: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (cheap), `us.anthropic.claude-opus-4-5-20251101-v1:0` (overkill).

---

## 🟡 Two blockers waiting on humans

### 1. Anthropic use case form

**Symptom:** every Bedrock invoke returns `ResourceNotFoundException: Model use case details have not been submitted`. Demo fallback handles it.

**Action:** Dimi or his lead opens AWS Console → Bedrock (us-east-1) → Bedrock configurations → Model access → finds Anthropic use-case form → fills out (~2 min) → waits 15 min → re-tests. See `03-blockers.md` for the exact form copy and re-test command.

### 2. Real Discord webhook URL

**Symptom:** Lambda env `WEBHOOK_URL` is the literal placeholder `https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN`. Webhook fires fail with 400 (non-fatal, Lambda still returns 200).

**Action:** Dimi pings Tatiana for the real URL → update Lambda env via the runbook commands. Also worth asking her: does the deployed `lambda_handler.py` need to merge her Telegram support? Currently the deployed code only sends Discord-format embeds — her Telegram work may live elsewhere.

---

## 🎯 Dimi's open tasks

### 🔴 Primary: **LD-8 — `/subscribe` Lambda + DynamoDB**

Tatiana is building the subscribe **UI** (LD-7) right now. As soon as her form submits a `POST /subscribe`, it needs an endpoint to hit.

- **New file:** `backend/subscribe_handler.py`
- **DynamoDB table:** `HydroTwinSubscriptions` (PK = `email`, SK = `region_id`)
- **API Gateway route:** `POST /subscribe` on the existing API ID `sdnatb43dl`
- **IAM:** add `dynamodb:PutItem` to `HydroTwinLambdaRole` (or a new role for `HydroTwinSubscribe`)
- **Body validation:** require `email` (regex) + `region_id` ∈ the 5 known IDs from `App.jsx`
- **Response:** 201 on success with `{ message: "subscribed" }`, 400 on invalid input, 409 on duplicate
- **CORS:** must mirror the existing `POST /assess` config (already wildcard at the API level)

Time: ~1.5–2h. Dimi is comfortable in Python + AWS at this point — drive him with concrete `python -m awscli` calls.

### 🟡 Secondary (parallel-friendly)

- 🧪 **Browser-smoke the live Vercel URL** on his phone + desktop. Check: map renders, all 5 markers clickable, AlertPanel responsive. *Manual only — Claude can't see browsers.*
- 🟡 Once Tatiana sends real Discord URL → update Lambda env (one runbook command — see `04-runbook.md` § "update env vars")
- 🟡 Once Anthropic form approved → re-test, confirm `[DEMO MODE — Bedrock unavailable]` string is gone from `reasoning`

### 🟢 Nice-to-have if time permits

- **LD-9** — add Bulgarian AOIs to `REGIONS[]` in `App.jsx`. The `initial_context.md` brief calls for 3 Bulgarian regions; current 5 regions are global. Pitch impact only if Angela's pitch follows the brief narrative — confirm with her first.
- **Vercel Preview env vars** — currently only Production + Development envs are set. Branch deploys from Tatiana's PR won't render the map. Add via `vercel env add VITE_MAPBOX_TOKEN preview` + same for `VITE_API_ENDPOINT`.
- **Backup screen recording** — if Bedrock form never approves, record a 30s loop of the live demo Sunday morning as a fallback for the pitch.

---

## 🎨 What Tatiana is building (DO NOT touch her files)

She owns this branch + scope (full brief in `HANDOFF-FRONTEND.md`):

| Task | File | Status |
|---|---|---|
| **LD-7** Subscribe UI — inline form, email validation, POST to `/subscribe`, toast states | `frontend/src/components/AlertPanel.jsx` | 🔄 In progress |
| **LD-10** SVG sparkline (stretch) | `frontend/src/components/` (new file) | ⏳ Stretch |

**Hard rule:** if Dimi asks you to change `AlertPanel.jsx`, **stop and check** — Tatiana is mid-PR there. Tell him to coordinate or wait for her merge. Suggest he edit `App.jsx` or backend instead.

Her PR will hit `main` from branch `20260425-subscribe-ui`. When it lands, the Subscribe button connects to LD-8 (Dimi's `/subscribe` Lambda) automatically — they're decoupled by the API contract.

---

## 🚦 Recommended execution order today

1. **5 min** — Dimi pings Tatiana for real Discord URL, submits Anthropic form (or asks lead to)
2. **5 min** — Update Lambda `WEBHOOK_URL` env once URL arrives (runbook one-liner)
3. **15 min wait** — Anthropic form propagation → smoke-test, confirm Bedrock works live
4. **1.5–2h** — LD-8: `/subscribe` Lambda + DynamoDB + API Gateway route + IAM update
5. **30 min** — Tatiana's PR lands → Dimi reviews → smoke test full subscribe flow end-to-end
6. **Sunday morning** — pitch rehearsal, backup screen recording, warm Lambda before stage

---

## ⚠️ Critical "watch out for"

| Risk | Mitigation |
|---|---|
| **AWS CLI is `python -m awscli`, not `aws`** | The Windows CLI was installed via `pip install awscli`. Always use `python -m awscli`. Don't suggest installing the v2 MSI mid-hackathon. |
| **`backend/.env` uses non-standard key names** | `AWS_ACCESS_KEY` (not `AWS_ACCESS_KEY_ID`), `AWS_SECRET_ACCESS` (not `..._KEY`). Don't rename — `~/.aws/credentials` already has them under correct names |
| **Vercel deploy token (`vcp_*`) is in chat history** | Dimi can revoke at https://vercel.com/account/tokens after the demo. Don't paste it into source files. |
| **Lambda zip needs Linux x86_64 wheels** | Build with `--platform manylinux2014_x86_64 --only-binary=:all:` — see `04-runbook.md`. Plain `pip install -t .` produces Windows `.pyd` files that crash Lambda. |
| **`anthropic.*` model IDs need `us.` prefix** | Direct foundation-model invoke gets `ValidationException` for current-gen models. Always use cross-region inference profile IDs. |
| **API Gateway quick-create doesn't auto-attach Lambda permission** | When adding a new route (e.g. `/subscribe`), explicitly run `lambda add-permission` — see how LD-1 did it. |
| **Demo fallbacks are load-bearing** | `lambda_handler.call_bedrock_agent()` and `App.jsx fetchAssessment()` both have try/except → demo fallback. **Never remove these.** |
| **Don't commit `.env`, `.aws-deploy/`, `*.zip`** | All gitignored. Check `git status` before commits. |

---

## 👤 How Dimi wants you to behave

- **Decisive copilot, not a re-planner.** Time is short. One option, not three.
- **Short, emoji-heavy responses.** Use ✅ ❌ ⚠️ 🔴 🟡 🟢 liberally. End every response with a status indicator.
- **Senior dev** — TS/React/C# strong, working in Python/JS for hackathon. Don't talk down.
- **Execute, don't re-argue.** If he made a call (model choice, stack lock), it stays.
- **No commits / pushes unless he says** "commit" or "push." Strict.
- **Don't create new spec docs** unless he asks. The `specs/02-lead-dev/02-deployment/` folder already covers what got shipped.
- **Don't propose framework migrations** — stack is locked (Vite + plain React + Mapbox + Python Lambda + Bedrock + Discord/Telegram).

---

## 📁 Boundaries

| Owns (edit freely) | Does NOT own (read-only) |
|---|---|
| `backend/lambda_handler.py` | `backend/sentinel_extractor.py` (Alexandre) |
| `backend/local_server.py` | `backend/meteorology_rules.md` (Elitsa) |
| `backend/requirements.txt` | `data_science/**` (Alexandre) |
| **NEW** `backend/subscribe_handler.py` (LD-8) | `frontend/src/components/AlertPanel.jsx` (Tatiana — in-flight) |
| `frontend/src/App.jsx` (when not colliding with Tatiana) | |
| `specs/02-lead-dev/**` | |
| `CLAUDE.md`, `HANDOFF*.md` | |

---

## 🚀 Start here when Dimi sends his first message

1. Greet briefly: *"Saw the handoff. Backend + frontend are live. What are we hitting first — LD-8, blocker chase, or something else?"*
2. If he says **LD-8** → start by checking `backend/lambda_handler.py` to mirror its style, then design the DynamoDB schema + the new handler skeleton
3. If he says **blockers** → walk through the Anthropic form (he or lead clicks) + offer to update the Lambda webhook env once Tatiana sends the URL
4. If he says **review Tatiana's PR** → wait for her to push the branch, then read `frontend/src/components/AlertPanel.jsx` against the LD-7 acceptance criteria in `01-tasks.md`

End your first response with the next concrete action and a status indicator. ✅

---

**Backend is live. Frontend is live. Tatiana is shipping. Pitch is in 21h. Let's keep moving.** 💧
