"""Backtest runner — deterministic replay of a strategy over synthetic bars.

Usage (CLI):
    python -m app.research.run --manifest experiments/my_run/manifest.yaml

Manifest schema (YAML):
    strategy_id: trend_v1
    params:
      fast: 5
      slow: 20
      qty: 1000
    symbols:
      - EUR/USD
    bars: 500           # number of bars to simulate
    seed: my_run_001    # passed as bot_id to SyntheticFeed for determinism
    risk:               # optional — mirrors BotConfig.risk fields
      max_position_notional: 50000
      max_total_exposure: 200000
      max_daily_loss: 5000
      max_drawdown_pct: 50
      max_open_orders: 20
      kill_switch: false

Results are written to experiments/<run_id>/:
    manifest.yaml  — copy of the input manifest
    metrics.json   — summary stats
    events.jsonl   — per-order events (append-only)

Identical manifest → byte-identical metrics.json (deterministic).
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.core.ids import new_id
from app.core.metrics import backtest_runs_total
from app.core.time import now_epoch_ms
from app.execution.models import ExecutionStatus, OrderIntent, OrderType, Side
from app.marketdata.feed import SyntheticFeed
from app.risk.engine import PortfolioSnapshot, RiskEngine
from app.risk.models import RiskLimits
from app.strategies.base import StrategyContext
from app.strategies.registry import create_strategy


@dataclass
class BacktestManifest:
    strategy_id: str
    params: dict[str, Any]
    symbols: list[str]
    bars: int = 500
    seed: str = "backtest"
    risk: dict[str, Any] = field(default_factory=dict)
    run_id: str = field(default_factory=lambda: new_id("run"))


@dataclass
class BacktestMetrics:
    run_id: str
    strategy_id: str
    symbols: list[str]
    bars_simulated: int
    total_orders: int
    filled_orders: int
    rejected_orders: int
    total_realized_pnl: float
    win_trades: int
    loss_trades: int
    win_rate: float
    max_drawdown_pct: float
    sharpe_ratio: float
    completed_at_ms: int

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "strategy_id": self.strategy_id,
            "symbols": self.symbols,
            "bars_simulated": self.bars_simulated,
            "total_orders": self.total_orders,
            "filled_orders": self.filled_orders,
            "rejected_orders": self.rejected_orders,
            "total_realized_pnl": round(self.total_realized_pnl, 4),
            "win_trades": self.win_trades,
            "loss_trades": self.loss_trades,
            "win_rate": round(self.win_rate, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "completed_at_ms": self.completed_at_ms,
        }


def run_backtest(manifest: BacktestManifest, output_dir: Path | None = None) -> BacktestMetrics:
    """Execute a backtest synchronously.  No DB writes; pure in-memory simulation."""
    strategy = create_strategy(manifest.strategy_id)
    feed = SyntheticFeed(bot_id=manifest.seed, symbol_namespace="paper")

    risk_cfg = RiskLimits(
        max_position_notional=manifest.risk.get("max_position_notional", 1_000_000),
        max_total_exposure=manifest.risk.get("max_total_exposure", 5_000_000),
        max_daily_loss=manifest.risk.get("max_daily_loss", 100_000),
        max_drawdown_pct=manifest.risk.get("max_drawdown_pct", 50),
        max_open_orders=manifest.risk.get("max_open_orders", 100),
        kill_switch=manifest.risk.get("kill_switch", False),
    )
    risk = RiskEngine(risk_cfg)

    # Warm up so strategies have enough history from bar 1
    for sym in manifest.symbols:
        feed.warm_up(sym, n=50)

    events: list[dict] = []
    positions: dict[str, float] = {sym: 0.0 for sym in manifest.symbols}
    avg_prices: dict[str, float | None] = {sym: None for sym in manifest.symbols}
    realized_pnl: float = 0.0
    pnl_curve: list[float] = [0.0]
    order_pnls: list[float] = []

    for _ in range(manifest.bars):
        for sym in manifest.symbols:
            bar = feed.next_bar(sym)
            ctx = StrategyContext(
                bot_id=manifest.seed,
                strategy_id=strategy.id,
                symbol=sym,
                config_version=1,
                params=manifest.params,
                bars=feed.history(sym),
                current_position_qty=positions[sym],
                mark_price=bar.close,
            )
            intents = strategy.on_data(ctx)
            for intent in intents:
                portfolio = PortfolioSnapshot()
                decision = risk.check(intent, portfolio, bar.close)
                status = "rejected"
                fill_pnl = 0.0
                if decision.allowed:
                    status = "filled"
                    qty = intent.quantity or 0.0
                    signed = qty if intent.side == Side.BUY else -qty
                    old_qty = positions[sym]
                    new_qty = old_qty + signed

                    if old_qty != 0 and (old_qty > 0) != (new_qty > 0 or new_qty == 0):
                        # closing or reducing
                        closed = min(abs(old_qty), abs(signed))
                        sign = 1.0 if old_qty > 0 else -1.0
                        if avg_prices[sym] is not None:
                            fill_pnl = sign * (bar.close - avg_prices[sym]) * closed
                            realized_pnl += fill_pnl
                            order_pnls.append(fill_pnl)

                    positions[sym] = new_qty
                    if new_qty == 0:
                        avg_prices[sym] = None
                    elif old_qty == 0 or (old_qty > 0) == (new_qty > 0):
                        if avg_prices[sym] is None:
                            avg_prices[sym] = bar.close
                        else:
                            total = abs(old_qty) * avg_prices[sym] + abs(signed) * bar.close
                            avg_prices[sym] = total / abs(new_qty)
                    else:
                        avg_prices[sym] = bar.close

                pnl_curve.append(realized_pnl)
                events.append({
                    "ts_ms": bar.ts_ms,
                    "symbol": sym,
                    "side": intent.side.value,
                    "qty": intent.quantity,
                    "price": bar.close,
                    "status": status,
                    "pnl": fill_pnl,
                    "reason": None if status == "filled" else decision.reason,
                })

    total_orders = len(events)
    filled = sum(1 for e in events if e["status"] == "filled")
    rejected = total_orders - filled
    win_trades = sum(1 for p in order_pnls if p > 0)
    loss_trades = sum(1 for p in order_pnls if p <= 0)
    win_rate = win_trades / len(order_pnls) if order_pnls else 0.0

    # Max drawdown
    peak = 0.0
    max_dd = 0.0
    for v in pnl_curve:
        peak = max(peak, v)
        dd = (peak - v) / (abs(peak) + 1e-9) * 100
        max_dd = max(max_dd, dd)

    # Sharpe (annualised, assuming 1 bar = 1 minute, 252 trading days × 390 min)
    if len(order_pnls) > 1:
        mean_ret = sum(order_pnls) / len(order_pnls)
        variance = sum((p - mean_ret) ** 2 for p in order_pnls) / len(order_pnls)
        std = math.sqrt(variance) if variance > 0 else 1e-9
        sharpe = (mean_ret / std) * math.sqrt(len(order_pnls))
    else:
        sharpe = 0.0

    metrics = BacktestMetrics(
        run_id=manifest.run_id,
        strategy_id=manifest.strategy_id,
        symbols=manifest.symbols,
        bars_simulated=manifest.bars,
        total_orders=total_orders,
        filled_orders=filled,
        rejected_orders=rejected,
        total_realized_pnl=realized_pnl,
        win_trades=win_trades,
        loss_trades=loss_trades,
        win_rate=win_rate,
        max_drawdown_pct=max_dd,
        sharpe_ratio=sharpe,
        completed_at_ms=now_epoch_ms(),
    )

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "manifest.yaml").write_text(
            yaml.dump(
                {
                    "strategy_id": manifest.strategy_id,
                    "params": manifest.params,
                    "symbols": manifest.symbols,
                    "bars": manifest.bars,
                    "seed": manifest.seed,
                    "run_id": manifest.run_id,
                },
                default_flow_style=False,
            )
        )
        (output_dir / "metrics.json").write_text(json.dumps(metrics.to_dict(), indent=2))
        with open(output_dir / "events.jsonl", "w") as f:
            for ev in events:
                f.write(json.dumps(ev, default=str) + "\n")
        _append_experiment_log(manifest, metrics, output_dir.parent)

    backtest_runs_total.labels(strategy_id=manifest.strategy_id, outcome="ok").inc()
    return metrics


def _append_experiment_log(manifest: BacktestManifest, metrics: BacktestMetrics, experiments_dir: Path) -> None:
    log_path = experiments_dir / "EXPERIMENT_LOG.md"
    entry = (
        f"\n## {manifest.run_id}\n"
        f"- strategy: `{manifest.strategy_id}` params={manifest.params}\n"
        f"- symbols: {manifest.symbols}  bars: {manifest.bars}  seed: `{manifest.seed}`\n"
        f"- pnl: {metrics.total_realized_pnl:.2f}  win_rate: {metrics.win_rate:.1%}  "
        f"sharpe: {metrics.sharpe_ratio:.2f}  max_dd: {metrics.max_drawdown_pct:.1f}%\n"
        f"- filled: {metrics.filled_orders}/{metrics.total_orders}\n"
    )
    with open(log_path, "a") as f:
        f.write(entry)


def load_manifest(path: Path) -> BacktestManifest:
    data = yaml.safe_load(path.read_text())
    return BacktestManifest(
        strategy_id=data["strategy_id"],
        params=data.get("params", {}),
        symbols=data["symbols"],
        bars=data.get("bars", 500),
        seed=data.get("seed", "backtest"),
        risk=data.get("risk", {}),
        run_id=data.get("run_id", new_id("run")),
    )
