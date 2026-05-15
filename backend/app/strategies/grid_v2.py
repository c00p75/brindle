"""grid_v2 — ATR-normalised mean-reversion for Deriv binary options.

Grid V1 emulated resting limit orders via price-level crossings — a pattern
suited for spot/forex where you accumulate a position.  Binary options are
independent fixed-expiry contracts, so accumulation logic is meaningless and
made V1 haemorrhage on V100/USD's random walk.

V2 rethinks the "grid" concept for binary options:
  - EMA(20) is the dynamic grid centre (mean).
  - ATR(14) normalises distance from centre into Z-score units, so the
    strategy adapts to current volatility without re-tuning.
  - Z = (price - EMA) / ATR
  - Z >= +z_threshold → price extended above mean → PUT (sell).
  - Z <= -z_threshold → price extended below mean → CALL (buy).
  - Trend guard: if the EMA itself is sloping > trend_max_slope ATR/period,
    the market is trending — skip mean-reversion entries.
  - One open contract at a time; hard cooldown between entries.

Why this is "grid-like":
  Higher |Z| = more extreme deviation = higher-confidence mean-reversion
  signal, exactly as a classic grid widens confidence with each rung.

Params:
  ema_period:       int   (default 20) — EMA lookback for grid centre
  atr_period:       int   (default 14) — ATR lookback for normalisation
  z_threshold:      float (default 1.5) — min ATR deviations to trigger
  trend_max_slope:  float (default 0.8) — skip if EMA slope > this many
                                           ATR-units per period (trending)
  slope_lookback:   int   (default 5) — periods over which EMA slope is measured
  qty:              float (default 1.0) — fallback stake (USD) if no
                                          risk_per_trade_pct configured
  cooldown_ticks:   int   (default 90) — seconds between entries
"""
from __future__ import annotations

import math

from app.core.ids import new_id
from app.core.time import now_epoch_ms
from app.execution.models import OrderIntent, OrderType, Side
from app.strategies.base import StrategyContext
from app.strategies.sizing import make_intent_kwargs


def _ema(values: list[float], period: int) -> list[float]:
    """Return EMA series for the full values list."""
    if len(values) < period:
        return []
    k = 2.0 / (period + 1)
    result = [sum(values[:period]) / period]
    for v in values[period:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def _atr(bars_h: list[float], bars_l: list[float], bars_c: list[float],
         period: int) -> float | None:
    """Average True Range over the last `period` bars."""
    if len(bars_c) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars_c)):
        h, l, prev_c = bars_h[i], bars_l[i], bars_c[i - 1]
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    if len(trs) < period:
        return None
    # Wilder smooth
    atr_val = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr_val = (atr_val * (period - 1) + tr) / period
    return atr_val


class GridV2:
    """ATR-normalised mean-reversion binary options strategy."""

    id = "grid_v2"

    PARAM_SCHEMA: dict[str, object] = {
        "ema_period": 20,
        "atr_period": 14,
        "z_threshold": 1.5,
        "trend_max_slope": 0.8,
        "slope_lookback": 5,
        "qty": 1.0,
        "cooldown_ticks": 90,
    }

    def __init__(self) -> None:
        self._ticks_since_trade: dict[str, int] = {}

    # ── helpers ───────────────────────────────────────────────────────────────

    def _indicators(self, ctx: StrategyContext, params: dict) -> dict | None:
        """Compute EMA, ATR, Z-score, slope. Returns None if not enough bars."""
        ema_p = int(params.get("ema_period", 20))
        atr_p = int(params.get("atr_period", 14))
        slope_lb = int(params.get("slope_lookback", 5))

        bars = [b for b in ctx.bars if b.symbol == ctx.symbol]
        min_bars = max(ema_p, atr_p + 1) + slope_lb
        if len(bars) < min_bars:
            return None

        closes = [b.close for b in bars]
        highs  = [b.high  for b in bars]
        lows   = [b.low   for b in bars]

        ema_series = _ema(closes, ema_p)
        if len(ema_series) < slope_lb + 1:
            return None

        atr_val = _atr(highs, lows, closes, atr_p)
        if atr_val is None or atr_val == 0:
            return None

        ema_now  = ema_series[-1]
        ema_prev = ema_series[-slope_lb - 1]
        slope    = (ema_now - ema_prev) / (atr_val * slope_lb)
        z_score  = (closes[-1] - ema_now) / atr_val

        return {
            "price":   closes[-1],
            "ema":     ema_now,
            "atr":     atr_val,
            "z_score": z_score,
            "slope":   slope,
            "bars_available": len(bars),
            "min_bars": min_bars,
        }

    # ── debug panel ───────────────────────────────────────────────────────────

    def debug_state(self, ctx: StrategyContext) -> dict:
        params = ctx.params
        z_thr  = float(params.get("z_threshold",    1.5))
        s_max  = float(params.get("trend_max_slope", 0.8))
        cd     = int(params.get("cooldown_ticks",   90))

        ind = self._indicators(ctx, params)
        if ind is None:
            bars = [b for b in ctx.bars if b.symbol == ctx.symbol]
            ema_p  = int(params.get("ema_period", 20))
            atr_p  = int(params.get("atr_period", 14))
            slb    = int(params.get("slope_lookback", 5))
            needed = max(ema_p, atr_p + 1) + slb
            return {
                "bars_available": len(bars),
                "bars_needed": needed,
                "indicators": {},
                "signal": {
                    "status": "warming_up",
                    "label": "Collecting data",
                    "detail": f"Need {needed} bars, have {len(bars)}",
                    "cooldown_remaining": 0,
                },
            }

        ticks = self._ticks_since_trade.get(ctx.symbol, cd)
        cd_remaining = max(0, cd - ticks)

        z  = ind["z_score"]
        sl = ind["slope"]
        trending = abs(sl) > s_max

        if cd_remaining > 0:
            status = "cooldown"
            label  = f"Cooldown — {cd_remaining}s remaining"
            detail = "Contract placed recently; waiting before next entry."
        elif trending:
            direction = "upward" if sl > 0 else "downward"
            status = "watching"
            label  = f"Trend guard — {direction} slope {sl:.2f} ATR/bar"
            detail = f"EMA slope ({sl:.2f}) > {s_max} threshold — skipping mean-reversion entry"
        elif z >= z_thr:
            status = "signal_sell"
            label  = f"PUT signal — Z={z:.2f} (≥{z_thr})"
            detail = (f"price {ind['price']:.4f} is {z:.2f} ATR above EMA {ind['ema']:.4f}; "
                      f"betting on reversion down")
        elif z <= -z_thr:
            status = "signal_buy"
            label  = f"CALL signal — Z={z:.2f} (≤-{z_thr})"
            detail = (f"price {ind['price']:.4f} is {abs(z):.2f} ATR below EMA {ind['ema']:.4f}; "
                      f"betting on reversion up")
        else:
            status = "watching"
            label  = f"Watching — Z={z:.2f}"
            detail = (f"price within ±{z_thr} ATR of EMA; "
                      f"need Z ≥{z_thr} or ≤-{z_thr} to trigger")

        return {
            "bars_available": ind["bars_available"],
            "bars_needed": ind["min_bars"],
            "indicators": {
                "ema":       round(ind["ema"],     5),
                "atr":       round(ind["atr"],     5),
                "z_score":   round(z,              3),
                "ema_slope": round(sl,             3),
            },
            "signal": {
                "status": status,
                "label": label,
                "detail": detail,
                "cooldown_remaining": cd_remaining,
            },
        }

    # ── signal generation ─────────────────────────────────────────────────────

    def on_data(self, ctx: StrategyContext) -> list[OrderIntent]:
        params  = ctx.params
        z_thr   = float(params.get("z_threshold",    1.5))
        s_max   = float(params.get("trend_max_slope", 0.8))
        qty     = float(params.get("qty",             1.0))
        cd      = int(params.get("cooldown_ticks",   90))

        # Don't stack contracts.
        if ctx.open_contract_count > 0:
            return []

        # Persistent cooldown (survives restarts).
        if ctx.last_trade_at_ms:
            if now_epoch_ms() - ctx.last_trade_at_ms < cd * 1000:
                return []

        # In-process cooldown.
        ticks = self._ticks_since_trade.get(ctx.symbol, cd)
        self._ticks_since_trade[ctx.symbol] = ticks + 1
        if ticks < cd:
            return []

        ind = self._indicators(ctx, params)
        if ind is None:
            return []

        z  = ind["z_score"]
        sl = ind["slope"]

        # Trend guard — don't fade a genuine trending move.
        if abs(sl) > s_max:
            return []

        # Determine direction.
        if z >= z_thr:
            side = Side.SELL   # price extended above EMA → PUT
        elif z <= -z_thr:
            side = Side.BUY    # price extended below EMA → CALL
        else:
            return []

        sizing = make_intent_kwargs(ctx, qty)
        if sizing is None:
            return []

        self._ticks_since_trade[ctx.symbol] = 0
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
