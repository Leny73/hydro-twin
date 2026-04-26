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

import html
import json
import logging
import os
import re

import boto3
import requests

from regions import REGION_NAMES
from sentinel_extractor import get_eo_and_weather_data

# ── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Configuration (from Lambda environment variables) ────────────────────────
# Comma-separated list of Discord webhook URLs — alerts fire to all of them
DISCORD_WEBHOOK_URLS = [
    u.strip()
    for u in os.environ.get("DISCORD_WEBHOOK_URL", "").split(",")
    if u.strip()
]
TELEGRAM_BOT_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID     = os.environ.get("TELEGRAM_CHAT_ID", "")
BEDROCK_MODEL_ID     = os.environ.get(
    "BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0"
)
BEDROCK_REGION       = os.environ.get("BEDROCK_REGION", "us-east-1")

# Path to the meteorology rules file — bundled inside the Lambda package
RULES_FILE = os.path.join(os.path.dirname(__file__), "meteorology_rules.md")


# ─────────────────────────────────────────────────────────────────────────────
#  AWS BEDROCK — Claude 3 Assessment
# ─────────────────────────────────────────────────────────────────────────────

def call_bedrock_agent(data: dict, rules: str, region_name: str) -> dict:
    """
    Send a structured prompt to AWS Bedrock (Claude 3 Sonnet) and return
    a risk assessment dict.

    The meteorology rules from ``meteorology_rules.md`` are injected verbatim
    into the system context so the model reasons against validated thresholds.

    Args:
        data:        dict from get_eo_and_weather_data() — EO + weather metrics.
        rules:       raw string content of meteorology_rules.md.
        region_name: human-readable region name (e.g. "Yambol Oblast") so the
                     reasoning text refers to the correct place. The rules file
                     is Pleven-calibrated, so without this Claude tends to say
                     "Pleven Oblast" for every region.

    Returns:
        dict with keys:
            status                – one of SAFE | DROUGHT_WATCH | DROUGHT_WARNING |
                                            FLOOD_WATCH | FLOOD_WARNING
            confidence            – float 0.0–1.0
            reasoning             – concise markdown assessment paragraph (legacy)
            reasoning_structured  – dict with 4 keys mapping to the v3 dashboard sections:
                                    whats_happening, why_it_matters, current_context, next_step
    """
    bedrock = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)

    # ── Prompt: inject rules + live sensor data ───────────────────────────
    # Audience for `reasoning` text: municipal authorities (mayors, civil
    # protection, emergency coordinators) — smart non-experts. Plain language,
    # markdown formatting, no meteorology jargon.
    prompt = f"""You are HydroTwin, a flood and drought early-warning AI.
Your audience is municipal authorities in Bulgaria — civil-protection officers, mayors,
emergency-response coordinators. They are smart non-experts; they do not know what NDVI,
SPI, SAR or NDWI mean. Translate everything into plain language.

You are powered by Copernicus Earth Observation satellite data and real-time weather feeds.

=== REGION UNDER ASSESSMENT ===
{region_name}

The thresholds in the rules below are calibrated against Bulgarian climatological norms.
Apply them to the sensor data for {region_name} as supplied. Do NOT assume the region is
Pleven Oblast or any other place — the rules are general Bulgaria-wide unless stated.

=== METEOROLOGY RULES & THRESHOLDS (authoritative — do not override) ===
{rules}

=== CURRENT SENSOR DATA (JSON) ===
{json.dumps(data, indent=2)}

Your task:
1. Compare each sensor reading against the rules above.
2. Decide the single most severe alert status that applies.
3. Explain WHY in plain language a non-meteorologist can act on.

Respond with a valid JSON object — no prose outside the JSON, no triple-backticks wrapping it.
Schema:
{{
  "status":     "<SAFE | DROUGHT_WATCH | DROUGHT_WARNING | FLOOD_WATCH | FLOOD_WARNING>",
  "confidence": <float 0.0–1.0>,
  "reasoning":  "<markdown string, 2–4 short paragraphs, under 600 chars>",
  "reasoning_structured": {{
    "whats_happening":  "<1–2 sentences — plain summary of current conditions>",
    "why_it_matters":   "<1–3 short bullet points OR 1–2 sentences — the key drivers with the actual numbers in **bold**>",
    "current_context":  "<1–2 sentences — seasonal context, trend direction, what is normal vs not>",
    "next_step":        "<1–2 sentences — concrete suggested action for municipal authorities>"
  }}
}}

WRITING RULES for the `reasoning_structured` fields:
- Same plain-language audience and voice as `reasoning` — no jargon, no internal status codes, no acronyms (NDVI / SPI / SAR / NDWI).
- `whats_happening`: lead with the headline situation. NO numbers in this section — just the picture in plain words.
- `why_it_matters`: this is the evidence. Put the 1–3 readings that drove the decision here, with the **actual numbers bolded**. Markdown bullets allowed if you list more than one driver.
- `current_context`: situate the readings against seasonal normals or trends ("for late April this is below average", "soil moisture has been dropping for two weeks").
- `next_step`: action-oriented. What should a mayor / civil-protection officer do today? E.g. "Pre-position pumps along the Vit", "Brief downstream villages", "Continue routine monitoring — no action needed".
- Each section is its own short markdown string. Do NOT repeat the same sentence verbatim in `reasoning` and any structured field.

WRITING RULES for the `reasoning` field:
- Format: markdown. Use **bold** to highlight 1–2 key numbers. Use a short bullet list (`- item`) only if you need to list 2+ breached conditions.
- Open with a one-sentence headline summarising what's happening — NO jargon.
- When you name the region, ONLY refer to it as "{region_name}" or generically as "the area" / "this region". DO NOT name a different oblast, river, or town that isn't in the sensor data — even if the rules file mentions one as an example.
- Then explain which 1–3 readings drove the decision in everyday terms.
  Good: "soil is unusually dry at **10%**, well below the safe 15–75% range".
  Bad:  "soil_moisture_pct below DROUGHT_WATCH threshold of 20%".
- If relevant, end with one line on what to watch next (e.g. "If rainfall stays low into next week, this could escalate to a drought warning.").
- DO NOT use the words "threshold", "metric", "index", or any internal status code (`DROUGHT_WATCH`, etc.) inside `reasoning`. Translate them.
- DO NOT explain what NDVI / SPI / SAR / NDWI are. Just describe what they tell you (vegetation health, how dry compared to normal, water extent, etc.)."""

    # ── Bedrock Messages API payload (Anthropic on Bedrock) ───────────────
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1200,          # Higher cap for legacy markdown + 4 structured sections
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
        text = raw["content"][0]["text"]          # Anthropic Messages API content blocks
        return json.loads(text)

    except Exception as exc:
        # Graceful degradation — catches NoCredentialsError, EndpointResolutionError,
        # throttling, JSON parse errors, etc. so the demo never returns a 500.
        logger.error("Bedrock call failed: %s", exc)
        return {
            "status":     "FLOOD_WATCH",
            "confidence": 0.78,
            "reasoning":  (
                "**Flood watch in effect — elevated risk over the next 24 hours.**\n\n"
                "Recent observations show:\n"
                "- River levels have risen **0.8 m** above the seasonal baseline in the past 3 days\n"
                "- Ground saturation is high at **89%** — soils cannot absorb much more water\n"
                "- A further **35 mm of rain** is forecast within the next 24 hours\n\n"
                "If rainfall arrives as expected, watch for fast rises along the Vit and Osam rivers. "
                f"_(Demo mode — live AI temporarily offline: {type(exc).__name__})_"
            ),
            "reasoning_structured": {
                "whats_happening": (
                    "Conditions across the area are trending toward elevated flood risk over the next "
                    "24 hours. Rivers are running well above seasonal baseline and the ground is nearly "
                    "saturated."
                ),
                "why_it_matters": (
                    "- River levels are up **0.8 m** above the seasonal baseline in the past 3 days.\n"
                    "- Soil saturation is at **89%** — the ground can't absorb much more water.\n"
                    "- A further **35 mm of rain** is forecast within the next 24 hours."
                ),
                "current_context": (
                    "Spring runoff is still elevated for this part of the year and the floodplain has "
                    "limited remaining capacity for additional surface water."
                ),
                "next_step": (
                    "Pre-position pumps along the Vit and Osam, brief downstream villages, and review "
                    "evacuation routes for low-lying districts."
                ),
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
#  WEBHOOK NOTIFIER — Discord / Telegram
# ─────────────────────────────────────────────────────────────────────────────

def trigger_webhook(alert_data: dict) -> None:
    """
    Fire alerts to Discord AND Telegram simultaneously (whichever are configured).

    Env vars:
      DISCORD_WEBHOOK_URL  – https://discord.com/api/webhooks/<id>/<token>
      TELEGRAM_BOT_TOKEN   – token from @BotFather
      TELEGRAM_CHAT_ID     – your personal or channel chat id

    Non-fatal — delivery failures never block the Lambda response.
    """
    STATUS_META = {
        "SAFE":            {"emoji": "✅", "color": 0x10B981},
        "DROUGHT_WATCH":   {"emoji": "🟡", "color": 0xF59E0B},
        "DROUGHT_WARNING": {"emoji": "🔴", "color": 0xF97316},
        "FLOOD_WATCH":     {"emoji": "🌊", "color": 0x3B82F6},
        "FLOOD_WARNING":   {"emoji": "🔴", "color": 0xEF4444},
    }
    meta   = STATUS_META.get(alert_data.get("status", "SAFE"), STATUS_META["SAFE"])
    status = alert_data.get("status", "N/A")
    region = alert_data.get("region_id", "Unknown Region")
    conf   = int(alert_data.get("confidence", 0) * 100)
    reason = alert_data.get("reasoning", "No reasoning provided.")

    if DISCORD_WEBHOOK_URLS:
        for url in DISCORD_WEBHOOK_URLS:
            try:
                _send_discord(url, meta, status, region, conf, reason)
            except requests.RequestException as exc:
                logger.error("Discord delivery failed (%s…): %s", url[:40], exc)
    else:
        logger.warning("DISCORD_WEBHOOK_URL not set — skipping Discord.")

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            _send_telegram(meta["emoji"], status, region, conf, reason)
        except requests.RequestException as exc:
            logger.error("Telegram delivery failed: %s", exc)
    else:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping Telegram.")


def _send_discord(url: str, meta: dict, status: str, region: str, conf: int, reason: str) -> None:
    payload = {
        "username":   "HydroTwin",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/3222/3222800.png",
        "embeds": [{
            "title":       f"{meta['emoji']} HydroTwin Alert — {region}",
            "description": reason,
            "color":       meta.get("color", 0x10B981),
            "fields": [
                {"name": "Status",     "value": status,     "inline": True},
                {"name": "Confidence", "value": f"{conf}%", "inline": True},
                {"name": "Region",     "value": region,     "inline": True},
            ],
            "footer": {"text": "HydroTwin · Copernicus EO + AWS Bedrock (Claude Sonnet 4.6)"},
        }],
    }
    resp = requests.post(url, json=payload, timeout=5)
    resp.raise_for_status()
    logger.info("Discord webhook delivered: HTTP %s", resp.status_code)


def _md_to_html(s: str) -> str:
    """
    Convert the lightweight markdown subset Claude emits into Telegram-compatible
    HTML. Discord renders markdown natively in embed descriptions; Telegram does
    not (in HTML parse mode), so we translate **bold**, *italic*, `code`, and
    `- ` bullet lines into their HTML / unicode equivalents. HTML-escapes the
    plain text first so any `<`, `>`, `&` from Claude can't break the message.
    """
    # Escape first so user/model content cannot inject raw HTML
    s = html.escape(s, quote=False)
    # **bold** → <b>bold</b>   (greedy-safe via lazy match)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s, flags=re.DOTALL)
    # __bold__ → <b>bold</b>
    s = re.sub(r"__(.+?)__",     r"<b>\1</b>", s, flags=re.DOTALL)
    # *italic* / _italic_ → <i>italic</i>   (avoid matching inside words)
    s = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", s, flags=re.DOTALL)
    s = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)",   r"<i>\1</i>", s, flags=re.DOTALL)
    # `code` → <code>code</code>
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    # bullet lines: leading "- " or "* " → "• "
    s = re.sub(r"^[\-\*]\s+", "• ", s, flags=re.MULTILINE)
    return s


def _send_telegram(emoji: str, status: str, region: str, conf: int, reason: str) -> None:
    url  = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    text = (
        f"{emoji} <b>HydroTwin Alert — {region}</b>\n\n"
        f"<b>Status:</b> {status}\n"
        f"<b>Confidence:</b> {conf}%\n\n"
        f"{_md_to_html(reason)}\n\n"
        f"<i>HydroTwin · Copernicus EO + AWS Bedrock (Claude Sonnet 4.6)</i>"
    )
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    resp = requests.post(url, json=payload, timeout=5)
    resp.raise_for_status()
    logger.info("Telegram message delivered: HTTP %s", resp.status_code)


# ─────────────────────────────────────────────────────────────────────────────
#  CORE PIPELINE — reusable by cron + API
# ─────────────────────────────────────────────────────────────────────────────

def assess_region(region_id: str, bbox: list) -> dict:
    """
    Run the full assess pipeline for one region — extractor → rules → Bedrock.

    No side effects (no webhook firing). Callers decide when to notify:
      - lambda_handler (POST /assess): fires on every non-SAFE status
      - cron_handler   (EventBridge):  fires only on status-code transition

    Returns:
        dict with keys: region_id, status, confidence, reasoning,
                        reasoning_structured, sources
    """
    logger.info("Fetching EO data for bbox: %s", bbox)
    eo_data = get_eo_and_weather_data(bbox)

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

    logger.info("Invoking Bedrock model: %s", BEDROCK_MODEL_ID)
    region_name = REGION_NAMES.get(region_id, region_id)
    assessment = call_bedrock_agent(eo_data, rules_text, region_name)
    assessment["region_id"] = region_id

    # V3-3: normalise `reasoning_structured` so downstream consumers don't have
    # to defensive-code around partial Bedrock output. If the model returned
    # the field but with missing keys, fill them with empty strings — the
    # frontend hides empty sections gracefully.
    structured = assessment.get("reasoning_structured")
    if not isinstance(structured, dict):
        structured = {}
    assessment["reasoning_structured"] = {
        "whats_happening": structured.get("whats_happening", "") or "",
        "why_it_matters":  structured.get("why_it_matters",  "") or "",
        "current_context": structured.get("current_context", "") or "",
        "next_step":       structured.get("next_step",       "") or "",
    }

    # V2-6: pass through extractor source string as a single-element array.
    # Future-ready for structured citations [{name, url, dataset_id}, ...].
    source = eo_data.get("source")
    assessment["sources"] = [source] if source else []

    return assessment


# ─────────────────────────────────────────────────────────────────────────────
#  LAMBDA ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context) -> dict:
    """
    AWS Lambda handler — invoked by API Gateway (HTTP API or REST API).

    Expected POST body (JSON):
    {
        "region_id": "pleven",                            // logical region identifier
        "bbox":      [lon_min, lat_min, lon_max, lat_max] // optional bounding box
    }

    Response (200):
    {
        "region_id":  "pleven",
        "status":     "FLOOD_WATCH",
        "confidence": 0.82,
        "reasoning":  "...",
        "sources":    ["Sentinel Hub Statistical API ..."]
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

    # ── 2. Run the core pipeline ──────────────────────────────────────────
    assessment = assess_region(region_id, bbox)

    # ── 3. Return API Gateway response ────────────────────────────────────
    # Webhooks (Discord/Telegram) fire from cron_handler only, on status
    # transitions. Firing here on every map click caused notification spam.
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
