# ☁️ AWS Deployment — Lambda + API Gateway + IAM

> Covers **LD-1** (Lambda + API Gateway), **LD-2** (env vars), **LD-3** (IAM Bedrock policy).
> Status: ✅ All deployed. Bedrock invoke gated on Anthropic use case form (see `03-blockers.md`).

---

## 🆔 AWS Resource Inventory

| Resource | Identifier |
|---|---|
| **AWS Account** | `640053196632` |
| **Region** | `us-east-1` |
| **IAM User (deployer)** | `arn:aws:iam::640053196632:user/hydrotwin-dev` |
| **Lambda function** | `HydroTwin` |
| **Lambda ARN** | `arn:aws:lambda:us-east-1:640053196632:function:HydroTwin` |
| **Lambda execution role** | `arn:aws:iam::640053196632:role/HydroTwinLambdaRole` |
| **API Gateway** | `HydroTwinApi` (HTTP API) |
| **API Gateway ID** | `sdnatb43dl` |
| **API Gateway URL** | `https://sdnatb43dl.execute-api.us-east-1.amazonaws.com` |
| **Live endpoint** | `POST https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/assess` |
| **Stage** | `$default` (auto-deploy enabled) |
| **CloudWatch log group** | `/aws/lambda/HydroTwin` |

---

## 🔧 Lambda configuration

| Setting | Value |
|---|---|
| Runtime | `python3.12` |
| Architecture | `x86_64` |
| Handler | `lambda_handler.lambda_handler` |
| Memory | `256 MB` |
| Timeout | `30 sec` |
| Code size | `~16 MB` (zipped) |
| Max memory used (cold start) | `91 MB` |
| Init duration (cold) | `~905 ms` |
| Warm execution | `~1.0 s` |

### 📦 Packaging strategy

- Plain zip (no Layers, no container) — Alexandre's deps fit comfortably
- Built using `pip install --target` with `--platform manylinux2014_x86_64 --python-version 3.12 --only-binary=:all:` to force **Linux x86_64 wheels** (Windows-native `.pyd` files would crash Lambda)
- Excluded from zip: `local_server.py`, `flask`, `flask-cors`, `python-dotenv`, `.env*`
- Included: `lambda_handler.py`, `sentinel_extractor.py`, `meteorology_rules.md`, `requests`, `boto3` (boto3 also pre-baked in Lambda runtime; left in for parity with local dev)
- Output: `hydrotwin-backend.zip` at repo root (gitignored via `*.zip`)

---

## 🔐 IAM execution role — `HydroTwinLambdaRole`

### Trust policy

Allows Lambda service to assume this role:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "lambda.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
```

### Attached managed policy

- `AWSLambdaBasicExecutionRole` (CloudWatch Logs write)

### Inline policy `BedrockInvokeAccess`

Broadened beyond initial Claude-3-Sonnet-only scope so model swaps don't require IAM redeploys:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "InvokeAnthropicModels",
    "Effect": "Allow",
    "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
    "Resource": [
      "arn:aws:bedrock:*::foundation-model/anthropic.*",
      "arn:aws:bedrock:*:*:inference-profile/*anthropic*"
    ]
  }]
}
```

### Resource-based policy on Lambda

Allows API Gateway `sdnatb43dl` to invoke:

```json
{
  "Sid": "apigateway-invoke",
  "Effect": "Allow",
  "Principal": { "Service": "apigateway.amazonaws.com" },
  "Action": "lambda:InvokeFunction",
  "Condition": {
    "ArnLike": {
      "AWS:SourceArn": "arn:aws:execute-api:us-east-1:640053196632:sdnatb43dl/*/*/assess"
    }
  }
}
```

---

## 🌍 Lambda environment variables (LD-2)

| Variable | Value | Notes |
|---|---|---|
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-sonnet-4-6` | **Required `us.` prefix** — cross-region inference profile |
| `BEDROCK_REGION` | `us-east-1` | Same as deploy region |
| `WEBHOOK_URL` | ⚠️ **placeholder** | Currently `YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN` — needs real Discord URL from Tatiana |

### 🤖 Model choice rationale

**Original env-example had:** `anthropic.claude-3-sonnet-20240229-v1:0` → marked LEGACY by AWS, refused to invoke.

**Probed available models in this account:**

| Model ID | Status | Why not |
|---|---|---|
| `us.anthropic.claude-3-sonnet-20240229-v1:0` | LEGACY | Account-level "not actively using" deprecation |
| `us.anthropic.claude-3-7-sonnet-20250219-v1:0` | LEGACY | Same as above |
| `us.anthropic.claude-opus-4-20250514-v1:0` | LEGACY | Same |
| `anthropic.claude-sonnet-4-6` | ❌ ValidationException | "On-demand throughput not supported — use inference profile" |
| **`us.anthropic.claude-sonnet-4-6`** | 🟢 **WORKS** | **Picked** — current gen, fast, balanced |
| `us.anthropic.claude-haiku-4-5-20251001-v1:0` | 🟢 works | Cheaper alt if cost matters |
| `us.anthropic.claude-opus-4-5-20251101-v1:0` | 🟢 works | Overkill for our 512-token JSON output |

**Pattern:** newer Anthropic models on Bedrock require the `us.` cross-region prefix.

---

## 🔥 CORS configuration (API Gateway)

Set on the HTTP API itself, applies to all routes:

| Setting | Value |
|---|---|
| `AllowOrigins` | `*` |
| `AllowMethods` | `POST, OPTIONS` |
| `AllowHeaders` | `Content-Type` |
| `MaxAge` | `86400` (24h) |

---

## 🧪 Smoke test

### Direct Lambda → API Gateway smoke

```bash
curl -X POST https://sdnatb43dl.execute-api.us-east-1.amazonaws.com/assess \
  -H "Content-Type: application/json" \
  -d '{"region_id": "danube-basin", "bbox": [8.0, 42.0, 30.0, 52.0]}'
```

### Verified results

| Check | Result |
|---|---|
| HTTP status | `200` |
| Cold start latency | `~3.1 s` |
| Warm latency | `~2.8 s` |
| Response shape | `{ status, confidence, reasoning, region_id }` ✅ |
| CORS `Access-Control-Allow-Origin` | `*` ✅ |
| Bedrock invoke | ❌ `ResourceNotFoundException` (use case form) |
| Demo fallback | ✅ Returns realistic `FLOOD_WATCH` payload |
| Webhook fire | ❌ `400 Bad Request` (placeholder URL) |
| Lambda response affected by webhook fail | ❌ No (non-fatal — by design) |

---

## ⚠️ Hiccups encountered + how resolved

| Issue | Resolution |
|---|---|
| `pip install -t .` produced Windows `.pyd` extensions | Re-ran with `--platform manylinux2014_x86_64 --only-binary=:all:` |
| AWS CLI not installed locally | `pip install awscli` (v1.44.86) — invoke as `python -m awscli` |
| `.env` keys named non-standard (`AWS_ACCESS_KEY` instead of `AWS_ACCESS_KEY_ID`) | Read values, wrote to `~/.aws/credentials` under correct names without modifying `.env` |
| `hydrotwin-dev` IAM user lacked Lambda/IAM/APIGateway perms | Lead attached broader permissions |
| Claude 3 Sonnet (env-example default) marked LEGACY | Switched to `us.anthropic.claude-sonnet-4-6` |
| Direct foundation model invoke `ValidationException` | Use cross-region inference profile (`us.` prefix) |
| API Gateway quick-create didn't auto-attach Lambda permission | Added explicit `lambda add-permission` |

---

## 🔁 Redeploy quick-ref

See [`04-runbook.md`](./04-runbook.md) for full commands. TL;DR for code-only changes:

```bash
# Rebuild zip (from repo root)
cd backend && rm -rf .build && mkdir .build && cp lambda_handler.py sentinel_extractor.py meteorology_rules.md .build/
pip install --target .build --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 --only-binary=:all: requests boto3
python -c "import zipfile, os; z=zipfile.ZipFile('../hydrotwin-backend.zip','w',zipfile.ZIP_DEFLATED); [z.write(os.path.join(r,f), os.path.relpath(os.path.join(r,f),'.build')) for r,_,fs in os.walk('.build') for f in fs if not f.endswith('.pyc')]; z.close()"

# Push to Lambda
python -m awscli lambda update-function-code --function-name HydroTwin --zip-file fileb://../hydrotwin-backend.zip
```
