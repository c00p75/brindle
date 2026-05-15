"""macd_v1 — momentum signal from MACD line / signal line crossover.

MACD = EMA(fast) - EMA(slow)
Signal = EMA(MACD, signal)

When MACD crosses above signal: BUY
When MACD crosses below signal: SELL

Params:
  fast:           int   (default 12)
  slow:           int   (default 26)
  signal:         int   (default 9)
  qty:            float (default 1000)
  cooldown_ticks: int   (default 8)
"""
from __future__ import annotations

from app.core.ids import new_id
from app.core.time import now_epoch_ms
from app.execution.models import OrderIntent, OrderType, Side
from app.strategies.base import StrategyContext
from app.strategies.sizing import make_intent_kwargs


def _ema(values: list[float], n: int) -> list[float]:
    """Return EMA series (same length as input). values[0] is the seed SMA."""
    if not values or n <= 0:
        return []
    if len(values) < n:
        return []
    k = 2.0 / (n + 1.0)
    seed = sum(values[:n]) / n
    out = [seed]
    for v in values[n:]:
        out.append(out[-1] + k * (v - out[-1]))
    return out


class MacdV1:
    id = "macd_v1"

    PARAM_SCHEMA: dict[str, object] = {
        "fast": 12,
        "slow": 26,
        "signal": 9,
        "qty": 1000.0,
        "cooldown_ticks": 8,
    }

    def __init__(self) -> None:
        self._cooldown: dict[str, int] = {}

    def _macd_series(self, closes: list[float], fast: int, slow: int, signal: int):
        fast_ema = _ema(closes, fast)
        slow_ema = _ema(closes, slow)
        if not fast_ema or not slow_ema:
            return None, None
        # Align series: slow has fewer entries (starts later)
        offset = len(fast_ema) - len(slow_ema)
        if offset < 0:
            return None, None
        fast_aligned = fast_ema[offset:]
        macd = [f - s for f, s in zip(fast_aligned, slow_ema)]
        sig_ema = _ema(macd, signal)
        if not sig_ema:
            return None, None
        # Align macd to signal length
        macd_aligned = macd[-len(sig_ema):]
        return macd_aligned, sig_ema

    def debug_state(self, ctx: StrategyContext) -> dict:
        params = ctx.params
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal = int(params.get("signal", 9))
        cooldown_ticks = int(params.get("cooldown_ticks", 8))

        closes = [b.close for b in ctx.bars if b.symbol == ctx.symbol]
        bars_needed = slow + signal + 1

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

        macd, sig = self._macd_series(closes, fast, slow, signal)
        if macd is None or sig is None or len(macd) < 2:
            return {
                "bars_available": len(closes),
                "bars_needed": bars_needed,
                "indicators": {},
                "signal": {"status": "warming_up", "label": "MACD warming",
                           "detail": "computing series", "cooldown_remaining": 0},
            }

        macd_now, macd_prev = macd[-1], macd[-2]
        sig_now, sig_prev = sig[-1], sig[-2]
        crossed_up = macd_prev <= sig_prev and macd_now > sig_now
        crossed_down = macd_prev >= sig_prev and macd_now < sig_now

        ticks = self._cooldown.get(ctx.symbol, cooldown_ticks)
        cooldown_remaining = max(0, cooldown_ticks - ticks)

        if cooldown_remaining > 0:
            status, label = "cooldown", f"Cooldown — {cooldown_remaining} tick(s) remaining"
            detail = "Recent signal fired."
        elif crossed_up:
            status, label = "signal_buy", "BUY (MACD crossed above signal)"
            detail = f"MACD {macd_now:.5f} > signal {sig_now:.5f}"
        elif crossed_down:
            status, label = "signal_sell", "SELL (MACD crossed below signal)"
            detail = f"MACD {macd_now:.5f} < signal {sig_now:.5f}"
        else:
            direction = "above" if macd_now > sig_now else "below"
            status, label = "watching", f"Watching — MACD {direction} signal"
            detail = f"MACD {macd_now:.5f} signal {sig_now:.5f}"

        return {
            "bars_available": len(closes),
            "bars_needed": bars_needed,
            "indicators": {
                "macd": round(macd_now, 6),
                "signal_line": round(sig_now, 6),
                "histogram": round(macd_now - sig_now, 6),
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
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal = int(params.get("signal", 9))
        qty = float(params.get("qty", 1000))
        cooldown_ticks = int(params.get("cooldown_ticks", 8))

        if ctx.last_trade_at_ms and now_epoch_ms() - ctx.last_trade_at_ms < cooldown_ticks * 1000:
            return []

        sizing = make_intent_kwargs(ctx, qty)
        if sizing is None:
            return []

        closes = [b.close for b in ctx.bars if b.symbol == ctx.symbol]
        if len(closes) < slow + signal + 1:
            return []

        macd, sig = self._macd_series(closes, fast, slow, signal)
        if macd is None or sig is None or len(macd) < 2:
            return []

        macd_now, macd_prev = macd[-1], macd[-2]
        sig_now, sig_prev = sig[-1], sig[-2]
        crossed_up = macd_prev <= sig_prev and macd_now > sig_now
        crossed_down = macd_prev >= sig_prev and macd_now < sig_now

        ticks = self._cooldown.get(ctx.symbol, cooldown_ticks)
        self._cooldown[ctx.symbol] = ticks + 1
        if ticks < cooldown_ticks:
            return []

        side: Side | None = None
        if crossed_up:
            side = Side.BUY
        elif crossed_down:
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
