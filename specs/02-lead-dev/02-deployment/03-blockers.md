# 🟡 Active Blockers

> Things that aren't fully done. Pitch is **Sun Apr 26 · 15:00**.
> Demo fallback hides both — pitch will work even if neither is resolved, but real AI assessments + real Discord alerts elevate the demo.

---

## 1️⃣ Anthropic use case form (Bedrock model access)

### 🔴 Symptom

Every Bedrock invoke from the deployed Lambda returns:

```
ResourceNotFoundException: Model use case details have not been submitted
for this account. Fill out the Anthropic use case details form before using
the model. If you have already filled out the form, try again in 15 minutes.
```

The Lambda's `call_bedrock_agent()` catches this and returns the demo fallback:

```json
{
  "status": "FLOOD_WATCH",
  "confidence": 0.78,
  "reasoning": "[DEMO MODE — Bedrock unavailable] River levels in this zone..."
}
```

### 🛠️ How to clear

**Owner:** Dimi or AWS account lead.

1. AWS Console → **Bedrock** (us-east-1)
2. Left sidebar → **Bedrock configurations** → **Model access**
3. Look for **"Anthropic — Submit use case details"** banner or link near Claude models
4. Fill out the form (~2 min):
   - Company name
   - Use case description (e.g. *"Flood/drought early warning for European municipalities — submitting structured JSON risk assessments based on Sentinel EO + OpenMeteo weather inputs"*)
   - Expected volume (low — hackathon demo)
5. Submit → **wait ~15 min** for propagation
6. Re-test with:

```bash
curl -X POST https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/assess \
  -H "Content-Type: application/json" \
  -d '{"region_id":"danube-basin","bbox":[8,42,30,52]}' \
  | python -c "import json,sys; d=json.loads(sys.stdin.read()); print('OK!' if 'DEMO MODE' not in d['reasoning'] else 'still fallback')"
```

### Why this happened

This is an **AWS-wide policy change** — Anthropic models on Bedrock now require account-level use case attestation before any invoke. It's a one-time form per AWS account, not per IAM identity or per model.

### Fallback behaviour (what the pitch will show if not cleared)

Pitch demo continues to work — every region returns a believable `FLOOD_WATCH` with confidence 0.78 and a hand-written `reasoning` string from `lambda_handler.call_bedrock_agent()`. The reasoning is realistic enough to pass casual inspection on stage.

---

## 2️⃣ Real Discord webhook URL

### 🔴 Symptom

Lambda env var `WEBHOOK_URL` is currently:

```
https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN
```

(literally the placeholder from `.env.example`). Every webhook fire returns `400 Bad Request`. Lambda execution is unaffected — the `try/except` in `trigger_webhook` makes it non-fatal.

### 🛠️ How to clear

**Owner:** Tatiana (already has the real URL from her notification work) → Dimi.

1. Tatiana sends Dimi the real Discord webhook URL (and Telegram URL if she added one)
2. Dimi updates the Lambda env var:

```bash
# Read current env vars file (locally cached after deploy)
NEW_URL='https://discord.com/api/webhooks/<real-id>/<real-token>'

# Update in-place using existing env-vars.json template
python -c "
import json
p = r'C:\Users\dimib\Desktop\hydro-twin\.aws-deploy\env-vars.json'
with open(p) as f: d = json.load(f)
d['Variables']['WEBHOOK_URL'] = '$NEW_URL'
with open(p, 'w') as f: json.dump(d, f)
"

# Push to Lambda
python -m awscli lambda update-function-configuration \
  --function-name HydroTwin \
  --environment "file://C:/Users/dimib/Desktop/hydro-twin/.aws-deploy/env-vars.json"
```

3. Smoke test by forcing a `WATCH`/`WARNING` payload — the Discord channel should get a colour-coded embed within 2s.

### Open question on Telegram

Tatiana's notification work adds Discord **and** Telegram — but the deployed `lambda_handler.py` only has Discord embed code. Two options:

- **Option A:** keep Discord only on the deployed Lambda; Tatiana's Telegram lives elsewhere (her local server, a separate fanout, etc.) — confirm with her
- **Option B:** merge her changes into `lambda_handler.py` and redeploy. This requires:
  - New env var `TELEGRAM_CHAT_ID`
  - Modified `WEBHOOK_URL` parser to detect Telegram vs Discord by hostname
  - Re-zip + `update-function-code` (see `04-runbook.md`)

→ Ask Tatiana which path she took.

---

## 3️⃣ Deferred (not blocking pitch but tracked)

| Item | Owner | Notes |
|---|---|---|
| Vercel **Preview** env vars not set | Dimi | Branch previews won't render map. Add via `vercel env add ... preview` if Tatiana's PR creates one |
| `sentinel_extractor.py` is still a stub returning hardcoded dict | Alexandre | Backend works regardless — Bedrock prompts use the dummy data fine |
| `meteorology_rules.md` Section 5 (regional baselines) is placeholder | Elitsa | Loaded verbatim by Lambda; placeholders won't break anything but reduce assessment quality |
| `/subscribe` endpoint (LD-7 + LD-8) | Dimi (Lambda) + Tatiana (UI) | Subscribe button is `window.alert()` stub on prod |
| Vercel deploy token (`vcp_*`) saved in chat history | Dimi | Revoke at https://vercel.com/account/tokens after demo if concerned |

---

## 🎬 Pitch-day priority

Both blockers have working demo fallbacks. **If we have to pick one to clear first, it's the Anthropic form** — real AI reasoning differentiates the pitch much more than real Discord alerts. The Discord embed UX is identical whether the URL is real or placeholder; only delivery differs.
