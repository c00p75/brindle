"""grid_v1 — fixed-interval mean reversion ("grid trading").

From quantvps.com/blog/trading-bot-strategies (#3): "set buy orders below
the current price and sell orders above it. When one order is executed, it
triggers a corresponding order in the opposite direction."

Since our strategy framework can't place resting limit orders directly, we
emulate the grid by detecting *level crossings* on each tick:
  - Anchor a base price the first time we see a symbol.
  - Carve the price space into evenly-spaced "levels" above and below the
    anchor (spacing = base * grid_spacing_pct).
  - When the current level (rounded down) differs from the level we last
    fired a signal on, emit a counter-trend signal:
      price moved UP by a level → SELL  (take profit at higher rung)
      price moved DOWN by a level → BUY (buy the dip at a lower rung)
  - Cooldown between signals to avoid noise.

Best in: range-bound or oscillating markets (the article notes grid trading
"thrives" in sideways markets and "may accumulate losing positions" in
strong trends — which is correct).

Params:
  base_price:        float | None  (default None — anchor on first observation)
  grid_spacing_pct:  float (default 0.05) — distance between levels, % of base
  qty:               float (default 1000)
  cooldown_ticks:    int   (default 3)
  reset_on_breakout_pct: float (default 1.0) — if price moves >X% from base,
                              re-anchor (we've left the grid range)
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.ids import new_id
from app.execution.models import OrderIntent, OrderType, Side
from app.strategies.base import StrategyContext
from app.strategies.sizing import make_intent_kwargs


@dataclass
class _GridState:
    base: float
    last_level: int
    cooldown: int


class GridV1:
    id = "grid_v1"

    PARAM_SCHEMA: dict[str, object] = {
        "base_price": None,            # None = auto-anchor on first tick
        "grid_spacing_pct": 0.05,      # 0.05% spacing — tune per instrument
        "qty": 1000.0,
        "cooldown_ticks": 3,
        "reset_on_breakout_pct": 1.0,  # re-anchor if price drifts beyond ±1%
    }

    def __init__(self) -> None:
        self._state: dict[str, _GridState] = {}

    def _level_of(self, base: float, price: float, spacing_pct: float) -> int:
        if base <= 0 or spacing_pct <= 0:
            return 0
        # Distance from base in "level units" — sign indicates direction.
        delta_pct = (price - base) / base * 100.0
        return int(delta_pct // spacing_pct)

    def _ensure_anchored(self, ctx: StrategyContext, params: dict) -> _GridState:
        st = self._state.get(ctx.symbol)
        if st is not None:
            return st
        configured = params.get("base_price")
        base = float(configured) if configured else float(ctx.mark_price)
        st = _GridState(base=base, last_level=0, cooldown=0)
        self._state[ctx.symbol] = st
        return st

    def debug_state(self, ctx: StrategyContext) -> dict:
        params = ctx.params
        spacing = float(params.get("grid_spacing_pct", 0.05))
        cooldown_ticks = int(params.get("cooldown_ticks", 3))
        st = self._ensure_anchored(ctx, params)
        level = self._level_of(st.base, ctx.mark_price, spacing)
        delta_pct = (ctx.mark_price - st.base) / st.base * 100.0 if st.base else 0.0
        cooldown_remaining = max(0, cooldown_ticks - st.cooldown)

        if cooldown_remaining > 0:
            status, label = "cooldown", f"Cooldown — {cooldown_remaining} tick(s)"
            detail = "Recent grid signal fired; waiting."
        elif level > st.last_level:
            status, label = "signal_sell", f"Grid SELL — moved up to level {level}"
            detail = f"price {ctx.mark_price:.5f} > base {st.base:.5f} by {delta_pct:.3f}% (last level {st.last_level})"
        elif level < st.last_level:
            status, label = "signal_buy", f"Grid BUY — moved down to level {level}"
            detail = f"price {ctx.mark_price:.5f} < base {st.base:.5f} by {delta_pct:.3f}% (last level {st.last_level})"
        else:
            status, label = "watching", f"Within grid level {level}"
            detail = f"price {ctx.mark_price:.5f}, base {st.base:.5f} ({delta_pct:+.3f}%)"

        return {
            "bars_available": len([b for b in ctx.bars if b.symbol == ctx.symbol]),
            "bars_needed": 1,
            "indicators": {
                "base_price": round(st.base, 6),
                "grid_level": level,
                "last_level": st.last_level,
                "delta_pct": round(delta_pct, 4),
                "spacing_pct": spacing,
            },
            "signal": {
                "status": status, "label": label, "detail": detail,
                "cooldown_remaining": cooldown_remaining,
            },
        }

    def on_data(self, ctx: StrategyContext) -> list[OrderIntent]:
        params = ctx.params
        spacing = float(params.get("grid_spacing_pct", 0.05))
        qty = float(params.get("qty", 1000))
        cooldown_ticks = int(params.get("cooldown_ticks", 3))
        reset_pct = float(params.get("reset_on_breakout_pct", 1.0))

        st = self._ensure_anchored(ctx, params)

        # Re-anchor if price has drifted beyond the configured breakout band —
        # the grid is no longer relevant in the current price regime.
        if st.base > 0:
            drift_pct = abs(ctx.mark_price - st.base) / st.base * 100.0
            if drift_pct > reset_pct:
                self._state[ctx.symbol] = _GridState(
                    base=ctx.mark_price, last_level=0, cooldown=0,
                )
                return []

        st.cooldown += 1
        if st.cooldown < cooldown_ticks:
            return []

        level = self._level_of(st.base, ctx.mark_price, spacing)
        if level == st.last_level:
            return []

        side = Side.SELL if level > st.last_level else Side.BUY

        sizing = make_intent_kwargs(ctx, qty)
        if sizing is None:
            return []

        st.last_level = level
        st.cooldown = 0
        return [OrderIntent(
            bot_id=ctx.bot_id,
            strategy_id=ctx.strategy_id,
            client_order_id=new_id("coid"),
            symbol=ctx.symbol,
            side=side,
            order_type=OrderType.MARKET,
            config_version=ctx.config_version,
            **sizing,
        )]
