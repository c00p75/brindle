"""dca_v1 — Dollar-Cost Averaging.

From quantvps.com/blog/trading-bot-strategies (#8): "invest a fixed amount
of money at regular intervals, no matter what's happening in the market.
When prices are high, your set amount buys fewer shares or units; when
prices drop, you get more for the same investment."

Honest caveat from the article itself, restated for the dashboard: certain
Bitcoin DCA setups underperformed buy-and-hold in their Sep 2024 – Jan 2025
test. DCA is a *risk-management* tool, not an alpha source.

Behavior:
  - Every `interval_ticks` ticks, emit a single BUY for `qty`.
  - No exit logic. (Classic DCA accumulates indefinitely.)
  - One independent counter per symbol.

Params:
  interval_ticks: int   (default 60) — buy every N ticks (~1 min on 1s ticks)
  qty:            float (default 100)
"""
from __future__ import annotations

from app.core.ids import new_id
from app.execution.models import OrderIntent, OrderType, Side
from app.strategies.base import StrategyContext
from app.strategies.sizing import make_intent_kwargs


class DcaV1:
    id = "dca_v1"

    PARAM_SCHEMA: dict[str, object] = {
        "interval_ticks": 60,
        "qty": 100.0,
    }

    def __init__(self) -> None:
        self._tick_count: dict[str, int] = {}

    def debug_state(self, ctx: StrategyContext) -> dict:
        params = ctx.params
        interval = int(params.get("interval_ticks", 60))
        ticks = self._tick_count.get(ctx.symbol, 0)
        ticks_until = max(0, interval - (ticks % interval))
        is_buy_tick = (ticks > 0) and (ticks % interval == 0)

        if is_buy_tick:
            status, label = "signal_buy", "DCA BUY tick"
            detail = f"Tick {ticks} % {interval} == 0 — scheduled accumulation"
        else:
            status, label = "watching", f"Accumulating in {ticks_until} ticks"
            detail = f"Tick counter {ticks}/{interval}"

        return {
            "bars_available": ticks,
            "bars_needed": interval,
            "indicators": {
                "tick_count": ticks,
                "interval": interval,
                "ticks_until_buy": ticks_until,
            },
            "signal": {
                "status": status, "label": label, "detail": detail,
                "cooldown_remaining": ticks_until,
            },
        }

    def on_data(self, ctx: StrategyContext) -> list[OrderIntent]:
        params = ctx.params
        interval = int(params.get("interval_ticks", 60))
        qty = float(params.get("qty", 100))
        if interval <= 0 or qty <= 0:
            return []

        ticks = self._tick_count.get(ctx.symbol, 0) + 1
        self._tick_count[ctx.symbol] = ticks

        # Buy on every Nth tick — note we skip tick 0 to avoid buying
        # immediately on bot startup before any meaningful state exists.
        if ticks > 0 and ticks % interval == 0:
            sizing = make_intent_kwargs(ctx, qty)
            if sizing is None:
                return []
            return [OrderIntent(
                bot_id=ctx.bot_id,
                strategy_id=ctx.strategy_id,
                client_order_id=new_id("coid"),
                symbol=ctx.symbol,
                side=Side.BUY,
                order_type=OrderType.MARKET,
                config_version=ctx.config_version,
                **sizing,
            )]
        return []
