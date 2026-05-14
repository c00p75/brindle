"""Telegram webhook — bidirectional AI chat with Brindle Assistant.

Incoming messages from TELEGRAM_CHAT_ID are routed through the same
LLM chat service used by the web UI.  Responses (including tool calls
for bot actions) are sent back as Telegram messages.

Security: every incoming update is validated against TELEGRAM_CHAT_ID.
Any update from a different chat is silently discarded.

Setup (one-time):
  curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
       -d '{"url":"https://<your-domain>/api/telegram/webhook"}'
"""
from __future__ import annotations

import logging
import os
import re

import httpx
from fastapi import APIRouter, Request

from app.chat.service import process_message

log = logging.getLogger("telegram.webhook")

router = APIRouter(prefix="/api/telegram", tags=["telegram"])

# In-memory map of chat_id → session_id so context persists across messages.
# Resets on service restart (fresh session = fresh context, which is fine).
_sessions: dict[str, str] = {}

_TG_API = "https://api.telegram.org"


def _token() -> str | None:
    return os.environ.get("TELEGRAM_BOT_TOKEN")


def _authorized_chat_id() -> str | None:
    return os.environ.get("TELEGRAM_CHAT_ID")


async def _send(chat_id: str, text: str, buttons: list[str] | None = None) -> None:
    token = _token()
    if not token:
        return

    # Telegram Markdown v1 chokes on unescaped special chars — send as plain
    # text but keep single-asterisk bold and backtick code which Telegram
    # handles fine.
    payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}

    if buttons:
        # Each suggestion becomes its own row so it's easy to tap.
        payload["reply_markup"] = {
            "inline_keyboard": [[{"text": b, "callback_data": b}] for b in buttons[:4]]
        }

    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{_TG_API}/bot{token}/sendMessage", json=payload)
        if r.status_code != 200:
            # Retry without parse_mode in case the text contained bad markup.
            payload.pop("parse_mode", None)
            async with httpx.AsyncClient(timeout=10) as c:
                await c.post(f"{_TG_API}/bot{token}/sendMessage", json=payload)
    except Exception as exc:
        log.warning("telegram send error: %s", exc)


async def _typing(chat_id: str) -> None:
    token = _token()
    if not token:
        return
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            await c.post(
                f"{_TG_API}/bot{token}/sendChatAction",
                json={"chat_id": chat_id, "action": "typing"},
            )
    except Exception:
        pass


def _get_admin_user():
    """Return the super-admin User object to act as the Telegram chat actor."""
    from app.auth.service import find_by_email
    from app.core.settings import get_settings
    return find_by_email(get_settings().super_admin_email)


def _format_for_telegram(text: str) -> str:
    """Convert GitHub-flavoured Markdown to Telegram-safe Markdown v1."""
    # **bold** → *bold*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    # ### headings → plain line
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Long horizontal rules
    text = re.sub(r"^[-—─]{4,}$", "──────────────────", text, flags=re.MULTILINE)
    # Trim to Telegram's 4096-char message limit
    if len(text) > 4000:
        text = text[:3990] + "\n\n_…(truncated)_"
    return text.strip()


@router.post("/webhook")
async def telegram_webhook(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        return {"ok": True}

    authorized = _authorized_chat_id()
    if not authorized:
        return {"ok": True}

    # Resolve the incoming message and chat_id from either a regular message
    # or a button callback query.
    message = body.get("message") or body.get("edited_message")
    callback = body.get("callback_query")

    if callback:
        chat_id = str(callback["message"]["chat"]["id"])
        text = callback.get("data", "").strip()
        # Acknowledge the callback so the button stops spinning.
        token = _token()
        if token:
            try:
                async with httpx.AsyncClient(timeout=5) as c:
                    await c.post(
                        f"{_TG_API}/bot{token}/answerCallbackQuery",
                        json={"callback_query_id": callback["id"]},
                    )
            except Exception:
                pass
    elif message:
        chat_id = str(message["chat"]["id"])
        text = message.get("text", "").strip()
    else:
        return {"ok": True}

    # Security gate — ignore anything not from our own chat.
    if chat_id != authorized:
        log.warning("telegram webhook: rejected update from chat_id=%s", chat_id)
        return {"ok": True}

    if not text:
        return {"ok": True}

    # Show typing indicator while we process.
    await _typing(chat_id)

    user = _get_admin_user()
    if user is None:
        await _send(chat_id, "⚠️ Admin user not found — cannot process request.")
        return {"ok": True}

    session_id = _sessions.get(chat_id)

    try:
        reply, session_id, _, _, _, suggestions = await process_message(
            message=text,
            session_id=session_id,
            user=user,
        )
        _sessions[chat_id] = session_id

        # process_message returns "Assistant error: ..." strings instead of raising.
        # Surface those cleanly rather than dumping the raw error object.
        if reply.startswith("Assistant error:"):
            log.warning("telegram webhook: assistant error for chat_id=%s: %s", chat_id, reply)
            await _send(chat_id, "⚠️ I ran into a problem processing that. Please try again.")
        else:
            formatted = _format_for_telegram(reply)
            await _send(chat_id, formatted, buttons=suggestions if suggestions else None)

    except Exception as exc:
        log.exception("telegram webhook: error processing message")
        await _send(chat_id, "⚠️ Something went wrong. Please try again in a moment.")

    return {"ok": True}
