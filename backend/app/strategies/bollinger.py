"""bollinger_v1 — mean-reversion on Bollinger Band touches.

When price closes below the lower band: BUY (mean-reversion long).
When price closes above the upper band: SELL.
When price returns to the middle band (SMA): exit (flat).

Params:
  period:        int   (default 20) — SMA window
  num_std:       float (default 2.0) — band width in stdevs
  qty:           float (default 1000) — units of the asset (or stake for Deriv)
  cooldown_ticks:int   (default 5) — skip ticks after a signal
"""
from __future__ import annotations

import math

from app.core.ids import new_id
from app.core.time import now_epoch_ms
from app.execution.models import OrderIntent, OrderType, Side
from app.strategies.base import StrategyContext
from app.strategies.sizing import make_intent_kwargs


def _sma(values: list[float], n: int) -> float | None:
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def _stdev(values: list[float], n: int, mean: float) -> float | None:
    if len(values) < n:
        return None
    window = values[-n:]
    var = sum((v - mean) ** 2 for v in window) / n
    return math.sqrt(var)


class BollingerV1:
    id = "bollinger_v1"

    PARAM_SCHEMA: dict[str, object] = {
        "period": 20,
        "num_std": 2.0,
        "qty": 1000.0,
        "cooldown_ticks": 5,
    }

    def __init__(self) -> None:
        self._cooldown: dict[str, int] = {}

    def debug_state(self, ctx: StrategyContext) -> dict:
        params = ctx.params
        period = int(params.get("period", 20))
        num_std = float(params.get("num_std", 2.0))
        cooldown_ticks = int(params.get("cooldown_ticks", 5))

        closes = [b.close for b in ctx.bars if b.symbol == ctx.symbol]
        bars_needed = period

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

        sma = _sma(closes, period) or 0.0
        sd = _stdev(closes, period, sma) or 0.0
        upper = sma + num_std * sd
        lower = sma - num_std * sd
        price = closes[-1]
        ticks = self._cooldown.get(ctx.symbol, cooldown_ticks)
        cooldown_remaining = max(0, cooldown_ticks - ticks)

        if cooldown_remaining > 0:
            status, label = "cooldown", f"Cooldown — {cooldown_remaining} tick(s) remaining"
            detail = "Recent signal fired; waiting before next entry."
        elif price < lower:
            status, label = "signal_buy", "BUY signal (price below lower band)"
            detail = f"price {price:.5f} < lower {lower:.5f}"
        elif price > upper:
            status, label = "signal_sell", "SELL signal (price above upper band)"
            detail = f"price {price:.5f} > upper {upper:.5f}"
        else:
            status, label = "watching", "Watching bands"
            detail = f"price {price:.5f} between {lower:.5f} and {upper:.5f}"

        return {
            "bars_available": len(closes),
            "bars_needed": bars_needed,
            "indicators": {
                "sma": round(sma, 6),
                "upper_band": round(upper, 6),
                "lower_band": round(lower, 6),
                "stdev": round(sd, 6),
                "price": round(price, 6),
            },
            "signal": {
                "status": status,
                "label": label,
                "detail": detail,
                "cooldown_remaining": cooldown_remaining,
            },
        }

    def on_data(self, ctx: StrategyContext) -> list[OrderIntent]:
        if ctx.open_contract_count > 0:
            return []

        params = ctx.params
        period = int(params.get("period", 20))
        num_std = float(params.get("num_std", 2.0))
        qty = float(params.get("qty", 1000))
        cooldown_ticks = int(params.get("cooldown_ticks", 5))

        if ctx.last_trade_at_ms and now_epoch_ms() - ctx.last_trade_at_ms < cooldown_ticks * 1000:
            return []

        sizing = make_intent_kwargs(ctx, qty)
        if sizing is None:
            return []

        closes = [b.close for b in ctx.bars if b.symbol == ctx.symbol]
        if len(closes) < period:
            return []

        sma = _sma(closes, period)
        sd = _stdev(closes, period, sma or 0.0)
        if sma is None or sd is None or sd == 0:
            return []
        upper = sma + num_std * sd
        lower = sma - num_std * sd
        price = closes[-1]

        ticks = self._cooldown.get(ctx.symbol, cooldown_ticks)
        self._cooldown[ctx.symbol] = ticks + 1
        if ticks < cooldown_ticks:
            return []

        side: Side | None = None
        if price < lower:
            side = Side.BUY
        elif price > upper:
            side = Side.SELL

        if side is None:
            return []

        self._cooldown[ctx.symbol] = 0
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
