"""orb_v1 — Opening Range Breakout.

From quantvps.com/blog/trading-bot-strategies (#10): "uses the first 15 to
60 minutes of trading to define a price range. If the price moves above
the high or below the low of this range, traders enter positions,
anticipating continued momentum."

Adapted for our context: we don't have a market open per se (V75 trades
24/7, our paper feed too), so the "session" is defined as the first
`range_ticks` ticks after the bot starts — i.e. the bot's own opening
range. After that, the range is locked and we trade breakouts.

Behavior:
  - Phase 1 (first range_ticks): track running high/low of mark price.
  - Phase 2 (after range locked): on each tick, if price > range_high
    and we have no position, BUY. If price < range_low and we have no
    position, SELL. Cooldown between flips.
  - Reset is a manual operation (restart bot to re-anchor the range).

Params:
  range_ticks:    int   (default 60) — bars used to define the range
  qty:            float (default 1000)
  cooldown_ticks: int   (default 30) — minimum gap between breakout signals
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.ids import new_id
from app.execution.models import OrderIntent, OrderType, Side
from app.strategies.base import StrategyContext
from app.strategies.sizing import make_intent_kwargs


@dataclass
class _OrbState:
    ticks_seen: int = 0
    high: float = 0.0
    low: float = 0.0
    locked: bool = False
    cooldown: int = 0
    last_side: str | None = None  # "buy"/"sell" — to suppress same-direction repeats


class OrbV1:
    id = "orb_v1"

    PARAM_SCHEMA: dict[str, object] = {
        "range_ticks": 60,
        "qty": 1000.0,
        "cooldown_ticks": 30,
    }

    def __init__(self) -> None:
        self._state: dict[str, _OrbState] = {}

    def _state_for(self, symbol: str) -> _OrbState:
        st = self._state.get(symbol)
        if st is None:
            st = _OrbState()
            self._state[symbol] = st
        return st

    def debug_state(self, ctx: StrategyContext) -> dict:
        params = ctx.params
        range_ticks = int(params.get("range_ticks", 60))
        cooldown_ticks = int(params.get("cooldown_ticks", 30))
        st = self._state_for(ctx.symbol)
        cooldown_remaining = max(0, cooldown_ticks - st.cooldown)

        if not st.locked:
            ticks_until_lock = max(0, range_ticks - st.ticks_seen)
            status, label = "warming_up", "Defining opening range"
            detail = (f"{st.ticks_seen}/{range_ticks} ticks — "
                      f"H {st.high:.5f} L {st.low:.5f}" if st.ticks_seen > 0
                      else f"Bar 0 — waiting for first observation")
        elif cooldown_remaining > 0:
            status, label = "cooldown", f"Cooldown — {cooldown_remaining} tick(s)"
            detail = "Recent breakout fired."
        elif ctx.mark_price > st.high:
            status, label = "signal_buy", f"BUY — break above {st.high:.5f}"
            detail = f"price {ctx.mark_price:.5f} > range high {st.high:.5f}"
        elif ctx.mark_price < st.low:
            status, label = "signal_sell", f"SELL — break below {st.low:.5f}"
            detail = f"price {ctx.mark_price:.5f} < range low {st.low:.5f}"
        else:
            status, label = "watching", f"Inside range ({st.low:.5f}–{st.high:.5f})"
            detail = f"price {ctx.mark_price:.5f}"

        return {
            "bars_available": st.ticks_seen,
            "bars_needed": range_ticks,
            "indicators": {
                "range_high": round(st.high, 6),
                "range_low": round(st.low, 6),
                "range_locked": st.locked,
                "ticks_seen": st.ticks_seen,
            },
            "signal": {
                "status": status, "label": label, "detail": detail,
                "cooldown_remaining": cooldown_remaining,
            },
        }

    def on_data(self, ctx: StrategyContext) -> list[OrderIntent]:
        params = ctx.params
        range_ticks = int(params.get("range_ticks", 60))
        qty = float(params.get("qty", 1000))
        cooldown_ticks = int(params.get("cooldown_ticks", 30))

        st = self._state_for(ctx.symbol)
        price = ctx.mark_price

        # Phase 1: build the range
        if not st.locked:
            if st.ticks_seen == 0:
                st.high = price
                st.low = price
            else:
                if price > st.high: st.high = price
                if price < st.low: st.low = price
            st.ticks_seen += 1
            if st.ticks_seen >= range_ticks:
                st.locked = True
            return []

        # Phase 2: trade breakouts
        st.cooldown += 1
        if st.cooldown < cooldown_ticks:
            return []

        side: Side | None = None
        if price > st.high and st.last_side != "buy":
            side = Side.BUY
            st.last_side = "buy"
        elif price < st.low and st.last_side != "sell":
            side = Side.SELL
            st.last_side = "sell"

        if side is None:
            return []

        sizing = make_intent_kwargs(ctx, qty)
        if sizing is None:
            return []

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
