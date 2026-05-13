"""Telegram notification fan-out for alerts.

Configure via env:
  TELEGRAM_BOT_TOKEN — token from @BotFather
  TELEGRAM_CHAT_ID   — recipient chat id (your own DM with the bot, a group, …)
  TELEGRAM_NOTIFY_SEVERITIES — comma-separated, default "warning,critical"

If either env var is missing, send() is a no-op — keeps local dev silent.
Best-effort: HTTP failures are logged and swallowed; an alert never blocks
because Telegram is slow.
"""
from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("alerts.telegram")


def _enabled() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def _allowed_severities() -> set[str]:
    raw = os.environ.get("TELEGRAM_NOTIFY_SEVERITIES", "warning,critical")
    return {s.strip().lower() for s in raw.split(",") if s.strip()}


def _post(token: str, chat_id: str, text: str) -> None:
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=5,
        )
        if r.status_code != 200:
            log.warning("telegram send failed status=%s body=%s", r.status_code, r.text[:200])
    except Exception as e:  # noqa: BLE001
        log.warning("telegram send error: %s", e)


def send(*, severity: str, source: str, message: str, bot_id: str | None = None) -> None:
    if not _enabled():
        return
    if severity.lower() not in _allowed_severities():
        return
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    icon = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(severity.lower(), "•")
    bot_line = f"\nBot: `{bot_id}`" if bot_id else ""
    text = f"{icon} *{severity.upper()}* — {source}{bot_line}\n{message}"
    _post(token, chat_id, text)


def send_raw(text: str) -> None:
    """Send arbitrary Markdown text — used for scheduled reports."""
    if not _enabled():
        return
    _post(os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"], text)
