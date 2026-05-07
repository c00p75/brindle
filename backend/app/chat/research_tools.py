"""Coaching and setup-discovery tools for the chat assistant.

Three building blocks:
  - analyze_portfolio()         : aggregate all bots, flag winners/losers, idle bots
  - scan_setups(strategy, syms) : run a strategy's signal logic on current Deriv bars
  - suggest_params(strategy, sym): synthetic parameter sweep, return top candidates

These wrap pre-existing services. They do not place orders or change config —
they exist purely to give the assistant something useful to *say* about the
user's portfolio and the current market.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import sys
from typing import Any

from app.bots import service as bot_service
from app.chat import market_tools
from app.configs.service import active_version
from app.execution import contracts as contracts_svc
from app.research.runner import BacktestManifest, run_backtest
from app.strategies.base import Bar, StrategyContext
from app.strategies.registry import (
    STRATEGY_REGISTRY,
    create_strategy,
    get_param_schema,
    is_known_strategy,
    list_strategies,
)

log = logging.getLogger("chat.research")

_DEFAULT_SCAN_BARS = 100
_DEFAULT_SUGGEST_BARS = 300
_MAX_SWEEP_RUNS = 5


# ---------------------------------------------------------------------------
# list_strategies_meta
# ---------------------------------------------------------------------------

def _strategy_description(strategy_cls: type) -> str:
    """Pull a one-line description from the strategy's defining module.

    Strategy classes don't carry their own docstrings — the prose lives at
    module level. We grab the first non-empty line of the module docstring
    and strip the conventional `id — ` prefix when present.
    """
    mod = sys.modules.get(strategy_cls.__module__)
    if mod is None:
        return ""
    doc = inspect.getdoc(mod) or ""
    first_line = next((ln.strip() for ln in doc.splitlines() if ln.strip()), "")
    # "macd_v1 — momentum signal..." → "momentum signal..."
    for sep in (" — ", " - ", ": "):
        if sep in first_line:
            head, _, tail = first_line.partition(sep)
            if head and tail and len(head) < 30:
                return tail.strip()
    return first_line


def list_strategies_meta() -> dict[str, Any]:
    """Return id, description, and PARAM_SCHEMA for every registered strategy.

    Read-only. Use this when the user describes a trading idea and you need
    to pick the closest registered strategy to backtest.
    """
    out = []
    for sid in sorted(STRATEGY_REGISTRY.keys()):
        cls = STRATEGY_REGISTRY[sid]
        out.append({
            "id": sid,
            "description": _strategy_description(cls),
            "params": dict(getattr(cls, "PARAM_SCHEMA", {})),
        })
    return {"strategies": out, "count": len(out)}


# ---------------------------------------------------------------------------
# analyze_portfolio
# ---------------------------------------------------------------------------

def _bot_summary(bot) -> dict[str, Any]:
    cv = active_version(bot.id)
    cfg = cv.config if cv else None
    summ = contracts_svc.summary(bot.id)
    recent = contracts_svc.list_recent(bot.id, limit=1)
    last_trade_at = recent[0]["purchased_at_ms"] if recent else None
    realized = float(summ["realized_pnl"])
    effective = (bot.allocation or 0) + realized if bot.allocation else None
    return {
        "id": bot.id,
        "name": bot.name,
        "state": bot.state.value if hasattr(bot.state, "value") else str(bot.state),
        "allocation": bot.allocation,
        "effective_balance": effective,
        "strategy_id": cfg.strategy.strategy_id if cfg else None,
        "symbols": list(cfg.symbols) if cfg else [],
        "params": dict(cfg.strategy.params) if cfg else {},
        "trades": int(summ["total_count"]),
        "open_count": int(summ["open_count"]),
        "win_rate": float(summ["win_rate"]),
        "realized_pnl": realized,
        "total_staked": float(summ["total_staked"]),
        "last_trade_at_ms": last_trade_at,
    }


def _diagnose(bots: list[dict]) -> dict[str, Any]:
    settled = [b for b in bots if b["trades"] > 0]
    if not settled:
        return {
            "summary": "No bots have traded yet.",
            "issues": [],
            "winners": [],
            "losers": [],
        }

    by_pnl = sorted(settled, key=lambda b: b["realized_pnl"])
    winners = [b for b in by_pnl[::-1] if b["realized_pnl"] > 0][:3]
    losers = [b for b in by_pnl if b["realized_pnl"] < 0][:3]

    issues: list[str] = []
    for b in settled:
        if b["trades"] >= 10 and b["win_rate"] < 0.4:
            issues.append(
                f"{b['name']} ({b['id']}): low win rate {b['win_rate']:.0%} over {b['trades']} trades"
            )
        if b["allocation"] and b["effective_balance"] is not None:
            drawdown_pct = (1 - b["effective_balance"] / b["allocation"]) * 100
            if drawdown_pct > 25:
                issues.append(
                    f"{b['name']} ({b['id']}): {drawdown_pct:.0f}% allocation drawdown"
                )
    # Idle running bots — running state but no recent trade in 24h
    from app.core.time import now_epoch_ms
    day_ago = now_epoch_ms() - 24 * 3_600_000
    for b in bots:
        if b["state"] != "running":
            continue
        if b["last_trade_at_ms"] is None or b["last_trade_at_ms"] < day_ago:
            issues.append(
                f"{b['name']} ({b['id']}): running but no trade in 24h — strategy may not be matching"
            )

    # Symbol concentration
    sym_count: dict[str, int] = {}
    for b in bots:
        for s in b["symbols"]:
            sym_count[s] = sym_count.get(s, 0) + 1
    if sym_count:
        top_sym, top_n = max(sym_count.items(), key=lambda x: x[1])
        if top_n >= 3 and top_n / max(1, sum(sym_count.values())) > 0.5:
            issues.append(
                f"portfolio is concentrated in {top_sym} ({top_n} bots) — consider diversifying"
            )

    return {
        "winners": [{"id": b["id"], "name": b["name"], "pnl": b["realized_pnl"]} for b in winners],
        "losers": [{"id": b["id"], "name": b["name"], "pnl": b["realized_pnl"]} for b in losers],
        "issues": issues,
    }


async def analyze_portfolio() -> dict[str, Any]:
    bots = bot_service.list_bots()
    bots = [b for b in bots if (b.state.value if hasattr(b.state, "value") else b.state) != "archived"]
    if not bots:
        return {"summary": "No active bots.", "bots": [], "issues": []}

    summaries = [_bot_summary(b) for b in bots]

    total_pnl = sum(b["realized_pnl"] for b in summaries)
    total_staked = sum(b["total_staked"] for b in summaries)
    total_alloc = sum((b["allocation"] or 0) for b in summaries)
    by_state: dict[str, int] = {}
    for b in summaries:
        by_state[b["state"]] = by_state.get(b["state"], 0) + 1

    diag = _diagnose(summaries)

    return {
        "totals": {
            "bot_count": len(summaries),
            "total_allocation": total_alloc,
            "total_staked": total_staked,
            "total_realized_pnl": total_pnl,
            "by_state": by_state,
        },
        "winners": diag["winners"],
        "losers": diag["losers"],
        "issues": diag["issues"],
        "bots": summaries,
    }


# ---------------------------------------------------------------------------
# scan_setups
# ---------------------------------------------------------------------------

async def scan_setups(
    strategy_id: str,
    symbols: list[str],
    bars: int = _DEFAULT_SCAN_BARS,
) -> dict[str, Any]:
    if not is_known_strategy(strategy_id):
        return {
            "error": f"unknown strategy '{strategy_id}'",
            "available": list_strategies(),
        }
    if not symbols:
        return {"error": "no symbols supplied"}

    strategy = create_strategy(strategy_id)
    candidates: list[dict[str, Any]] = []

    # Fetch each symbol's bars in parallel.
    fetches = await asyncio.gather(
        *[market_tools.get_recent_bars(s, bars) for s in symbols],
        return_exceptions=True,
    )

    for sym, resp in zip(symbols, fetches):
        if isinstance(resp, Exception):
            candidates.append({"symbol": sym, "status": "error", "detail": str(resp)})
            continue
        if "error" in resp:
            candidates.append({"symbol": sym, "status": "error", "detail": resp["error"]})
            continue

        bar_list = [
            Bar(symbol=sym, ts_ms=b["ts_ms"], open=b["open"], high=b["high"],
                low=b["low"], close=b["close"])
            for b in resp["bars"]
        ]
        if not bar_list:
            candidates.append({"symbol": sym, "status": "no_data"})
            continue

        ctx = StrategyContext(
            bot_id="scan",
            strategy_id=strategy_id,
            symbol=sym,
            config_version=0,
            params=get_param_schema(strategy_id),  # use defaults
            bars=bar_list,
            current_position_qty=0.0,
            mark_price=bar_list[-1].close,
        )

        debug = {}
        debug_fn = getattr(strategy, "debug_state", None)
        if callable(debug_fn):
            try:
                debug = debug_fn(ctx) or {}
            except Exception as e:  # noqa: BLE001
                debug = {"error": f"debug_state failed: {e}"}

        try:
            intents = strategy.on_data(ctx)
        except Exception as e:  # noqa: BLE001
            candidates.append({"symbol": sym, "status": "error", "detail": str(e)})
            continue

        signal = debug.get("signal") if isinstance(debug, dict) else None
        signal_status = signal.get("status") if isinstance(signal, dict) else (
            "intent" if intents else "no_signal"
        )
        candidates.append({
            "symbol": sym,
            "status": signal_status,
            "label": signal.get("label") if isinstance(signal, dict) else None,
            "detail": signal.get("detail") if isinstance(signal, dict) else None,
            "indicators": debug.get("indicators") if isinstance(debug, dict) else None,
            "intent_count": len(intents),
            "last_price": bar_list[-1].close,
        })

    # Rank: live signals first, then weak/cooldown, then watching/no_signal, errors last.
    rank_order = {
        "signal_buy": 0, "signal_sell": 0, "intent": 0,
        "weak_signal": 1, "cooldown": 2,
        "watching": 3, "warming_up": 4, "no_signal": 5,
        "no_data": 6, "error": 7,
    }
    candidates.sort(key=lambda c: rank_order.get(c.get("status", "no_signal"), 9))

    return {
        "strategy_id": strategy_id,
        "bars_per_symbol": bars,
        "candidates": candidates,
    }


# ---------------------------------------------------------------------------
# suggest_params
# ---------------------------------------------------------------------------

def _sweep_variants(strategy_id: str, base: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate a small, opinionated parameter sweep for known strategies.

    Falls back to a 'baseline only' run for strategies we don't know how to
    sweep. Capped at _MAX_SWEEP_RUNS variants.
    """
    variants: list[dict[str, Any]] = [dict(base)]  # always include baseline

    if strategy_id == "trend_v1":
        for fast, slow in [(3, 15), (5, 20), (8, 30), (10, 40)]:
            v = dict(base)
            v.update(fast=fast, slow=slow)
            variants.append(v)
    elif strategy_id == "bollinger_v1":
        for period, k in [(15, 1.5), (20, 2.0), (30, 2.5)]:
            v = dict(base)
            v.update(period=period, k=k)
            variants.append(v)
    elif strategy_id == "macd_v1":
        for fast, slow, sig in [(8, 21, 5), (12, 26, 9), (5, 13, 4)]:
            v = dict(base)
            v.update(fast=fast, slow=slow, signal=sig)
            variants.append(v)
    elif strategy_id == "scalp_v1":
        for atr_mult in [0.5, 1.0, 1.5, 2.0]:
            v = dict(base)
            v.update(atr_mult=atr_mult)
            variants.append(v)
    # else: baseline only

    # Dedupe + cap
    seen = set()
    out: list[dict[str, Any]] = []
    for v in variants:
        key = tuple(sorted(v.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
        if len(out) >= _MAX_SWEEP_RUNS:
            break
    return out


def _score(metrics: dict[str, Any]) -> float:
    """Rank metric for sweep: prefer Sharpe, break ties on PnL.

    Penalize zero-trade runs so they sort to the bottom.
    """
    if metrics.get("filled_orders", 0) == 0:
        return -1e9
    return metrics.get("sharpe_ratio", 0.0) * 1000 + metrics.get("total_realized_pnl", 0.0)


async def suggest_params(
    strategy_id: str,
    symbol: str,
    bars: int = _DEFAULT_SUGGEST_BARS,
) -> dict[str, Any]:
    if not is_known_strategy(strategy_id):
        return {
            "error": f"unknown strategy '{strategy_id}'",
            "available": list_strategies(),
        }

    base = get_param_schema(strategy_id)
    variants = _sweep_variants(strategy_id, base)

    def _run_one(params: dict[str, Any]) -> dict[str, Any]:
        manifest = BacktestManifest(
            strategy_id=strategy_id,
            params=params,
            symbols=[symbol],
            bars=bars,
        )
        try:
            metrics = run_backtest(manifest, output_dir=None).to_dict()
        except Exception as e:  # noqa: BLE001
            return {"params": params, "error": f"{type(e).__name__}: {e}"}
        return {"params": params, "metrics": metrics}

    # Run in a thread pool — run_backtest is sync and CPU-bound.
    results = await asyncio.gather(*[asyncio.to_thread(_run_one, v) for v in variants])

    ok = [r for r in results if "metrics" in r]
    ok.sort(key=lambda r: _score(r["metrics"]), reverse=True)

    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "bars_per_run": bars,
        "data_source": "synthetic",
        "note": (
            "Sweep ran on synthetic data for speed. The top candidate should be "
            "re-validated with run_backtest on real Deriv history before any "
            "config change."
        ),
        "ranked": ok[:3],
        "errors": [r for r in results if "error" in r],
    }
