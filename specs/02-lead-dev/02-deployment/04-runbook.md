# 🔁 Runbook — Redeploy & Operate

> Copy-paste commands for the most common operations on the live HydroTwin stack.
> Assumes you're at the repo root (`C:\Users\dimib\Desktop\hydro-twin\`) in a bash shell, with AWS creds in `~/.aws/credentials` and Vercel token available.

---

## 🐍 Backend Lambda — code-only update

When you change `lambda_handler.py`, `sentinel_extractor.py`, or `meteorology_rules.md`:

```bash
cd backend
rm -rf .build && mkdir .build
cp lambda_handler.py sentinel_extractor.py meteorology_rules.md .build/

# Linux x86_64 wheels (must match Lambda runtime)
pip install --target .build \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  requests boto3

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

# Push to Lambda
python -m awscli lambda update-function-code \
  --function-name HydroTwin \
  --zip-file fileb://../hydrotwin-backend.zip \
  --query 'LastModified'

cd ..
```

**Verify deploy:**

```bash
python -m awscli lambda wait function-updated --function-name HydroTwin
curl -X POST https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/assess \
  -H "Content-Type: application/json" \
  -d '{"region_id":"danube-basin","bbox":[8,42,30,52]}'
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
| Is API Gateway live? | `python -m awscli apigatewayv2 get-api --api-id sdnatb43dl --query '[ApiEndpoint,Name]'` |
| Is Vercel project live? | `curl -I https://hydrotwin.vercel.app` (expect HTTP 200) |
| What env vars are on Lambda? | `python -m awscli lambda get-function-configuration --function-name HydroTwin --query 'Environment.Variables' | python -c "import json,sys; [print(k) for k in json.load(sys.stdin)]"` |
| What models are available? | `python -m awscli bedrock list-foundation-models --query "modelSummaries[?contains(modelId,'claude')].modelId" --output text` |
