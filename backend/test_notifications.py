"""
test_notifications.py — Smoke-test Discord + Telegram webhooks directly.

Run from the backend/ directory:
    python test_notifications.py
"""

import os
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.local", override=True)

# Re-import after env is loaded so the module picks up the values
from lambda_handler import trigger_webhook

FAKE_ALERT = {
    "region_id":  "danube-basin",
    "status":     "FLOOD_WATCH",
    "confidence": 0.82,
    "reasoning":  (
        "[TEST] River levels have risen 0.8 m above seasonal baseline. "
        "Soil saturation at 89 %. Additional 35 mm precipitation expected "
        "within 24 hours. FLOOD_WATCH thresholds breached."
    ),
}

if __name__ == "__main__":
    discord_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    tg_token    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat     = os.environ.get("TELEGRAM_CHAT_ID", "")

    print(f"Discord  : {'SET — ' + discord_url[:40] + '...' if discord_url else 'NOT SET'}")
    print(f"Telegram : {'SET' if tg_token and tg_chat else 'NOT SET'} "
          f"(token={'yes' if tg_token else 'no'}, chat_id={'yes' if tg_chat else 'no'})")
    print()
    print("Firing test notifications…")
    trigger_webhook(FAKE_ALERT)
    print("Done — check Discord and Telegram.")
