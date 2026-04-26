# HydroTwin — Notifications & Email Subscription Handoff

> **STATUS: ACTIVE — core bugs fixed; SES email delivery implemented; unsubscribe flow added.**
> **Owner:** @hazbik
> **Last updated:** 2026-04-26

This document describes the current state of the email subscription feature and the Telegram/Discord notification system as of April 2026. It covers how each piece works, where the data lives, known bugs, and what still needs to be built.

---

## 1. Email Subscription — How It Works Today

### 1.1 User Flow

1. User clicks a region on the map → `AlertPanel` opens.
2. User clicks **"Subscribe to Push Alerts"** → email input form appears.
3. User enters their email and clicks **Confirm**.
4. Frontend sends `POST /subscribe` with `{ email, region_id }`.
5. Backend validates and writes the record to DynamoDB.
6. UI shows success or error toast.

### 1.2 What the Subscribe Endpoint Actually Does

| Step | Action | File |
|------|--------|------|
| Parse body | Extract `email` + `region_id` from POST JSON | `subscribe_handler.py:99–107` |
| Validate email | Regex `^[^@\s]+@[^@\s]+\.[^@\s]+$` | `subscribe_handler.py:60, 109` |
| Validate region | Check against `KNOWN_REGIONS` whitelist | `subscribe_handler.py:112` |
| Write to DynamoDB | `put_item` with conditional expression — no overwrite | `subscribe_handler.py:127–132` |
| Duplicate check | Returns `409` if `(email, region_id)` pair already exists | `subscribe_handler.py:136–142` |
| Demo fallback | If DynamoDB is unavailable → returns `201` with `demo_mode: true` | `subscribe_handler.py:144–161` |

### 1.3 Where Emails Are Stored

- **Database:** AWS DynamoDB
- **Table:** `HydroTwinSubscriptions` (env var `SUBSCRIPTIONS_TABLE`)
- **Schema:**

| Attribute | Type | Role |
|-----------|------|------|
| `email` | String | Primary Key (PK) |
| `region_id` | String | Sort Key (SK) |
| `created_at` | String (ISO-8601) | Metadata |

One user can subscribe to multiple regions. The same `(email, region_id)` pair can exist only once.

### 1.4 CRITICAL: No Emails Are Ever Sent

> **The system stores subscriptions in DynamoDB but has zero email delivery logic.**

There is no SES integration, no SendGrid, no SMTP — nothing. The `HydroTwinSubscriptions` table currently collects addresses that are never read back for sending. If the goal is to send alert emails to subscribers, this layer does not exist yet and must be built from scratch.

---

## 2. Known Bugs

### Bug 1 — Wrong error message on duplicate subscription

**Symptom:** User submits a valid email like `dimtrios.v.2002@gmail.com` and sees:
```
That email was rejected — please double-check it.
```

**Root cause:** The frontend maps **any** non-200/201 response to the generic "rejected" message:

```javascript
// AlertPanel.jsx:159-162
if (res.status === 400) {
  setToast({ kind: 'error', msg: 'That email was rejected — please double-check it.' });
} else if (!res.ok) {
  setToast({ kind: 'error', msg: `Subscription failed (${res.status}). Please try again.` });
}
```

When the email was already subscribed, the backend returns `409 Conflict` — which falls into the `else if (!res.ok)` branch and shows a generic message, not `400`. However, the *real* cause is likely the `400` branch being shown when the backend can't reach DynamoDB at all (demo mode returns `201`, but a real DynamoDB error for an unknown region returns `400`).

**Fix required:** Add a dedicated `409` handler in `AlertPanel.jsx`:

```javascript
if (res.status === 409) {
  setToast({ kind: 'error', msg: 'You are already subscribed to alerts for this region.' });
} else if (res.status === 400) {
  setToast({ kind: 'error', msg: 'That email was rejected — please double-check it.' });
} else if (!res.ok) {
  setToast({ kind: 'error', msg: `Subscription failed (${res.status}). Please try again.` });
}
```

**File:** `frontend/src/components/AlertPanel.jsx:159`

---

### Bug 2 — Notifications fire on every map click

**Symptom:** Clicking the same region 5 times sends 5 Discord/Telegram messages.

**Root cause:** The click path in `lambda_handler.py` fires the webhook unconditionally on every non-SAFE status:

```python
# lambda_handler.py:420-423
if assessment["status"] != "SAFE":
    logger.info("Non-SAFE status detected (%s) — firing webhook.", assessment["status"])
    trigger_webhook(assessment)
```

The scheduled cron (`cron_handler.py`) does this correctly — it only fires on **status transitions** using `_should_fire_webhook(prior, new_status)`. The click path has no such deduplication.

**Fix required:** Either remove webhook firing from the click path entirely (rely on cron only), or add a DynamoDB status snapshot check before firing, same as the cron does.

---

## 3. Telegram Notifications

### 3.1 How It Works

Telegram uses the Bot API to send an HTML-formatted message to a chat.

| Detail | Value |
|--------|-------|
| API endpoint | `https://api.telegram.org/bot{token}/sendMessage` |
| Parse mode | `HTML` |
| Trigger | Non-SAFE status on map click OR status transition on cron |
| Format | Bold status + region + confidence + short reasoning excerpt |

**Env vars required:**

```
TELEGRAM_BOT_TOKEN=<your bot token from @BotFather>
TELEGRAM_CHAT_ID=<chat or channel ID where alerts go>
```

**Code:** `backend/lambda_handler.py:305–317` (`_send_telegram`)

### 3.2 Message Format

```
🔴 FLOOD_WARNING — Pleven Oblast
Confidence: 82%
<reasoning excerpt, first 600 chars>
```

Markdown in the AI reasoning is converted to HTML before sending (`_md_to_html()`, `lambda_handler.py:281–302`).

### 3.3 When It Fires (current — broken)

- **Click path:** Fires on **every** click where status ≠ SAFE → notification spam
- **Cron path:** Fires on first non-SAFE detection OR status change → correct behaviour

---

## 4. Discord Notifications

### 4.1 How It Works

Discord uses incoming webhooks. Multiple webhook URLs are supported (comma-separated).

| Detail | Value |
|--------|-------|
| Delivery | HTTP POST to Discord webhook URL |
| Format | Rich embed with title, description, fields, footer |
| Trigger | Same as Telegram (click OR cron) |
| Multiple channels | Comma-separate URLs in `DISCORD_WEBHOOK_URL` |

**Env vars required:**

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/<id>/<token>
# Multiple channels:
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/AAA/BBB,https://discord.com/api/webhooks/CCC/DDD
```

**Code:** `backend/lambda_handler.py:260–278` (`_send_discord`)

### 4.2 Embed Format

```
Title:       🔴 FLOOD_WARNING
Description: <reasoning excerpt>
Fields:      Status | Confidence | Region
Footer:      HydroTwin · AWS Bedrock
Color:       Red (danger) / Orange (warning) / Yellow (watch) / Green (safe)
```

### 4.3 Failure Handling

Both Discord and Telegram failures are **non-fatal** — a failed webhook never blocks the Lambda response or breaks the frontend. Errors are logged to CloudWatch only.

---

## 5. Notification Trigger Logic — Cron vs Click

| Path | File | When it fires | Problem |
|------|------|---------------|---------|
| User clicks region | `lambda_handler.py:420` | Every non-SAFE click | Spams on repeat clicks |
| Cron (every 30 min) | `cron_handler.py:115–179` | Status transitions only | Correct — no spam |

The cron uses `_should_fire_webhook(prior_status, new_status)`:

```python
# cron_handler.py:115-128
# Fires when:
#   - First non-SAFE detection (no prior record)
#   - Escalation: SAFE → non-SAFE
#   - Recovery: non-SAFE → SAFE
# Does NOT fire:
#   - Same status as before (e.g. FLOOD_WARNING → FLOOD_WARNING)
#   - Municipality-level changes (oblast-level only)
```

---

## 6. Required Infrastructure (not yet built)

### 6.1 Email Delivery (SES or SendGrid)

To make the subscription actually do something, a delivery layer is needed:

```
Option A — AWS SES (recommended, already in AWS ecosystem)
  1. Verify sender domain in SES
  2. Build a new Lambda: alert_emailer.py
  3. Trigger: EventBridge rule that listens for cron status transitions
  4. Reads HydroTwinSubscriptions (scan by region_id that transitioned)
  5. Sends templated HTML email via SES

Option B — SendGrid
  1. Add SENDGRID_API_KEY to Lambda env vars
  2. Same trigger logic, use sendgrid Python SDK
  3. No domain verification hassle for MVP
```

### 6.2 Unsubscribe Flow

There is no unsubscribe mechanism. Minimum needed:
- `DELETE /subscribe` endpoint in `subscribe_handler.py`
- Unsubscribe link in every email (legally required in most jurisdictions)

---

## 7. Environment Variables Summary

| Variable | Used by | Required for |
|----------|---------|--------------|
| `SUBSCRIPTIONS_TABLE` | `subscribe_handler.py` | Storing email subscriptions |
| `DISCORD_WEBHOOK_URL` | `lambda_handler.py` | Discord alerts |
| `TELEGRAM_BOT_TOKEN` | `lambda_handler.py` | Telegram alerts |
| `TELEGRAM_CHAT_ID` | `lambda_handler.py` | Telegram alerts |
| `AWS_REGION` | both handlers | DynamoDB region |

---

## 8. Pending Tasks

- [x] **Fix Bug 1** — `AlertPanel.jsx:159` now shows "Already subscribed" on 409, not "email rejected"
- [x] **Fix Bug 2** — Click-path webhook removed from `lambda_handler.py`; cron fires on transitions only
- [x] **Build email delivery** — `trigger_email_alerts()` in `lambda_handler.py`; called by `cron_handler.py` on transitions; uses SES + HTML template with unsubscribe link
- [x] **Build unsubscribe** — `DELETE /subscribe` + `GET /unsubscribe?email=&region_id=` in `subscribe_handler.py`; routed in `local_server.py`
- [ ] **Configure SES in AWS** — verify sender domain, set `SES_SENDER_EMAIL` and `UNSUBSCRIBE_BASE_URL` Lambda env vars
- [ ] **Verify DynamoDB table exists** in production — confirm `HydroTwinSubscriptions` is provisioned (PK=email, SK=region_id)
- [ ] **Add GSI on region_id** in `HydroTwinSubscriptions` — current scan + filter works for MVP but will be slow at scale
- [ ] **Email verification flow** — optional: send confirmation email before activating subscription
