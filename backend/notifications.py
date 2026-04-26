"""
notifications.py — Multi-channel delivery layer for HydroTwin
================================================================

Single home for every outbound message HydroTwin can fire at a subscriber.
Each channel exposes the same shape:

    send_<channel>(...) -> bool   # True on success, False on any failure
                                  # Never raises — caller can fan out blindly.

Channels:
  📧 Email     — Brevo (Sendinblue) Transactional API      [LIVE]
  💬 Discord   — per-user Incoming Webhook URL            [LIVE]
  📱 SMS       — AWS SNS (sandbox-friendly)               [STUB / demo-mode]
  ✈️  Telegram — Bot API to a user-supplied chat_id       [STUB / demo-mode]

The HTML email template is intentionally inlined (email clients ignore <style>
tags reliably only when CSS is on each element). Keep it under ~10 KB so Gmail
doesn't clip the message.

Demo-first philosophy (matches lambda_handler.py):
  Every function catches its own exceptions and returns False on failure so
  the cron + subscribe handler can fan out without blowing up. The reason is
  logged to CloudWatch.

Environment variables consumed:
  BREVO_API_KEY          — required for live email
  BREVO_SENDER_EMAIL     — required for live email     (must be Brevo-verified)
  BREVO_SENDER_NAME      — display name, defaults to "HydroTwin"
  FRONTEND_BASE_URL      — used in deep links + unsubscribe URLs
                            (default: https://hydrotwin.vercel.app)
  UNSUBSCRIBE_SECRET     — HMAC secret for unsubscribe tokens
                            (default: a fixed dev-mode value, override in prod)
"""

import hmac
import hashlib
import html as _html_lib
import json
import logging
import os
import re

import boto3
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# ── Configuration (cached at module load) ────────────────────────────────────
BREVO_API_KEY      = os.environ.get("BREVO_API_KEY", "").strip()
BREVO_SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL", "").strip()
BREVO_SENDER_NAME  = os.environ.get("BREVO_SENDER_NAME", "HydroTwin").strip()
FRONTEND_BASE_URL  = os.environ.get("FRONTEND_BASE_URL", "https://hydrotwin.vercel.app").rstrip("/")
UNSUBSCRIBE_SECRET = os.environ.get("UNSUBSCRIBE_SECRET", "hydrotwin-dev-secret-change-me")

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


# ─────────────────────────────────────────────────────────────────────────────
#  STATUS METADATA — shared across email + Discord templates
# ─────────────────────────────────────────────────────────────────────────────

STATUS_META = {
    "SAFE":            {"emoji": "🟢", "label": "Safe",            "color": "#10B981", "color_int": 0x10B981},
    "DROUGHT_WATCH":   {"emoji": "🟡", "label": "Drought Watch",   "color": "#F59E0B", "color_int": 0xF59E0B},
    "DROUGHT_WARNING": {"emoji": "🟠", "label": "Drought Warning", "color": "#F97316", "color_int": 0xF97316},
    "FLOOD_WATCH":     {"emoji": "🌊", "label": "Flood Watch",     "color": "#3B82F6", "color_int": 0x3B82F6},
    "FLOOD_WARNING":   {"emoji": "🔴", "label": "Flood Warning",   "color": "#EF4444", "color_int": 0xEF4444},
}


def _meta(status: str) -> dict:
    return STATUS_META.get(status, STATUS_META["SAFE"])


# ─────────────────────────────────────────────────────────────────────────────
#  DEEP LINKS + UNSUBSCRIBE TOKENS
# ─────────────────────────────────────────────────────────────────────────────

def region_deep_link(region_id: str) -> str:
    """Public URL that opens HydroTwin with that region's panel pre-selected."""
    return f"{FRONTEND_BASE_URL}/?region={region_id}"


def make_unsubscribe_token(email: str, region_id: str) -> str:
    """HMAC-SHA256 signature truncated to 16 hex chars — short but unguessable."""
    msg = f"{email}|{region_id}".encode("utf-8")
    sig = hmac.new(UNSUBSCRIBE_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return sig[:16]


def verify_unsubscribe_token(email: str, region_id: str, token: str) -> bool:
    """Constant-time comparison so a timing oracle can't brute-force tokens."""
    expected = make_unsubscribe_token(email, region_id)
    return hmac.compare_digest(expected, token or "")


def unsubscribe_link(email: str, region_id: str) -> str:
    token = make_unsubscribe_token(email, region_id)
    # urllib.parse.quote isn't strictly required for these chars but plays it safe
    safe_email = requests.utils.quote(email, safe="")
    return (
        f"{FRONTEND_BASE_URL}/unsubscribe"
        f"?e={safe_email}&r={region_id}&t={token}"
    )


# ─────────────────────────────────────────────────────────────────────────────
#  📧 EMAIL — Brevo Transactional API
# ─────────────────────────────────────────────────────────────────────────────

def send_email(to_email: str, subject: str, html_body: str, text_body: str = "") -> bool:
    """
    Fire a single transactional email via Brevo. Returns True on 2xx, False otherwise.
    Falls through to demo-mode (logs only) if BREVO_API_KEY isn't configured.
    """
    if not BREVO_API_KEY or not BREVO_SENDER_EMAIL:
        logger.warning(
            "[email demo-mode] Would have sent to %s — subject=%r (BREVO not configured)",
            to_email, subject,
        )
        return False

    payload = {
        "sender":      {"name": BREVO_SENDER_NAME, "email": BREVO_SENDER_EMAIL},
        "to":          [{"email": to_email}],
        "subject":     subject,
        "htmlContent": html_body,
    }
    if text_body:
        payload["textContent"] = text_body

    try:
        resp = requests.post(
            BREVO_ENDPOINT,
            headers={
                "api-key":      BREVO_API_KEY,
                "Content-Type": "application/json",
                "Accept":       "application/json",
            },
            json=payload,
            timeout=8,
        )
        if 200 <= resp.status_code < 300:
            logger.info("Brevo email delivered to %s — HTTP %s", to_email, resp.status_code)
            return True
        logger.error(
            "Brevo email rejected (HTTP %s): %s", resp.status_code, resp.text[:300],
        )
        return False
    except requests.RequestException as exc:
        logger.error("Brevo email transport failed: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  EMAIL TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────

# Compact dark-themed template that matches the dashboard palette. All CSS is
# inline because Gmail/Outlook strip <style> blocks. Keep paragraphs short —
# Gmail clips messages over ~102 KB, but trimmed early helps with previews too.

def _render_email_shell(*, region_name: str, region_id: str, status: str,
                        confidence: float, reasoning: str, headline: str,
                        cta_label: str, intro_html: str, recipient_email: str) -> str:
    meta       = _meta(status)
    deep_link  = region_deep_link(region_id)
    unsub_link = unsubscribe_link(recipient_email, region_id)
    conf_pct   = int(round(float(confidence or 0) * 100))
    safe_reason = _md_to_email_html(reasoning or "No reasoning available.")

    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0; padding:24px 12px; background:#0B1220; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"
         style="max-width:580px; margin:0 auto; background:#0F172A; border:1px solid #1E293B;
                border-radius:14px; overflow:hidden;">

    <tr><td style="padding:24px 24px 16px;">
      <div style="font-size:22px; font-weight:700; color:#67E8F9; letter-spacing:0.5px;">
        💧 HydroTwin
      </div>
      <div style="font-size:12px; color:#64748B; margin-top:2px;">
        Flood &amp; drought early warning · Bulgaria
      </div>
    </td></tr>

    <tr><td style="padding:0 24px 8px;">
      <div style="font-size:18px; font-weight:600; color:#F1F5F9; line-height:1.3;">
        {_html_lib.escape(headline)}
      </div>
      <div style="font-size:14px; color:#94A3B8; margin-top:6px;">
        {intro_html}
      </div>
    </td></tr>

    <tr><td style="padding:16px 24px 4px;">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"
             style="background:#0B1220; border:1px solid {meta['color']}55;
                    border-left:4px solid {meta['color']}; border-radius:10px;">
        <tr><td style="padding:14px 16px;">
          <div style="font-size:10px; color:#64748B; text-transform:uppercase; letter-spacing:1.5px;">
            Current Status
          </div>
          <div style="font-size:18px; font-weight:700; color:{meta['color']}; margin-top:4px;">
            {meta['emoji']} {meta['label']}
          </div>
          <div style="font-size:11px; color:#64748B; margin-top:6px;">
            {_html_lib.escape(region_name)} · AI confidence {conf_pct}%
          </div>
        </td></tr>
      </table>
    </td></tr>

    <tr><td style="padding:18px 24px 4px;">
      <div style="font-size:10px; color:#64748B; text-transform:uppercase; letter-spacing:1.5px; margin-bottom:6px;">
        AI Reasoning
      </div>
      <div style="font-size:14px; color:#CBD5E1; line-height:1.6;">
        {safe_reason}
      </div>
    </td></tr>

    <tr><td style="padding:24px 24px 8px; text-align:center;">
      <a href="{_html_lib.escape(deep_link)}"
         style="display:inline-block; background:#0891B2; color:#F0FDFF;
                text-decoration:none; font-weight:600; font-size:14px;
                padding:12px 22px; border-radius:8px;
                border:1px solid #22D3EE;">
        {_html_lib.escape(cta_label)}
      </a>
    </td></tr>

    <tr><td style="padding:8px 24px 24px; text-align:center;">
      <div style="font-size:11px; color:#64748B; line-height:1.7;">
        Powered by Copernicus EO + AWS Bedrock (Claude Sonnet)<br>
        You're receiving this because you subscribed to alerts for
        <strong style="color:#94A3B8;">{_html_lib.escape(region_name)}</strong>.<br>
        <a href="{_html_lib.escape(unsub_link)}" style="color:#64748B; text-decoration:underline;">
          Unsubscribe from this region
        </a>
      </div>
    </td></tr>
  </table>
</body>
</html>"""


def render_welcome_email(*, region_name: str, region_id: str, status: str,
                         confidence: float, reasoning: str, recipient_email: str) -> tuple[str, str]:
    """Returns (subject, html). Sent right after a successful subscribe."""
    meta    = _meta(status)
    subject = f"✅ Subscribed: HydroTwin alerts for {region_name}"
    intro = (
        "You'll only hear from us when conditions change "
        "(e.g. when this region escalates from <strong>SAFE</strong> to a watch or warning)."
    )
    html = _render_email_shell(
        region_name=region_name,
        region_id=region_id,
        status=status,
        confidence=confidence,
        reasoning=reasoning,
        headline=f"You're subscribed — {region_name}",
        cta_label="Open the live dashboard →",
        intro_html=intro,
        recipient_email=recipient_email,
    )
    return subject, html


def render_alert_email(*, region_name: str, region_id: str, status: str,
                       prior_status: str | None, confidence: float, reasoning: str,
                       recipient_email: str) -> tuple[str, str]:
    """Returns (subject, html). Sent when cron detects a status transition."""
    meta = _meta(status)
    subject = f"{meta['emoji']} {meta['label']} — {region_name}"
    if prior_status:
        prior_meta = _meta(prior_status)
        intro = (
            f"Status just changed from <strong style=\"color:{prior_meta['color']};\">"
            f"{prior_meta['label']}</strong> to "
            f"<strong style=\"color:{meta['color']};\">{meta['label']}</strong>."
        )
    else:
        intro = "First reading from the satellite + weather feed for this region."
    html = _render_email_shell(
        region_name=region_name,
        region_id=region_id,
        status=status,
        confidence=confidence,
        reasoning=reasoning,
        headline=f"{meta['label']} declared for {region_name}",
        cta_label="Open the live assessment →",
        intro_html=intro,
        recipient_email=recipient_email,
    )
    return subject, html


def _md_to_email_html(s: str) -> str:
    """
    Minimal markdown-to-HTML for the email body. Same subset Claude emits:
    **bold**, `code`, leading "- " bullets, double newlines for paragraphs.
    HTML-escapes the input first to neutralise any raw tags from the model.
    """
    s = _html_lib.escape(s)
    # **bold**
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong style=\"color:#F1F5F9;\">\1</strong>", s, flags=re.DOTALL)
    # `code`
    s = re.sub(
        r"`([^`]+)`",
        r"<code style=\"background:#1E293B; padding:1px 5px; border-radius:4px; "
        r"font-family:Menlo,Monaco,monospace; font-size:12px; color:#67E8F9;\">\1</code>",
        s,
    )
    # bullets: any line starting with "- " or "* " becomes a flex-row li
    lines = []
    in_list = False
    for ln in s.split("\n"):
        if re.match(r"^\s*[-*]\s+", ln):
            if not in_list:
                lines.append("<ul style=\"margin:6px 0; padding-left:20px;\">")
                in_list = True
            lines.append("<li style=\"margin:2px 0;\">" + re.sub(r"^\s*[-*]\s+", "", ln) + "</li>")
        else:
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(ln)
    if in_list:
        lines.append("</ul>")
    s = "\n".join(lines)
    # paragraph breaks on blank lines
    s = re.sub(r"\n{2,}", "</p><p style=\"margin:8px 0;\">", s)
    s = "<p style=\"margin:8px 0;\">" + s + "</p>"
    # Single newlines → <br>
    s = s.replace("\n", "<br>")
    return s


# ─────────────────────────────────────────────────────────────────────────────
#  💬 DISCORD — per-user webhook
# ─────────────────────────────────────────────────────────────────────────────

DISCORD_WEBHOOK_RE = re.compile(
    r"^https://(?:[a-z]+\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$"
)


def is_valid_discord_webhook(url: str) -> bool:
    """Cheap shape check — Discord rejects anything else with a 401, but we'd
    rather refuse it at the API boundary than store junk in DynamoDB."""
    return bool(url) and bool(DISCORD_WEBHOOK_RE.match(url.strip()))


def send_discord_to_webhook(webhook_url: str, *, region_name: str, region_id: str,
                            status: str, confidence: float, reasoning: str,
                            kind: str = "alert") -> bool:
    """
    Send a themed embed to a single user-provided Discord webhook URL.

    `kind` controls the title prefix:
        "welcome" → "✅ Subscribed — <region>"
        "alert"   → "<emoji> HydroTwin Alert — <region>"
    """
    if not is_valid_discord_webhook(webhook_url):
        logger.warning("Refusing to deliver to malformed webhook URL")
        return False

    meta = _meta(status)
    conf = int(round(float(confidence or 0) * 100))
    deep = region_deep_link(region_id)

    if kind == "welcome":
        title       = f"✅ Subscribed — {region_name}"
        description = (
            f"You're now subscribed to HydroTwin alerts for **{region_name}**.\n"
            f"You'll get a ping in this channel whenever the status changes.\n\n"
            f"**Current status:** {meta['emoji']} {meta['label']}\n\n"
            f"{(reasoning or '').strip()[:1500]}"
        )
    else:
        title       = f"{meta['emoji']} HydroTwin Alert — {region_name}"
        description = (reasoning or "").strip()[:2000]

    payload = {
        "username":   "HydroTwin",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/3222/3222800.png",
        "embeds": [{
            "title":       title,
            "description": description,
            "color":       meta["color_int"],
            "url":         deep,
            "fields": [
                {"name": "Status",     "value": meta["label"], "inline": True},
                {"name": "Confidence", "value": f"{conf}%",    "inline": True},
                {"name": "Region",     "value": region_name,   "inline": True},
            ],
            "footer": {"text": "HydroTwin · Copernicus EO + AWS Bedrock"},
        }],
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=5)
        if 200 <= resp.status_code < 300:
            logger.info("Per-user Discord delivered (%s…) — HTTP %s", webhook_url[:40], resp.status_code)
            return True
        logger.error(
            "Per-user Discord rejected (HTTP %s): %s", resp.status_code, resp.text[:200],
        )
        return False
    except requests.RequestException as exc:
        logger.error("Per-user Discord transport failed: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  📱 SMS — AWS SNS publish (sandbox-friendly)
# ─────────────────────────────────────────────────────────────────────────────

# SMS region must match where the destination phone is sandbox-verified. For
# Bulgarian (+359) numbers Ireland (eu-west-1) gives the best delivery rates.
SMS_REGION = os.environ.get("SMS_REGION", "eu-west-1")

_PHONE_RE = re.compile(r"^\+?[1-9]\d{6,14}$")  # E.164-ish


def is_valid_phone(phone: str) -> bool:
    if not phone:
        return False
    return bool(_PHONE_RE.match(phone.strip().replace(" ", "")))


def send_sms(phone: str, message: str) -> bool:
    """
    Stub today: returns False + logs a demo-mode line. Once the AWS lead has
    moved the account out of the SNS SMS sandbox (or verified this number
    inside the sandbox), flip SMS_ENABLED=1 in the Lambda env to enable real
    sends. The frontend already shows the channel as "Coming soon".
    """
    if os.environ.get("SMS_ENABLED", "").strip() not in ("1", "true", "yes"):
        logger.warning(
            "[sms demo-mode] Would have sent to %s — %r (SMS_ENABLED not set)",
            phone, message[:80],
        )
        return False
    if not is_valid_phone(phone):
        logger.error("Refusing to send SMS — phone failed E.164 shape check: %s", phone)
        return False

    try:
        sns = boto3.client("sns", region_name=SMS_REGION)
        sns.publish(
            PhoneNumber=phone.strip(),
            Message=message[:1500],  # SNS hard cap is 1600 bytes
            MessageAttributes={
                "AWS.SNS.SMS.SMSType": {
                    "DataType":    "String",
                    "StringValue": "Transactional",
                },
            },
        )
        logger.info("SMS published via SNS to %s", phone)
        return True
    except Exception as exc:
        logger.error("SMS publish failed: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  ✈️  TELEGRAM — per-user chat_id (stub)
# ─────────────────────────────────────────────────────────────────────────────

def send_telegram_to_user(chat_id: str, message: str) -> bool:
    """
    Stub. Per-user Telegram needs the user to first DM our bot (so it learns
    their chat_id). That UX isn't built yet — frontend shows "Coming soon".
    """
    logger.warning(
        "[telegram demo-mode] Would have sent to chat_id=%s — %r",
        chat_id, message[:80],
    )
    return False


# ─────────────────────────────────────────────────────────────────────────────
#  PLAIN-TEXT FALLBACK FOR EMAIL (good practice for spam scoring)
# ─────────────────────────────────────────────────────────────────────────────

def render_email_text_fallback(*, region_name: str, status: str,
                               reasoning: str, region_id: str) -> str:
    meta = _meta(status)
    return (
        f"HydroTwin — {region_name}\n"
        f"Status: {meta['label']}\n\n"
        f"{(reasoning or '').strip()}\n\n"
        f"Open the live dashboard: {region_deep_link(region_id)}\n"
    )
