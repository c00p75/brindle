"""Configure every non-running allocation bot to "run until depleted" mode, then start it.

Targets all bots in PAUSED, HALTED, or READY state that have an allocation set.
Skips bots with no allocation (no defined budget to deplete).

Risk settings applied:
  max_drawdown_pct    = 100  — only auto-pauses when allocation is fully gone
  max_daily_loss      = allocation — same effective threshold
  max_consecutive_losses = 0 — streak-based circuit breaker disabled

The allocation-depletion guard in the runtime (_allocation_depleted) is the
sole stopping condition, so each bot trades freely until it hits $0 equity.
"""
from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

from app.bots import service as bot_service
from app.bots.models import BotState
from app.configs import service as config_service
from app.runtime.manager import get_runtime_manager

ACTOR = "system/tournament-setup"
ROLE = "admin"
_DOWN = {BotState.PAUSED, BotState.HALTED, BotState.READY}


async def configure_and_start(bot_id: str, bot_name: str, allocation: float) -> None:
    print(f"\n--- {bot_name} ({bot_id}) ---")

    av = config_service.active_version(bot_id)
    if not av:
        print("  ⚠  No active config — skipping")
        return

    cfg = av.config
    cfg.risk.max_drawdown_pct = 100.0
    cfg.risk.max_daily_loss = allocation
    cfg.risk.max_consecutive_losses = 0

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
        print(f"  ✓  Config applied (v{draft.version}): drawdown=100%, daily_loss=${allocation:.0f}, streak_limit=off")
    except Exception as e:
        print(f"  ❌ Config update failed: {e}")
        return

    # Halt first to clear any PAUSED state before restarting.
    bot = bot_service.get(bot_id)
    if bot and bot.state in {BotState.PAUSED, BotState.RUNNING}:
        try:
            bot_service.stop(bot_id, actor_email=ACTOR, actor_role=ROLE)
            await get_runtime_manager().stop(bot_id)
        except Exception as e:
            print(f"  ⚠  Stop failed (may already be halted): {e}")

    # Clear baseline so PnL and drawdown tracking start fresh.
    bot_service.reset_starting_balance(bot_id)

    try:
        started = bot_service.start(bot_id, actor_email=ACTOR, actor_role=ROLE)
        await get_runtime_manager().start(started)
        print(f"  🚀 Started — trading until ${allocation:.0f} depleted")
    except Exception as e:
        print(f"  ❌ Start failed: {e}")


async def main() -> None:
    all_bots = bot_service.list_bots()
    down = [b for b in all_bots if b.state in _DOWN]

    if not down:
        print("No bots in PAUSED / HALTED / READY state — nothing to do.")
        return

    no_alloc = [b for b in down if not b.allocation]
    targets  = [b for b in down if b.allocation]

    if no_alloc:
        print(f"Skipping {len(no_alloc)} bot(s) with no allocation (no budget to deplete):")
        for b in no_alloc:
            print(f"  - {b.name} ({b.id})  state={b.state.value}")
        print()

    if not targets:
        print("No allocation bots to start.")
        return

    print(f"Configuring and starting {len(targets)} bot(s):\n")
    for b in targets:
        print(f"  {b.name:<40}  state={b.state.value:<8}  allocation=${b.allocation:.0f}")

    for b in targets:
        await configure_and_start(b.id, b.name, allocation=b.allocation)

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
