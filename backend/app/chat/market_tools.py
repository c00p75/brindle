"""Market-data helpers exposed to the chat assistant.

Three building blocks:
  - quote(symbol)            : latest tick price + timestamp
  - recent_bars(symbol, n)   : N most-recent bars (synthesized from Deriv ticks)
  - indicators(symbol, ...)  : technical indicators computed from bars

All three share an in-memory TTL cache so repeated chat questions about the
same symbol within a few seconds don't re-hit the broker. Failures are
returned as `{"error": ...}` dicts — the LLM can read and explain them
rather than crashing the chat turn.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from typing import Any

from app.adapters.symbols.mapping import NAMESPACES
from app.research.deriv_history import _fetch_ticks_async
from app.strategies.base import Bar

log = logging.getLogger("chat.market")

_QUOTE_TTL_S = 5.0
_BARS_TTL_S = 30.0
_MAX_BARS = 500

_quote_cache: dict[str, tuple[float, dict]] = {}
_bars_cache: dict[tuple[str, int], tuple[float, list[Bar]]] = {}


def _supported_symbols() -> list[str]:
    return sorted(set(NAMESPACES["deriv"]._canon_to_native.keys()))


def _creds() -> tuple[str, str, str] | None:
    app_id = os.environ.get("DERIV_APP_ID", "")
    pat = os.environ.get("DERIV_API_TOKEN", "")
    account_id = os.environ.get("DERIV_BACKTEST_ACCOUNT_ID", "")
    if not (app_id and pat and account_id):
        return None
    return app_id, pat, account_id


async def _fetch_bars(symbol: str, count: int) -> list[Bar]:
    creds = _creds()
    if creds is None:
        raise RuntimeError(
            "Deriv credentials missing — set DERIV_APP_ID, DERIV_API_TOKEN, "
            "and DERIV_BACKTEST_ACCOUNT_ID to enable live market data."
        )
    app_id, pat, account_id = creds
    return await _fetch_ticks_async(
        symbol, count, account_id=account_id, app_id=app_id, pat=pat,
    )


async def get_quote(symbol: str) -> dict[str, Any]:
    if symbol not in _supported_symbols():
        return {
            "error": f"symbol '{symbol}' not supported on Deriv",
            "supported": _supported_symbols(),
        }

    now = time.monotonic()
    cached = _quote_cache.get(symbol)
    if cached and (now - cached[0]) < _QUOTE_TTL_S:
        return cached[1]

    try:
        bars = await asyncio.wait_for(_fetch_bars(symbol, 1), timeout=20)
    except asyncio.TimeoutError:
        return {"error": f"timed out fetching quote for {symbol}"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"quote fetch failed: {type(e).__name__}: {e}"}

    if not bars:
        return {"error": f"no ticks returned for {symbol}"}

    latest = bars[-1]
    out = {
        "symbol": symbol,
        "price": latest.close,
        "ts_ms": latest.ts_ms,
        "source": "deriv",
    }
    _quote_cache[symbol] = (now, out)
    return out


async def get_recent_bars(symbol: str, count: int = 100) -> dict[str, Any]:
    if symbol not in _supported_symbols():
        return {
            "error": f"symbol '{symbol}' not supported on Deriv",
            "supported": _supported_symbols(),
        }
    count = max(1, min(int(count), _MAX_BARS))

    now = time.monotonic()
    cached = _bars_cache.get((symbol, count))
    if cached and (now - cached[0]) < _BARS_TTL_S:
        bars = cached[1]
    else:
        try:
            bars = await asyncio.wait_for(_fetch_bars(symbol, count), timeout=30)
        except asyncio.TimeoutError:
            return {"error": f"timed out fetching {count} bars for {symbol}"}
        except Exception as e:  # noqa: BLE001
            return {"error": f"bars fetch failed: {type(e).__name__}: {e}"}
        if not bars:
            return {"error": f"no bars returned for {symbol}"}
        _bars_cache[(symbol, count)] = (now, bars)

    return {
        "symbol": symbol,
        "count": len(bars),
        "first_ts_ms": bars[0].ts_ms,
        "last_ts_ms": bars[-1].ts_ms,
        "last_price": bars[-1].close,
        "bars": [
            {"ts_ms": b.ts_ms, "open": b.open, "high": b.high,
             "low": b.low, "close": b.close}
            for b in bars
        ],
    }


# --- indicators -------------------------------------------------------------
# Pure-Python implementations. Inputs are lists of Bar; outputs are the most
# recent value (and a short trailing window for context).

def _closes(bars: list[Bar]) -> list[float]:
    return [b.close for b in bars]


def _ema(values: list[float], period: int) -> list[float]:
    if len(values) < period or period <= 0:
        return []
    k = 2.0 / (period + 1)
    out = [sum(values[:period]) / period]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def _rsi(values: list[float], period: int = 14) -> list[float]:
    if len(values) < period + 1:
        return []
    gains = []
    losses = []
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    out: list[float] = []
    for i in range(period, len(gains)):
        if i > period:
            avg_g = (avg_g * (period - 1) + gains[i]) / period
            avg_l = (avg_l * (period - 1) + losses[i]) / period
        if avg_l == 0:
            out.append(100.0)
        else:
            rs = avg_g / avg_l
            out.append(100.0 - 100.0 / (1.0 + rs))
    return out


def _macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9):
    fast_e = _ema(values, fast)
    slow_e = _ema(values, slow)
    if not fast_e or not slow_e:
        return [], [], []
    # align: slow_e starts later; trim fast_e to match length
    offset = len(fast_e) - len(slow_e)
    fast_e = fast_e[offset:]
    macd_line = [f - s for f, s in zip(fast_e, slow_e)]
    signal_line = _ema(macd_line, signal)
    if not signal_line:
        return macd_line, [], []
    sig_offset = len(macd_line) - len(signal_line)
    hist = [m - s for m, s in zip(macd_line[sig_offset:], signal_line)]
    return macd_line, signal_line, hist


def _atr(bars: list[Bar], period: int = 14) -> list[float]:
    if len(bars) < period + 1:
        return []
    trs: list[float] = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i].high, bars[i].low, bars[i - 1].close
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    out = [sum(trs[:period]) / period]
    for tr in trs[period:]:
        out.append((out[-1] * (period - 1) + tr) / period)
    return out


def _bollinger(values: list[float], period: int = 20, k: float = 2.0):
    if len(values) < period:
        return [], [], []
    mids: list[float] = []
    ups: list[float] = []
    los: list[float] = []
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        m = sum(window) / period
        var = sum((x - m) ** 2 for x in window) / period
        sd = math.sqrt(var)
        mids.append(m)
        ups.append(m + k * sd)
        los.append(m - k * sd)
    return mids, ups, los


_INDICATOR_KINDS = {"rsi", "ema", "macd", "atr", "bollinger"}


async def get_indicators(
    symbol: str,
    indicators: list[str],
    bars: int = 100,
    params: dict | None = None,
) -> dict[str, Any]:
    params = params or {}
    requested = [i.lower() for i in indicators if i.lower() in _INDICATOR_KINDS]
    if not requested:
        return {
            "error": "no recognized indicators requested",
            "supported": sorted(_INDICATOR_KINDS),
        }

    bars_resp = await get_recent_bars(symbol, bars)
    if "error" in bars_resp:
        return bars_resp

    raw = bars_resp["bars"]
    bar_objs = [
        Bar(symbol=symbol, ts_ms=b["ts_ms"], open=b["open"], high=b["high"],
            low=b["low"], close=b["close"])
        for b in raw
    ]
    closes = _closes(bar_objs)

    out: dict[str, Any] = {
        "symbol": symbol,
        "bars_used": len(bar_objs),
        "last_price": closes[-1] if closes else None,
        "last_ts_ms": bar_objs[-1].ts_ms if bar_objs else None,
        "indicators": {},
    }

    if "rsi" in requested:
        period = int(params.get("rsi_period", 14))
        series = _rsi(closes, period)
        out["indicators"]["rsi"] = {
            "period": period,
            "value": series[-1] if series else None,
            "interpretation": (
                "overbought" if series and series[-1] >= 70 else
                "oversold" if series and series[-1] <= 30 else
                "neutral" if series else "insufficient_data"
            ),
        }

    if "ema" in requested:
        fast = int(params.get("ema_fast", 12))
        slow = int(params.get("ema_slow", 26))
        ef = _ema(closes, fast)
        es = _ema(closes, slow)
        cross = None
        if ef and es:
            cross = "fast_above_slow" if ef[-1] > es[-1] else "fast_below_slow"
        out["indicators"]["ema"] = {
            "fast_period": fast, "slow_period": slow,
            "fast": ef[-1] if ef else None,
            "slow": es[-1] if es else None,
            "cross": cross,
        }

    if "macd" in requested:
        macd_line, signal_line, hist = _macd(
            closes,
            int(params.get("macd_fast", 12)),
            int(params.get("macd_slow", 26)),
            int(params.get("macd_signal", 9)),
        )
        out["indicators"]["macd"] = {
            "macd": macd_line[-1] if macd_line else None,
            "signal": signal_line[-1] if signal_line else None,
            "histogram": hist[-1] if hist else None,
            "trend": (
                "bullish" if hist and hist[-1] > 0 else
                "bearish" if hist and hist[-1] < 0 else "neutral"
            ),
        }

    if "atr" in requested:
        period = int(params.get("atr_period", 14))
        series = _atr(bar_objs, period)
        out["indicators"]["atr"] = {
            "period": period,
            "value": series[-1] if series else None,
        }

    if "bollinger" in requested:
        period = int(params.get("bb_period", 20))
        k = float(params.get("bb_k", 2.0))
        mids, ups, los = _bollinger(closes, period, k)
        if mids and ups and los:
            last = closes[-1]
            position = (
                "above_upper" if last > ups[-1] else
                "below_lower" if last < los[-1] else "inside"
            )
            out["indicators"]["bollinger"] = {
                "period": period, "k": k,
                "middle": mids[-1], "upper": ups[-1], "lower": los[-1],
                "price_position": position,
            }
        else:
            out["indicators"]["bollinger"] = {"error": "insufficient_data"}

    return out
