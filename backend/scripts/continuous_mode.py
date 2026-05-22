"""Switch all Tournament bots to continuous (never-stop) mode for data gathering.

Targets every bot whose name contains "Tournament" (case-insensitive) that is
not archived.

What changes:
  allocation          → 100 000  (large virtual budget; stakes stay ≤$5 via
                                   max_stake — allocation just controls sizing mode)
  max_drawdown_pct    = 100      (only fires if full $100k is lost — never)
  max_daily_loss      = 100 000  (disabled in practice)
  max_consecutive_los = 0        (streak circuit breaker off)
  max_position_notional = 5 000  (generous ceiling)
  max_total_exposure    = 5 000
  max_open_orders       = 5
  risk_per_trade_pct    = 1.0    (1% of effective balance)
  max_stake             = 5.0    (hard $5/trade cap so sizing stays small)

Lifecycle per bot:
  1. Update allocation field in the DB.
  2. Create draft → validate → apply new risk config.
  3. Stop if currently running, reset baseline, start fresh.

Run from the backend/ directory:
    python scripts/continuous_mode.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.append(os.getcwd())

from dotenv import load_dotenv
load_dotenv()

from app.bots import service as bot_service
from app.bots.models import BotConfig, BotState, StrategyConfig
from app.configs import service as config_service
from app.core.time import now_epoch_ms
from app.db.engine import session_scope
from app.db.orm import BotRow
from app.risk.models import RiskLimits
from app.runtime.manager import get_runtime_manager

ACTOR = "system/continuous-mode"
ROLE = "admin"
LARGE_ALLOCATION = 100_000.0

_DOWN = {BotState.PAUSED, BotState.HALTED, BotState.READY}
_UP = {BotState.RUNNING}

CONTINUOUS_RISK = RiskLimits(
    max_position_notional=5_000.0,
    max_total_exposure=5_000.0,
    max_daily_loss=LARGE_ALLOCATION,
    max_drawdown_pct=100.0,
    max_open_orders=5,
    max_consecutive_losses=0,
    risk_per_trade_pct=1.0,
    max_stake=5.0,
)


def _set_allocation(bot_id: str, allocation: float) -> None:
    """Write allocation directly — bot_service.update() skips None values."""
    with session_scope() as s:
        row = s.get(BotRow, bot_id)
        if row is None:
            raise ValueError(f"bot {bot_id} not found")
        row.allocation = allocation
        row.updated_at_ms = now_epoch_ms()
        s.flush()


async def apply_continuous(bot_id: str, bot_name: str) -> None:
    print(f"\n--- {bot_name} ({bot_id}) ---")

    # 1. Set large allocation so the depletion guard never fires
    _set_allocation(bot_id, LARGE_ALLOCATION)
    print(f"  allocation → ${LARGE_ALLOCATION:,.0f}")

    # 2. Update risk config
    av = config_service.active_version(bot_id)
    if not av:
        print("  ⚠  No active config — skipping risk update")
    else:
        cfg = av.config
        cfg.risk = CONTINUOUS_RISK
        try:
            draft = config_service.create_draft(actor_email=ACTOR, actor_role=ROLE, config=cfg)
            validated = config_service.validate(
                actor_email=ACTOR, actor_role=ROLE, bot_id=bot_id, version=draft.version
            )
            if validated.validation_errors:
                print(f"  ❌ Validation failed: {validated.validation_errors}")
                return
            for w in validated.validation_warnings:
                print(f"  ⚠  {w}")
            config_service.apply(
                actor_email=ACTOR,
                actor_role=ROLE,
                bot_id=bot_id,
                version=draft.version,
                typed_confirmation="APPLY RISK CHANGE",
            )
            print(f"  ✓  Risk config applied (v{draft.version}): continuous mode")
        except Exception as e:
            print(f"  ❌ Config update failed: {e}")
            return

    # 3. Stop if running, reset baseline, start fresh
    bot = bot_service.get(bot_id)
    if bot and bot.state in (_UP | _DOWN):
        if bot.state in _UP or bot.state in _DOWN:
            try:
                bot_service.stop(bot_id, actor_email=ACTOR, actor_role=ROLE)
                await get_runtime_manager().stop(bot_id)
            except Exception as e:
                print(f"  ⚠  Stop skipped (may already be down): {e}")

    bot_service.reset_starting_balance(bot_id)

    try:
        started = bot_service.start(bot_id, actor_email=ACTOR, actor_role=ROLE)
        await get_runtime_manager().start(started)
        print("  🚀 Started — continuous trading")
    except Exception as e:
        print(f"  ❌ Start failed: {e}")


async def main() -> None:
    all_bots = bot_service.list_bots()
    skip = {BotState.ARCHIVED, BotState.DRAFT}
    targets = [
        b for b in all_bots
        if b.state not in skip and "tournament" in b.name.lower()
    ]

    if not targets:
        print("No Tournament bots found (non-archived).")
        return

    print(f"Switching {len(targets)} Tournament bot(s) to continuous mode:\n")
    for b in targets:
        print(f"  {b.name:<50}  state={b.state.value:<8}  alloc=${b.allocation or 0:.0f}")

    for b in targets:
        await apply_continuous(b.id, b.name)

    print("\nDone — all Tournament bots are now in continuous trading mode.")
    print(f"Allocation set to ${LARGE_ALLOCATION:,.0f} (virtual; max $5/trade via max_stake).")


if __name__ == "__main__":
    asyncio.run(main())
