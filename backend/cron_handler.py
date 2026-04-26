"""
cron_handler.py — HydroTwin EventBridge-triggered orchestrator
================================================================

Runs every 30 minutes via EventBridge Scheduler. For each known region:
  1. Read prior snapshot from HydroTwinStatus
  2. Run the assess pipeline (extractor → rules → Bedrock)
  3. Write new snapshot (upsert by region_id)
  4. Fire webhook ONLY on status-code transition (de-dup)

This is the v2 backbone: it keeps the map's pre-computed state fresh AND
makes notifications actually fire on real-world condition changes (not just
when a user clicks a region).

Demo-first philosophy: any single region's failure is logged + skipped;
the rest of the run continues.

Environment Variables:
  STATUS_TABLE         – DynamoDB table name (default: HydroTwinStatus)
  AWS_REGION           – auto-set by Lambda runtime (default: us-east-1)
  + all env vars used by lambda_handler.py
    (DISCORD_WEBHOOK_URL, BEDROCK_MODEL_ID, BEDROCK_REGION, SH_CLIENT_ID/SECRET)

Deploy:
  Runtime  : Python 3.12
  Handler  : cron_handler.lambda_handler
  Memory   : 256 MB
  Timeout  : 15 min  (32 regions × ~10–15s each — bumped from 5 min when
             municipalities were added to ALL_REGIONS, 2026-04-25)
  Trigger  : EventBridge Schedule, rate(30 minutes)
  IAM      : same as HydroTwin (Bedrock + Sentinel) PLUS dynamodb:GetItem,
             dynamodb:PutItem on arn:aws:dynamodb:<region>:<acct>:table/HydroTwinStatus

V2-5 hook (colleague's history table):
  After _write_snapshot() succeeds, append `{region_id, assessed_at, ...}` to
  HydroTwinHistory (PK=region_id, SK=assessed_at) — ~5 lines, zero impact on
  this file's snapshot logic.
"""

import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr

import notifications
from lambda_handler import assess_region, trigger_webhook
from regions import ALL_REGIONS, REGIONS, REGION_NAMES

# ── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Configuration ────────────────────────────────────────────────────────────
STATUS_TABLE        = os.environ.get("STATUS_TABLE",        "HydroTwinStatus")
SUBSCRIPTIONS_TABLE = os.environ.get("SUBSCRIPTIONS_TABLE", "HydroTwinSubscriptions")
AWS_REGION          = os.environ.get("AWS_REGION",          "us-east-1")

# Lazy DynamoDB clients — instantiated on first invocation, reused warm.
_TABLE      = None
_SUBS_TABLE = None


def _get_table():
    global _TABLE
    if _TABLE is None:
        _TABLE = boto3.resource("dynamodb", region_name=AWS_REGION).Table(STATUS_TABLE)
    return _TABLE


def _get_subs_table():
    global _SUBS_TABLE
    if _SUBS_TABLE is None:
        _SUBS_TABLE = boto3.resource("dynamodb", region_name=AWS_REGION).Table(SUBSCRIPTIONS_TABLE)
    return _SUBS_TABLE


# ─────────────────────────────────────────────────────────────────────────────
#  SUBSCRIBER FAN-OUT — email + per-user Discord on transitions
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_subscribers_for(region_id: str) -> list[dict]:
    """
    Pull all subscriptions for a single region. Uses Scan + FilterExpression
    because the table's primary key is (email, region_id) — there's no GSI on
    region_id yet. At hackathon scale (tens to low hundreds of subscribers)
    this is fine; revisit with a GSI on `region_id` if it grows past ~1k rows.
    """
    try:
        subs   = []
        kwargs = {"FilterExpression": Attr("region_id").eq(region_id)}
        while True:
            resp = _get_subs_table().scan(**kwargs)
            subs.extend(resp.get("Items", []))
            if "LastEvaluatedKey" not in resp:
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return subs
    except Exception as exc:
        logger.error("Could not fetch subscribers for %s: %s", region_id, exc)
        return []


def _notify_subscribers(*, region_id: str, region_name: str,
                        new_status: str, prior_status: str | None,
                        confidence: float, reasoning: str) -> dict:
    """
    Fan out a transition notification to every subscriber of `region_id`. Each
    channel call is wrapped — a single dead Discord webhook can't take down
    the rest of the email batch.
    """
    subs    = _fetch_subscribers_for(region_id)
    counts  = {"emails_sent": 0, "discord_sent": 0, "subscribers": len(subs)}

    for sub in subs:
        email   = sub.get("email")
        webhook = sub.get("discord_webhook")

        if email:
            subject, html = notifications.render_alert_email(
                region_name     = region_name,
                region_id       = region_id,
                status          = new_status,
                prior_status    = prior_status,
                confidence      = float(confidence or 0),
                reasoning       = reasoning or "",
                recipient_email = email,
            )
            text = notifications.render_email_text_fallback(
                region_name = region_name,
                status      = new_status,
                reasoning   = reasoning or "",
                region_id   = region_id,
            )
            if notifications.send_email(email, subject, html, text):
                counts["emails_sent"] += 1

        if webhook:
            if notifications.send_discord_to_webhook(
                webhook,
                region_name = region_name,
                region_id   = region_id,
                status      = new_status,
                confidence  = float(confidence or 0),
                reasoning   = reasoning or "",
                kind        = "alert",
            ):
                counts["discord_sent"] += 1

    if subs:
        logger.info(
            "Fan-out for %s (%s): %d emails, %d discord (of %d subscribers)",
            region_id, new_status,
            counts["emails_sent"], counts["discord_sent"], counts["subscribers"],
        )
    return counts


# ─────────────────────────────────────────────────────────────────────────────
#  SNAPSHOT TABLE I/O
# ─────────────────────────────────────────────────────────────────────────────

def _read_prior_status(region_id: str) -> dict | None:
    """
    Fetch the previous snapshot for a region. Returns None on first-ever run
    or if the table read fails (treated identically — fall through to "no prior").
    """
    try:
        response = _get_table().get_item(Key={"region_id": region_id})
        return response.get("Item")
    except Exception as exc:
        logger.warning("Could not read prior status for %s: %s", region_id, exc)
        return None


def _write_snapshot(region_id: str, assessment: dict) -> None:
    """
    Upsert the latest snapshot for a region into HydroTwinStatus.

    DynamoDB rejects native Python floats — round-trip the item through JSON
    with `parse_float=Decimal` so confidence (and any nested floats from the
    extractor) become Decimal automatically.
    """
    item = {
        "region_id":            region_id,
        "status":               assessment.get("status", "SAFE"),
        "confidence":           assessment.get("confidence", 0),
        "reasoning":            assessment.get("reasoning", ""),
        # V3-3: persist the 4-section structured reasoning alongside the legacy
        # markdown blob so /status can hand it back to the frontend without a
        # second LLM call. Empty dict is fine — DynamoDB accepts it.
        "reasoning_structured": assessment.get("reasoning_structured", {}),
        "sources":              assessment.get("sources", []),
        "assessed_at":          datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    item = json.loads(json.dumps(item), parse_float=Decimal)
    _get_table().put_item(Item=item)


# ─────────────────────────────────────────────────────────────────────────────
#  DE-DUP LOGIC — fire webhook only on status-code transitions
# ─────────────────────────────────────────────────────────────────────────────

def _should_fire_webhook(prior: dict | None, new_status: str) -> bool:
    """
    Decision matrix:
        prior None,     new SAFE       → False  (first run, all-clear, stay quiet)
        prior None,     new non-SAFE   → True   (first run, alert)
        prior SAFE,     new SAFE       → False  (no change)
        prior SAFE,     new non-SAFE   → True   (escalation)
        prior non-SAFE, new SAFE       → True   (recovery — subscribers want to know)
        prior non-SAFE, new same       → False  (no change)
        prior non-SAFE, new different  → True   (escalation/de-escalation between alert tiers)
    """
    if prior is None:
        return new_status != "SAFE"
    return prior.get("status") != new_status


# ─────────────────────────────────────────────────────────────────────────────
#  LAMBDA ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context) -> dict:
    """
    Invoked by EventBridge Scheduler. The event payload is ignored — this
    runs on a fixed cadence regardless of contents.

    Returns a summary dict (visible in CloudWatch + manual `aws lambda invoke`).
    """
    logger.info(
        "HydroTwinCron run started — %d region(s) (%d oblast + %d municipality)",
        len(ALL_REGIONS), len(REGIONS), len(ALL_REGIONS) - len(REGIONS),
    )

    summary = {
        "regions_total":            len(ALL_REGIONS),
        "regions_succeeded":        0,
        "regions_failed":           0,
        "oblasts_processed":        0,
        "municipalities_processed": 0,
        "webhooks_fired":           0,
        "subscriber_emails_sent":   0,
        "subscriber_discord_sent":  0,
        "transitions":              [],
        "errors":                   [],
    }

    # Oblasts are iterated first (REGIONS) so they always refresh even if a
    # later municipality call hits the Lambda timeout. Webhooks fire only on
    # oblast transitions — subscriptions are oblast-scoped and 29 muni-level
    # alerts per cycle would be noise.
    for region_id, bbox in ALL_REGIONS.items():
        is_oblast = region_id in REGIONS
        try:
            prior        = _read_prior_status(region_id)
            prior_status = prior.get("status") if prior else None

            assessment = assess_region(region_id, bbox)
            new_status = assessment.get("status", "SAFE")

            _write_snapshot(region_id, assessment)

            if is_oblast and _should_fire_webhook(prior, new_status):
                logger.info(
                    "Status transition for %s: %s → %s — firing webhook.",
                    region_id, prior_status, new_status,
                )
                trigger_webhook(assessment)
                summary["webhooks_fired"] += 1
                summary["transitions"].append({
                    "region_id": region_id,
                    "from":      prior_status,
                    "to":        new_status,
                })

                # Fan out to per-region subscribers (email + per-user Discord).
                # Wrapped so a notifications crash never kills the cron run.
                try:
                    region_name = REGION_NAMES.get(region_id, region_id)
                    counts = _notify_subscribers(
                        region_id    = region_id,
                        region_name  = region_name,
                        new_status   = new_status,
                        prior_status = prior_status,
                        confidence   = assessment.get("confidence", 0),
                        reasoning    = assessment.get("reasoning", ""),
                    )
                    summary["subscriber_emails_sent"]  += counts["emails_sent"]
                    summary["subscriber_discord_sent"] += counts["discord_sent"]
                except Exception as exc:
                    logger.error("Subscriber fan-out failed for %s: %s", region_id, exc)
            else:
                logger.info(
                    "No webhook for %s (status=%s, oblast=%s).",
                    region_id, new_status, is_oblast,
                )

            summary["regions_succeeded"] += 1
            if is_oblast:
                summary["oblasts_processed"] += 1
            else:
                summary["municipalities_processed"] += 1

        except Exception as exc:
            logger.error("Assess failed for %s: %s", region_id, exc, exc_info=True)
            summary["regions_failed"] += 1
            summary["errors"].append({"region_id": region_id, "error": str(exc)})

    logger.info("HydroTwinCron run complete: %s", json.dumps(summary, default=str))
    return summary
