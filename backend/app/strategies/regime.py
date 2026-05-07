"""regime_v1 — ADX-gated trend follower.

Theoretical motivation:
Plain SMA crossovers fail on ranging/choppy markets because they generate
constant false signals when the trend is weak. ADX (Average Directional
Index) is a classic measure of *trend strength* — higher ADX means stronger
trend, lower means choppy.

This strategy:
  1. Computes ADX on a rolling window
  2. Only takes trade signals when ADX > min_adx (i.e. market is trending)
  3. When ADX is low (ranging), sits in cash — does nothing
  4. Direction comes from a fast/slow SMA crossover (same as trend_v1)

Hypothesis: by filtering out ranging markets, we should see a higher
test-set win rate than plain SMA crossover. Whether this hypothesis
holds in practice is what walk-forward tests will tell us.

ADX calculation (Wilder's classic method):
  TR  = max(high-low, |high-prev_close|, |low-prev_close|)
  +DM = max(high-prev_high, 0) if high-prev_high > prev_low-low else 0
  -DM = max(prev_low-low, 0) if prev_low-low > high-prev_high else 0
  Smooth all three using Wilder's smoothing (EMA-like with alpha=1/n)
  +DI = 100 * smoothed(+DM) / smoothed(TR)
  -DI = 100 * smoothed(-DM) / smoothed(TR)
  DX  = 100 * |+DI - -DI| / (+DI + -DI)
  ADX = smoothed(DX, n)

Params:
  fast:           int   (default 5)
  slow:           int   (default 20)
  adx_period:     int   (default 14) — ADX rolling window
  min_adx:        float (default 25) — gate threshold; <25 typically = ranging
  qty:            float (default 1000)
  cooldown_ticks: int   (default 8)
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


def _wilder_smooth(values: list[float], n: int) -> list[float]:
    """Wilder's smoothing — EMA with alpha = 1/n. Returns same-length list."""
    if len(values) < n:
        return []
    out: list[float] = []
    seed = sum(values[:n]) / n
    out.append(seed)
    for v in values[n:]:
        out.append(out[-1] - (out[-1] / n) + v)
    return out


def _adx_series(highs: list[float], lows: list[float], closes: list[float], n: int) -> list[float]:
    """Compute ADX series. Returns empty list if insufficient data."""
    if len(highs) < 2 * n:
        return []
    tr: list[float] = []
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for i in range(1, len(highs)):
        h, l, ph, pl, pc = highs[i], lows[i], highs[i-1], lows[i-1], closes[i-1]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
        up_move = h - ph
        down_move = pl - l
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)

    if len(tr) < n:
        return []

    smoothed_tr = _wilder_smooth(tr, n)
    smoothed_plus = _wilder_smooth(plus_dm, n)
    smoothed_minus = _wilder_smooth(minus_dm, n)
    if not smoothed_tr or not smoothed_plus or not smoothed_minus:
        return []

    dx_series: list[float] = []
    for i in range(len(smoothed_tr)):
        denom = smoothed_tr[i] if smoothed_tr[i] != 0 else 1e-12
        plus_di = 100.0 * smoothed_plus[i] / denom
        minus_di = 100.0 * smoothed_minus[i] / denom
        di_sum = plus_di + minus_di
        if di_sum == 0:
            dx_series.append(0.0)
        else:
            dx_series.append(100.0 * abs(plus_di - minus_di) / di_sum)

    return _wilder_smooth(dx_series, n)


class RegimeV1:
    id = "regime_v1"

    PARAM_SCHEMA: dict[str, object] = {
        "fast": 5,
        "slow": 20,
        "adx_period": 14,
        "min_adx": 25.0,
        "qty": 1000.0,
        "cooldown_ticks": 8,
    }

    def __init__(self) -> None:
        self._cooldown: dict[str, int] = {}

    def debug_state(self, ctx: StrategyContext) -> dict:
        params = ctx.params
        fast_n = int(params.get("fast", 5))
        slow_n = int(params.get("slow", 20))
        adx_n = int(params.get("adx_period", 14))
        min_adx = float(params.get("min_adx", 25.0))
        cooldown_ticks = int(params.get("cooldown_ticks", 8))

        bars = [b for b in ctx.bars if b.symbol == ctx.symbol]
        bars_needed = max(slow_n + 1, adx_n * 2 + 1)

        if len(bars) < bars_needed:
            return {
                "bars_available": len(bars), "bars_needed": bars_needed,
                "indicators": {},
                "signal": {
                    "status": "warming_up", "label": "Collecting data",
                    "detail": f"Need {bars_needed} bars, have {len(bars)}",
                    "cooldown_remaining": 0,
                },
            }

        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]

        fast_now = _sma(closes, fast_n) or 0.0
        slow_now = _sma(closes, slow_n) or 0.0
        adx_series = _adx_series(highs, lows, closes, adx_n)
        adx_now = adx_series[-1] if adx_series else 0.0

        ticks = self._cooldown.get(ctx.symbol, cooldown_ticks)
        cooldown_remaining = max(0, cooldown_ticks - ticks)

        if cooldown_remaining > 0:
            status, label = "cooldown", f"Cooldown — {cooldown_remaining} tick(s)"
            detail = "Recent signal fired."
        elif adx_now < min_adx:
            status, label = "watching", f"Ranging (ADX {adx_now:.1f} < {min_adx})"
            detail = "Market is choppy — gating disabled trades"
        elif fast_now > slow_now:
            status, label = "watching", f"Trending up (ADX {adx_now:.1f})"
            detail = f"Fast SMA {fast_now:.5f} > slow {slow_now:.5f} — bias long"
        else:
            status, label = "watching", f"Trending down (ADX {adx_now:.1f})"
            detail = f"Fast SMA {fast_now:.5f} < slow {slow_now:.5f} — bias short"

        return {
            "bars_available": len(bars), "bars_needed": bars_needed,
            "indicators": {
                "fast_sma": round(fast_now, 6),
                "slow_sma": round(slow_now, 6),
                "adx": round(adx_now, 2),
                "min_adx": min_adx,
            },
            "signal": {
                "status": status, "label": label, "detail": detail,
                "cooldown_remaining": cooldown_remaining,
            },
        }

    def on_data(self, ctx: StrategyContext) -> list[OrderIntent]:
        params = ctx.params
        fast_n = int(params.get("fast", 5))
        slow_n = int(params.get("slow", 20))
        adx_n = int(params.get("adx_period", 14))
        min_adx = float(params.get("min_adx", 25.0))
        qty = float(params.get("qty", 1000))
        cooldown_ticks = int(params.get("cooldown_ticks", 8))

        if fast_n <= 0 or slow_n <= fast_n:
            return []

        sizing = make_intent_kwargs(ctx, qty)
        if sizing is None:
            return []

        bars = [b for b in ctx.bars if b.symbol == ctx.symbol]
        if len(bars) < max(slow_n + 1, adx_n * 2 + 1):
            return []

        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]

        fast_now = _sma(closes, fast_n)
        slow_now = _sma(closes, slow_n)
        fast_prev = _sma(closes[:-1], fast_n)
        slow_prev = _sma(closes[:-1], slow_n)
        adx_series = _adx_series(highs, lows, closes, adx_n)
        if None in (fast_now, slow_now, fast_prev, slow_prev) or not adx_series:
            return []
        adx_now = adx_series[-1]

        ticks = self._cooldown.get(ctx.symbol, cooldown_ticks)
        self._cooldown[ctx.symbol] = ticks + 1
        if ticks < cooldown_ticks:
            return []

        # Regime gate — only trade when market is trending
        if adx_now < min_adx:
            return []

        crossed_up = fast_prev <= slow_prev and fast_now > slow_now  # type: ignore[operator]
        crossed_down = fast_prev >= slow_prev and fast_now < slow_now  # type: ignore[operator]

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
