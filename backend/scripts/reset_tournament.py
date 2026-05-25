"""Archive all existing Tournament bots and spin up fresh replacements.

Existing bots (any name containing "tournament", case-insensitive) are
stopped if running, then archived.  Fresh bots are created with continuous
mode config baked in from the start: $100k virtual allocation, $1 max stake.

Run from the backend/ directory:
    python scripts/reset_tournament.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.append(os.getcwd())

from dotenv import load_dotenv
load_dotenv()

from app.adapters.brokers.base import BrokerConfig
from app.bots import service as bot_service
from app.bots.models import BotConfig, BotState, StrategyConfig
from app.configs import service as config_service
from app.core.time import now_epoch_ms
from app.db.engine import session_scope
from app.db.orm import BotRow
from app.risk.models import RiskLimits
from app.runtime.manager import get_runtime_manager

ACTOR = "system/reset-tournament"
ROLE = "admin"
ALLOCATION = 100_000.0

ACCOUNT_ID = os.environ.get("TARGET_ACCOUNT_ID", "DOT91022417")
BROKER = BrokerConfig(
    type="deriv",
    environment="demo",
    account_id=ACCOUNT_ID,
    credential_ref="secret://env/DERIV_API_TOKEN",
    symbol_namespace="deriv",
)

RISK = RiskLimits(
    max_position_notional=5_000.0,
    max_total_exposure=5_000.0,
    max_daily_loss=ALLOCATION,
    max_drawdown_pct=100.0,
    max_open_orders=5,
    max_consecutive_losses=0,
    risk_per_trade_pct=1.0,
    max_stake=1.0,
)

BOTS: list[tuple[str, list[str], dict]] = [
    (
        "trend_v1",
        ["EUR/USD"],
        {"fast": 5, "slow": 20, "qty": 1.0, "min_cross_pct": 0.01, "cooldown_ticks": 30},
    ),
    (
        "bollinger_v1",
        ["EUR/USD"],
        {"period": 15, "num_std": 1.5, "qty": 1.0, "cooldown_ticks": 30},
    ),
    (
        "macd_v1",
        ["EUR/USD"],
        {"fast": 8, "slow": 17, "signal": 6, "qty": 1.0, "cooldown_ticks": 30},
    ),
    (
        "regime_v1",
        ["EUR/USD"],
        {"fast": 3, "slow": 10, "adx_period": 10, "min_adx": 20.0, "qty": 1.0, "cooldown_ticks": 30},
    ),
    (
        "range_v1",
        ["EUR/USD"],
        {"channel_period": 30, "tolerance_pct": 10.0, "breakout_buffer": 0.01, "qty": 1.0, "cooldown_ticks": 30},
    ),
    (
        "vol_breakout_v1",
        ["V75/USD"],
        {"atr_period": 10, "expansion_mult": 1.5, "qty": 1.0, "cooldown_ticks": 30},
    ),
    (
        "grid_v2",
        ["V75/USD"],
        {"ema_period": 20, "atr_period": 14, "z_threshold": 1.5, "trend_max_slope": 0.8,
         "slope_lookback": 5, "qty": 1.0, "cooldown_ticks": 90},
    ),
    (
        "deriv_v1",
        ["V75/USD"],
        {"sma_period": 10, "rsi_period": 10, "rsi_overbought": 65.0,
         "rsi_oversold": 35.0, "stake": 1.0, "cooldown_ticks": 30},
    ),
    (
        "deriv_v2",
        ["V75/USD"],
        {"bb_period": 20, "bb_std": 2.0, "rsi_period": 14,
         "rsi_oversold": 30.0, "rsi_overbought": 70.0, "notional": 1.0, "cooldown_ticks": 30},
    ),
]


def _set_allocation(bot_id: str, allocation: float) -> None:
    with session_scope() as s:
        row = s.get(BotRow, bot_id)
        if row is None:
            raise ValueError(f"bot {bot_id} not found")
        row.allocation = allocation
        row.updated_at_ms = now_epoch_ms()
        s.flush()


async def archive_existing() -> None:
    mgr = get_runtime_manager()
    all_bots = bot_service.list_bots()
    targets = [b for b in all_bots if "tournament" in b.name.lower()
               and b.state != BotState.ARCHIVED]

    if not targets:
        print("No active Tournament bots to archive.")
        return

    print(f"Archiving {len(targets)} existing Tournament bot(s)...\n")
    for b in targets:
        print(f"  {b.name:<55} state={b.state.value}")
        try:
            if b.state == BotState.RUNNING:
                bot_service.stop(b.id, actor_email=ACTOR, actor_role=ROLE)
                try:
                    await mgr.stop(b.id)
                except Exception:
                    pass
            bot_service.archive(b.id, actor_email=ACTOR, actor_role=ROLE)
            print(f"    ✓ archived")
        except Exception as e:
            print(f"    ❌ {e}")


async def create_fresh() -> None:
    print(f"\nCreating {len(BOTS)} fresh Tournament bot(s)...\n")
    for strategy_id, symbols, params in BOTS:
        bot_name = f"Tournament — {strategy_id}"
        print(f"--- {bot_name} ---")

        bot = bot_service.create(
            name=bot_name,
            owner_email=ACTOR,
            actor_email=ACTOR,
            actor_role=ROLE,
            allocation=ALLOCATION,
        )
        print(f"  Created  {bot.id}")

        cfg = BotConfig(
            bot_id=bot.id,
            version=0,
            name=bot_name,
            strategy=StrategyConfig(strategy_id=strategy_id, params=params),
            risk=RISK,
            broker=BROKER,
            symbols=symbols,
        )
        try:
            draft = config_service.create_draft(actor_email=ACTOR, actor_role=ROLE, config=cfg)
            validated = config_service.validate(
                actor_email=ACTOR, actor_role=ROLE, bot_id=bot.id, version=draft.version
            )
            if validated.validation_errors:
                print(f"  ❌ Validation failed: {validated.validation_errors}")
                continue
            for w in validated.validation_warnings:
                print(f"  ⚠  {w}")
            config_service.apply(
                actor_email=ACTOR,
                actor_role=ROLE,
                bot_id=bot.id,
                version=draft.version,
                typed_confirmation="APPLY RISK CHANGE",
            )
            print(f"  ✓  Config applied: {strategy_id} on {symbols} @ $1/trade")
        except Exception as e:
            print(f"  ❌ Config failed: {e}")
            continue

        try:
            started = bot_service.start(bot.id, actor_email=ACTOR, actor_role=ROLE)
            await get_runtime_manager().start(started)
            print(f"  🚀 Started")
        except Exception as e:
            print(f"  ❌ Start failed: {e}")


async def main() -> None:
    await archive_existing()
    await create_fresh()
    print("\nDone — fresh Tournament bots are live with clean P&L tracking.")
    print(f"Allocation: ${ALLOCATION:,.0f} virtual  |  Max stake: $1/trade")


if __name__ == "__main__":
    asyncio.run(main())
