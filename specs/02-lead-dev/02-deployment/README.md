# 🚀 Deployment Log — HydroTwin (Sat Apr 25, 2026)

> **What this folder is:** snapshot of what actually got deployed for LD-1 → LD-4, including IDs, URLs, decisions, and active blockers.
> **Audience:** future Claude sessions, teammates, post-hackathon retro.

---

## 🟢 Live URLs

| Layer | URL |
|---|---|
| 🌐 **Frontend** | https://hydrotwin.vercel.app |
| 🔌 **API endpoint** | https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/assess |
| 📊 **Vercel project** | demetrios-projects-24fffdd4/hydrotwin |
| 🔍 **Lambda inspector** | AWS Console → Lambda → `HydroTwin` (us-east-1) |

---

## ✅ Tasks completed in this session

| Task | Outcome |
|---|---|
| **LD-1** Lambda + API Gateway | ✅ Deployed — see [01-aws-deployment.md](./01-aws-deployment.md) |
| **LD-2** Lambda env vars | ✅ Set (model, region, webhook) |
| **LD-3** IAM Bedrock policy | ✅ Attached (broad `anthropic.*` + inference profiles) |
| **LD-4** Frontend on Vercel | ✅ Deployed — see [02-vercel-deployment.md](./02-vercel-deployment.md) |
| **Smoke test** | ✅ HTTP 200, JSON envelope, CORS — see [01-aws-deployment.md](./01-aws-deployment.md#smoke-test) |

---

## 🟡 Blockers still open

See [03-blockers.md](./03-blockers.md) for full details.

1. ⏳ **Anthropic use case form** — every Bedrock invoke fails with `ResourceNotFoundException` until Dimi or lead submits the form in Bedrock Console (~2 min + 15 min wait)
2. ⏳ **Real Discord webhook URL** — Lambda env `WEBHOOK_URL` is the placeholder from `.env.example`. Tatiana has the real one from her notification work

Demo fallback hides both issues for the pitch — see "Demo-First Philosophy" section in root `CLAUDE.md`.

---

## 📂 Files in this folder

- 📄 [`README.md`](./README.md) — this file
- 📄 [`01-aws-deployment.md`](./01-aws-deployment.md) — Lambda, IAM, API Gateway, model choice rationale
- 📄 [`02-vercel-deployment.md`](./02-vercel-deployment.md) — Vercel project setup, env vars, build verification
- 📄 [`03-blockers.md`](./03-blockers.md) — active external blockers + how to clear them
- 📄 [`04-runbook.md`](./04-runbook.md) — redeploy commands (zip Lambda, push frontend, update env vars)

---

## 🗓️ Timeline

- **09:30** — AWS access keys received from lead
- **10:00** — Initial deploy blocked: `hydrotwin-dev` IAM user too scoped (no Lambda/IAM perms)
- **10:15** — Lead granted broader permissions
- **10:30** — Lambda + API Gateway live, smoke test HTTP 200
- **10:35** — Bedrock invoke failed: model ID needed inference profile prefix (`us.anthropic.*`)
- **10:40** — Switched to `us.anthropic.claude-sonnet-4-6` (current generation)
- **10:50** — New blocker: Anthropic use case form required for all Anthropic models in this account
- **13:30** — Vercel deploy live at https://hydrotwin.vercel.app
- **13:40** — End-of-deploy snapshot captured (this folder)

---

**Next:** see `03-blockers.md` for unblock paths, then `04-runbook.md` for redeploy commands when teammate work merges.
