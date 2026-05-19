"""deriv_v2 — RSI + Bollinger Band confluence for Deriv binary options.

Enters only when RSI and Bollinger Bands agree:
  BUY  (Rise/Call) when RSI < rsi_oversold  AND price is below lower band
  SELL (Fall/Put)  when RSI > rsi_overbought AND price is above upper band

Double confirmation filters out noise from either indicator alone, giving
fewer but higher-conviction signals — important for fixed-payout binary
contracts where the win/loss decision is made at expiry.

Distinction vs. deriv_v1:
  - deriv_v1 uses RSI + SMA crossover (trend-following bias)
  - deriv_v2 uses RSI + Bollinger Bands (mean-reversion bias — buys dips,
    sells rips when both indicators confirm the move is overextended)

Params:
  bb_period:       int   (default 20) — Bollinger Band SMA window
  bb_std:          float (default 2.0) — band width in standard deviations
  rsi_period:      int   (default 14) — RSI window
  rsi_oversold:    float (default 30.0)
  rsi_overbought:  float (default 70.0)
  notional:        float (default 10.0) — stake per contract
  cooldown_ticks:  int   (default 10)
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


def _rsi(closes: list[float], n: int) -> float | None:
    """Wilder's RSI. Returns None if insufficient data."""
    if len(closes) < n + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    if len(gains) < n:
        return None
    avg_gain = sum(gains[:n]) / n
    avg_loss = sum(losses[:n]) / n
    for i in range(n, len(gains)):
        avg_gain = (avg_gain * (n - 1) + gains[i]) / n
        avg_loss = (avg_loss * (n - 1) + losses[i]) / n
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


class DerivV2:
    id = "deriv_v2"

    PARAM_SCHEMA: dict[str, object] = {
        "bb_period": 20,
        "bb_std": 2.0,
        "rsi_period": 14,
        "rsi_oversold": 30.0,
        "rsi_overbought": 70.0,
        "notional": 10.0,
        "cooldown_ticks": 10,
    }

    def debug_state(self, ctx: StrategyContext) -> dict:
        params = ctx.params
        bb_n = int(params.get("bb_period", 20))
        bb_std = float(params.get("bb_std", 2.0))
        rsi_n = int(params.get("rsi_period", 14))
        oversold = float(params.get("rsi_oversold", 30.0))
        overbought = float(params.get("rsi_overbought", 70.0))
        cooldown_ticks = int(params.get("cooldown_ticks", 10))

        closes = [b.close for b in ctx.bars if b.symbol == ctx.symbol]
        bars_needed = max(bb_n, rsi_n + 1)

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

        sma = _sma(closes, bb_n) or 0.0
        sd = _stdev(closes, bb_n, sma) or 0.0
        upper = sma + bb_std * sd
        lower = sma - bb_std * sd
        rsi = _rsi(closes, rsi_n)
        price = closes[-1]
        rsi_val = rsi or 0.0

        if ctx.last_trade_at_ms:
            elapsed_ms = now_epoch_ms() - ctx.last_trade_at_ms
            cooldown_remaining = max(0, cooldown_ticks - int(elapsed_ms / 1000))
        else:
            cooldown_remaining = 0

        if cooldown_remaining > 0:
            status, label = "cooldown", f"Cooldown — {cooldown_remaining}s remaining"
            detail = "Recent signal fired."
        elif rsi_val < oversold and price < lower:
            status, label = "signal_buy", f"BUY — RSI {rsi_val:.1f} + below lower band"
            detail = f"RSI {rsi_val:.1f} < {oversold} AND price {price:.5f} < lower {lower:.5f}"
        elif rsi_val > overbought and price > upper:
            status, label = "signal_sell", f"SELL — RSI {rsi_val:.1f} + above upper band"
            detail = f"RSI {rsi_val:.1f} > {overbought} AND price {price:.5f} > upper {upper:.5f}"
        elif rsi_val < oversold or price < lower:
            status, label = "watching", f"Partial oversold (RSI {rsi_val:.1f})"
            detail = "One condition met — waiting for confluence"
        elif rsi_val > overbought or price > upper:
            status, label = "watching", f"Partial overbought (RSI {rsi_val:.1f})"
            detail = "One condition met — waiting for confluence"
        else:
            status, label = "watching", f"Neutral (RSI {rsi_val:.1f})"
            detail = f"Price {price:.5f} between bands, RSI mid-range"

        return {
            "bars_available": len(closes),
            "bars_needed": bars_needed,
            "indicators": {
                "rsi": round(rsi_val, 2),
                "sma": round(sma, 6),
                "upper_band": round(upper, 6),
                "lower_band": round(lower, 6),
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
        bb_n = int(params.get("bb_period", 20))
        bb_std = float(params.get("bb_std", 2.0))
        rsi_n = int(params.get("rsi_period", 14))
        oversold = float(params.get("rsi_oversold", 30.0))
        overbought = float(params.get("rsi_overbought", 70.0))
        notional = float(params.get("notional", 10.0))
        cooldown_ticks = int(params.get("cooldown_ticks", 10))

        if ctx.last_trade_at_ms and now_epoch_ms() - ctx.last_trade_at_ms < cooldown_ticks * 1000:
            return []

        sizing = make_intent_kwargs(ctx, notional)
        if sizing is None:
            return []

        closes = [b.close for b in ctx.bars if b.symbol == ctx.symbol]
        if len(closes) < max(bb_n, rsi_n + 1):
            return []

        sma = _sma(closes, bb_n)
        sd = _stdev(closes, bb_n, sma or 0.0)
        if sma is None or sd is None or sd == 0:
            return []
        upper = sma + bb_std * sd
        lower = sma - bb_std * sd

        rsi = _rsi(closes, rsi_n)
        if rsi is None:
            return []
        price = closes[-1]

        side: Side | None = None
        if rsi < oversold and price < lower:
            side = Side.BUY
        elif rsi > overbought and price > upper:
            side = Side.SELL

        if side is None:
            return []

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
