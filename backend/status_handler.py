"""
status_handler.py — HydroTwin GET /status Lambda
=================================================

Read-only endpoint that returns the latest snapshot per region from the
HydroTwinStatus DynamoDB table (populated by cron_handler.py).

The frontend calls this on page load to paint every region polygon by its
current status — no per-region click-to-fetch needed for at-a-glance state.

Flow:
  1. Scan the HydroTwinStatus table (one row per region — small N, scan is fine)
  2. Convert DynamoDB Decimals back to native Python numbers for JSON
  3. Return { regions: [...], generated_at } with CORS headers

Environment Variables:
  STATUS_TABLE  – DynamoDB table name (default: HydroTwinStatus)
  AWS_REGION    – auto-set by Lambda runtime (default: us-east-1)

Deploy:
  Runtime  : Python 3.12
  Handler  : status_handler.lambda_handler
  Memory   : 128 MB
  Timeout  : 10s
  IAM      : dynamodb:Scan on arn:aws:dynamodb:<region>:<acct>:table/HydroTwinStatus

Demo-first philosophy:
  If the table is missing OR scan fails, return 200 with `regions: []` and
  `demo_mode: true` so the frontend just paints polygons in neutral grey
  rather than crashing the dashboard.
"""

import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3

# ── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Configuration ────────────────────────────────────────────────────────────
STATUS_TABLE = os.environ.get("STATUS_TABLE", "HydroTwinStatus")
AWS_REGION   = os.environ.get("AWS_REGION", "us-east-1")

# Lazy DynamoDB client — instantiated on first invocation, reused warm.
_TABLE = None


def _get_table():
    global _TABLE
    if _TABLE is None:
        _TABLE = boto3.resource("dynamodb", region_name=AWS_REGION).Table(STATUS_TABLE)
    return _TABLE


def _to_native(obj):
    """
    Recursively convert DynamoDB Decimal types to int/float so the response
    serialises cleanly through json.dumps without TypeErrors.
    """
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
    """
    GET /status — returns the latest assessment per region.

    Response (200):
    {
      "regions": [
        {
          "region_id":   "pleven",
          "status":      "FLOOD_WATCH",
          "confidence":  0.82,
          "reasoning":   "...",
          "sources":     ["..."],
          "assessed_at": "2026-04-25T14:30:00+00:00"
        }
      ],
      "generated_at": "2026-04-25T14:31:12+00:00"
    }
    """
    logger.info("Event received: %s", json.dumps(event))

    # ── Handle CORS preflight ────────────────────────────────────────────
    if event.get("httpMethod") == "OPTIONS":
        return _response(200, {})

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    try:
        # Small table (one row per region) — scan is fine. Switch to a query
        # if regions ever grow into the hundreds.
        response = _get_table().scan()
        items    = response.get("Items", [])
        regions  = _to_native(items)
        logger.info("Returned %d region snapshot(s)", len(regions))
        return _response(200, {
            "regions":      regions,
            "generated_at": generated_at,
        })

    except Exception as exc:
        # Table missing, throttling, no credentials — fall through to empty
        # array so the frontend renders neutral polygons rather than crashing.
        logger.error("Status scan failed: %s", exc)
        return _response(200, {
            "regions":      [],
            "generated_at": generated_at,
            "demo_mode":    True,
            "warning":      f"Snapshot unavailable ({type(exc).__name__})",
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
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body),
    }
