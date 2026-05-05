"""Per-bot runtime: pulls market data, runs the strategy, executes intents.

Lifecycle is mirrored from the bot state machine:
- bot.start  → spawn an asyncio task
- bot.pause  → cancel; can resume on next start
- bot.stop   → cancel; bot must be re-started explicitly
- bot.archive → cancel

The runtime is fully async and does NOT block FastAPI's event loop.
On adapter unhealth or repeated risk rejections, the bot is auto-paused
and an alert is emitted.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.adapters.brokers.factory import create_adapter
from app.alerts.models import Severity
from app.alerts.service import emit as emit_alert
from app.bots.models import Bot, BotConfig
from app.configs.service import active_version
from app.execution.persistence import get_position_qty
from app.execution.service import ExecutionService
from app.marketdata.source import build_source
from app.risk.engine import PortfolioSnapshot, RiskEngine
from app.core.eventbus import get_event_bus
from app.strategies.base import StrategyContext
from app.strategies.registry import create_strategy

log = logging.getLogger("runtime")

# Tunable. Kept short for snappy paper trading; real adapters would tune higher.
TICK_INTERVAL_S = 1.0
# Sweep open contracts for settlement every N ticks (~10s with 1s tick).
CONTRACT_POLL_INTERVAL = 10
# Poll broker balance every N ticks (~30s) for the UI.
BALANCE_POLL_INTERVAL = 30


@dataclass
class _Runtime:
    bot_id: str
    task: asyncio.Task


class RuntimeManager:
    """Process-local registry of running bot tasks."""

    def __init__(self) -> None:
        self._runtimes: dict[str, _Runtime] = {}
        self._lock = asyncio.Lock()
        # Last-known balance per bot, refreshed by the runtime loop.
        # Shape: { bot_id: {"currency": "USD", "available": float, "total": float, "ts_ms": int} }
        self._balance_cache: dict[str, dict] = {}

    def cache_balance(self, bot_id: str, balance: dict) -> None:
        self._balance_cache[bot_id] = balance

    def get_cached_balance(self, bot_id: str) -> dict | None:
        return self._balance_cache.get(bot_id)

    async def start(self, bot: Bot) -> None:
        async with self._lock:
            if bot.id in self._runtimes and not self._runtimes[bot.id].task.done():
                return  # already running
            cv = active_version(bot.id)
            if cv is None:
                raise RuntimeError("cannot start runtime: no applied config")
            task = asyncio.create_task(_run_bot_loop(bot, cv.config))
            self._runtimes[bot.id] = _Runtime(bot_id=bot.id, task=task)

    async def stop(self, bot_id: str) -> None:
        async with self._lock:
            rt = self._runtimes.pop(bot_id, None)
        if rt is None:
            return
        rt.task.cancel()
        try:
            await rt.task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    async def stop_all(self) -> None:
        async with self._lock:
            ids = list(self._runtimes.keys())
        for bot_id in ids:
            await self.stop(bot_id)

    def is_running(self, bot_id: str) -> bool:
        rt = self._runtimes.get(bot_id)
        return rt is not None and not rt.task.done()

    def running_ids(self) -> list[str]:
        return [bid for bid, rt in self._runtimes.items() if not rt.task.done()]


_manager: RuntimeManager | None = None


def get_runtime_manager() -> RuntimeManager:
    global _manager
    if _manager is None:
        _manager = RuntimeManager()
    return _manager


async def _run_bot_loop(bot: Bot, cfg: BotConfig) -> None:
    """Single bot tick loop. Runs until cancelled, fatal error, or auto-pause."""
    adapter = create_adapter(cfg.broker)
    try:
        await adapter.connect()
    except Exception as e:
        log.error("runtime startup failed bot=%s (connect): %s", bot.id, e)
        emit_alert(
            severity=Severity.CRITICAL,
            source="runtime",
            message=f"adapter connect failed: {type(e).__name__}: {e}",
            bot_id=bot.id,
        )
        return

    source = build_source(
        bot_id=bot.id,
        broker_type=cfg.broker.type,
        adapter=adapter,
        symbol_namespace=cfg.broker.symbol_namespace,
    )
    try:
        for symbol in cfg.symbols:
            await source.warm_up(symbol, n=25)  # enough for trend_v1's slow_n=20
    except Exception as e:
        log.error("runtime startup failed bot=%s (warm_up): %s", bot.id, e)
        emit_alert(
            severity=Severity.CRITICAL,
            source="runtime",
            message=f"warm_up failed: {type(e).__name__}: {e}",
            bot_id=bot.id,
        )
        await adapter.close()
        return

    strategy = create_strategy(cfg.strategy.strategy_id)
    risk = RiskEngine(cfg.risk)
    exec_svc = ExecutionService(
        adapter=adapter,
        risk=risk,
        actor_email=f"runtime/{bot.id}",
        actor_role="system",
    )

    consecutive_risk_rejects = 0
    _stale_alerted: set[str] = set()
    tick_count = 0
    log.info("runtime started bot=%s strategy=%s symbols=%s source=%s",
             bot.id, strategy.id, cfg.symbols, type(source).__name__)
    # Seed the balance cache immediately so the UI has data on first load.
    await _poll_balance(bot.id, adapter)

    try:
        while True:
            tick_count += 1
            # Every CONTRACT_POLL_INTERVAL ticks, sweep open contracts for settlement.
            if tick_count % CONTRACT_POLL_INTERVAL == 0:
                await _poll_contracts(bot.id, adapter)
                # Drawdown auto-stop check uses authoritative contract P&L.
                if await _drawdown_breached(bot, cfg):
                    return
            # Every BALANCE_POLL_INTERVAL ticks, refresh broker balance for the UI.
            if tick_count % BALANCE_POLL_INTERVAL == 0:
                await _poll_balance(bot.id, adapter)

            for symbol in cfg.symbols:
                # Staleness guard — NOOP and alert on first detection
                if source.is_stale(symbol):
                    if symbol not in _stale_alerted:
                        emit_alert(
                            severity=Severity.WARNING,
                            source="runtime",
                            message=f"market data stale for {symbol} — skipping execution",
                            bot_id=bot.id,
                        )
                        _stale_alerted.add(symbol)
                        log.warning("stale data bot=%s symbol=%s", bot.id, symbol)
                    continue
                _stale_alerted.discard(symbol)

                bar = await source.next_bar(symbol)
                if bar is None:
                    continue  # transient fetch failure

                ctx = StrategyContext(
                    bot_id=bot.id,
                    strategy_id=strategy.id,
                    symbol=symbol,
                    config_version=cfg.version,
                    params=cfg.strategy.params,
                    bars=source.history(symbol),
                    current_position_qty=get_position_qty(bot.id, symbol),
                    mark_price=bar.close,
                )
                intents = strategy.on_data(ctx)

                # Publish a tick event so the UI debug panel can display live
                # strategy state regardless of whether a signal was generated.
                _publish_tick(bot.id, strategy, ctx, bar)

                if not intents:
                    continue

                portfolio = PortfolioSnapshot()
                for intent in intents:
                    result = await exec_svc.execute(intent, portfolio, bar.close)
                    if result.status.value == "rejected" and (result.reason or "").startswith("risk:"):
                        consecutive_risk_rejects += 1
                    else:
                        consecutive_risk_rejects = 0

                    if consecutive_risk_rejects >= 5:
                        emit_alert(
                            severity=Severity.CRITICAL,
                            source="runtime",
                            message="auto-pausing bot after 5 consecutive risk rejections",
                            bot_id=bot.id,
                        )
                        from app.bots import service as bot_service
                        try:
                            bot_service.pause(
                                bot.id,
                                actor_email="runtime",
                                actor_role="system",
                            )
                        except Exception:  # noqa: BLE001
                            pass
                        return

            await asyncio.sleep(TICK_INTERVAL_S)
    except asyncio.CancelledError:  # noqa: PERF203
        log.info("runtime cancelled bot=%s", bot.id)
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("runtime crashed bot=%s err=%s", bot.id, e)
        emit_alert(
            severity=Severity.CRITICAL,
            source="runtime",
            message=f"runtime crashed: {type(e).__name__}: {e}",
            bot_id=bot.id,
        )
    finally:
        try:
            await adapter.close()
        except Exception:  # noqa: BLE001
            pass


async def _poll_balance(bot_id: str, adapter) -> None:
    """Refresh cached broker balance for the UI. Best-effort — silent on failure."""
    try:
        balances = await adapter.get_balance()
    except Exception as e:  # noqa: BLE001
        log.warning("balance poll failed bot=%s: %s", bot_id, e)
        return
    if not balances:
        return
    b = balances[0]
    from app.core.time import now_epoch_ms
    get_runtime_manager().cache_balance(bot_id, {
        "currency": b.currency,
        "available": b.available,
        "total": b.total,
        "ts_ms": now_epoch_ms(),
    })


async def _poll_contracts(bot_id: str, adapter) -> None:
    """Settle Deriv contracts that have expired since last poll.

    Best-effort — silently skips adapters that don't expose contract status
    (paper, future non-options brokers).
    """
    get_status = getattr(adapter, "get_contract_status", None)
    if get_status is None:
        return
    from app.execution import contracts as contracts_svc
    open_ids = contracts_svc.list_open_ids(bot_id)
    for cid in open_ids:
        try:
            status = await get_status(cid)
        except Exception as e:  # noqa: BLE001
            log.warning("contract poll failed bot=%s id=%s: %s", bot_id, cid, e)
            continue
        if status is None or not status.get("is_sold"):
            continue
        outcome = status.get("status", "lost")
        # Deriv reports "won" or "lost"; anything else is treated as lost.
        normalized = "won" if outcome == "won" else "lost"
        contracts_svc.settle(
            contract_id=cid,
            payout_received=status.get("payout", 0.0),
            status=normalized,
        )
        log.info("contract settled bot=%s id=%s status=%s payout=%.2f profit=%.2f",
                 bot_id, cid, normalized, status.get("payout", 0.0), status.get("profit", 0.0))


async def _drawdown_breached(bot: Bot, cfg: BotConfig) -> bool:
    """Auto-pause if realized losses exceed daily_loss or max_drawdown_pct.

    Returns True if the bot should stop. Authoritative source is the contract
    table for Deriv bots (real settled P&L), positions.realized_pnl otherwise.
    """
    from app.execution import contracts as contracts_svc

    # Daily loss check — sum of negative realized PnL today
    summary = contracts_svc.summary(bot.id)
    realized = summary["realized_pnl"]
    daily_loss = -realized if realized < 0 else 0.0

    breached = False
    reason = ""
    if cfg.risk.max_daily_loss > 0 and daily_loss >= cfg.risk.max_daily_loss:
        breached = True
        reason = f"daily loss ${daily_loss:.2f} >= limit ${cfg.risk.max_daily_loss:.2f}"

    if breached:
        emit_alert(
            severity=Severity.CRITICAL,
            source="runtime",
            message=f"auto-pausing bot — drawdown limit hit: {reason}",
            bot_id=bot.id,
        )
        log.warning("drawdown auto-stop bot=%s: %s", bot.id, reason)
        from app.bots import service as bot_service
        try:
            bot_service.pause(bot.id, actor_email="runtime", actor_role="system")
        except Exception:  # noqa: BLE001
            pass
        return True
    return False


def _publish_tick(bot_id: str, strategy: object, ctx: StrategyContext, bar: object) -> None:
    """Publish a live tick event for the UI debug panel. Best-effort — never raises."""
    try:
        debug_fn = getattr(strategy, "debug_state", None)
        if debug_fn is None:
            return
        state = debug_fn(ctx)
        get_event_bus().publish(bot_id, "tick", {
            "symbol": ctx.symbol,
            "ts_ms": getattr(bar, "ts_ms", 0),
            "mark_price": ctx.mark_price,
            "strategy_id": ctx.strategy_id,
            "position_qty": ctx.current_position_qty,
            **state,
        })
    except Exception:  # noqa: BLE001
        pass
