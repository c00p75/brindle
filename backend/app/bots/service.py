from __future__ import annotations

from sqlalchemy import select

from app.audit.service import record as audit
from app.bots.models import Bot, BotState
from app.configs.models import ConfigStatus
from app.configs.service import active_version, list_versions
from app.core.ids import new_id
from app.core.time import now_epoch_ms
from app.db.engine import session_scope
from app.db.orm import BotRow


def _row_to_bot(row: BotRow) -> Bot:
    return Bot(
        id=row.id,
        name=row.name,
        owner_email=row.owner_email,
        state=BotState(row.state),
        active_config_version=row.active_config_version,
        created_at_ms=row.created_at_ms,
        updated_at_ms=row.updated_at_ms,
    )


def create(*, name: str, owner_email: str, actor_email: str, actor_role: str) -> Bot:
    bot_id = new_id("bot")
    now = now_epoch_ms()
    with session_scope() as s:
        row = BotRow(
            id=bot_id,
            name=name,
            owner_email=owner_email,
            state=BotState.DRAFT.value,
            active_config_version=None,
            created_at_ms=now,
            updated_at_ms=now,
        )
        s.add(row)
        s.flush()
        bot = _row_to_bot(row)
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
    with session_scope() as s:
        row = s.get(BotRow, bot_id)
        return _row_to_bot(row) if row else None


def list_bots() -> list[Bot]:
    with session_scope() as s:
        rows = (
            s.execute(select(BotRow).order_by(BotRow.created_at_ms.desc()))
            .scalars()
            .all()
        )
        return [_row_to_bot(r) for r in rows]


def _set_state(bot_id: str, state: BotState, allowed_from: set[BotState]) -> Bot:
    with session_scope() as s:
        row = s.get(BotRow, bot_id)
        if row is None:
            raise ValueError("bot not found")
        current = BotState(row.state)
        if current not in allowed_from:
            raise ValueError(f"cannot go from {current.value} to {state.value}")
        row.state = state.value
        row.updated_at_ms = now_epoch_ms()
        s.flush()
        return _row_to_bot(row)


def refresh_state_from_config(bot: Bot) -> Bot:
    """Reflect config lifecycle into bot state for unstarted bots."""
    if bot.state in {
        BotState.RUNNING,
        BotState.PAUSED,
        BotState.HALTED,
        BotState.ERROR,
        BotState.ARCHIVED,
    }:
        return bot

    active = active_version(bot.id)
    new_state: BotState | None = None
    new_active_version: int | None = bot.active_config_version

    if active is not None:
        new_active_version = active.version
        new_state = BotState.READY
    else:
        versions = list_versions(bot.id)
        if any(v.status == ConfigStatus.VALIDATED for v in versions):
            new_state = BotState.VALIDATED

    if new_state is None and new_active_version == bot.active_config_version:
        return bot

    with session_scope() as s:
        row = s.get(BotRow, bot.id)
        if row is None:
            return bot
        if new_state is not None:
            row.state = new_state.value
        if new_active_version is not None:
            row.active_config_version = new_active_version
        row.updated_at_ms = now_epoch_ms()
        s.flush()
        return _row_to_bot(row)


def start(bot_id: str, actor_email: str, actor_role: str) -> Bot:
    if active_version(bot_id) is None:
        raise ValueError("cannot start: no applied config")
    bot = _set_state(
        bot_id, BotState.RUNNING, {BotState.READY, BotState.PAUSED, BotState.VALIDATED}
    )
    audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action="bot.start",
        resource_type="bot",
        resource_id=bot.id,
    )
    return bot


def pause(bot_id: str, actor_email: str, actor_role: str) -> Bot:
    bot = _set_state(bot_id, BotState.PAUSED, {BotState.RUNNING})
    audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action="bot.pause",
        resource_type="bot",
        resource_id=bot.id,
    )
    return bot


def stop(bot_id: str, actor_email: str, actor_role: str) -> Bot:
    bot = _set_state(
        bot_id, BotState.HALTED, {BotState.RUNNING, BotState.PAUSED, BotState.ERROR}
    )
    audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action="bot.stop",
        resource_type="bot",
        resource_id=bot.id,
    )
    return bot


def archive(bot_id: str, actor_email: str, actor_role: str) -> Bot:
    allowed = set(BotState) - {BotState.RUNNING}
    bot = _set_state(bot_id, BotState.ARCHIVED, allowed)
    audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action="bot.archive",
        resource_type="bot",
        resource_id=bot.id,
    )
    return bot
