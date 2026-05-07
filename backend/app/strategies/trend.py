"""trend_v1 — SMA crossover with guardrails.

Buys when fast SMA crosses above slow SMA, flips short when it crosses
below. Position size is fixed `qty` from params. Trades only one symbol
at a time. Deterministic — no randomness.

Guardrails (vs the original bare-bones version):
  - Minimum signal strength: crossover must exceed `min_cross_pct` of
    the slow SMA to filter out micro-noise crossovers.
  - Cooldown: after a trade signal, suppress further signals for
    `cooldown_ticks` ticks to prevent whipsawing.

Params:
  fast:           int   (default 5)
  slow:           int   (default 20)
  qty:            float (default 1000) — units of the asset
  min_cross_pct:  float (default 0.02) — minimum fast-slow spread as % of slow SMA
  cooldown_ticks: int   (default 10) — ticks to wait between signals
"""
from __future__ import annotations

from app.core.ids import new_id
from app.execution.models import OrderIntent, OrderType, Side
from app.strategies.base import StrategyContext


def _sma(values: list[float], n: int) -> float | None:
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


class TrendV1:
    id = "trend_v1"

    PARAM_SCHEMA: dict[str, object] = {
        "fast": 5,
        "slow": 20,
        "qty": 1000.0,
        "min_cross_pct": 0.02,
        "cooldown_ticks": 10,
    }

    def __init__(self) -> None:
        self._ticks_since_trade: dict[str, int] = {}

    def debug_state(self, ctx: StrategyContext) -> dict:
        """Return current indicator values and signal reasoning for the debug panel."""
        params = ctx.params
        fast_n = int(params.get("fast", 5))
        slow_n = int(params.get("slow", 20))
        min_cross_pct = float(params.get("min_cross_pct", 0.02))
        cooldown_ticks = int(params.get("cooldown_ticks", 10))

        closes = [b.close for b in ctx.bars if b.symbol == ctx.symbol]
        bars_needed = slow_n + 1

        if len(closes) < bars_needed:
            return {
                "bars_available": len(closes),
                "bars_needed": bars_needed,
                "indicators": {},
                "signal": {
                    "status": "warming_up",
                    "label": "Collecting data",
                    "detail": f"Need {bars_needed} bars, have {len(closes)}",
                    "cooldown_remaining": 0,
                },
            }

        fast_now = _sma(closes, fast_n)
        slow_now = _sma(closes, slow_n)
        fast_prev = _sma(closes[:-1], fast_n)
        slow_prev = _sma(closes[:-1], slow_n)

        spread_pct = (
            abs(fast_now - slow_now) / abs(slow_now) * 100  # type: ignore[operator]
            if slow_now
            else 0.0
        )
        crossed_up = (fast_prev or 0) <= (slow_prev or 0) and (fast_now or 0) > (slow_now or 0)
        crossed_down = (fast_prev or 0) >= (slow_prev or 0) and (fast_now or 0) < (slow_now or 0)

        ticks = self._ticks_since_trade.get(ctx.symbol, cooldown_ticks)
        cooldown_remaining = max(0, cooldown_ticks - ticks)

        if cooldown_remaining > 0:
            status, label = "cooldown", f"Cooldown — {cooldown_remaining} tick{'s' if cooldown_remaining != 1 else ''} remaining"
            detail = "Recent signal fired; waiting before next entry."
        elif crossed_up and spread_pct >= min_cross_pct:
            status, label = "signal_buy", "BUY signal"
            detail = f"Fast SMA crossed above slow SMA (spread {spread_pct:.3f}% ≥ min {min_cross_pct}%)"
        elif crossed_down and spread_pct >= min_cross_pct:
            status, label = "signal_sell", "SELL signal"
            detail = f"Fast SMA crossed below slow SMA (spread {spread_pct:.3f}% ≥ min {min_cross_pct}%)"
        elif (crossed_up or crossed_down) and spread_pct < min_cross_pct:
            status, label = "weak_signal", "Crossover too weak"
            detail = f"Cross detected but spread {spread_pct:.3f}% < min {min_cross_pct}% — filtered out"
        else:
            direction = "above" if (fast_now or 0) > (slow_now or 0) else "below"
            status, label = "watching", "Watching for crossover"
            detail = f"Fast SMA ({fast_now:.5f}) is {direction} slow SMA ({slow_now:.5f}) — no new cross"

        return {
            "bars_available": len(closes),
            "bars_needed": bars_needed,
            "indicators": {
                "fast_sma": round(fast_now or 0, 6),
                "slow_sma": round(slow_now or 0, 6),
                "spread_pct": round(spread_pct, 4),
            },
            "signal": {
                "status": status,
                "label": label,
                "detail": detail,
                "cooldown_remaining": cooldown_remaining,
            },
        }

    def on_data(self, ctx: StrategyContext) -> list[OrderIntent]:
        params = ctx.params
        fast_n = int(params.get("fast", 5))
        slow_n = int(params.get("slow", 20))
        qty = float(params.get("qty", 1000))
        min_cross_pct = float(params.get("min_cross_pct", 0.02))
        cooldown_ticks = int(params.get("cooldown_ticks", 10))
        if fast_n <= 0 or slow_n <= fast_n:
            return []

        # Use dynamic sizing if risk_per_trade_pct is configured
        if ctx.risk_per_trade_pct is not None and ctx.effective_balance > 0 and ctx.mark_price > 0:
            # qty in units = (balance * pct/100) / current_price
            qty = (ctx.effective_balance * ctx.risk_per_trade_pct / 100.0) / ctx.mark_price
        elif qty <= 0:
            return []

        closes = [b.close for b in ctx.bars if b.symbol == ctx.symbol]
        # Need slow + 1 bars to detect a cross between t-1 and t.
        if len(closes) < slow_n + 1:
            return []

        fast_now = _sma(closes, fast_n)
        slow_now = _sma(closes, slow_n)
        fast_prev = _sma(closes[:-1], fast_n)
        slow_prev = _sma(closes[:-1], slow_n)
        if None in (fast_now, slow_now, fast_prev, slow_prev):
            return []

        crossed_up = fast_prev <= slow_prev and fast_now > slow_now  # type: ignore[operator]
        crossed_down = fast_prev >= slow_prev and fast_now < slow_now  # type: ignore[operator]

        # Cooldown check
        ticks = self._ticks_since_trade.get(ctx.symbol, cooldown_ticks)
        self._ticks_since_trade[ctx.symbol] = ticks + 1
        if ticks < cooldown_ticks:
            return []

        # Signal strength filter: only act when the spread between fast and
        # slow SMA is at least min_cross_pct % of the slow SMA value.
        if slow_now and slow_now != 0:  # type: ignore[redundant-expr]
            spread_pct = abs(fast_now - slow_now) / abs(slow_now) * 100  # type: ignore[operator]
            if spread_pct < min_cross_pct:
                return []

        intents: list[OrderIntent] = []
        pos = ctx.current_position_qty

        if crossed_up:
            target = qty
            delta = target - pos
            if delta > 0:
                intents.append(self._intent(ctx, Side.BUY, abs(delta)))
            elif delta < 0:
                intents.append(self._intent(ctx, Side.SELL, abs(delta)))
        elif crossed_down:
            target = -qty
            delta = target - pos
            if delta < 0:
                intents.append(self._intent(ctx, Side.SELL, abs(delta)))
            elif delta > 0:
                intents.append(self._intent(ctx, Side.BUY, abs(delta)))

        if intents:
            self._ticks_since_trade[ctx.symbol] = 0

        return intents

    @staticmethod
    def _intent(ctx: StrategyContext, side: Side, qty: float) -> OrderIntent:
        return OrderIntent(
            bot_id=ctx.bot_id,
            strategy_id=ctx.strategy_id,
            client_order_id=new_id("coid"),
            symbol=ctx.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=qty,
            config_version=ctx.config_version,
        )
