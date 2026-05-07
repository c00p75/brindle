"""range_v1 — explicit support/resistance range trader.

From quantvps.com (#18 Range-Bound Trading): "profits from price
oscillations within set support and resistance levels."

Distinction vs. bollinger_v1:
  - bollinger_v1 uses a *moving* envelope (SMA ± stdev). It floats with
    price.
  - range_v1 uses *fixed* levels — discovered automatically from a recent
    window's high/low — and rotates: BUY at support, SELL at resistance,
    flat in the middle. The range is rebuilt only after a detected
    breakout (price closes outside the channel by more than `breakout_buffer`).

Mechanics:
  - Channel is the highest-high and lowest-low of the last `channel_period`
    bars at lock time.
  - Anchored once enough bars exist; refreshed only when broken.
  - BUY when price <= low + tolerance × range_size and we're flat or short.
  - SELL when price >= high - tolerance × range_size and we're flat or long.
  - Flat zone in the middle generates no signals.
  - Cooldown to suppress noise from oscillation right at a level.

Params:
  channel_period:   int   (default 50)
  tolerance_pct:    float (default 0.1) — how close to a level counts as "at" it
  breakout_buffer:  float (default 0.005) — % outside the channel before refresh
  qty:              float (default 1000)
  cooldown_ticks:   int   (default 5)
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.ids import new_id
from app.execution.models import OrderIntent, OrderType, Side
from app.strategies.base import StrategyContext
from app.strategies.sizing import make_intent_kwargs


@dataclass
class _RangeState:
    high: float | None = None
    low: float | None = None
    locked: bool = False
    cooldown: int = 0


class RangeV1:
    id = "range_v1"

    PARAM_SCHEMA: dict[str, object] = {
        "channel_period": 50,
        "tolerance_pct": 0.1,
        "breakout_buffer": 0.005,
        "qty": 1000.0,
        "cooldown_ticks": 5,
    }

    def __init__(self) -> None:
        self._state: dict[str, _RangeState] = {}

    def _state_for(self, sym: str) -> _RangeState:
        st = self._state.get(sym)
        if st is None:
            st = _RangeState()
            self._state[sym] = st
        return st

    def _maybe_relock(self, ctx: StrategyContext, period: int, breakout_buf: float) -> _RangeState:
        st = self._state_for(ctx.symbol)
        bars = [b for b in ctx.bars if b.symbol == ctx.symbol]
        # Initial lock once we have enough bars
        if not st.locked and len(bars) >= period:
            window = bars[-period:]
            st.high = max(b.high for b in window)
            st.low = min(b.low for b in window)
            st.locked = True
            return st
        # Re-lock if price has clearly broken out of the channel
        if st.locked and st.high is not None and st.low is not None:
            range_size = st.high - st.low
            if range_size <= 0:
                return st
            if (ctx.mark_price > st.high + breakout_buf * range_size or
                    ctx.mark_price < st.low - breakout_buf * range_size):
                if len(bars) >= period:
                    window = bars[-period:]
                    st.high = max(b.high for b in window)
                    st.low = min(b.low for b in window)
                    st.cooldown = 0
        return st

    def debug_state(self, ctx: StrategyContext) -> dict:
        params = ctx.params
        period = int(params.get("channel_period", 50))
        tolerance = float(params.get("tolerance_pct", 0.1))
        cooldown_ticks = int(params.get("cooldown_ticks", 5))
        breakout_buf = float(params.get("breakout_buffer", 0.005))
        st = self._maybe_relock(ctx, period, breakout_buf)
        bars = [b for b in ctx.bars if b.symbol == ctx.symbol]
        cooldown_remaining = max(0, cooldown_ticks - st.cooldown)

        if not st.locked or st.high is None or st.low is None:
            return {
                "bars_available": len(bars), "bars_needed": period,
                "indicators": {},
                "signal": {
                    "status": "warming_up", "label": "Building channel",
                    "detail": f"{len(bars)}/{period} bars",
                    "cooldown_remaining": 0,
                },
            }
        rng = st.high - st.low
        tol_band = rng * tolerance / 100.0  # interpreted as percent (e.g. 0.1 → 0.1% of range)
        if cooldown_remaining > 0:
            status, label = "cooldown", f"Cooldown — {cooldown_remaining} tick(s)"
            detail = "Recent rotation fired."
        elif ctx.mark_price <= st.low + tol_band:
            status, label = "signal_buy", f"BUY — at support {st.low:.5f}"
            detail = f"price {ctx.mark_price:.5f} within tol of low"
        elif ctx.mark_price >= st.high - tol_band:
            status, label = "signal_sell", f"SELL — at resistance {st.high:.5f}"
            detail = f"price {ctx.mark_price:.5f} within tol of high"
        else:
            status, label = "watching", "Mid-channel"
            detail = f"low {st.low:.5f}, mark {ctx.mark_price:.5f}, high {st.high:.5f}"
        return {
            "bars_available": len(bars), "bars_needed": period,
            "indicators": {
                "channel_high": round(st.high, 6),
                "channel_low": round(st.low, 6),
                "range_size": round(rng, 6),
                "position_in_range_pct": round((ctx.mark_price - st.low) / rng * 100, 2) if rng > 0 else 0,
            },
            "signal": {
                "status": status, "label": label, "detail": detail,
                "cooldown_remaining": cooldown_remaining,
            },
        }

    def on_data(self, ctx: StrategyContext) -> list[OrderIntent]:
        params = ctx.params
        period = int(params.get("channel_period", 50))
        tolerance = float(params.get("tolerance_pct", 0.1))
        breakout_buf = float(params.get("breakout_buffer", 0.005))
        qty = float(params.get("qty", 1000))
        cooldown_ticks = int(params.get("cooldown_ticks", 5))

        sizing = make_intent_kwargs(ctx, qty)
        if sizing is None:
            return []

        st = self._maybe_relock(ctx, period, breakout_buf)
        if not st.locked or st.high is None or st.low is None:
            return []
        rng = st.high - st.low
        if rng <= 0:
            return []

        st.cooldown += 1
        if st.cooldown < cooldown_ticks:
            return []

        tol_band = rng * tolerance / 100.0
        side: Side | None = None
        if ctx.mark_price <= st.low + tol_band:
            side = Side.BUY
        elif ctx.mark_price >= st.high - tol_band:
            side = Side.SELL
        if side is None:
            return []

        st.cooldown = 0
        return [OrderIntent(
            bot_id=ctx.bot_id, strategy_id=ctx.strategy_id,
            client_order_id=new_id("coid"), symbol=ctx.symbol,
            side=side, order_type=OrderType.MARKET,
            config_version=ctx.config_version,
            **sizing,
        )]
