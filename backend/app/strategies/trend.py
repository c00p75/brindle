"""trend_v1 — simple SMA crossover.

Buys when fast SMA crosses above slow SMA, flips short when it crosses
below. Position size is fixed `qty` from params. Trades only one symbol
at a time. Deterministic — no randomness.

Params:
  fast: int  (default 5)
  slow: int  (default 20)
  qty:  float (default 1000)
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

    def on_data(self, ctx: StrategyContext) -> list[OrderIntent]:
        params = ctx.params
        fast_n = int(params.get("fast", 5))
        slow_n = int(params.get("slow", 20))
        qty = float(params.get("qty", 1000))
        if fast_n <= 0 or slow_n <= fast_n:
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
