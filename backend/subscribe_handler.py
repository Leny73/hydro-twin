"""
subscribe_handler.py — HydroTwin /subscribe Lambda
====================================================

Stores a multi-channel subscription in DynamoDB and immediately confirms it to
the user via every channel they enabled (welcome email + Discord ping).

Channels supported today:
  📧 email           — required, validated, delivered via Brevo (notifications.py)
  💬 discord_webhook — optional, validated against Discord's webhook URL shape,
                       a "you're subscribed" embed fires immediately on save
  📱 phone           — accepted + stored, but SMS delivery is gated on AWS SNS
                       sandbox approval (set SMS_ENABLED=1 in Lambda env later)
  ✈️  telegram_chat   — accepted + stored, never delivered yet (stub)

Flow:
  1. Parse incoming API Gateway POST
  2. Validate inputs against the region whitelist + per-channel format checks
  3. PutItem to DynamoDB with conditional expression (no overwrite)
       └─ PK = email, SK = region_id (composite key — same email can subscribe
          to multiple regions, each with its own channel preferences)
  4. Pull the latest snapshot from HydroTwinStatus so the welcome message can
     show the *current* status of that region (compact, actionable on day one)
  5. Fire welcome email via Brevo + welcome Discord embed (if webhook provided)
  6. Return API Gateway-compatible JSON with CORS headers
       201 = subscribed (always, demo-safe), 400 = invalid input, 409 = duplicate

Environment variables (set in AWS Lambda Console):
  SUBSCRIPTIONS_TABLE   — DynamoDB table (default: HydroTwinSubscriptions)
  STATUS_TABLE          — DynamoDB table (default: HydroTwinStatus) for the
                          current-status lookup that powers the welcome message
  AWS_REGION            — auto-set by Lambda runtime
  + all env vars consumed by notifications.py
    (BREVO_API_KEY, BREVO_SENDER_EMAIL, BREVO_SENDER_NAME, FRONTEND_BASE_URL,
     UNSUBSCRIBE_SECRET)

Demo-first philosophy:
  Welcome-message delivery failures NEVER block a successful save. If Brevo is
  down or the user's Discord webhook is dead, the row is still in the table
  and the cron will retry on the next status transition.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from regions import KNOWN_REGIONS, REGION_NAMES, parent_oblast
import notifications

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# ── Configuration ────────────────────────────────────────────────────────────
SUBSCRIPTIONS_TABLE = os.environ.get("SUBSCRIPTIONS_TABLE", "HydroTwinSubscriptions")
STATUS_TABLE        = os.environ.get("STATUS_TABLE",        "HydroTwinStatus")
AWS_REGION          = os.environ.get("AWS_REGION",          "us-east-1")

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Lazy DynamoDB resources — re-used across warm invocations.
_SUBS_TABLE   = None
_STATUS_TABLE = None


def _get_subs_table():
    global _SUBS_TABLE
    if _SUBS_TABLE is None:
        _SUBS_TABLE = boto3.resource("dynamodb", region_name=AWS_REGION).Table(SUBSCRIPTIONS_TABLE)
    return _SUBS_TABLE


def _get_status_table():
    global _STATUS_TABLE
    if _STATUS_TABLE is None:
        _STATUS_TABLE = boto3.resource("dynamodb", region_name=AWS_REGION).Table(STATUS_TABLE)
    return _STATUS_TABLE


# ─────────────────────────────────────────────────────────────────────────────
#  WELCOME MESSAGE — pulls current status snapshot so it's actionable
# ─────────────────────────────────────────────────────────────────────────────

def _current_snapshot(region_id: str) -> dict:
    """
    Best-effort read of the latest snapshot for `region_id` from HydroTwinStatus.
    Falls through to a SAFE placeholder if the table read fails — better than
    sending a welcome email that says "status: unknown".
    """
    try:
        resp = _get_status_table().get_item(Key={"region_id": region_id})
        item = resp.get("Item") or {}
        if item:
            return item
    except Exception as exc:
        logger.warning("Could not read snapshot for %s: %s", region_id, exc)

    return {
        "region_id":  region_id,
        "status":     "SAFE",
        "confidence": 0.5,
        "reasoning":  (
            "No live snapshot available yet — the next cron run (every 30 min) "
            "will assess this region and you'll be notified if conditions change."
        ),
    }


def _fire_welcome_messages(*, email: str, region_id: str, region_name: str,
                           discord_webhook: str | None) -> dict:
    """
    Fan out the welcome message to every channel the user enabled. Returns a
    delivery-status dict so the caller can surface partial-success info to the
    UI (e.g. "subscribed, but Discord webhook rejected the test ping").
    """
    snap   = _current_snapshot(region_id)
    status = snap.get("status",     "SAFE")
    conf   = snap.get("confidence", 0.5)
    reason = snap.get("reasoning",  "") or ""

    delivered = {"email": False, "discord": False}

    # 📧 Email
    subject, html = notifications.render_welcome_email(
        region_name     = region_name,
        region_id       = region_id,
        status          = status,
        confidence      = float(conf),
        reasoning       = reason,
        recipient_email = email,
    )
    text = notifications.render_email_text_fallback(
        region_name = region_name,
        status      = status,
        reasoning   = reason,
        region_id   = region_id,
    )
    delivered["email"] = notifications.send_email(email, subject, html, text)

    # 💬 Discord (per-user webhook)
    if discord_webhook:
        delivered["discord"] = notifications.send_discord_to_webhook(
            discord_webhook,
            region_name = region_name,
            region_id   = region_id,
            status      = status,
            confidence  = float(conf),
            reasoning   = reason,
            kind        = "welcome",
        )

    return delivered


# ─────────────────────────────────────────────────────────────────────────────
#  LAMBDA ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context) -> dict:
    """
    AWS Lambda handler — invoked by API Gateway on POST /subscribe.

    Expected POST body (JSON):
    {
        "email":           "user@example.com",   // required
        "region_id":       "burgas",             // required
        "discord_webhook": "https://discord...", // optional
        "phone":           "+359...",            // optional, stored only
        "telegram_chat":   "...",                // optional, stored only
    }

    Responses:
      201  { "message": "subscribed", "delivered": { "email": true, "discord": false }, ... }
      400  { "error":   "Invalid email" | "Unknown region_id" | "Invalid Discord webhook" }
      409  { "error":   "Already subscribed", ... }
    """
    logger.info("Event received: %s", json.dumps(event))

    # ── CORS preflight ───────────────────────────────────────────────────
    if event.get("httpMethod") == "OPTIONS":
        return _response(200, {})

    # ── 1. Parse body ────────────────────────────────────────────────────
    try:
        raw_body = event.get("body", "{}")
        body     = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
    except (json.JSONDecodeError, AttributeError) as exc:
        logger.error("Invalid request body: %s", exc)
        return _response(400, {"error": f"Invalid JSON body: {exc}"})

    email           = (body.get("email")           or "").strip().lower()
    requested_id    = (body.get("region_id")       or "").strip()
    discord_webhook = (body.get("discord_webhook") or "").strip()
    phone           = (body.get("phone")           or "").strip()
    telegram_chat   = (body.get("telegram_chat")   or "").strip()

    # Roll municipality clicks up to the parent oblast so a click on Iskar
    # (BGR.13.6_1) subscribes the user to Pleven Oblast — one notification per
    # real event instead of one per municipality.
    region_id = parent_oblast(requested_id)

    # ── 2. Validate ──────────────────────────────────────────────────────
    if not EMAIL_REGEX.match(email):
        return _response(400, {"error": "Invalid email address"})

    if region_id not in KNOWN_REGIONS:
        return _response(400, {
            "error":     "Unknown region_id",
            "requested": requested_id,
            "allowed":   sorted(KNOWN_REGIONS),
        })

    if discord_webhook and not notifications.is_valid_discord_webhook(discord_webhook):
        return _response(400, {
            "error": (
                "Invalid Discord webhook URL — paste the full URL from "
                "Server Settings → Integrations → Webhooks → Copy URL."
            ),
        })

    if phone and not notifications.is_valid_phone(phone):
        return _response(400, {
            "error": "Invalid phone number — use international format (e.g. +359888123456).",
        })

    region_name = REGION_NAMES.get(region_id, region_id)
    created_at  = datetime.now(timezone.utc).isoformat(timespec="seconds")
    item = {
        "email":           email,
        "region_id":       region_id,
        "created_at":      created_at,
        "discord_webhook": discord_webhook or None,
        "phone":           phone           or None,
        "telegram_chat":   telegram_chat   or None,
    }
    # DynamoDB rejects None — strip them out so the column is simply absent
    # for the channels the user didn't fill in.
    item = {k: v for k, v in item.items() if v not in (None, "")}

    # ── 3. Save to DynamoDB ──────────────────────────────────────────────
    save_demo_mode = False
    try:
        _get_subs_table().put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(email) AND attribute_not_exists(region_id)",
        )
        logger.info("Subscribed: %s → %s (channels=%s)", email, region_id,
                    [k for k in ("discord_webhook", "phone", "telegram_chat") if item.get(k)])

    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "ConditionalCheckFailedException":
            logger.info("Duplicate subscription: %s → %s", email, region_id)
            return _response(409, {
                "error":     "Already subscribed",
                "email":     email,
                "region_id": region_id,
            })
        logger.error("DynamoDB put failed (%s): %s", code, exc)
        save_demo_mode = True

    except Exception as exc:
        logger.error("Subscribe failed: %s", exc)
        save_demo_mode = True

    # ── 4. Fire welcome messages (non-fatal) ─────────────────────────────
    try:
        delivered = _fire_welcome_messages(
            email           = email,
            region_id       = region_id,
            region_name     = region_name,
            discord_webhook = discord_webhook,
        )
    except Exception as exc:
        # Should be impossible — every notifications.* call already swallows
        # its own errors — but belt-and-braces so the API never 500s here.
        logger.error("Welcome message dispatch crashed: %s", exc)
        delivered = {"email": False, "discord": False}

    # ── 5. Respond ───────────────────────────────────────────────────────
    response_body = {
        "message":     "subscribed",
        "email":       email,
        "region_id":   region_id,
        "region_name": region_name,
        "created_at":  created_at,
        "delivered":   delivered,
    }
    # Surface the rollup so the frontend can show "Subscribed to Pleven Oblast
    # (covers Iskar)" instead of silently swapping the user's selection.
    if requested_id and requested_id != region_id:
        response_body["requested_region_id"] = requested_id
        response_body["rolled_up_to"]        = region_id
    if save_demo_mode:
        response_body["demo_mode"] = True
        response_body["warning"]   = "Stored in demo mode only (DynamoDB unavailable)"

    return _response(201, response_body)


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _response(status_code: int, body: dict) -> dict:
    """API Gateway-compatible response with CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type":                 "application/json",
            "Access-Control-Allow-Origin":  "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body),
    }
