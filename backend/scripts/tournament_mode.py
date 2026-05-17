"""Configure every tournament bot to "run until depleted" mode, then start it.

Risk settings applied:
  max_drawdown_pct    = 100  — only auto-pauses when allocation is fully gone
  max_daily_loss      = allocation (default $100) — same effective threshold
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
NAME_FILTER = "tournament"


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
        if validated.validation_warnings:
            for w in validated.validation_warnings:
                print(f"  ⚠  {w}")
        config_service.apply(
            actor_email=ACTOR,
            actor_role=ROLE,
            bot_id=bot_id,
            version=draft.version,
            typed_confirmation="APPLY RISK CHANGE",
        )
        print(f"  ✓  Tournament config applied (v{draft.version})")
    except Exception as e:
        print(f"  ❌ Config update failed: {e}")
        return

    # Halt cleanly before restarting to clear any PAUSED/RUNNING state.
    bot = bot_service.get(bot_id)
    if bot and bot.state in {BotState.PAUSED, BotState.RUNNING}:
        try:
            bot_service.stop(bot_id, actor_email=ACTOR, actor_role=ROLE)
            await get_runtime_manager().stop(bot_id)
        except Exception as e:
            print(f"  ⚠  Stop failed (may already be halted): {e}")

    # Clear baseline so PnL and drawdown tracking start fresh from this run.
    bot_service.reset_starting_balance(bot_id)

    try:
        started = bot_service.start(bot_id, actor_email=ACTOR, actor_role=ROLE)
        await get_runtime_manager().start(started)
        print(f"  🚀 Started — will trade until ${allocation:.0f} allocation depleted")
    except Exception as e:
        print(f"  ❌ Start failed: {e}")


async def main() -> None:
    all_bots = bot_service.list_bots()
    tournament_bots = [b for b in all_bots if NAME_FILTER in b.name.lower()]

    if not tournament_bots:
        print(f"No bots found with '{NAME_FILTER}' in their name.")
        return

    print(f"Found {len(tournament_bots)} tournament bot(s):\n")
    for b in tournament_bots:
        alloc = b.allocation or 100.0
        print(f"  {b.name:<35}  state={b.state.value:<8}  allocation=${alloc:.0f}")

    print()
    for b in tournament_bots:
        await configure_and_start(b.id, b.name, allocation=b.allocation or 100.0)

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
