#!/usr/bin/env python3
"""Batch-update all running bot configs with optimized parameters.

This script:
1. Lists all bots
2. For each RUNNING bot, fetches its active config
3. Creates a new draft with optimized strategy params and risk settings
4. Validates, approves, and applies the new config
5. The runtime will pick up the new config on next tick

Usage:
  python scripts/optimize_bot_configs.py [--dry-run]

Requires the backend to be running (connects via the DB directly).
"""
from __future__ import annotations

import argparse
import sys
import os

# Add parent dir to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env BEFORE importing app modules (they need DATABASE_URL)
from dotenv import load_dotenv
load_dotenv()

from app.bots import service as bot_service
from app.bots.models import BotState
from app.configs import service as config_service

# ── Optimized parameters per strategy ──
STRATEGY_PARAMS = {
    "deriv_v1": {
        "sma_period": 10,
        "rsi_period": 10,
        "rsi_overbought": 65.0,
        "rsi_oversold": 35.0,
        "stake": 1.0,
        "cooldown_ticks": 30,
    },
    "trend_v1": {
        "fast": 3,
        "slow": 10,
        "qty": 1.0,
        "min_cross_pct": 0.01,
        "cooldown_ticks": 30,
    },
    "macd_v1": {
        "fast": 8,
        "slow": 17,
        "signal": 6,
        "qty": 1.0,
        "cooldown_ticks": 30,
    },
    "bollinger_v1": {
        "period": 15,
        "num_std": 1.5,
        "qty": 1.0,
        "cooldown_ticks": 30,
    },
    "vol_breakout_v1": {
        "atr_period": 10,
        "expansion_mult": 1.5,
        "qty": 1.0,
        "cooldown_ticks": 30,
    },
    "regime_v1": {
        "fast": 3,
        "slow": 10,
        "adx_period": 10,
        "min_adx": 20.0,
        "qty": 1.0,
        "cooldown_ticks": 30,
    },
    "scalp_v1": {
        "lookback": 3,
        "atr_period": 10,
        "entry_atr_mult": 0.3,
        "tp_atr_mult": 0.8,
        "sl_atr_mult": 0.5,
        "qty": 1.0,
        "max_hold_ticks": 60,
        "cooldown_ticks": 5,
    },
    "range_v1": {
        "channel_period": 30,
        "tolerance_pct": 0.2,
        "breakout_buffer": 0.01,
        "qty": 1.0,
        "cooldown_ticks": 30,
    },
    "orb_v1": {
        "range_ticks": 30,
        "qty": 1.0,
        "cooldown_ticks": 30,
    },
    "grid_v1": {
        "grid_spacing_pct": 0.03,
        "qty": 1.0,
        "cooldown_ticks": 20,
        "reset_on_breakout_pct": 0.5,
    },
    "dca_v1": {
        "interval_ticks": 300,
        "qty": 0.50,
    },
    "mm_v1": {
        "fair_period": 15,
        "spread_pct": 0.03,
        "qty": 1.0,
        "cooldown_ticks": 5,
    },
}

# Default risk settings for all bots
DEFAULT_RISK = {
    "max_position_notional": 5.0,
    "max_total_exposure": 10.0,
    "max_daily_loss": 15.0,
    "max_drawdown_pct": 15.0,
    "max_open_orders": 3,
    "kill_switch": False,
    "max_consecutive_losses": 5,
    "risk_per_trade_pct": 1.0,
}

# Strategy-specific risk overrides
RISK_OVERRIDES = {
    "scalp_v1": {"max_consecutive_losses": 7},
    "grid_v1": {"max_open_orders": 5, "max_consecutive_losses": 8},
    "dca_v1": {"max_total_exposure": 50.0, "max_daily_loss": 20.0, "max_drawdown_pct": 20.0, "max_open_orders": 10, "risk_per_trade_pct": 0.5},
    "macd_v1": {"max_consecutive_losses": 6},
    "bollinger_v1": {"max_consecutive_losses": 6},
}


def optimize_bot(bot, dry_run: bool = False) -> bool:
    """Update a single bot's config. Returns True if config was changed."""
    active = config_service.active_version(bot.id)
    if active is None:
        print(f"  ⚠️  {bot.name}: no active config, skipping")
        return False

    cfg = active.config
    strategy_id = cfg.strategy.strategy_id
    old_params = dict(cfg.strategy.params)
    old_risk = cfg.risk.model_dump()

    # Get optimized params
    new_params = STRATEGY_PARAMS.get(strategy_id)
    if new_params is None:
        print(f"  ⚠️  {bot.name}: unknown strategy '{strategy_id}', skipping")
        return False

    # Build new risk settings
    new_risk = {**DEFAULT_RISK, **RISK_OVERRIDES.get(strategy_id, {})}

    # Check if anything actually changed
    params_changed = old_params != new_params
    risk_changed = any(
        old_risk.get(k) != v for k, v in new_risk.items()
    )

    if not params_changed and not risk_changed:
        print(f"  ✓  {bot.name}: already optimized")
        return False

    print(f"  📝  {bot.name} ({strategy_id}):")
    if params_changed:
        for k, v in new_params.items():
            old = old_params.get(k, "—")
            if old != v:
                print(f"      param.{k}: {old} → {v}")
    if risk_changed:
        for k, v in new_risk.items():
            old = old_risk.get(k, "—")
            if old != v:
                print(f"      risk.{k}: {old} → {v}")

    if dry_run:
        print(f"      [dry-run] skipping apply")
        return True

    # Build the updated config
    from app.bots.models import BotConfig, StrategyConfig
    from app.risk.models import RiskLimits

    new_cfg = BotConfig(
        bot_id=cfg.bot_id,
        version=0,  # will be set by create_draft
        name=cfg.name,
        description=cfg.description,
        strategy=StrategyConfig(
            strategy_id=strategy_id,
            params=new_params,
        ),
        risk=RiskLimits(**new_risk),
        broker=cfg.broker,
        symbols=cfg.symbols,
    )

    # Create → Validate → Apply
    actor = "system/optimizer"
    role = "admin"

    draft = config_service.create_draft(actor_email=actor, actor_role=role, config=new_cfg)
    print(f"      draft v{draft.version} created")

    validated = config_service.validate(
        actor_email=actor, actor_role=role,
        bot_id=bot.id, version=draft.version,
    )
    if validated.validation_errors:
        print(f"      ❌ validation failed: {validated.validation_errors}")
        return False
    if validated.validation_warnings:
        print(f"      ⚠️  warnings: {validated.validation_warnings}")

    applied = config_service.apply(
        actor_email=actor, actor_role=role,
        bot_id=bot.id, version=draft.version,
        typed_confirmation="APPLY RISK CHANGE",
    )
    print(f"      ✅ v{applied.version} applied")
    return True


def main():
    parser = argparse.ArgumentParser(description="Optimize all bot configs")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without applying")
    parser.add_argument("--all", action="store_true", help="Optimize all bots (not just running)")
    args = parser.parse_args()

    bots = bot_service.list_bots()
    skip = {BotState.ARCHIVED, BotState.DRAFT}
    if args.all:
        targets = [b for b in bots if b.state not in skip]
    else:
        targets = [b for b in bots if b.state == BotState.RUNNING]

    print(f"\n{'='*60}")
    print(f"Bot Configuration Optimizer")
    print(f"{'='*60}")
    print(f"Total bots: {len(bots)}, Targets: {len(targets)}")
    if args.dry_run:
        print("Mode: DRY RUN (no changes will be applied)")
    print(f"{'='*60}\n")

    changed = 0
    for bot in targets:
        try:
            if optimize_bot(bot, dry_run=args.dry_run):
                changed += 1
        except Exception as e:
            print(f"  ❌ {bot.name}: {e}")

    print(f"\n{'='*60}")
    print(f"Summary: {changed}/{len(targets)} bots {'would be ' if args.dry_run else ''}updated")
    if not args.dry_run and changed > 0:
        print("⚡ Bots will pick up new configs on next tick (no restart needed)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
