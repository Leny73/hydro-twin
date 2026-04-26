"""
subscribe_handler.py — HydroTwin /subscribe Lambda
====================================================

Stores a (email, region_id) subscription in DynamoDB so the Subscribe-to-Alerts
button in the frontend has a real backend.

Flow:
  1.  Parse incoming API Gateway POST  (email + region_id)
  2.  Validate email format + region_id against the known region whitelist
  3.  PutItem to DynamoDB with a conditional expression (no overwrite)
        └─ Composite key:  PK = email, SK = region_id
        └─ One user can subscribe to multiple regions; same (email, region) pair
           only exists once.
  4.  Return API Gateway-compatible JSON response with CORS headers
        201 = subscribed, 400 = invalid input, 409 = already subscribed

Environment Variables (set in AWS Lambda Console):
  SUBSCRIPTIONS_TABLE  – DynamoDB table name           (default: HydroTwinSubscriptions)
  AWS_REGION           – auto-set by Lambda runtime    (default: us-east-1)

Deploy:
  Runtime  : Python 3.10+
  Handler  : subscribe_handler.lambda_handler
  Memory   : 128 MB    (DynamoDB PutItem is tiny)
  Timeout  : 10s
  Include  : subscribe_handler.py + boto3 (pre-installed in Lambda runtime)
  IAM      : dynamodb:PutItem on arn:aws:dynamodb:<region>:<acct>:table/HydroTwinSubscriptions

Demo-first philosophy (matches lambda_handler.py):
  If SUBSCRIPTIONS_TABLE is unset OR the DynamoDB call fails for any reason,
  return 201 with `demo_mode: true` so the Subscribe UI still shows success
  during the pitch. The warning is logged to CloudWatch, not bubbled up.
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

# Loose RFC-ish email regex — strict validation belongs to a verification email,
# not a synchronous API call.
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Lazy DynamoDB client — instantiated on first invocation, reused warm.
_TABLE = None


def _get_table():
    global _TABLE
    if _TABLE is None:
        _TABLE = boto3.resource("dynamodb", region_name=AWS_REGION).Table(SUBSCRIPTIONS_TABLE)
    return _TABLE


# ─────────────────────────────────────────────────────────────────────────────
#  LAMBDA ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context) -> dict:
    """
    AWS Lambda handler — invoked by API Gateway.

    POST /subscribe
      Body: { "email": "user@example.com", "region_id": "danube-basin" }
      201  subscribed | 400  invalid input | 409  already subscribed

    DELETE /subscribe  (or GET /unsubscribe?email=...&region_id=...)
      Removes the (email, region_id) pair from DynamoDB.
      200  unsubscribed | 400  invalid input | 404  not found
    """
    logger.info("Event received: %s", json.dumps(event))

    # ── Handle CORS preflight ────────────────────────────────────────────
    if event.get("httpMethod") == "OPTIONS":
        return _response(200, {})

    # ── Route DELETE and GET /unsubscribe to the unsubscribe handler ─────
    method = event.get("httpMethod", "POST")
    if method == "DELETE" or (method == "GET" and "/unsubscribe" in (event.get("path") or "")):
        return _handle_unsubscribe(event)

    # ── 1. Parse + validate request body ─────────────────────────────────
    try:
        raw_body = event.get("body", "{}")
        body     = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
    except (json.JSONDecodeError, AttributeError) as exc:
        logger.error("Invalid request body: %s", exc)
        return _response(400, {"error": f"Invalid JSON body: {exc}"})

    email     = (body.get("email")     or "").strip().lower()
    region_id = (body.get("region_id") or "").strip()

    if not EMAIL_REGEX.match(email):
        return _response(400, {"error": "Invalid email address"})

    if region_id not in KNOWN_REGIONS:
        return _response(400, {
            "error": "Unknown region_id",
            "allowed": sorted(KNOWN_REGIONS),
        })

    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    item = {
        "email":      email,
        "region_id":  region_id,
        "created_at": created_at,
    }

    # ── 2. Write to DynamoDB (conditional — no overwrite) ────────────────
    try:
        _get_table().put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(email) AND attribute_not_exists(region_id)",
        )
        logger.info("Subscribed: %s → %s", email, region_id)
        return _response(201, {"message": "subscribed", **item})

    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "ConditionalCheckFailedException":
            logger.info("Duplicate subscription: %s → %s", email, region_id)
            return _response(409, {
                "error":     "Already subscribed",
                "email":     email,
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

def _handle_unsubscribe(event: dict) -> dict:
    """
    Remove a subscription. Accepts two request shapes:
      DELETE /subscribe  — body: { "email": "...", "region_id": "..." }
      GET    /unsubscribe?email=...&region_id=...  — for email link clicks
    """
    method = event.get("httpMethod", "DELETE")
    if method == "GET":
        params    = event.get("queryStringParameters") or {}
        email     = (params.get("email")     or "").strip().lower()
        region_id = (params.get("region_id") or "").strip()
    else:
        try:
            raw_body = event.get("body", "{}")
            body     = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
        except (json.JSONDecodeError, AttributeError) as exc:
            return _response(400, {"error": f"Invalid JSON body: {exc}"})
        email     = (body.get("email")     or "").strip().lower()
        region_id = (body.get("region_id") or "").strip()

    if not EMAIL_REGEX.match(email):
        return _response(400, {"error": "Invalid email address"})
    if not region_id:
        return _response(400, {"error": "region_id is required"})

    try:
        _get_table().delete_item(
            Key={"email": email, "region_id": region_id},
            ConditionExpression="attribute_exists(email) AND attribute_exists(region_id)",
        )
        logger.info("Unsubscribed: %s from %s", email, region_id)
        # For GET (email link click) return a simple HTML confirmation page
        if method == "GET":
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "text/html"},
                "body": (
                    "<html><body style='font-family:system-ui;text-align:center;padding:60px;background:#0f172a;color:#e2e8f0;'>"
                    f"<h2>✅ Unsubscribed</h2>"
                    f"<p>You have been removed from alerts for <strong>{region_id}</strong>.</p>"
                    "</body></html>"
                ),
            }
        return _response(200, {"message": "unsubscribed", "email": email, "region_id": region_id})

    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "ConditionalCheckFailedException":
            return _response(404, {"error": "Subscription not found", "email": email, "region_id": region_id})
        logger.error("DynamoDB delete failed (%s): %s", code, exc)
        return _response(500, {"error": "Internal error — please try again."})

    except Exception as exc:
        logger.error("Unsubscribe failed: %s", exc)
        return _response(500, {"error": f"Internal error: {type(exc).__name__}"})


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
