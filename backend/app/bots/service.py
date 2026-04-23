from __future__ import annotations

from app.audit.service import record as audit
from app.bots.models import Bot, BotState
from app.configs.models import ConfigStatus
from app.configs.service import active_version, list_versions
from app.core.ids import new_id
from app.core.time import now_epoch_ms
from app.db.store import get_store

TABLE = "bots"


def create(*, name: str, owner_email: str, actor_email: str, actor_role: str) -> Bot:
    bot = Bot(
        id=new_id("bot"),
        name=name,
        owner_email=owner_email,
        state=BotState.DRAFT,
        created_at_ms=now_epoch_ms(),
        updated_at_ms=now_epoch_ms(),
    )
    get_store().put(TABLE, bot.id, bot.model_dump())
    audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action="bot.create",
        resource_type="bot",
        resource_id=bot.id,
        metadata={"name": name},
    )
    return bot


def get(bot_id: str) -> Bot | None:
    raw = get_store().get(TABLE, bot_id)
    return Bot(**raw) if raw else None


def list_bots() -> list[Bot]:
    return sorted(
        [Bot(**r) for r in get_store().list(TABLE)],
        key=lambda b: b.created_at_ms,
        reverse=True,
    )


def _save(bot: Bot) -> Bot:
    bot.updated_at_ms = now_epoch_ms()
    get_store().put(TABLE, bot.id, bot.model_dump())
    return bot


def _transition(bot: Bot, to: BotState, allowed_from: set[BotState]) -> Bot:
    if bot.state not in allowed_from:
        raise ValueError(f"cannot go from {bot.state} to {to}")
    bot.state = to
    return _save(bot)


def refresh_state_from_config(bot: Bot) -> Bot:
    """Reflect config lifecycle into bot state for unstarted bots."""
    if bot.state in {BotState.RUNNING, BotState.PAUSED, BotState.HALTED, BotState.ERROR, BotState.ARCHIVED}:
        return bot
    active = active_version(bot.id)
    if active is not None:
        bot.active_config_version = active.version
        bot.state = BotState.READY
    else:
        versions = list_versions(bot.id)
        if any(v.status == ConfigStatus.VALIDATED for v in versions):
            bot.state = BotState.VALIDATED
    return _save(bot)


def start(bot_id: str, actor_email: str, actor_role: str) -> Bot:
    bot = get(bot_id)
    if bot is None:
        raise ValueError("bot not found")
    if active_version(bot.id) is None:
        raise ValueError("cannot start: no applied config")
    bot = _transition(bot, BotState.RUNNING, {BotState.READY, BotState.PAUSED, BotState.VALIDATED})
    audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action="bot.start",
        resource_type="bot",
        resource_id=bot.id,
    )
    return bot


def pause(bot_id: str, actor_email: str, actor_role: str) -> Bot:
    bot = get(bot_id)
    if bot is None:
        raise ValueError("bot not found")
    bot = _transition(bot, BotState.PAUSED, {BotState.RUNNING})
    audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action="bot.pause",
        resource_type="bot",
        resource_id=bot.id,
    )
    return bot


def stop(bot_id: str, actor_email: str, actor_role: str) -> Bot:
    bot = get(bot_id)
    if bot is None:
        raise ValueError("bot not found")
    bot = _transition(bot, BotState.HALTED, {BotState.RUNNING, BotState.PAUSED, BotState.ERROR})
    audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action="bot.stop",
        resource_type="bot",
        resource_id=bot.id,
    )
    return bot


def archive(bot_id: str, actor_email: str, actor_role: str) -> Bot:
    bot = get(bot_id)
    if bot is None:
        raise ValueError("bot not found")
    bot = _transition(bot, BotState.ARCHIVED, set(BotState) - {BotState.RUNNING})
    audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action="bot.archive",
        resource_type="bot",
        resource_id=bot.id,
    )
    return bot
