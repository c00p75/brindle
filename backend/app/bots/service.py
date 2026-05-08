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
        allocation=row.allocation,
        created_at_ms=row.created_at_ms,
        updated_at_ms=row.updated_at_ms,
        starting_balance=row.starting_balance,
        starting_balance_currency=row.starting_balance_currency,
        starting_balance_at_ms=row.starting_balance_at_ms,
    )


def create(*, name: str, owner_email: str, actor_email: str, actor_role: str, allocation: float | None = None) -> Bot:
    bot_id = new_id("bot")
    now = now_epoch_ms()
    with session_scope() as s:
        row = BotRow(
            id=bot_id,
            name=name,
            owner_email=owner_email,
            state=BotState.DRAFT.value,
            active_config_version=None,
            allocation=allocation,
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
        metadata={"name": name, "allocation": allocation},
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


def get_starting_balance(bot_id: str) -> tuple[float | None, str | None, int | None]:
    """Return (amount, currency, ts_ms) — None tuple if never snapshotted."""
    with session_scope() as s:
        row = s.get(BotRow, bot_id)
        if row is None:
            return (None, None, None)
        return (row.starting_balance, row.starting_balance_currency, row.starting_balance_at_ms)


def snapshot_starting_balance(bot_id: str, amount: float, currency: str) -> bool:
    """Store the first observed balance as the bot's baseline. No-op if already set.

    Returns True if a new snapshot was recorded, False if one already existed.
    """
    with session_scope() as s:
        row = s.get(BotRow, bot_id)
        if row is None:
            return False
        if row.starting_balance is not None:
            return False
        row.starting_balance = amount
        row.starting_balance_currency = currency
        row.starting_balance_at_ms = now_epoch_ms()
        s.flush()
        return True


def reset_starting_balance(bot_id: str) -> bool:
    """Clear the snapshot so the next balance poll captures a new baseline.
    Also clears historical balance snapshots to reset drawdown tracking.
    """
    with session_scope() as s:
        row = s.get(BotRow, bot_id)
        if row is None:
            return False
        row.starting_balance = None
        row.starting_balance_currency = None
        row.starting_balance_at_ms = None
        
        # Clear snapshots to reset RiskEngine HWM
        from app.db.orm import BalanceSnapshotRow
        from sqlalchemy import delete
        s.execute(delete(BalanceSnapshotRow).where(BalanceSnapshotRow.bot_id == bot_id))
        
        s.flush()
        return True


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
    cv = active_version(bot_id)
    if cv is None:
        raise ValueError("cannot start: no applied config")
    
    current = get(bot_id)
    if current is None:
        raise ValueError("bot not found")

    # Check for existing drawdown breach in history before allowing start.
    # Prevents "zombie" pauses where a bot starts and immediately auto-pauses.
    from app.execution import balance_history
    history = balance_history.history(bot_id=bot_id, max_points=1000)
    if history:
        hwm = max(float(h["balance"]) for h in history)
        if current.allocation:
            from app.execution import contracts as contracts_svc
            pnl = contracts_svc.summary(bot_id)["realized_pnl"]
            equity = current.allocation + pnl
        else:
            # For non-allocation bots, we use the last recorded balance
            equity = history[-1]["balance"]
            
        if hwm > 0:
            dd_pct = (hwm - equity) / hwm * 100
            limit = cv.config.risk.max_drawdown_pct
            if dd_pct >= limit:
                raise ValueError(
                    f"cannot start: bot is in drawdown ({dd_pct:.1f}% >= {limit}% limit). "
                    "Reset the baseline or adjust risk limits to continue."
                )

    # Ensure state reflects an applied config (DRAFT → READY) before transitioning.
    refreshed = refresh_state_from_config(current)
    
    # If starting fresh (not resuming from PAUSED), reset the baseline so 
    # drawdown/PnL tracking starts from today's balance.
    if current.state != BotState.PAUSED:
        reset_starting_balance(bot_id)

    bot = _set_state(
        bot_id,
        BotState.RUNNING,
        {BotState.READY, BotState.PAUSED, BotState.VALIDATED, BotState.DRAFT, BotState.HALTED}
        if refreshed.active_config_version is not None
        else {BotState.READY, BotState.PAUSED, BotState.VALIDATED, BotState.HALTED},
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
def update(bot_id: str, *, name: str | None = None, allocation: float | None = None, 
           actor_email: str, actor_role: str) -> Bot:
    with session_scope() as s:
        row = s.get(BotRow, bot_id)
        if row is None:
            raise ValueError("bot not found")
            
        old_allocation = row.allocation
        if name is not None:
            row.name = name
        if allocation is not None:
            row.allocation = allocation
            
        # If allocation changed, automatically reset baseline and history to 
        # avoid false drawdown rejections.
        if allocation != old_allocation:
            reset_starting_balance(bot_id)
            
        row.updated_at_ms = now_epoch_ms()
        s.flush()
        return _row_to_bot(row)
