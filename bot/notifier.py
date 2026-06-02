"""Discord / Slack webhook notifier for critical bot failures."""

from __future__ import annotations

import os

import requests

from bot.logger import log

# Read once at import time; empty string or None means notifications are disabled.
_WEBHOOK_URL: str | None = os.environ.get("DISCORD_WEBHOOK_URL")


def send_alert(message: str) -> None:
    """POST a message to the configured Discord/Slack webhook.

    - If DISCORD_WEBHOOK_URL is not set, this is a silent no-op.
    - If the webhook request itself fails, the error is logged but never raised
      (notifications must never crash the bot).
    """
    if not _WEBHOOK_URL:
        log.debug("No DISCORD_WEBHOOK_URL configured — skipping notification")
        return

    payload = {"content": message}

    try:
        resp = requests.post(_WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        log.info("Notification sent: %s", message[:80])
    except requests.RequestException as exc:
        log.warning("Failed to send webhook notification: %s", exc)
