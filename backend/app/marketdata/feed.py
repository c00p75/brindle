"""Synthetic market data feed for paper mode.

Deterministic per `(bot_id, symbol)` seed so replays are reproducible.
Generates a random walk around a fixed mark price. Bars are emitted on
demand — call `next_bar(symbol)` to advance the clock by one tick.

Real brokers will plug in via a separate `MarketDataSource` in slice 5.
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass

from app.adapters.symbols.mapping import get_mapper
from app.core.time import now_epoch_ms
from app.strategies.base import Bar

# Reasonable starting marks for the canonical symbols our PaperAdapter knows.
_DEFAULT_MARKS = {
    "EUR/USD": 1.10,
    "GBP/USD": 1.27,
    "USD/JPY": 148.0,
    "BTC/USD": 60_000.0,
    "BTC/USDT": 60_000.0,
}


@dataclass
class _Stream:
    rng: random.Random
    last_price: float
    history: list[Bar]


class SyntheticFeed:
    """Per-bot deterministic synthetic feed.

    Tickers move via small Gaussian-ish increments scaled to the mark price.
    """

    def __init__(self, bot_id: str, symbol_namespace: str = "paper", history_cap: int = 500):
        self.bot_id = bot_id
        self._mapper = get_mapper(symbol_namespace)
        self._history_cap = history_cap
        self._streams: dict[str, _Stream] = {}

    def _stream(self, symbol: str) -> _Stream:
        if symbol not in self._streams:
            self._mapper.to_native(symbol)  # validate mapping
            seed_str = f"{self.bot_id}|{symbol}"
            digest = hashlib.sha256(seed_str.encode()).digest()
            seed_int = int.from_bytes(digest[:4], "little")
            mark = _DEFAULT_MARKS.get(symbol, 1.0)
            self._streams[symbol] = _Stream(
                rng=random.Random(seed_int), last_price=mark, history=[]
            )
        return self._streams[symbol]

    def mark(self, symbol: str) -> float:
        return self._stream(symbol).last_price

    def history(self, symbol: str) -> list[Bar]:
        return list(self._stream(symbol).history)

    def next_bar(self, symbol: str) -> Bar:
        s = self._stream(symbol)
        # Brownian-ish increment: mean 0, stddev ~5 bps.
        u1 = max(s.rng.random(), 1e-9)
        u2 = s.rng.random()
        z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)  # normal
        sigma = 0.0005  # 5 bps per tick
        ret = z * sigma
        new_price = s.last_price * math.exp(ret)
        # Synthesize an OHLC from a small intra-bar wiggle around new_price.
        wiggle = abs(new_price * sigma)
        open_ = s.last_price
        close = new_price
        high = max(open_, close) + s.rng.random() * wiggle
        low = min(open_, close) - s.rng.random() * wiggle
        bar = Bar(
            symbol=symbol,
            ts_ms=now_epoch_ms(),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=0.0,
        )
        s.last_price = close
        s.history.append(bar)
        if len(s.history) > self._history_cap:
            s.history = s.history[-self._history_cap :]
        return bar

    def warm_up(self, symbol: str, n: int) -> None:
        """Pre-fill `n` bars so strategies that need slow_n+1 bars start fast."""
        for _ in range(n):
            self.next_bar(symbol)
