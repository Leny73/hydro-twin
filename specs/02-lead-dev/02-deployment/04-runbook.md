# 🔁 Runbook — Redeploy & Operate

> Copy-paste commands for the most common operations on the live HydroTwin stack.
> Assumes you're at the repo root (`C:\Users\dimib\Desktop\hydro-twin\`) in a bash shell, with AWS creds in `~/.aws/credentials` and Vercel token available.

## 🗂️ v2 Stack inventory

| Resource | Name / ID | Notes |
|---|---|---|
| 🐍 Lambda — assess | `HydroTwin` | `lambda_handler.lambda_handler` · 256 MB · 30 s |
| 🐍 Lambda — subscribe | `HydroTwinSubscribe` | `subscribe_handler.lambda_handler` · 128 MB · 10 s |
| 🐍 Lambda — cron orchestrator | `HydroTwinCron` | `cron_handler.lambda_handler` · 256 MB · **5 min** |
| 🐍 Lambda — status reader | `HydroTwinStatus` | `status_handler.lambda_handler` · 128 MB · 10 s |
| 🔐 Shared role | `HydroTwinLambdaRole` | All 4 Lambdas use it (Bedrock + DynamoDB + CloudWatch) |
| 🗄️ DynamoDB — subscriptions | `HydroTwinSubscriptions` | PK=`email`, SK=`region_id` |
| 🗄️ DynamoDB — snapshots | `HydroTwinStatus` | PK=`region_id`, latest assessment per region |
| ⏱️ EventBridge rule | `HydroTwinCronSchedule` | `rate(30 minutes)` → invokes `HydroTwinCron` |
| 🌐 API Gateway (HTTP) | `sdnatb43dl` | `POST /assess` · `POST /subscribe` · `GET /status` |
| 🌐 Frontend | `https://hydrotwin.vercel.app` | Vercel project `hydrotwin` |

**Key principle — single zip, four Lambdas.** `hydrotwin-backend.zip` ships every handler + shared module. Each Lambda config sets the right `Handler`, so one `update-function-code` per function with the same artefact keeps them all in sync.

---

## 🐍 Backend Lambda — code-only update (all 4 functions)

When you change anything in `backend/*.py` or `backend/meteorology_rules.md`:

```bash
cd backend
rm -rf .build && mkdir .build
cp lambda_handler.py subscribe_handler.py cron_handler.py status_handler.py \
   regions.py sentinel_extractor.py meteorology_rules.md .build/

# Linux x86_64 wheels (must match Lambda runtime)
pip install --target .build \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  requests boto3 python-dotenv

# Build zip via Python (no `zip` binary in MSYS bash on Windows)
python -c "
import os, zipfile
out = '../hydrotwin-backend.zip'
if os.path.exists(out): os.remove(out)
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk('.build'):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in files:
            if f.endswith('.pyc'): continue
            z.write(os.path.join(root, f), os.path.relpath(os.path.join(root, f), '.build'))
print('zip built:', os.path.getsize(out)//1024, 'KB')
"

# Push to ALL 4 Lambdas (same artefact)
for fn in HydroTwin HydroTwinSubscribe HydroTwinCron HydroTwinStatus; do
  python -m awscli lambda update-function-code \
    --function-name "$fn" \
    --zip-file fileb://../hydrotwin-backend.zip \
    --query 'FunctionName' --output text
done

# Wait for all to settle
for fn in HydroTwin HydroTwinSubscribe HydroTwinCron HydroTwinStatus; do
  python -m awscli lambda wait function-updated --function-name "$fn" && echo "$fn settled"
done

cd ..
```

> ⚠️ **`python-dotenv` is required** — `sentinel_extractor.py` imports it. Skipping it crashes any Lambda whose handler transitively imports the extractor (`HydroTwin` and `HydroTwinCron`).

**Verify deploy:**

```bash
python -m awscli lambda wait function-updated --function-name HydroTwin
curl -X POST https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/assess \
  -H "Content-Type: application/json" \
  -d '{"region_id":"pleven","bbox":[23.9,43.15,25.2,43.7]}'
```

---

## ⏱️ Manually trigger the cron orchestrator

The cron normally runs every 30 min via EventBridge. To force a run (e.g. after redeploy, to refresh stale snapshots, or to test status-transition webhooks):

```bash
python -m awscli lambda invoke \
  --function-name HydroTwinCron \
  --payload '{}' \
  /c/Users/dimib/Desktop/hydro-twin/cron-out.json
cat /c/Users/dimib/Desktop/hydro-twin/cron-out.json
rm -f /c/Users/dimib/Desktop/hydro-twin/cron-out.json
```

Expected response shape:

```json
{"regions_total": 3, "regions_succeeded": 3, "regions_failed": 0,
 "webhooks_fired": 0, "transitions": [], "errors": []}
```

`webhooks_fired` only ticks up when a region's status code changes between runs (SAFE → DROUGHT_WATCH, FLOOD_WARNING → SAFE, etc.). De-dup is intentional — it stops Discord from getting spammed every 30 min.

**Inspect snapshot table contents:**

```bash
python -m awscli dynamodb scan --table-name HydroTwinStatus --region us-east-1 \
  --query 'Items[].[region_id.S, status.S, assessed_at.S]' --output table
```

**Smoke-test the public reader:**

```bash
curl -s https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/status | python -m json.tool
```

---

## ⏯️ Pause / resume the EventBridge schedule

To stop the 30-min cron (e.g. during a billing-sensitive period or while debugging):

```bash
# Pause
python -m awscli events disable-rule --name HydroTwinCronSchedule
# Resume
python -m awscli events enable-rule --name HydroTwinCronSchedule
# Inspect
python -m awscli events describe-rule --name HydroTwinCronSchedule \
  --query '[Name,State,ScheduleExpression]' --output text
```

---

## 🌍 Backend Lambda — update env vars

When `WEBHOOK_URL` or `BEDROCK_MODEL_ID` change. Edit `.aws-deploy/env-vars.json` first (gitignored), then push:

```bash
# Inspect / edit (no secret echoing)
python -c "
import json
p = r'C:\Users\dimib\Desktop\hydro-twin\.aws-deploy\env-vars.json'
with open(p) as f: d = json.load(f)
print(list(d['Variables'].keys()))   # name list only
"

# Push
python -m awscli lambda update-function-configuration \
  --function-name HydroTwin \
  --environment "file://C:/Users/dimib/Desktop/hydro-twin/.aws-deploy/env-vars.json" \
  --query 'Environment.Variables' \
  | python -c "
import json, sys
for k, v in json.load(sys.stdin).items():
    print(f'  {k} = {\"<masked>\" if any(s in k.lower() for s in [\"webhook\", \"key\", \"token\", \"secret\"]) else v}')
"
```

---

## 📜 Tail Lambda CloudWatch logs

```bash
python -c "
import boto3
logs = boto3.client('logs', region_name='us-east-1')
streams = logs.describe_log_streams(
    logGroupName='/aws/lambda/HydroTwin',
    orderBy='LastEventTime', descending=True, limit=1
)
stream = streams['logStreams'][0]['logStreamName']
events = logs.get_log_events(
    logGroupName='/aws/lambda/HydroTwin',
    logStreamName=stream, startFromHead=False, limit=50
)
for ev in events['events']:
    msg = ev['message'].rstrip()
    if msg: print(msg)
"
```

---

## 🌐 Frontend — redeploy to Vercel

When `frontend/src/**` changes:

```bash
export VERCEL_TOKEN="<your-vcp_*-token>"   # from your secret store
cd frontend
npx --yes vercel@latest deploy --prod --yes --token "$VERCEL_TOKEN"
cd ..
```

Output prints the new direct URL; the alias `https://hydrotwin.vercel.app` updates automatically.

---

## 🔑 Frontend — update env vars

```bash
export VERCEL_TOKEN="<your-vcp_*-token>"
cd frontend

# Remove old value first (env add doesn't overwrite — it errors)
npx --yes vercel@latest env rm VITE_API_ENDPOINT production --yes --token "$VERCEL_TOKEN"

# Add new value (stdin so the value never echoes)
printf '%s' "https://new-api-url.example.com/assess" \
  | npx --yes vercel@latest env add VITE_API_ENDPOINT production --token "$VERCEL_TOKEN"

# Redeploy to bake the new value into the JS bundle
npx --yes vercel@latest deploy --prod --yes --token "$VERCEL_TOKEN"
cd ..
```

---

## 🧪 Smoke test — full end-to-end

Run this after any change to either layer:

```bash
python << 'PYEOF'
import urllib.request, json, time, re

# 1. Frontend reachable
r = urllib.request.urlopen('https://hydrotwin.vercel.app/', timeout=10)
print(f'frontend: HTTP {r.status}')

# 2. API reachable + JSON envelope correct
api = 'https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/assess'
body = json.dumps({"region_id": "danube-basin", "bbox": [8, 42, 30, 52]}).encode()
req = urllib.request.Request(api, data=body, headers={'Content-Type': 'application/json'}, method='POST')
t0 = time.time()
r = urllib.request.urlopen(req, timeout=35)
elapsed = time.time() - t0
data = json.loads(r.read().decode())
print(f'api: HTTP {r.status} in {elapsed:.2f}s')
print(f'  status={data["status"]}, confidence={data["confidence"]}')
print(f'  bedrock={"FALLBACK" if "DEMO MODE" in data["reasoning"] else "LIVE"}')
PYEOF
```

---

## 🔄 Rotate compromised secrets

### AWS keys

If the access key in `backend/.env` is exposed:

1. AWS Console → IAM → Users → `hydrotwin-dev` → Security credentials
2. Deactivate the old access key
3. Create a new one
4. Update `backend/.env` with new `AWS_ACCESS_KEY` + `AWS_SECRET_ACCESS`
5. Re-run the credentials-write Python helper:

```bash
python << 'PYEOF'
import os, pathlib, configparser
keys = {}
with open(r'C:\Users\dimib\Desktop\hydro-twin\backend\.env') as f:
    for line in f:
        if '=' in line and not line.strip().startswith('#'):
            k, v = line.strip().split('=', 1)
            keys[k] = v.strip().strip('"\'')
ak = keys.get('AWS_ACCESS_KEY_ID') or keys['AWS_ACCESS_KEY']
sk = keys.get('AWS_SECRET_ACCESS_KEY') or keys['AWS_SECRET_ACCESS']
aws_dir = pathlib.Path(os.path.expanduser('~')) / '.aws'
aws_dir.mkdir(exist_ok=True)
cred = configparser.ConfigParser()
(aws_dir / 'credentials').exists() and cred.read(aws_dir / 'credentials')
cred['default'] = {'aws_access_key_id': ak, 'aws_secret_access_key': sk}
with open(aws_dir / 'credentials', 'w') as f: cred.write(f)
print('rotated ~/.aws/credentials')
PYEOF
```

### Vercel deploy token

1. https://vercel.com/account/tokens → revoke `hydrotwin-deploy`
2. Create a new token with same scope
3. Use the new token in `--token` flag for future deploys

### Mapbox token

1. https://account.mapbox.com/access-tokens/ → rotate the public token
2. Update `frontend/.env.local` (local) AND Vercel env var (prod):

```bash
export VERCEL_TOKEN="..."
cd frontend
npx vercel env rm VITE_MAPBOX_TOKEN production --yes --token "$VERCEL_TOKEN"
printf '%s' "$NEW_TOKEN" | npx vercel env add VITE_MAPBOX_TOKEN production --token "$VERCEL_TOKEN"
npx vercel deploy --prod --yes --token "$VERCEL_TOKEN"
```

---

## 🏃 Quick checks

| Question | Command |
|---|---|
| Is Lambda live? | `python -m awscli lambda get-function --function-name HydroTwin --query 'Configuration.[State,LastUpdateStatus,LastModified]'` |
| Are all 4 Lambdas in sync (same code)? | `for fn in HydroTwin HydroTwinSubscribe HydroTwinCron HydroTwinStatus; do python -m awscli lambda get-function-configuration --function-name $fn --query '[FunctionName,LastModified,CodeSha256]' --output text; done` |
| Is API Gateway live? | `python -m awscli apigatewayv2 get-api --api-id sdnatb43dl --query '[ApiEndpoint,Name]'` |
| Which routes exist? | `python -m awscli apigatewayv2 get-routes --api-id sdnatb43dl --query 'Items[].RouteKey' --output text` |
| Is Vercel project live? | `curl -I https://hydrotwin.vercel.app` (expect HTTP 200) |
| Is the cron schedule armed? | `python -m awscli events describe-rule --name HydroTwinCronSchedule --query '[Name,State,ScheduleExpression]' --output text` |
| When did the cron last run? | `python -m awscli logs describe-log-streams --log-group-name /aws/lambda/HydroTwinCron --order-by LastEventTime --descending --max-items 1 --query 'logStreams[0].[logStreamName,lastEventTimestamp]' --output text` |
| How many region snapshots in the table? | `python -m awscli dynamodb scan --table-name HydroTwinStatus --region us-east-1 --query 'Count'` |
| What env vars are on Lambda? | `python -m awscli lambda get-function-configuration --function-name HydroTwin --query 'Environment.Variables' | python -c "import json,sys; [print(k) for k in json.load(sys.stdin)]"` |
| What models are available? | `python -m awscli bedrock list-foundation-models --query "modelSummaries[?contains(modelId,'claude')].modelId" --output text` |

---

## 🚨 v2 troubleshooting — common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Cron returns `regions_failed > 0` and CloudWatch shows `No module named 'dotenv'` | Zip missing `python-dotenv` | Re-run the build with `python-dotenv` in the pip install line |
| `/status` returns `regions: []` indefinitely | Cron has never run, or DynamoDB perms missing on `HydroTwinLambdaRole` | Manually invoke cron + verify `HydroTwinStatusDynamoDB` inline policy is attached to the role |
| Bedrock reasoning names a different oblast than `region_id` | Prompt missing region context (the rules file mentions Pleven by name) | Verify `lambda_handler.call_bedrock_agent` receives `region_name` and includes the `=== REGION UNDER ASSESSMENT ===` block |
| `webhooks_fired` is 0 even after a real status change | Snapshot wasn't persisted on the prior run | Check CloudWatch `/aws/lambda/HydroTwinCron` for `put_item` errors; confirm the role has `dynamodb:PutItem` on `HydroTwinStatus` |
| Discord channel gets a webhook every 30 min for the same status | De-dup logic regression | `cron_handler._should_fire_webhook` should compare prior vs new — re-read it; should return `False` when statuses match |
| Frontend map polygons all neutral grey | `/status` fetch failed OR table is empty | Check browser DevTools → Network for `/status` response. If 200 with `regions: []`, kick the cron once. If 4xx/5xx, check API Gateway integration and the Lambda's CloudWatch logs |
