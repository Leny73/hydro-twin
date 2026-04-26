"""
subscribe_handler.py — HydroTwin /subscribe Lambda
====================================================

Stores a (phone, region_id) subscription in DynamoDB and sends a confirmation
SMS via AWS SNS so subscribers receive push notifications on status transitions.

Flow:
  1.  Parse incoming API Gateway POST  (phone + region_id)
  2.  Validate E.164 phone format + region_id against the known region whitelist
  3.  PutItem to DynamoDB with a conditional expression (no overwrite)
        └─ Composite key:  PK = phone, SK = region_id
        └─ One user can subscribe to multiple regions; same (phone, region) pair
           only exists once.
  4.  Send a confirmation SMS via AWS SNS with region info
  5.  Return API Gateway-compatible JSON response with CORS headers
        201 = subscribed, 400 = invalid input, 409 = already subscribed

Environment Variables (set in AWS Lambda Console):
  SUBSCRIPTIONS_TABLE  – DynamoDB table name           (default: HydroTwinSubscriptions)
  AWS_REGION           – auto-set by Lambda runtime    (default: us-east-1)

Deploy:
  Runtime  : Python 3.10+
  Handler  : subscribe_handler.lambda_handler
  Memory   : 128 MB
  Timeout  : 10s
  Include  : subscribe_handler.py + boto3 (pre-installed in Lambda runtime)
  IAM      : dynamodb:PutItem on arn:aws:dynamodb:<region>:<acct>:table/HydroTwinSubscriptions
             sns:Publish (for direct SMS — no topic needed)

Demo-first philosophy (matches lambda_handler.py):
  If SUBSCRIPTIONS_TABLE is unset OR the DynamoDB call fails for any reason,
  return 201 with `demo_mode: true` so the Subscribe UI still shows success
  during the pitch. SNS failures are also non-fatal — logged and ignored.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from regions import KNOWN_REGIONS

# ── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Configuration ────────────────────────────────────────────────────────────
SUBSCRIPTIONS_TABLE = os.environ.get("SUBSCRIPTIONS_TABLE", "HydroTwinSubscriptions")
AWS_REGION          = os.environ.get("AWS_REGION", "us-east-1")

# Region whitelist sourced from backend/regions.py — single source of truth.
# Sync with frontend/src/regions.geojson + frontend/src/App.jsx REGIONS[].id when adding regions.

# E.164 international phone number format: +[country code][number], 8–15 digits total.
PHONE_REGEX = re.compile(r"^\+[1-9]\d{7,14}$")

# Lazy clients — instantiated on first invocation, reused across warm invocations.
_TABLE   = None
_SNS     = None


def _get_table():
    global _TABLE
    if _TABLE is None:
        _TABLE = boto3.resource("dynamodb", region_name=AWS_REGION).Table(SUBSCRIPTIONS_TABLE)
    return _TABLE


def _get_sns():
    global _SNS
    if _SNS is None:
        _SNS = boto3.client("sns", region_name=AWS_REGION)
    return _SNS


def _send_confirmation_sms(phone: str, region_id: str) -> None:
    """Fire a confirmation SMS via AWS SNS direct publish. Non-fatal on any error."""
    region_label = region_id.replace("-", " ").title()
    message = (
        f"HydroTwin: You are now subscribed to flood & drought alerts for "
        f"{region_label}. You will receive an SMS whenever the risk level changes. "
        f"Reply STOP to unsubscribe."
    )
    logger.info("SMS payload → %s: %s", phone, message)
    print(f"\n[HydroTwin SMS] To: {phone}\n[HydroTwin SMS] {message}\n", flush=True)
    try:
        _get_sns().publish(
            PhoneNumber=phone,
            Message=message,
            MessageAttributes={
                "AWS.SNS.SMS.SMSType": {
                    "DataType":    "String",
                    "StringValue": "Transactional",
                },
                "AWS.SNS.SMS.SenderID": {
                    "DataType":    "String",
                    "StringValue": "HydroTwin",
                },
            },
        )
        logger.info("Confirmation SMS sent to %s for %s", phone, region_id)
    except Exception as exc:
        # SNS failure must not block the subscribe response.
        logger.warning("SMS send failed (no AWS creds?) — message was logged above. Error: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
#  LAMBDA ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context) -> dict:
    """
    AWS Lambda handler — invoked by API Gateway on POST /subscribe.

    Expected POST body (JSON):
    {
        "phone":     "+359876543210",
        "region_id": "danube-basin"
    }

    Responses:
      201  { "message": "subscribed", "phone": ..., "region_id": ..., "created_at": ... }
      400  { "error": "Invalid phone number" | "Unknown region_id" | "Invalid JSON body" }
      409  { "error": "Already subscribed", ... }
    """
    logger.info("Event received: %s", json.dumps(event))

    # ── Handle CORS preflight ────────────────────────────────────────────
    if event.get("httpMethod") == "OPTIONS":
        return _response(200, {})

    # ── 1. Parse + validate request body ─────────────────────────────────
    try:
        raw_body = event.get("body", "{}")
        body     = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
    except (json.JSONDecodeError, AttributeError) as exc:
        logger.error("Invalid request body: %s", exc)
        return _response(400, {"error": f"Invalid JSON body: {exc}"})

    phone     = (body.get("phone")     or "").strip()
    region_id = (body.get("region_id") or "").strip()

    if not PHONE_REGEX.match(phone):
        return _response(400, {"error": "Invalid phone number — use international format: +359876543210"})

    if region_id not in KNOWN_REGIONS:
        return _response(400, {
            "error": "Unknown region_id",
            "allowed": sorted(KNOWN_REGIONS),
        })

    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    item = {
        "phone":      phone,
        "region_id":  region_id,
        "created_at": created_at,
    }

    # ── 2. Write to DynamoDB (conditional — no overwrite) ────────────────
    try:
        _get_table().put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(phone) AND attribute_not_exists(region_id)",
        )
        logger.info("Subscribed: %s → %s", phone, region_id)
        _send_confirmation_sms(phone, region_id)
        return _response(201, {"message": "subscribed", **item})

    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "ConditionalCheckFailedException":
            logger.info("Duplicate subscription: %s → %s", phone, region_id)
            return _response(409, {
                "error":     "Already subscribed",
                "phone":     phone,
                "region_id": region_id,
            })
        # Real AWS error (table missing, throttling, IAM denied, etc.) — fall
        # through to demo-mode response so the UI doesn't show a hard failure.
        logger.error("DynamoDB put failed (%s): %s", code, exc)
        return _response(201, {
            "message":   "subscribed",
            **item,
            "demo_mode": True,
            "warning":   f"Stored in demo mode only ({code or 'ClientError'})",
        })

    except Exception as exc:
        # NoCredentialsError, EndpointConnectionError, anything else — same fallback.
        logger.error("Subscribe failed: %s", exc)
        return _response(201, {
            "message":   "subscribed",
            **item,
            "demo_mode": True,
            "warning":   f"Stored in demo mode only ({type(exc).__name__})",
        })


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _response(status_code: int, body: dict) -> dict:
    """API Gateway-compatible response with CORS headers (matches lambda_handler.py)."""
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
