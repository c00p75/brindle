"""Tests for MarketDataSource implementations and staleness detection."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.marketdata.source import LiveAdapterSource, SyntheticSource, build_source
from app.adapters.brokers.base import Ticker
from app.core.time import now_epoch_ms


def _ticker(bid: float, ask: float) -> Ticker:
    return Ticker(symbol="EUR/USD", bid=bid, ask=ask, ts_ms=now_epoch_ms())


# ---------------------------------------------------------------------------
# SyntheticSource
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_synthetic_source_never_stale():
    src = SyntheticSource("bot_syn")
    await src.warm_up("EUR/USD", n=5)
    assert not src.is_stale("EUR/USD")


@pytest.mark.asyncio
async def test_synthetic_source_history_grows():
    src = SyntheticSource("bot_syn2")
    for _ in range(10):
        await src.next_bar("EUR/USD")
    assert len(src.history("EUR/USD")) == 10


@pytest.mark.asyncio
async def test_synthetic_source_bar_fields():
    src = SyntheticSource("bot_syn3")
    bar = await src.next_bar("EUR/USD")
    assert bar is not None
    assert bar.symbol == "EUR/USD"
    assert bar.high >= bar.low
    assert bar.open > 0
    assert bar.close > 0


# ---------------------------------------------------------------------------
# LiveAdapterSource
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_live_source_returns_bar():
    adapter = AsyncMock()
    adapter.get_ticker.return_value = _ticker(1.0999, 1.1001)
    src = LiveAdapterSource(adapter)
    bar = await src.next_bar("EUR/USD")
    assert bar is not None
    assert bar.symbol == "EUR/USD"
    assert bar.close == pytest.approx(1.1000, abs=1e-4)


@pytest.mark.asyncio
async def test_live_source_not_stale_on_fresh_tick():
    adapter = AsyncMock()
    adapter.get_ticker.return_value = _ticker(1.0999, 1.1001)
    src = LiveAdapterSource(adapter)
    await src.next_bar("EUR/USD")
    assert not src.is_stale("EUR/USD")


@pytest.mark.asyncio
async def test_live_source_stale_after_threshold():
    adapter = AsyncMock()
    # Ticker timestamp 60 seconds in the past → definitely stale
    old_ts = now_epoch_ms() - 60_000
    t = Ticker(symbol="EUR/USD", bid=1.0999, ask=1.1001, ts_ms=old_ts)
    adapter.get_ticker.return_value = t
    src = LiveAdapterSource(adapter, stale_threshold_ms=5_000)  # 5 s threshold
    await src.next_bar("EUR/USD")
    assert src.is_stale("EUR/USD")


@pytest.mark.asyncio
async def test_live_source_not_stale_before_any_tick():
    adapter = AsyncMock()
    src = LiveAdapterSource(adapter)
    # No ticks yet — not stale (just uninitialized)
    assert not src.is_stale("EUR/USD")


@pytest.mark.asyncio
async def test_live_source_returns_none_on_adapter_error():
    adapter = AsyncMock()
    adapter.get_ticker.side_effect = Exception("network error")
    src = LiveAdapterSource(adapter)
    bar = await src.next_bar("EUR/USD")
    assert bar is None


@pytest.mark.asyncio
async def test_live_source_history_cap():
    adapter = AsyncMock()
    adapter.get_ticker.return_value = _ticker(1.0999, 1.1001)
    src = LiveAdapterSource(adapter, history_cap=5)
    for _ in range(10):
        await src.next_bar("EUR/USD")
    assert len(src.history("EUR/USD")) == 5


@pytest.mark.asyncio
async def test_live_source_ohlc_coherent():
    adapter = AsyncMock()
    # Two ticks at different prices
    adapter.get_ticker.side_effect = [
        _ticker(1.0999, 1.1001),
        _ticker(1.1009, 1.1011),
    ]
    src = LiveAdapterSource(adapter)
    bar1 = await src.next_bar("EUR/USD")
    bar2 = await src.next_bar("EUR/USD")
    assert bar1 is not None and bar2 is not None
    assert bar2.open == pytest.approx(bar1.close, abs=1e-5)  # open = prev close
    assert bar2.high >= bar2.low


# ---------------------------------------------------------------------------
# build_source factory
# ---------------------------------------------------------------------------

def test_build_source_paper_returns_synthetic():
    adapter = MagicMock()
    src = build_source("bot_x", "paper", adapter, "paper")
    assert isinstance(src, SyntheticSource)


def test_build_source_oanda_returns_live():
    adapter = MagicMock()
    src = build_source("bot_x", "oanda", adapter, "oanda")
    assert isinstance(src, LiveAdapterSource)


def test_build_source_no_adapter_returns_synthetic():
    src = build_source("bot_x", "oanda", None, "oanda")
    assert isinstance(src, SyntheticSource)
