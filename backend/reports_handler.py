"""
reports_handler.py — HydroTwin /reports Lambda (POST + GET)
=============================================================

Public, unauthenticated endpoint for citizen-submitted incident reports.

Routes (single Lambda — switches on httpMethod):
  POST /reports   submit a new report
  GET  /reports   list all reports, newest-first

Demo-first philosophy:
  - Validation rejects obvious bad input with 400 but never 500s.
  - DynamoDB failures are logged and surfaced as 503 with a JSON body so
    the frontend can show a friendly error toast.
  - Demo mode (table missing entirely): GET returns empty list + warning
    flag rather than an error, matching /status's behaviour.

Environment Variables:
  REPORTS_TABLE  – DynamoDB table name (default: HydroTwinReports)
  AWS_REGION     – auto-set by Lambda runtime (default: us-east-1)

Deploy:
  Runtime  : Python 3.12
  Handler  : reports_handler.lambda_handler
  Memory   : 256 MB
  Timeout  : 10 s
  IAM      : dynamodb:PutItem + dynamodb:Scan on
             arn:aws:dynamodb:<region>:<acct>:table/HydroTwinReports

Table schema (HydroTwinReports):
  PK = report_id (UUID v4 string)
  Attributes:
    email         (str)        — submitter's email
    region_id     (str)        — pleven | yambol | burgas | other
    description   (str)        — free-text 10–500 chars
    lat           (Decimal)    — latitude
    lng           (Decimal)    — longitude
    submitted_at  (str)        — ISO-8601 UTC

  No GSI — small N for the demo, scan is fine. Add a GSI on submitted_at if
  reports ever grow past a few thousand.
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3

# ── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Configuration ────────────────────────────────────────────────────────────
REPORTS_TABLE = os.environ.get("REPORTS_TABLE", "HydroTwinReports")
AWS_REGION    = os.environ.get("AWS_REGION", "us-east-1")

ALLOWED_REGIONS  = {"pleven", "yambol", "burgas", "other"}
EMAIL_RE         = re.compile(r"^\S+@\S+\.\S+$")
MIN_DESC_LEN     = 10
MAX_DESC_LEN     = 500

# Lazy DynamoDB resource — instantiated on first invocation, reused warm.
_TABLE = None


def _get_table():
    global _TABLE
    if _TABLE is None:
        _TABLE = boto3.resource("dynamodb", region_name=AWS_REGION).Table(REPORTS_TABLE)
    return _TABLE


def _to_native(obj):
    """Recursively convert DynamoDB Decimals to int/float for JSON output."""
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    if isinstance(obj, list):
        return [_to_native(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    return obj


# ─────────────────────────────────────────────────────────────────────────────
#  LAMBDA ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context) -> dict:
    """Routes by HTTP method; CORS preflight short-circuits to 200."""
    logger.info("Event received: %s", json.dumps(event)[:1000])

    method = (event.get("httpMethod") or "").upper()

    if method == "OPTIONS":
        return _response(200, {})

    if method == "POST":
        return _handle_post(event)

    if method == "GET":
        return _handle_get()

    return _response(405, {"error": f"Method {method or 'unknown'} not allowed"})


# ─────────────────────────────────────────────────────────────────────────────
#  POST /reports — submit a new report
# ─────────────────────────────────────────────────────────────────────────────

def _handle_post(event: dict) -> dict:
    # ── Parse body ───────────────────────────────────────────────────────
    try:
        raw_body = event.get("body", "{}")
        body     = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
    except (json.JSONDecodeError, AttributeError) as exc:
        return _response(400, {"error": f"Invalid JSON body: {exc}"})

    # ── Validate ─────────────────────────────────────────────────────────
    email       = (body.get("email")       or "").strip()
    region_id   = (body.get("region_id")   or "").strip().lower()
    description = (body.get("description") or "").strip()
    lat         = body.get("lat")
    lng         = body.get("lng")

    errors = []
    if not EMAIL_RE.match(email):
        errors.append("email is invalid")
    if region_id not in ALLOWED_REGIONS:
        errors.append(f"region_id must be one of {sorted(ALLOWED_REGIONS)}")
    if len(description) < MIN_DESC_LEN:
        errors.append(f"description must be at least {MIN_DESC_LEN} characters")
    if len(description) > MAX_DESC_LEN:
        errors.append(f"description must be at most {MAX_DESC_LEN} characters")
    try:
        lat_f = float(lat)
        lng_f = float(lng)
        if not (-90 <= lat_f <= 90):   errors.append("lat out of range")
        if not (-180 <= lng_f <= 180): errors.append("lng out of range")
    except (TypeError, ValueError):
        errors.append("lat and lng must be numbers")
        lat_f = lng_f = None

    if errors:
        return _response(400, {"error": "Validation failed", "details": errors})

    # ── Build item ───────────────────────────────────────────────────────
    report_id    = str(uuid.uuid4())
    submitted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    item = {
        "report_id":    report_id,
        "email":        email,
        "region_id":    region_id,
        "description":  description,
        "lat":          lat_f,
        "lng":          lng_f,
        "submitted_at": submitted_at,
    }
    # Round-trip floats → Decimal for DynamoDB
    item = json.loads(json.dumps(item), parse_float=Decimal)

    # ── Persist ──────────────────────────────────────────────────────────
    try:
        _get_table().put_item(Item=item)
        logger.info("Report %s persisted (region=%s)", report_id, region_id)
    except Exception as exc:
        logger.error("DynamoDB put_item failed: %s", exc, exc_info=True)
        return _response(503, {"error": f"Persistence unavailable ({type(exc).__name__})"})

    return _response(200, {
        "report_id":    report_id,
        "submitted_at": submitted_at,
    })


# ─────────────────────────────────────────────────────────────────────────────
#  GET /reports — list newest-first
# ─────────────────────────────────────────────────────────────────────────────

def _handle_get() -> dict:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    try:
        # Small table, scan is fine. Switch to a query on a date-bucketed GSI
        # if reports ever grow into the thousands.
        response = _get_table().scan()
        items    = _to_native(response.get("Items", []))
        # Newest first by submitted_at ISO-8601 (lexicographic == chronological)
        items.sort(key=lambda r: r.get("submitted_at", ""), reverse=True)
        logger.info("Returning %d report(s)", len(items))
        return _response(200, {
            "reports":      items,
            "generated_at": generated_at,
        })

    except Exception as exc:
        # Table missing, throttling, no creds — fall through to empty list
        # so the frontend renders the empty state rather than an error.
        logger.error("Reports scan failed: %s", exc, exc_info=True)
        return _response(200, {
            "reports":      [],
            "generated_at": generated_at,
            "demo_mode":    True,
            "warning":      f"Reports unavailable ({type(exc).__name__})",
        })


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
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body),
    }
