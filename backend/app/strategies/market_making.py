"""mm_v1 — basic market making (mean-reversion against the mid).

From quantvps.com (#5 Market Making): "places buy and sell orders around
the current market price to take advantage of the bid-ask spread."

Honest scope note:
  Real market making needs Level-2 order book data, fast cancel/replace,
  and inventory management — none of which Deriv exposes for binary
  options. This is a *simplified* market-making simulation appropriate
  for our framework: we treat the rolling-mean as the "fair value" and
  fade short-term deviations from it (essentially: ultra-short
  mean-reversion). It's how the strategy looks from the outside without
  the order-book mechanics underneath.

Mechanics:
  - Compute a short rolling-mean "fair value".
  - When mark price > fair + spread/2: SELL (price is "too high" — mm
    leans short).
  - When mark price < fair − spread/2: BUY  (price is "too low" — mm
    leans long).
  - Within ±spread/2 of fair, do nothing.
  - Cooldown to avoid stacking same-side signals.

Params:
  fair_period:    int   (default 20) — bars for rolling-mean fair value
  spread_pct:     float (default 0.02) — half-spread as % of fair value
  qty:            float (default 1000)
  cooldown_ticks: int   (default 2)
"""
from __future__ import annotations

from app.core.ids import new_id
from app.execution.models import OrderIntent, OrderType, Side
from app.strategies.base import StrategyContext
from app.strategies.sizing import make_intent_kwargs


def _sma(values: list[float], n: int) -> float | None:
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


class MarketMakingV1:
    id = "mm_v1"

    PARAM_SCHEMA: dict[str, object] = {
        "fair_period": 20,
        "spread_pct": 0.02,
        "qty": 1000.0,
        "cooldown_ticks": 2,
    }

    def __init__(self) -> None:
        self._cooldown: dict[str, int] = {}

    def debug_state(self, ctx: StrategyContext) -> dict:
        params = ctx.params
        period = int(params.get("fair_period", 20))
        spread_pct = float(params.get("spread_pct", 0.02))
        cooldown_ticks = int(params.get("cooldown_ticks", 2))
        bars = [b for b in ctx.bars if b.symbol == ctx.symbol]
        fair = _sma([b.close for b in bars], period)
        cooldown_remaining = max(0, cooldown_ticks - self._cooldown.get(ctx.symbol, cooldown_ticks))

        if fair is None:
            return {
                "bars_available": len(bars), "bars_needed": period,
                "indicators": {},
                "signal": {
                    "status": "warming_up", "label": "Building fair value",
                    "detail": f"{len(bars)}/{period} bars",
                    "cooldown_remaining": 0,
                },
            }

        half_spread = fair * spread_pct / 100.0
        upper = fair + half_spread
        lower = fair - half_spread
        if cooldown_remaining > 0:
            status, label = "cooldown", f"Cooldown — {cooldown_remaining} tick(s)"
            detail = "Recent quote fired."
        elif ctx.mark_price > upper:
            status, label = "signal_sell", "SELL above ask"
            detail = f"mark {ctx.mark_price:.5f} > fair+half {upper:.5f}"
        elif ctx.mark_price < lower:
            status, label = "signal_buy", "BUY below bid"
            detail = f"mark {ctx.mark_price:.5f} < fair−half {lower:.5f}"
        else:
            status, label = "watching", "Inside the spread"
            detail = f"bid {lower:.5f} / fair {fair:.5f} / ask {upper:.5f}"
        return {
            "bars_available": len(bars), "bars_needed": period,
            "indicators": {
                "fair_value": round(fair, 6),
                "bid": round(lower, 6),
                "ask": round(upper, 6),
                "half_spread": round(half_spread, 6),
            },
            "signal": {
                "status": status, "label": label, "detail": detail,
                "cooldown_remaining": cooldown_remaining,
            },
        }

    def on_data(self, ctx: StrategyContext) -> list[OrderIntent]:
        params = ctx.params
        period = int(params.get("fair_period", 20))
        spread_pct = float(params.get("spread_pct", 0.02))
        qty = float(params.get("qty", 1000))
        cooldown_ticks = int(params.get("cooldown_ticks", 2))

        bars = [b for b in ctx.bars if b.symbol == ctx.symbol]
        fair = _sma([b.close for b in bars], period)
        if fair is None:
            return []

        ticks = self._cooldown.get(ctx.symbol, cooldown_ticks)
        self._cooldown[ctx.symbol] = ticks + 1
        if ticks < cooldown_ticks:
            return []

        half_spread = fair * spread_pct / 100.0
        side: Side | None = None
        if ctx.mark_price > fair + half_spread:
            side = Side.SELL
        elif ctx.mark_price < fair - half_spread:
            side = Side.BUY
        if side is None:
            return []

        sizing = make_intent_kwargs(ctx, qty)
        if sizing is None:
            return []

        self._cooldown[ctx.symbol] = 0
        return [OrderIntent(
            bot_id=ctx.bot_id, strategy_id=ctx.strategy_id,
            client_order_id=new_id("coid"), symbol=ctx.symbol,
            side=side, order_type=OrderType.MARKET,
            config_version=ctx.config_version,
            **sizing,
        )]
