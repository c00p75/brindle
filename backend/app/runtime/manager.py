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
            await source.warm_up(symbol, n=60)  # enough for MACD (36), Regime (29), Range (50)
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
    await _poll_balance(bot, adapter)

    try:
        while True:
            # Refresh bot state from DB to ensure allocation changes or 
            # baseline resets are respected in the current tick.
            from app.bots import service as bot_service
            fresh_bot = bot_service.get(bot.id)
            if fresh_bot:
                bot = fresh_bot

            tick_count += 1
            # Every CONTRACT_POLL_INTERVAL ticks, sweep open contracts for settlement.
            if tick_count % CONTRACT_POLL_INTERVAL == 0:
                await _poll_contracts(bot.id, adapter)
                # Drawdown auto-stop — uses real broker balance (balance_history)
                if await _drawdown_breached(bot, cfg):
                    return
                # Loss-streak circuit breaker — auto-pause if last N settled
                # contracts are all losses. Catches "running into a wall"
                # patterns the daily-loss limit may be too coarse to catch.
                if _loss_streak_breached(bot, cfg):
                    return
                # Allocation depletion stop — stop if the virtual budget is gone.
                if _allocation_depleted(bot, cfg):
                    return
            # Every BALANCE_POLL_INTERVAL ticks, refresh broker balance for the UI.
            if tick_count % BALANCE_POLL_INTERVAL == 0:
                await _poll_balance(bot, adapter)

            # Fetch broker state once per tick for all symbols to use in reconciliation
            # and risk checks. Catches "orphaned" trades if the backend crashed.
            broker_positions = []
            try:
                broker_positions = await adapter.get_positions()
            except Exception as e:
                log.warning("failed to fetch broker positions for sync bot=%s: %s", bot.id, e)

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

                # Calculate effective balance for the strategy
                effective_balance = 0.0
                if bot.allocation:
                    from app.execution import contracts as contracts_svc
                    pnl = contracts_svc.summary(bot.id, since_ms=bot.starting_balance_at_ms)["realized_pnl"]
                    effective_balance = bot.allocation + pnl
                else:
                    balance = get_runtime_manager().get_cached_balance(bot.id)
                    effective_balance = balance["available"] if balance else 0.0

                from app.execution import contracts as contracts_svc
                # Reconcile DB with Broker state:
                # 1. Start with what we have in the DB
                db_open_ids = contracts_svc.list_open_ids(bot.id)
                # 2. Check the Broker for any open position on this symbol.
                #    If the broker has a position but we don't have it in the DB,
                #    it's likely an orphaned trade from a crash.
                broker_open_count = sum(1 for p in broker_positions if p.symbol == symbol)
                effective_open_count = max(len(db_open_ids), broker_open_count)

                recent = contracts_svc.list_recent(bot.id, limit=1)
                last_trade_at = recent[0]["purchased_at_ms"] if recent else None

                ctx = StrategyContext(
                    bot_id=bot.id,
                    strategy_id=strategy.id,
                    symbol=symbol,
                    config_version=cfg.version,
                    params=cfg.strategy.params,
                    bars=source.history(symbol),
                    current_position_qty=get_position_qty(bot.id, symbol),
                    mark_price=bar.close,
                    allocation=bot.allocation,
                    effective_balance=effective_balance,
                    risk_per_trade_pct=cfg.risk.risk_per_trade_pct,
                    open_contract_count=effective_open_count,
                    last_trade_at_ms=last_trade_at,
                )
                intents = strategy.on_data(ctx)

                # Publish a tick event so the UI debug panel can display live
                # strategy state regardless of whether a signal was generated.
                _publish_tick(bot.id, strategy, ctx, bar)

                if not intents:
                    continue

                portfolio = await _build_portfolio_snapshot(bot, adapter, broker_positions, cfg.symbols)
                for intent in intents:
                    result = await exec_svc.execute(intent, portfolio, bar.close)
                    if result.status.value == "rejected" and (result.reason or "").startswith("risk:"):
                        consecutive_risk_rejects += 1
                    else:
                        consecutive_risk_rejects = 0

                    if consecutive_risk_rejects >= 5:
                        notional_estimate = 0.0
                        for intent in intents:
                            if intent.notional:
                                notional_estimate += intent.notional
                            elif intent.quantity:
                                notional_estimate += intent.quantity * bar.close

                        emit_alert(
                            severity=Severity.CRITICAL,
                            source="runtime",
                            message="auto-pausing bot after 5 consecutive risk rejections",
                            bot_id=bot.id,
                            metadata={
                                "last_reason": result.reason,
                                "last_intent_notional": notional_estimate,
                                "cap_max_position_notional": cfg.risk.max_position_notional,
                                "cap_max_total_exposure": cfg.risk.max_total_exposure,
                                "allocation": bot.allocation,
                            },
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


async def _poll_balance(bot: Bot, adapter) -> None:
    """Refresh cached broker balance for the UI. Best-effort — silent on failure.

    On the first successful read for a bot, snapshot the balance into the bot
    record as `starting_balance` so the UI has a real baseline (instead of a
    hardcoded $10K) when computing net change.
    """
    try:
        balances = await adapter.get_balance()
    except Exception as e:  # noqa: BLE001
        log.warning("balance poll failed bot=%s: %s", bot.id, e)
        return
    if not balances:
        return
    b = balances[0]
    
    # Use virtual balance for allocation-aware bots
    effective_balance = b.available
    if bot.allocation:
        from app.execution import contracts as contracts_svc
        summary = contracts_svc.summary(bot.id, since_ms=bot.starting_balance_at_ms)
        effective_balance = bot.allocation + summary["realized_pnl"]

    from app.core.time import now_epoch_ms
    from app.bots import service as bot_service
    get_runtime_manager().cache_balance(bot.id, {
        "currency": b.currency,
        "available": effective_balance,
        "total": b.total,
        "ts_ms": now_epoch_ms(),
    })
    # For allocation-aware bots, the "starting balance" is conceptually the 
    # allocation itself. We only snapshot for real-balance bots.
    if not bot.allocation:
        if bot_service.snapshot_starting_balance(bot.id, effective_balance, b.currency):
            log.info("bot=%s snapshotted starting balance %.2f %s", 
                     bot.id, effective_balance, b.currency)
    # Append to the persisted balance history so we can render real equity
    # curves and drawdown across time, not just whatever's in memory.
    try:
        from app.execution import balance_history
        balance_history.record(
            bot_id=bot.id, balance=effective_balance,
            currency=b.currency, source="poll",
        )
    except Exception:  # noqa: BLE001
        pass


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


def _loss_streak_breached(bot: Bot, cfg: BotConfig) -> bool:
    """Auto-pause if the most recent N settled trades are all losses.

    Returns True if the bot was paused. Streak threshold is taken from
    `risk.max_consecutive_losses`; 0 disables the check.
    """
    limit = int(getattr(cfg.risk, "max_consecutive_losses", 0) or 0)
    if limit <= 0:
        return False

    from app.execution import contracts as contracts_svc

    # Fetch enough recent contracts to evaluate the streak (settled only).
    # Limited to the current run to avoid legacy streaks.
    recent = contracts_svc.list_recent(bot.id, limit=limit + 5, since_ms=bot.starting_balance_at_ms)
    settled = [c for c in recent if c.get("status") in ("won", "lost")]
    if len(settled) < limit:
        return False  # not enough data yet

    # contracts.list_recent is ordered most-recent first
    last_n = settled[:limit]
    if not all(c["status"] == "lost" for c in last_n):
        return False

    emit_alert(
        severity=Severity.CRITICAL,
        source="runtime",
        message=f"auto-pausing bot — {limit} consecutive losing trades",
        bot_id=bot.id,
    )
    log.warning("loss-streak auto-stop bot=%s n=%d", bot.id, limit)
    from app.bots import service as bot_service
    try:
        bot_service.pause(bot.id, actor_email="runtime", actor_role="system")
    except Exception:  # noqa: BLE001
        pass
    return True


async def _drawdown_breached(bot: Bot, cfg: BotConfig) -> bool:
    """Auto-pause if real broker balance has lost too much.

    Source of truth is the persisted balance_snapshots series (real broker
    balance), NOT the contract tracker — they diverge in practice. We
    enforce two independent limits:

      max_daily_loss   — current balance vs balance ~24h ago
      max_drawdown_pct — current balance vs all-time peak observed

    Both limits are skipped silently if there isn't enough balance history
    yet (e.g. brand-new bot with one snapshot).
    """
    from app.bots import service as bot_service
    from app.execution import balance_history, contracts as contracts_svc
    from app.core.time import now_epoch_ms

    breached = False
    reason = ""

    # Find current balance — use the most-recent snapshot
    latest = balance_history.latest(bot.id)
    if latest is None:
        return False
    
    current = float(latest["balance"])
    if bot.allocation:
        summary = contracts_svc.summary(bot.id, since_ms=bot.starting_balance_at_ms)
        current = bot.allocation + summary["realized_pnl"]

    # 1) Daily-loss check: compare current balance to a "starting" balance.
    #    For allocation bots, the baseline is always the allocation itself.
    #    For real-balance bots, we use the persisted snapshot or 24h fallback.
    if bot.allocation:
        start_amt = bot.allocation
    else:
        start_amt, _, start_ts = bot_service.get_starting_balance(bot.id)
        if start_amt is None:
            # Use the earliest snapshot in the current run window (since last start)
            # as a proxy baseline until the first official poll completes.
            lookback_ts = max(now_epoch_ms() - 24 * 3_600_000, bot.updated_at_ms)
            recent = balance_history.history(bot_id=bot.id, since_ms=lookback_ts, max_points=2000)
            start_amt = float(recent[0]["balance"]) if recent else current

    daily_loss = max(0.0, start_amt - current)
    if cfg.risk.max_daily_loss > 0 and daily_loss >= cfg.risk.max_daily_loss:
        breached = True
        reason = f"daily loss ${daily_loss:.2f} >= limit ${cfg.risk.max_daily_loss:.2f}"

    # 2) Drawdown-from-peak check: max_drawdown_pct is enforced here, not just
    #    in the schema. Peak is the highest balance observed for this bot.
    if not breached and cfg.risk.max_drawdown_pct > 0:
        all_history = balance_history.history(bot_id=bot.id, max_points=10_000, since_ms=bot.starting_balance_at_ms)
        if all_history:
            peak = max(float(h["balance"]) for h in all_history)
            if peak > 0:
                dd_pct = (peak - current) / peak * 100.0
                if dd_pct >= cfg.risk.max_drawdown_pct:
                    breached = True
                    reason = (f"drawdown {dd_pct:.2f}% from peak ${peak:.2f} to ${current:.2f} "
                              f">= limit {cfg.risk.max_drawdown_pct:.2f}%")

    if breached:
        emit_alert(
            severity=Severity.CRITICAL,
            source="runtime",
            message=f"auto-pausing bot — drawdown limit hit: {reason}",
            bot_id=bot.id,
        )
        log.warning("drawdown auto-stop bot=%s: %s", bot.id, reason)
        try:
            bot_service.pause(bot.id, actor_email="runtime", actor_role="system")
        except Exception:  # noqa: BLE001
            pass
        return True
    return False


def _allocation_depleted(bot: Bot, cfg: BotConfig) -> bool:
    """Auto-pause if the bot's virtual allocation has been fully lost.
    
    If allocation is 100 and realized_pnl is -101, the bot must stop.
    """
    if not bot.allocation:
        return False

    from app.execution import contracts as contracts_svc
    summary = contracts_svc.summary(bot.id, since_ms=bot.starting_balance_at_ms)
    pnl = summary["realized_pnl"]
    effective = bot.allocation + pnl

    if effective <= 0:
        emit_alert(
            severity=Severity.CRITICAL,
            source="runtime",
            message=f"auto-pausing bot — virtual allocation depleted (${effective:.2f} remaining)",
            bot_id=bot.id,
        )
        log.warning("allocation-depletion auto-stop bot=%s balance=%.2f", bot.id, effective)
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
        
        # Phase 2: Record tick status for observation report
        from app.research.observation import record_tick
        signal = state.get("signal", {})
        status = signal.get("status", "unknown")
        record_tick(bot_id, status)

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


async def _build_portfolio_snapshot(
    bot: Bot, adapter, broker_positions: list[Position], symbols: list[str]
) -> PortfolioSnapshot:
    """Aggregate live portfolio state for risk-engine validation."""
    from app.execution import contracts as contracts_svc
    from app.execution import persistence as exec_persistence
    from app.execution import balance_history

    # 1. Day PnL and Equity
    equity = 0.0
    day_pnl = 0.0
    if bot.allocation:
        summ = contracts_svc.summary(bot.id, since_ms=bot.starting_balance_at_ms)
        equity = bot.allocation + summ["realized_pnl"]
        day_pnl = summ["realized_pnl"]
    else:
        balance = get_runtime_manager().get_cached_balance(bot.id)
        if balance:
            equity = balance["available"]
            day_pnl = 0.0

    # 2. Exposure & Orders
    # Gross exposure across all symbols (for non-option bots, from DB)
    positions = exec_persistence.list_positions(bot.id)
    gross_exposure = sum(
        abs(p["quantity"]) * p["avg_price"] for p in positions if p["avg_price"]
    )

    # Add broker-live exposure (Deriv contracts) for the bot's symbols.
    # This ensures that even orphaned trades from crashes are counted in risk checks.
    bot_symbols = set(symbols)
    for p in broker_positions:
        if p.symbol in bot_symbols:
            # For Deriv, Position.quantity is the USD stake (notional)
            gross_exposure += abs(p.quantity)

    # 3. High Water Mark
    hwm = 0.0
    history = balance_history.history(bot_id=bot.id, max_points=1000)
    if history:
        hwm = max(float(h["balance"]) for h in history)

    return PortfolioSnapshot(
        gross_exposure=gross_exposure,
        open_orders=0,
        day_pnl=day_pnl,
        high_water_mark=hwm,
        equity=equity,
    )
