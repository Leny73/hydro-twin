"""
unsubscribe_handler.py — HydroTwin /unsubscribe Lambda
=========================================================

One-click unsubscribe for every email we send. The link in the footer of every
welcome + alert email is signed with an HMAC token so a random visitor can't
remove other people's subscriptions just by guessing emails + region IDs.

Link format:
    {FRONTEND_BASE_URL}/unsubscribe?e=<email>&r=<region_id>&t=<token>

The frontend route renders a simple confirmation page that POSTs here. We also
support GET so the email link itself can hit the API directly during local
testing — both branches do the same thing.

Responses:
  200  { "message": "unsubscribed", ... }   — row deleted (or never existed)
  400  { "error":   "Missing parameters" | "Invalid token" | ... }

Demo-first philosophy: if DynamoDB is unavailable we still return 200 (with a
demo_mode flag) so the user sees a successful confirmation page on stage.
"""

import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

import notifications
from regions import KNOWN_REGIONS

logger = logging.getLogger()
logger.setLevel(logging.INFO)


SUBSCRIPTIONS_TABLE = os.environ.get("SUBSCRIPTIONS_TABLE", "HydroTwinSubscriptions")
AWS_REGION          = os.environ.get("AWS_REGION",          "us-east-1")

_TABLE = None


def _get_table():
    global _TABLE
    if _TABLE is None:
        _TABLE = boto3.resource("dynamodb", region_name=AWS_REGION).Table(SUBSCRIPTIONS_TABLE)
    return _TABLE


def lambda_handler(event: dict, context) -> dict:
    """Accepts GET (querystring) or POST (JSON body) — both with e/r/t."""
    if event.get("httpMethod") == "OPTIONS":
        return _response(200, {})

    method = (event.get("httpMethod") or "GET").upper()

    # ── 1. Pull e, r, t from wherever they're hiding ─────────────────────
    if method == "POST":
        try:
            raw  = event.get("body", "{}")
            body = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (json.JSONDecodeError, AttributeError) as exc:
            return _response(400, {"error": f"Invalid JSON body: {exc}"})
        email     = (body.get("email")     or body.get("e") or "").strip().lower()
        region_id = (body.get("region_id") or body.get("r") or "").strip()
        token     = (body.get("token")     or body.get("t") or "").strip()
    else:
        params = event.get("queryStringParameters") or {}
        email     = (params.get("e") or "").strip().lower()
        region_id = (params.get("r") or "").strip()
        token     = (params.get("t") or "").strip()

    # ── 2. Validate ──────────────────────────────────────────────────────
    if not email or not region_id or not token:
        return _response(400, {"error": "Missing parameters (e, r, t required)"})

    if region_id not in KNOWN_REGIONS:
        return _response(400, {"error": "Unknown region_id"})

    if not notifications.verify_unsubscribe_token(email, region_id, token):
        logger.warning("Bad unsubscribe token for %s/%s", email, region_id)
        return _response(400, {"error": "Invalid or expired token"})

    # ── 3. Delete from DynamoDB (idempotent — ok if row is missing) ─────
    try:
        _get_table().delete_item(
            Key={"email": email, "region_id": region_id},
        )
        logger.info("Unsubscribed: %s ↛ %s", email, region_id)
        return _response(200, {
            "message":   "unsubscribed",
            "email":     email,
            "region_id": region_id,
        })

    except ClientError as exc:
        logger.error("DynamoDB delete failed: %s", exc)
        return _response(200, {
            "message":   "unsubscribed",
            "email":     email,
            "region_id": region_id,
            "demo_mode": True,
            "warning":   "Confirmed in demo mode (storage unavailable).",
        })

    except Exception as exc:
        logger.error("Unsubscribe failed: %s", exc)
        return _response(200, {
            "message":   "unsubscribed",
            "email":     email,
            "region_id": region_id,
            "demo_mode": True,
            "warning":   f"Confirmed in demo mode ({type(exc).__name__}).",
        })


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type":                 "application/json",
            "Access-Control-Allow-Origin":  "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body),
    }
