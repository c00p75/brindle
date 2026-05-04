"""Fetch real Deriv historical ticks for deterministic-ish backtests.

Uses the same OTP-auth flow as DerivAdapter. Returns a list of Bar objects
shaped identically to SyntheticFeed bars so the rest of the backtest runner
can stay symbol-agnostic.

Note: Deriv ticks have no OHLC structure — each "tick" is a single price
point. We synthesise a 1-tick "bar" with open=high=low=close=price.
For longer-timeframe backtests, downsample by passing count > target bars.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx
import websockets

from app.adapters.symbols.mapping import get_mapper
from app.strategies.base import Bar

log = logging.getLogger("research.deriv")

_OTP_BASE = "https://api.derivws.com"


async def _fetch_ws_url(account_id: str, app_id: str, pat: str) -> str:
    headers = {"Deriv-App-ID": app_id, "Authorization": f"Bearer {pat}"}
    async with httpx.AsyncClient(base_url=_OTP_BASE, timeout=15) as c:
        resp = await c.post(f"/trading/v1/options/accounts/{account_id}/otp", headers=headers)
    if resp.status_code != 200:
        raise ConnectionError(f"OTP fetch failed ({resp.status_code}): {resp.text[:200]}")
    return resp.json()["data"]["url"]


async def _fetch_ticks_async(
    canonical_symbol: str, count: int, *, account_id: str, app_id: str, pat: str
) -> list[Bar]:
    mapper = get_mapper("deriv")
    native = mapper.to_native(canonical_symbol)
    ws_url = await _fetch_ws_url(account_id, app_id, pat)
    bars: list[Bar] = []
    async with websockets.connect(ws_url, open_timeout=15) as ws:
        await ws.send(json.dumps({
            "ticks_history": native,
            "count": count,
            "end": "latest",
            "style": "ticks",
            "req_id": 1,
        }))
        resp: dict[str, Any] = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
        if "error" in resp:
            raise RuntimeError(f"Deriv ticks_history error: {resp['error']['message']}")
        history = resp.get("history", {})
        prices = history.get("prices", [])
        times = history.get("times", [])
        for p, t in zip(prices, times):
            price = float(p)
            bars.append(Bar(
                symbol=canonical_symbol,
                ts_ms=int(t) * 1000,
                open=price, high=price, low=price, close=price, volume=0.0,
            ))
    return bars


def fetch_historical_bars(canonical_symbol: str, count: int) -> list[Bar]:
    """Synchronous wrapper for backtest runners. Pulls credentials from env.

    Raises if env vars are missing or the fetch fails — callers should fall
    back to SyntheticFeed for offline/CI scenarios.
    """
    app_id = os.environ.get("DERIV_APP_ID", "")
    pat = os.environ.get("DERIV_API_TOKEN", "")
    account_id = os.environ.get("DERIV_BACKTEST_ACCOUNT_ID", "")
    if not (app_id and pat and account_id):
        raise RuntimeError(
            "DERIV_APP_ID, DERIV_API_TOKEN, and DERIV_BACKTEST_ACCOUNT_ID "
            "must be set to run a Deriv-historical backtest"
        )
    return asyncio.run(_fetch_ticks_async(
        canonical_symbol, count, account_id=account_id, app_id=app_id, pat=pat,
    ))


class DerivHistoricalFeed:
    """Replays a pre-fetched list of Bars one at a time, mimicking SyntheticFeed.

    Usage:
        feed = DerivHistoricalFeed.from_deriv("V75/USD", count=2000)
        feed.warm_up("V75/USD", 50)
        bar = feed.next_bar("V75/USD")
    """
    def __init__(self, history: dict[str, list[Bar]]) -> None:
        self._all = {sym: list(bars) for sym, bars in history.items()}
        self._cursor: dict[str, int] = {sym: 0 for sym in history}
        self._seen: dict[str, list[Bar]] = {sym: [] for sym in history}

    @classmethod
    def from_deriv(cls, *symbols: str, count: int = 2000) -> "DerivHistoricalFeed":
        history = {sym: fetch_historical_bars(sym, count) for sym in symbols}
        return cls(history)

    def warm_up(self, symbol: str, n: int) -> None:
        # consume n bars into history without "yielding" them
        for _ in range(n):
            self.next_bar(symbol)

    def next_bar(self, symbol: str) -> Bar:
        idx = self._cursor.get(symbol, 0)
        bars = self._all.get(symbol, [])
        if idx >= len(bars):
            # Replay loop: roll back to start once exhausted
            idx = 0
        bar = bars[idx]
        self._cursor[symbol] = idx + 1
        self._seen.setdefault(symbol, []).append(bar)
        return bar

    def history(self, symbol: str) -> list[Bar]:
        return list(self._seen.get(symbol, []))
