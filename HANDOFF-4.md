# 🤝 HANDOFF-4 — v2 Sprint (post-pitch architecture + features)

> **You** = a fresh Claude Code session, picking up the **v2 sprint** for HydroTwin.
> **Dimi** = the user, sole human you'll talk to. Lead dev, codes solo with Claude.
> **Date opened:** 2026-04-25, post-pitch sprint.
> **Pitch (v1) is done** — this is the *next phase*, not the demo dash.

---

## 📚 Read these first (in this order)

1. **`CLAUDE.md`** (root) — stack rules, integration contracts, hard NOs, demo-fallback philosophy
2. **`specs/02-lead-dev/03-v2-tasks.md`** — the **v2 sprint stubs** you'll be expanding + executing. This is your scope.
3. **`specs/02-lead-dev/01-tasks.md`** — v1 tasks (all ✅ done, useful as context for what already exists)
4. **`specs/02-lead-dev/02-deployment/README.md`** + `04-runbook.md` — what's deployed and how to redeploy (Lambda + Vercel)
5. **`HANDOFF-2.md`** — original deployment handoff (current architecture state)
6. *(skip unless relevant)* `HANDOFF.md`, `HANDOFF-FRONTEND.md`, `HANDOFF-3.md` — older, role-specific handoffs

---

## ⏰ Where v1 left us (production state)

| Layer | State |
|---|---|
| 🌐 Frontend | ✅ `https://hydrotwin.vercel.app` — single Pleven Oblast zone, click → AlertPanel with live Bedrock reasoning |
| 🔌 API | ✅ `https://sdnatb43dl.execute-api.us-east-1.amazonaws.com` (`/assess` + `/subscribe`) |
| 🐍 Lambda | ✅ `HydroTwin` (assess) + `HydroTwinSubscribe` (subscribe) — both live, IAM scoped, env vars set |
| 🤖 Bedrock | ✅ `us.anthropic.claude-sonnet-4-6` — Anthropic use-case form approved, returns real reasoning |
| 🛰️ Sentinel Hub | ✅ `SH_CLIENT_ID` / `SH_CLIENT_SECRET` set on Lambda env, real EO data flowing |
| 🗄️ DynamoDB | ✅ `HydroTwinSubscriptions` (PK=email, SK=region_id) — only used by `/subscribe` so far |
| 📢 Discord webhook | ✅ Real URL set, fires on every `WATCH`/`WARNING` from `/assess` |
| 🎨 AlertPanel | ✅ Subscribe button at top, sparkline mounted, react-markdown reasoning |

---

## 🎯 Your scope — v2 sprint

**You own these (5 of 6 v2 tasks):**

| # | Task | Why it matters |
|---|------|----------------|
| **V2-1** | Add more monitored regions (list pending — Dimi will provide) | Expand beyond Pleven |
| **V2-2** | Pre-computed map state + legend on page load | Removes click-to-load wait, turns the map into an at-a-glance dashboard |
| **V2-3** | Scheduled background Lambda runs (cron) | Notifications currently only fire on user clicks — need real-time monitoring |
| **V2-4** | Drill-down per-region risk detail | More granular spatial info when a region is clicked |
| **V2-6** | Visualize data sources used in computations | Citations UI plumbing |

**🚫 NOT yours — Dimi's colleague is doing this in parallel:**

| # | Task | Owned by |
|---|------|----------|
| **V2-5** | Time-period dropdown / replay for demo day | Colleague (parallel work-stream) |

**Coordination on V2-5:** the colleague needs a **history table** (time-series of assessments per region). Your V2-2 builds a **snapshot table** (last assessment per region only). When you design the cron + DB schema, **leave room** for the colleague to:
- Append each cron run to a separate history table without changing your snapshot logic
- Reuse the same EventBridge / Vercel Cron trigger you create

Don't build the history table yourself. Don't touch time-travel UI. If your design forces V2-5 into a corner, raise it with Dimi before committing.

---

## 🧩 Before you write any code — PLAN FIRST

Dimi explicitly asked for a **plan + cleared task spec** before execution. Do these in order, get sign-off at each gate:

### Gate 1 — Architecture decisions (cross-cutting)

`03-v2-tasks.md` § "Cross-cutting concerns" lists 5 decisions that affect multiple tasks. Resolve them up front:

1. **DB choice** for cached state — DynamoDB extension vs Vercel KV vs Edge Config vs S3 vs Postgres. Make a recommendation with one sentence on the tradeoff. Default lean: **extend DynamoDB** (lowest friction, already in stack, IAM already wired)
2. **Cron mechanism** — EventBridge Scheduler vs Vercel Cron vs `cron-job.org`. Default lean: **EventBridge** (AWS-native, already in stack, no Vercel function needed)
3. **Notification de-dup logic** — fire only on status change? Quiet hours? Default lean: **only on status change** (`SAFE → *_WATCH/WARNING` or escalation), skip same-status repeat fires
4. **`/assess` response contract** — does V2-6 require adding a `sources: []` field? If yes, it's a contract change that needs to be coordinated with `sentinel_extractor.py` owner (Alexandre)
5. **V2-4 feasibility** — flag for Alexandre. Don't commit time to V2-4 until he confirms whether sub-region drill-down is achievable with the current data resolution

**Output:** a short architecture proposal in chat (decisions + tradeoffs in 1 sentence each). **Wait for Dimi's sign-off** before proceeding.

### Gate 2 — Expand each stub into a real spec

Once architecture is locked, **edit `03-v2-tasks.md` directly** to convert each stub into a real task spec. For each of V2-1, V2-2, V2-3, V2-4, V2-6:

- Replace "Stub — needs expansion" with a concrete acceptance criteria checklist
- Resolve open questions inline (or flag what's still pending from whom)
- Add a **Files** section
- Add a **Time estimate**
- Note **PR boundaries** if the task spans multiple PRs

Use `01-tasks.md` (the v1 spec) as the format template — it's known-good.

**Output:** an updated `03-v2-tasks.md` PR/diff for Dimi to review. **Wait for sign-off.**

### Gate 3 — Recommend execution order

After expansion, propose the order you'll execute in. Default order from `03-v2-tasks.md`:

1. V2-1 (regions) — unblocks frontend
2. V2-2 + V2-3 together (shared cron + DB infrastructure)
3. V2-6 (citations UI plumbing — small, content-dependent)
4. V2-4 (only if Alexandre greenlights feasibility)

V2-5 is the colleague's — don't list it.

**Output:** order + rationale. Then execute.

---

## 🚦 Critical rules (carried forward from v1 CLAUDE.md)

These are **non-negotiable** — they exist because something previously broke when ignored:

- ❌ **NEVER** rename keys in `get_eo_and_weather_data()` return dict — `lambda_handler.py` and Bedrock prompt depend on the schema. Adding new keys is fine; renaming is not
- ❌ **NEVER** change the function signature `get_eo_and_weather_data(bbox: list) -> dict`
- ❌ **NEVER** modify `meteorology_rules.md` thresholds without Elitsa's approval — they go straight into Claude's prompt as authoritative context
- ❌ **NEVER** remove the demo fallback in `lambda_handler.call_bedrock_agent()` — it keeps the demo bullet-proof when Bedrock has a hiccup
- ❌ **NEVER** remove the demo fallback in `App.jsx fetchAssessment()` — same reason, frontside
- ❌ **NEVER** make `trigger_webhook` failures fatal — webhook delivery must not block the API response
- ❌ **NEVER** commit `.env.local`, `.env`, `.aws-deploy/`, `*.zip`, or any secrets
- ❌ **NEVER** ship Mapbox tokens with broader scope than `styles:read, tiles:read`
- ❌ **NEVER** break the Lambda response envelope (`statusCode` + `headers` with CORS + `body` JSON-stringified)
- ✅ **ALWAYS** keep CORS headers on every response including `OPTIONS` preflight short-circuit
- ✅ **ALWAYS** use `temperature=0.1` and request strict JSON in Bedrock prompts
- ✅ **ALWAYS** keep 44×44 px touch targets for mobile (WCAG 2.5.5)
- ✅ **ALWAYS** use `100dvh` not `100vh` on full-height frontend elements
- ✅ **ALWAYS** ask before AWS infra changes (new IAM policies, DB schema, API Gateway routes), credential rotation, force pushes

---

## 🚫 Files / scopes you do NOT own

| Path | Owner | Why off-limits |
|---|---|---|
| `backend/sentinel_extractor.py` + `backend/sentinel_extractor/` | Alexandre (Data Analyst) | Real EO extraction logic — coordinate via the dict-return contract only |
| `backend/meteorology_rules.md` | Elitsa (Meteorologist, NIMH) | Authoritative thresholds — needs her approval to edit |
| `data_science/**` | Alexandre | Notebook scratch space |
| Anything related to V2-5 — time-travel UI, history table, replay logic | Dimi's colleague | Parallel work-stream; coordinate, don't overlap |

You **can** edit `lambda_handler.py`, `subscribe_handler.py`, frontend `src/**`, all spec files, deployment runbook.

---

## 🛠️ Local dev (5 min)

```bash
# Backend (Flask shim that mimics API Gateway → Lambda)
pip install --user --break-system-packages flask flask-cors requests boto3 python-dotenv
python backend/local_server.py   # → http://localhost:5050/{assess,subscribe}

# Frontend
cd frontend
npm install
cp .env.example .env.local        # ask Dimi for VITE_MAPBOX_TOKEN if missing
npm run dev -- --host             # → http://localhost:5173 + LAN URL for phone testing
```

**Smoke-test the live API** without redeploying:

```bash
curl -X POST https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/assess \
  -H 'Content-Type: application/json' \
  -d '{"region_id":"pleven","bbox":[23.9,43.15,25.2,43.7]}'
```

Reasoning should NOT contain `[DEMO MODE` — that means Bedrock is live.

---

## ⚠️ Critical "watch out for"

| Risk | Mitigation |
|---|---|
| **AWS CLI is `python -m awscli`, not `aws`** | Installed via pip on this machine. Don't suggest installing the v2 MSI mid-sprint |
| **Lambda zip needs Linux x86_64 wheels** | Build with `--platform manylinux2014_x86_64 --only-binary=:all:` — see `04-runbook.md`. Plain `pip install -t .` produces Windows `.pyd` files that crash Lambda |
| **`anthropic.*` model IDs need `us.` prefix** | Direct foundation-model invoke errors for current-gen models. Use cross-region inference profile IDs |
| **API Gateway quick-create doesn't auto-attach Lambda permission** | When adding a new route (e.g. `/status`, `/cron-trigger`), explicitly run `lambda add-permission` — see how `/assess` and `/subscribe` did it |
| **Demo fallbacks are load-bearing** | Both `lambda_handler.call_bedrock_agent()` and `App.jsx fetchAssessment()` have try/except → demo fallback. Never remove |
| **`vercel env add` CLI is broken in non-interactive mode for preview targets** | Returns `action_required: git_branch_required` even with `--yes`. Use the REST API: `POST /v10/projects/{id}/env` with `target: ["preview"]`. See `01-tasks.md` § Findings |
| **DynamoDB merge-update for Lambda env** | `update-function-configuration --environment` REPLACES the whole environment. Always **read live first**, merge, then push, or you'll wipe existing keys |

---

## 👤 How Dimi wants you to behave

- **Decisive copilot, not a re-planner.** One option, not three. State your recommendation; let him override
- **Short, emoji-heavy responses.** Use ✅ ❌ ⚠️ 🔴 🟡 🟢 liberally. End every response with a status indicator
- **Senior dev** — TS/React/C# strong, working in Python/JS for hackathon. Don't talk down
- **Execute, don't re-litigate.** If he made a call (model choice, stack lock, Pleven-only scope), it stays
- **No commits / pushes unless he says** "commit" or "push." Strict
- **No new spec docs** unless he asks. Edit `03-v2-tasks.md` in place; don't create satellite files
- **Stack is locked** — Vite + plain React + Mapbox + Python Lambda + Bedrock + DynamoDB + Discord. Don't propose framework migrations
- **Ask before AWS infra changes** — new IAM policies, DB tables, API Gateway routes, credential rotation. He'll authorise, you execute
- **Status indicator confidence at end of significant changes:**
  - 🟢 95–100% — single file, fallback verified, no schema impact
  - 🟡 80–94% — multi-file, locally smoke-tested
  - 🟠 60–79% — touches contracts (extractor schema, response envelope, status codes), needs E2E verification
  - 🔴 <60% — high risk (auth, IAM, AWS infra), needs hands-on validation by Dimi

---

## 🚀 Start here when Dimi sends his first message

1. **Read** `specs/02-lead-dev/03-v2-tasks.md` end-to-end — it's your sprint
2. **Greet briefly:** *"Read the v2 stubs. Five tasks: V2-1, V2-2, V2-3, V2-4, V2-6 (V2-5 is colleague's). Want me to start with the architecture decisions for the cross-cutting concerns, or do you want to lock the region list (V2-1) first?"*
3. Whichever he picks → **propose, get sign-off, then execute.** Don't skip the proposal step
4. When you start expanding stubs in `03-v2-tasks.md`, mirror the format of `01-tasks.md` (acceptance criteria as `- [ ]` checkboxes, **Files**, **Time** estimate, **Dependencies**)
5. End your first response with the next concrete action and a 🟢/🟡/🟠 confidence indicator

---

## 🎬 Sprint goal in one sentence

**Turn HydroTwin from a click-to-assess prototype into a continuously-monitoring multi-region dashboard with at-a-glance status, scheduled real notifications, drill-down detail, and source attribution — without breaking the demo fallbacks that kept v1 bullet-proof.**

---

**v1 is live. v2 is on you. Plan first, then execute. Ask before AWS infra changes.** 💧
