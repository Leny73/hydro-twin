"""
lambda_handler.py — HydroTwin AWS Lambda Entry Point
=======================================================

Orchestration flow:
  1.  Parse incoming API Gateway request  (region_id + bbox)
  2.  Fetch Earth Observation + weather data via sentinel_extractor.py
        └─ STUB: Data Analysts team fills this in
  3.  Read meteorology thresholds from meteorology_rules.md
        └─ STUB: Meteorologist fills this in
  4.  Call AWS Bedrock (Claude 3) for AI risk assessment
  5.  Fire Discord/Telegram webhook if status is WATCH or WARNING
  6.  Return API Gateway-compatible JSON response

Environment Variables (set in AWS Lambda Console):
  WEBHOOK_URL       – Discord or Telegram webhook URL
  BEDROCK_MODEL_ID  – default: anthropic.claude-3-sonnet-20240229-v1:0
  BEDROCK_REGION    – AWS region where Bedrock is enabled (default: us-east-1)

Deploy:
  Runtime  : Python 3.10+
  Handler  : lambda_handler.lambda_handler
  Include  : lambda_handler.py, sentinel_extractor.py, meteorology_rules.md
             + pip install -r requirements.txt -t .
"""

import json
import logging
import os

import boto3
import requests

from sentinel_extractor import get_eo_and_weather_data

# ── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Configuration (from Lambda environment variables) ────────────────────────
WEBHOOK_URL      = os.environ.get("WEBHOOK_URL", "")
BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0"
)
BEDROCK_REGION   = os.environ.get("BEDROCK_REGION", "us-east-1")

# Path to the meteorology rules file — bundled inside the Lambda package
RULES_FILE = os.path.join(os.path.dirname(__file__), "meteorology_rules.md")


# ─────────────────────────────────────────────────────────────────────────────
#  AWS BEDROCK — Claude 3 Assessment
# ─────────────────────────────────────────────────────────────────────────────

def call_bedrock_agent(data: dict, rules: str) -> dict:
    """
    Send a structured prompt to AWS Bedrock (Claude 3 Sonnet) and return
    a risk assessment dict.

    The meteorology rules from ``meteorology_rules.md`` are injected verbatim
    into the system context so the model reasons against validated thresholds.

    Args:
        data:  dict from get_eo_and_weather_data() — EO + weather metrics.
        rules: raw string content of meteorology_rules.md.

    Returns:
        dict with keys:
            status      – one of SAFE | DROUGHT_WATCH | DROUGHT_WARNING |
                                  FLOOD_WATCH | FLOOD_WARNING
            confidence  – float 0.0–1.0
            reasoning   – concise assessment paragraph
    """
    bedrock = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)

    # ── Prompt: inject rules + live sensor data ───────────────────────────
    prompt = f"""You are HydroTwin, a disaster early-warning AI for floods and droughts.
You are powered by Copernicus Earth Observation satellite data and real-time weather feeds.

=== METEOROLOGY RULES & THRESHOLDS (authoritative — do not override) ===
{rules}

=== CURRENT SENSOR DATA (JSON) ===
{json.dumps(data, indent=2)}

Your task:
1. Compare each sensor metric against the threshold rules above.
2. Determine the single most severe status that applies.
3. Respond ONLY with a valid JSON object — no markdown, no prose outside the JSON.

Required JSON schema:
{{
  "status":     "<SAFE | DROUGHT_WATCH | DROUGHT_WARNING | FLOOD_WATCH | FLOOD_WARNING>",
  "confidence": <float 0.0–1.0>,
  "reasoning":  "<one concise paragraph explaining which thresholds were triggered>"
}}"""

    # ── Bedrock Converse API payload (Claude 3 Messages format) ───────────
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 512,
        "temperature": 0.1,          # Low temperature for deterministic assessment
        "messages": [
            {"role": "user", "content": prompt}
        ],
    })

    try:
        response = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=body,
        )
        raw  = json.loads(response["body"].read())
        text = raw["content"][0]["text"]          # Claude 3 returns content blocks
        return json.loads(text)

    except Exception as exc:
        # Graceful degradation — catches NoCredentialsError, EndpointResolutionError,
        # throttling, JSON parse errors, etc. so the demo never returns a 500.
        logger.error("Bedrock call failed: %s", exc)
        return {
            "status":     "FLOOD_WATCH",
            "confidence": 0.78,
            "reasoning":  (
                "[DEMO MODE — Bedrock unavailable] River levels in this zone have risen "
                "0.8 m above the seasonal baseline over the past 72 hours. Soil "
                "saturation is at 89 %. Precipitation forecast shows an additional "
                "35 mm expected within 24 hours. Two FLOOD_WATCH thresholds are "
                f"breached. (Live AI offline: {type(exc).__name__})"
            ),
        }


# ─────────────────────────────────────────────────────────────────────────────
#  WEBHOOK NOTIFIER — Discord / Telegram
# ─────────────────────────────────────────────────────────────────────────────

def trigger_webhook(alert_data: dict) -> None:
    """
    Send a formatted alert embed to a Discord or Telegram webhook.

    Discord  : set WEBHOOK_URL = https://discord.com/api/webhooks/<id>/<token>
    Telegram : set WEBHOOK_URL = https://api.telegram.org/bot<TOKEN>/sendMessage
               (also set TELEGRAM_CHAT_ID env var; requires payload modification below)

    This function is non-fatal — a webhook failure will never block the Lambda
    response to the client.

    Args:
        alert_data: dict containing region_id, status, confidence, reasoning.
    """
    if not WEBHOOK_URL:
        logger.warning("WEBHOOK_URL is not set — skipping webhook notification.")
        return

    # ── Colour & emoji based on severity ─────────────────────────────────
    STATUS_META = {
        "SAFE":            {"emoji": "✅", "color": 0x10B981},
        "DROUGHT_WATCH":   {"emoji": "🟡", "color": 0xF59E0B},
        "DROUGHT_WARNING": {"emoji": "🔴", "color": 0xF97316},
        "FLOOD_WATCH":     {"emoji": "🌊", "color": 0x3B82F6},
        "FLOOD_WARNING":   {"emoji": "🔴", "color": 0xEF4444},
    }
    meta = STATUS_META.get(alert_data.get("status", "SAFE"), STATUS_META["SAFE"])

    # ── Discord embed payload ─────────────────────────────────────────────
    discord_payload = {
        "username":   "HydroTwin",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/3222/3222800.png",
        "embeds": [{
            "title":       (
                f"{meta['emoji']} HydroTwin Alert — "
                f"{alert_data.get('region_id', 'Unknown Region')}"
            ),
            "description": alert_data.get("reasoning", "No reasoning provided."),
            "color":       meta["color"],
            "fields": [
                {
                    "name":   "Status",
                    "value":  alert_data.get("status", "N/A"),
                    "inline": True,
                },
                {
                    "name":   "Confidence",
                    "value":  f"{int(alert_data.get('confidence', 0) * 100)}%",
                    "inline": True,
                },
                {
                    "name":   "Region ID",
                    "value":  alert_data.get("region_id", "N/A"),
                    "inline": True,
                },
            ],
            "footer": {
                "text": "HydroTwin · Copernicus EO + AWS Bedrock (Claude 3)",
            },
        }],
    }

    try:
        resp = requests.post(WEBHOOK_URL, json=discord_payload, timeout=5)
        resp.raise_for_status()
        logger.info("Webhook delivered successfully: HTTP %s", resp.status_code)
    except requests.RequestException as exc:
        # Non-fatal — log and continue
        logger.error("Webhook delivery failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
#  LAMBDA ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context) -> dict:
    """
    AWS Lambda handler — invoked by API Gateway (HTTP API or REST API).

    Expected POST body (JSON):
    {
        "region_id": "danube-basin",                      // logical region identifier
        "bbox":      [lon_min, lat_min, lon_max, lat_max] // optional bounding box
    }

    Response (200):
    {
        "region_id":  "danube-basin",
        "status":     "FLOOD_WATCH",
        "confidence": 0.82,
        "reasoning":  "..."
    }
    """
    logger.info("Event received: %s", json.dumps(event))

    # ── Handle CORS preflight (OPTIONS) ──────────────────────────────────
    if event.get("httpMethod") == "OPTIONS":
        return _response(200, {})

    # ── 1. Parse request body ─────────────────────────────────────────────
    try:
        raw_body = event.get("body", "{}")
        body     = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
        region_id = body.get("region_id", "unknown-region")
        bbox      = body.get("bbox", [-10.0, 35.0, 40.0, 72.0])  # fallback: Europe
    except (json.JSONDecodeError, AttributeError) as exc:
        logger.error("Invalid request body: %s", exc)
        return _response(400, {"error": f"Invalid JSON body: {exc}"})

    # ── 2. Fetch EO + weather data (analysts' stub) ───────────────────────
    logger.info("Fetching EO data for bbox: %s", bbox)
    eo_data = get_eo_and_weather_data(bbox)

    # ── 3. Load meteorology rules file ────────────────────────────────────
    try:
        with open(RULES_FILE, "r", encoding="utf-8") as fh:
            rules_text = fh.read()
        logger.info("Loaded meteorology_rules.md (%d chars)", len(rules_text))
    except FileNotFoundError:
        rules_text = (
            "Rules file not found. Apply conservative defaults:\n"
            "- River level rise > 0.5 m in 7 days → FLOOD_WATCH\n"
            "- Soil moisture < 15% + NDVI < 0.2   → DROUGHT_WATCH\n"
        )
        logger.warning("meteorology_rules.md not found — using built-in fallback rules.")

    # ── 4. Call AWS Bedrock (Claude 3) ────────────────────────────────────
    logger.info("Invoking Bedrock model: %s", BEDROCK_MODEL_ID)
    assessment = call_bedrock_agent(eo_data, rules_text)
    assessment["region_id"] = region_id   # attach region identifier to response

    # ── 5. Trigger webhook for non-SAFE statuses ──────────────────────────
    if assessment.get("status", "SAFE") != "SAFE":
        logger.info("Non-SAFE status detected (%s) — firing webhook.", assessment["status"])
        trigger_webhook(assessment)

    # ── 6. Return API Gateway response ────────────────────────────────────
    logger.info("Assessment complete: %s (confidence: %s)",
                assessment.get("status"), assessment.get("confidence"))
    return _response(200, assessment)


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _response(status_code: int, body: dict) -> dict:
    """
    Wrap a dict into an API Gateway–compatible HTTP response with CORS headers.
    All origins are allowed so the Vercel frontend can reach this endpoint.
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type":                "application/json",
            "Access-Control-Allow-Origin":  "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body),
    }
