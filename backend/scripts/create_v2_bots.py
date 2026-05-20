"""Create, configure, and start one tournament bot per remaining strategy.

Creates a fresh "Tournament v2" bot for each of the 9 active strategies,
sets $100 allocation, applies run-until-depleted risk limits, and starts.

Run from the backend/ directory:
    python scripts/create_v2_bots.py

Bot naming: "Tournament v2 — {strategy_id}"
Tournament risk:
    max_drawdown_pct       = 100  (run until $0)
    max_daily_loss         = 100  (= allocation)
    max_consecutive_losses = 0    (disabled)
    risk_per_trade_pct     = 1.0  (~$1/trade initially)
    max_stake              = 5.0  (hard cap per trade)
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
from app.risk.models import RiskLimits
from app.runtime.manager import get_runtime_manager

ACTOR = "system/create-v2-bots"
ROLE = "admin"
ALLOCATION = 100.0

ACCOUNT_ID = os.environ.get("TARGET_ACCOUNT_ID", "DOT91022417")
BROKER = BrokerConfig(
    type="deriv",
    environment="demo",
    account_id=ACCOUNT_ID,
    credential_ref="secret://env/DERIV_API_TOKEN",
    symbol_namespace="deriv",
)

TOURNAMENT_RISK = RiskLimits(
    max_position_notional=100.0,
    max_total_exposure=100.0,
    max_daily_loss=ALLOCATION,
    max_drawdown_pct=100.0,
    max_open_orders=5,
    max_consecutive_losses=0,
    risk_per_trade_pct=1.0,
    max_stake=5.0,
)

# One entry per strategy: (strategy_id, symbols, params)
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


async def create_and_start(strategy_id: str, symbols: list[str], params: dict) -> None:
    bot_name = f"Tournament v2 — {strategy_id}"
    print(f"\n--- {bot_name} ---")

    # Create bot
    bot = bot_service.create(
        name=bot_name,
        owner_email=ACTOR,
        actor_email=ACTOR,
        actor_role=ROLE,
        allocation=ALLOCATION,
    )
    print(f"  Created  {bot.id}")

    # Build and apply config
    cfg = BotConfig(
        bot_id=bot.id,
        version=0,
        name=bot_name,
        strategy=StrategyConfig(strategy_id=strategy_id, params=params),
        risk=TOURNAMENT_RISK,
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
            return
        for w in validated.validation_warnings:
            print(f"  ⚠  {w}")
        config_service.apply(
            actor_email=ACTOR,
            actor_role=ROLE,
            bot_id=bot.id,
            version=draft.version,
            typed_confirmation="APPLY RISK CHANGE",
        )
        print(f"  ✓  Config applied (v{draft.version}): {strategy_id} on {symbols}")
    except Exception as e:
        print(f"  ❌ Config apply failed: {e}")
        return

    # Start
    try:
        started = bot_service.start(bot.id, actor_email=ACTOR, actor_role=ROLE)
        await get_runtime_manager().start(started)
        print(f"  🚀 Started — trading until ${ALLOCATION:.0f} depleted")
    except Exception as e:
        print(f"  ❌ Start failed: {e}")


async def main() -> None:
    print(f"Creating {len(BOTS)} Tournament v2 bots — ${ALLOCATION:.0f} each\n")
    for strategy_id, symbols, params in BOTS:
        await create_and_start(strategy_id, symbols, params)
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
