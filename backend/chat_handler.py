"""
chat_handler.py — HydroSentry Context-Aware Alert Assistant
=============================================================

POST /chat-alert

Accepts:
    {
        "user_message":  "Which neighbourhoods are at highest risk?",
        "alert_context": {
            "region_id":   "BGR.13.9_1",
            "region_name": "Nikopol Municipality, Pleven Region",
            "status":      "FLOOD_WATCH",
            "confidence":  0.78,
            "reasoning":   "...",
            "eo_data": {           // optional — extractor dict if available
                "ndvi": 0.41,
                "soil_moisture_pct": 89,
                "precip_mm_7d": 47,
                ...
            }
        }
    }

Returns:
    { "reply": "<assistant answer>" }

The handler is intentionally simple — no conversation history, no RAG, no
external tools. Each call is fully self-contained so it can never grow into a
slow, hallucination-prone free-chat.  The strict system prompt keeps Claude
scoped to the alert data and under 3 sentences per reply.
"""

import json
import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0"
)
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")

SYSTEM_PROMPT = """You are 'HydroSentry', an elite Earth Observation assistant for the Bulgarian Civil Defense.
You are currently helping a municipality employee understand an active disaster alert.

CRITICAL RULES:
1. You will be provided with the raw Sentinel satellite data and weather forecast for their region.
2. Answer the question strictly based on the provided alert context. Do not use outside knowledge.
3. Translate complex geospatial terms (NDWI, NDVI, soil moisture, SPI) into plain, non-technical language.
4. Keep your answers short, actionable, and professional. Maximum 3 sentences.
5. If the question is unrelated to the current alert or region, politely redirect the employee back to the active disaster parameters.
6. Never reveal internal status codes or raw JSON keys — always use plain English equivalents.
7. Respond in the same language the employee used (English or Bulgarian)."""

CORS_HEADERS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Content-Type":                 "application/json",
}


def _build_context_block(ctx: dict) -> str:
    """Render alert_context as a readable block injected into the user prompt."""
    lines = [
        f"Region: {ctx.get('region_name') or ctx.get('region_id', 'Unknown')}",
        f"Active alert status: {ctx.get('status', 'UNKNOWN')}",
        f"AI confidence: {int((ctx.get('confidence') or 0) * 100)}%",
    ]

    reasoning = ctx.get("reasoning", "").strip()
    if reasoning:
        lines.append(f"AI assessment summary:\n{reasoning}")

    eo = ctx.get("eo_data") or {}
    if eo:
        lines.append("\nSensor readings:")
        field_labels = {
            "ndvi":              "Vegetation health index (NDVI)",
            "soil_moisture_pct": "Soil saturation (%)",
            "precip_mm_7d":      "Rainfall last 7 days (mm)",
            "precip_mm_30d":     "Rainfall last 30 days (mm)",
            "river_level_m":     "River level above baseline (m)",
            "flood_extent_km2":  "Estimated flooded area (km²)",
            "temp_max_c":        "Max temperature (°C)",
            "drought_index":     "Drought index (SPI-3)",
        }
        for key, label in field_labels.items():
            if key in eo:
                lines.append(f"  • {label}: {eo[key]}")

    return "\n".join(lines)


def _call_bedrock(user_message: str, context_block: str) -> str:
    """Call Claude via Bedrock and return the assistant's reply string."""
    bedrock = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)

    full_user_message = (
        f"=== ACTIVE ALERT CONTEXT ===\n{context_block}\n\n"
        f"=== EMPLOYEE QUESTION ===\n{user_message}"
    )

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens":        300,
        "temperature":       0.2,
        "system":            SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": full_user_message}
        ],
    })

    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    raw  = json.loads(response["body"].read())
    return raw["content"][0]["text"].strip()


def _demo_reply(user_message: str, ctx: dict) -> str:
    """Deterministic fallback when Bedrock is unavailable (no creds, throttling, etc.)."""
    status      = ctx.get("status", "UNKNOWN")
    region_name = ctx.get("region_name") or ctx.get("region_id", "this region")
    return (
        f"[Demo mode — live AI offline] Based on the active **{status}** for "
        f"**{region_name}**: soil saturation is critically high and river levels are "
        f"rising. I recommend pre-positioning emergency teams and monitoring the "
        f"Vit/Osam river gauges every 2 hours. _(Your question: '{user_message[:80]}')_"
    )


def lambda_handler(event: dict, context) -> dict:
    """Entry point — works both as an AWS Lambda and via local_server.py."""
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": "{}"}

    try:
        raw  = event.get("body", "{}")
        body = json.loads(raw) if isinstance(raw, str) else (raw or {})

        user_message  = (body.get("user_message") or "").strip()
        alert_context = body.get("alert_context") or {}

        if not user_message:
            return {
                "statusCode": 400,
                "headers":    CORS_HEADERS,
                "body":       json.dumps({"error": "user_message is required"}),
            }

        context_block = _build_context_block(alert_context)
        logger.info("Chat request — region: %s, message: %.80s",
                    alert_context.get("region_id"), user_message)

        try:
            reply = _call_bedrock(user_message, context_block)
        except Exception as exc:
            logger.warning("Bedrock unavailable for chat (%s) — using demo reply.", exc)
            reply = _demo_reply(user_message, alert_context)

        return {
            "statusCode": 200,
            "headers":    CORS_HEADERS,
            "body":       json.dumps({"reply": reply}),
        }

    except Exception as exc:
        logger.error("chat_handler error: %s", exc)
        return {
            "statusCode": 500,
            "headers":    CORS_HEADERS,
            "body":       json.dumps({"error": "Internal server error"}),
        }
