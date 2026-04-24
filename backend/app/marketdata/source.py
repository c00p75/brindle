"""MarketDataSource protocol + staleness-aware wrappers.

Two implementations:
  SyntheticSource  — wraps SyntheticFeed; always fresh (paper only).
  LiveAdapterSource — polls adapter.get_ticker(); marks stale when ticks stop.

Runtime chooses: paper broker → SyntheticSource, anything else → LiveAdapterSource.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.core.time import now_epoch_ms
from app.marketdata.feed import SyntheticFeed
from app.strategies.base import Bar

if TYPE_CHECKING:
    from app.adapters.brokers.base import BrokerAdapter

log = logging.getLogger("marketdata")

LIVE_STALE_THRESHOLD_MS = 15_000  # 15 s without a fresh tick → stale


@runtime_checkable
class MarketDataSource(Protocol):
    async def next_bar(self, symbol: str) -> Bar | None: ...
    def is_stale(self, symbol: str) -> bool: ...
    def history(self, symbol: str) -> list[Bar]: ...
    async def warm_up(self, symbol: str, n: int) -> None: ...


# ---------------------------------------------------------------------------
# Synthetic (paper)
# ---------------------------------------------------------------------------

class SyntheticSource:
    """Thin wrapper around SyntheticFeed that satisfies MarketDataSource."""

    def __init__(self, bot_id: str, symbol_namespace: str = "paper", history_cap: int = 500) -> None:
        self._feed = SyntheticFeed(bot_id=bot_id, symbol_namespace=symbol_namespace, history_cap=history_cap)

    async def next_bar(self, symbol: str) -> Bar | None:
        return self._feed.next_bar(symbol)

    def is_stale(self, symbol: str) -> bool:
        return False  # synthetic feed never goes stale

    def history(self, symbol: str) -> list[Bar]:
        return self._feed.history(symbol)

    async def warm_up(self, symbol: str, n: int) -> None:
        self._feed.warm_up(symbol, n)


# ---------------------------------------------------------------------------
# Live (adapter-backed)
# ---------------------------------------------------------------------------

class LiveAdapterSource:
    """Builds bars from adapter.get_ticker() — one bar per runtime tick.

    Staleness: if the last successful tick is older than LIVE_STALE_THRESHOLD_MS
    the source reports stale and next_bar() returns None.  The runtime loop
    treats None as a NOOP and emits an alert on first detection.
    """

    def __init__(self, adapter: BrokerAdapter, stale_threshold_ms: int = LIVE_STALE_THRESHOLD_MS, history_cap: int = 500) -> None:
        self._adapter = adapter
        self._stale_ms = stale_threshold_ms
        self._history_cap = history_cap
        self._last_price: dict[str, float] = {}
        self._last_ts: dict[str, int] = {}
        self._history: dict[str, list[Bar]] = {}
        self._stale_alerted: set[str] = set()

    async def next_bar(self, symbol: str) -> Bar | None:
        try:
            ticker = await self._adapter.get_ticker(symbol)
        except Exception as exc:  # noqa: BLE001
            log.warning("live feed get_ticker failed symbol=%s err=%s", symbol, exc)
            return None

        mid = (ticker.bid + ticker.ask) / 2
        spread_half = (ticker.ask - ticker.bid) / 2
        last = self._last_price.get(symbol, mid)

        bar = Bar(
            symbol=symbol,
            ts_ms=ticker.ts_ms,
            open=last,
            high=max(last, mid) + spread_half,
            low=min(last, mid) - spread_half,
            close=mid,
            volume=0.0,
        )

        self._last_price[symbol] = mid
        self._last_ts[symbol] = ticker.ts_ms
        self._stale_alerted.discard(symbol)  # recovered

        hist = self._history.setdefault(symbol, [])
        hist.append(bar)
        if len(hist) > self._history_cap:
            hist[:] = hist[-self._history_cap :]

        return bar

    def is_stale(self, symbol: str) -> bool:
        last = self._last_ts.get(symbol)
        if last is None:
            return False  # haven't started yet — not stale, just uninitialized
        return (now_epoch_ms() - last) > self._stale_ms

    def history(self, symbol: str) -> list[Bar]:
        return list(self._history.get(symbol, []))

    async def warm_up(self, symbol: str, n: int) -> None:
        # For live sources, warm_up pre-fills by polling; strategies that
        # need more history than n bars will emit no signal until ready.
        for _ in range(n):
            await self.next_bar(symbol)


def build_source(bot_id: str, broker_type: str, adapter: BrokerAdapter | None, symbol_namespace: str) -> MarketDataSource:
    """Select the appropriate source for the given broker type."""
    if broker_type == "paper" or adapter is None:
        return SyntheticSource(bot_id=bot_id, symbol_namespace=symbol_namespace)
    return LiveAdapterSource(adapter=adapter)
