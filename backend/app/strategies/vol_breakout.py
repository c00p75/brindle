"""vol_breakout_v1 — volatility-expansion breakout (ATR-based).

From quantvps.com (#17 Volatility-Based Strategies): "focuses on price
movement intensity, not direction." When realized volatility expands
suddenly, a directional move is often underway — enter in the direction
of the expansion.

Mechanics:
  - Compute ATR (Average True Range, Wilder smoothing) over `atr_period` bars.
  - Compute the ratio of the current bar's true range to the smoothed ATR.
  - If ratio > `expansion_mult` AND the bar closed above its open: BUY.
  - If ratio > `expansion_mult` AND the bar closed below its open: SELL.
  - Cooldown to avoid stacking signals on the same expansion event.

Distinction vs. existing strategies:
  - trend_v1 / macd_v1 react to *direction* changes; this reacts to
    *intensity* changes regardless of trend regime.
  - bollinger_v1 trades reversion to a band; this trades into the breakout.

Params:
  atr_period:     int   (default 14)
  expansion_mult: float (default 2.0) — current TR / smoothed ATR threshold
  qty:            float (default 1000)
  cooldown_ticks: int   (default 5)
"""
from __future__ import annotations

from app.core.ids import new_id
from app.core.time import now_epoch_ms
from app.execution.models import OrderIntent, OrderType, Side
from app.strategies.base import StrategyContext
from app.strategies.sizing import make_intent_kwargs


def _wilder(values: list[float], n: int) -> float | None:
    """Wilder's smoothing with seed = SMA of first n. Returns final value."""
    if len(values) < n:
        return None
    seed = sum(values[:n]) / n
    s = seed
    for v in values[n:]:
        s = s - (s / n) + v
    return s


def _true_ranges(bars) -> list[float]:
    out: list[float] = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i].high, bars[i].low, bars[i-1].close
        out.append(max(h - l, abs(h - pc), abs(l - pc)))
    return out


class VolBreakoutV1:
    id = "vol_breakout_v1"

    PARAM_SCHEMA: dict[str, object] = {
        "atr_period": 14,
        "expansion_mult": 2.0,
        "qty": 1000.0,
        "cooldown_ticks": 5,
    }

    def _compute(self, ctx: StrategyContext, params: dict):
        atr_n = int(params.get("atr_period", 14))
        bars = [b for b in ctx.bars if b.symbol == ctx.symbol]
        if len(bars) < atr_n + 1:
            return None
        trs = _true_ranges(bars)
        atr = _wilder(trs, atr_n)
        if atr is None or atr == 0:
            return None
        current_tr = trs[-1]
        ratio = current_tr / atr
        last = bars[-1]
        direction_bias = 1 if last.close > last.open else -1 if last.close < last.open else 0
        return atr, current_tr, ratio, direction_bias, len(bars)

    def debug_state(self, ctx: StrategyContext) -> dict:
        params = ctx.params
        atr_n = int(params.get("atr_period", 14))
        mult = float(params.get("expansion_mult", 2.0))
        cooldown_ticks = int(params.get("cooldown_ticks", 5))
        c = self._compute(ctx, params)
        if ctx.last_trade_at_ms:
            elapsed_ms = now_epoch_ms() - ctx.last_trade_at_ms
            cooldown_remaining = max(0, cooldown_ticks - int(elapsed_ms / 1000))
        else:
            cooldown_remaining = 0

        if c is None:
            bars = [b for b in ctx.bars if b.symbol == ctx.symbol]
            return {
                "bars_available": len(bars), "bars_needed": atr_n + 1,
                "indicators": {},
                "signal": {
                    "status": "warming_up", "label": "Building ATR",
                    "detail": f"Need {atr_n + 1} bars, have {len(bars)}",
                    "cooldown_remaining": 0,
                },
            }
        atr, tr, ratio, bias, n = c
        if cooldown_remaining > 0:
            status, label = "cooldown", f"Cooldown — {cooldown_remaining} tick(s)"
            detail = "Recent expansion fired; waiting."
        elif ratio >= mult and bias > 0:
            status, label = "signal_buy", f"BUY — vol expansion ×{ratio:.2f}"
            detail = f"TR {tr:.5f} / ATR {atr:.5f} = {ratio:.2f}× ≥ {mult} (bullish bar)"
        elif ratio >= mult and bias < 0:
            status, label = "signal_sell", f"SELL — vol expansion ×{ratio:.2f}"
            detail = f"TR {tr:.5f} / ATR {atr:.5f} = {ratio:.2f}× ≥ {mult} (bearish bar)"
        else:
            status, label = "watching", f"Vol normal ({ratio:.2f}×)"
            detail = f"TR/ATR {ratio:.2f}, threshold {mult}"
        return {
            "bars_available": n, "bars_needed": atr_n + 1,
            "indicators": {
                "atr": round(atr, 6),
                "current_tr": round(tr, 6),
                "tr_atr_ratio": round(ratio, 4),
                "expansion_threshold": mult,
            },
            "signal": {
                "status": status, "label": label, "detail": detail,
                "cooldown_remaining": cooldown_remaining,
            },
        }

    def on_data(self, ctx: StrategyContext) -> list[OrderIntent]:
        if ctx.open_contract_count > 0:
            return []

        params = ctx.params
        mult = float(params.get("expansion_mult", 2.0))
        qty = float(params.get("qty", 1000))
        cooldown_ticks = int(params.get("cooldown_ticks", 5))

        if ctx.last_trade_at_ms and now_epoch_ms() - ctx.last_trade_at_ms < cooldown_ticks * 1000:
            return []

        sizing = make_intent_kwargs(ctx, qty)
        if sizing is None:
            return []

        c = self._compute(ctx, params)
        if c is None:
            return []
        _, _, ratio, bias, _ = c
        if ratio < mult or bias == 0:
            return []
        side = Side.BUY if bias > 0 else Side.SELL
        return [OrderIntent(
            bot_id=ctx.bot_id, strategy_id=ctx.strategy_id,
            client_order_id=new_id("coid"), symbol=ctx.symbol,
            side=side, order_type=OrderType.MARKET,
            config_version=ctx.config_version,
            **sizing,
        )]
