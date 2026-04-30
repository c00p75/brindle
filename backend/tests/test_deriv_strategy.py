"""Unit tests for deriv_v1 strategy."""
import pytest

from app.strategies.base import Bar, StrategyContext
from app.strategies.deriv import DerivV1, _rsi, _sma
from app.strategies.registry import is_known_strategy


def _bars(prices: list[float], symbol: str = "EUR/USD") -> list[Bar]:
    return [
        Bar(symbol=symbol, ts_ms=1000 + i, open=p, high=p, low=p, close=p)
        for i, p in enumerate(prices)
    ]


def _ctx(prices: list[float], params: dict | None = None) -> StrategyContext:
    return StrategyContext(
        bot_id="b1",
        strategy_id="deriv_v1",
        symbol="EUR/USD",
        config_version=1,
        params=params or {"sma_period": 5, "rsi_period": 5, "stake": 10.0, "cooldown_ticks": 0},
        bars=_bars(prices),
        current_position_qty=0.0,
        mark_price=prices[-1],
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_deriv_v1_in_registry():
    assert is_known_strategy("deriv_v1")


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def test_sma_basic():
    assert _sma([1.0, 2.0, 3.0], 3) == pytest.approx(2.0)


def test_sma_insufficient():
    assert _sma([1.0, 2.0], 3) is None


def test_rsi_all_gains():
    # Steadily increasing → RSI should be 100
    prices = [float(i) for i in range(20)]
    result = _rsi(prices, 14)
    assert result == pytest.approx(100.0)


def test_rsi_all_losses():
    # Steadily decreasing → RSI should be near 0
    prices = [float(20 - i) for i in range(20)]
    result = _rsi(prices, 14)
    assert result == pytest.approx(0.0)


def test_rsi_insufficient():
    assert _rsi([1.0, 2.0], 5) is None


# ---------------------------------------------------------------------------
# No signal
# ---------------------------------------------------------------------------

def test_no_signal_insufficient_data():
    s = DerivV1()
    assert s.on_data(_ctx([1.0, 1.0, 1.0])) == []


def test_no_signal_flat_market():
    s = DerivV1()
    # Flat prices → RSI stays around 50, no crossover through OB/OS thresholds
    prices = [1.0] * 30
    assert s.on_data(_ctx(prices)) == []


# ---------------------------------------------------------------------------
# Uses notional, not quantity
# ---------------------------------------------------------------------------

def test_signal_uses_notional():
    """Any signal emitted should use notional (stake), not quantity."""
    s = DerivV1()
    # Build a scenario with RSI crossing above oversold + price > SMA
    # Downtrend then sudden recovery
    prices = [1.0] * 10 + [0.99, 0.98, 0.97, 0.96, 0.95, 0.94, 0.95, 0.96, 0.97, 0.98, 0.99, 1.0, 1.01, 1.02]
    ctx = _ctx(prices, params={"sma_period": 5, "rsi_period": 5, "stake": 15.0, "cooldown_ticks": 0,
                               "rsi_oversold": 30, "rsi_overbought": 70})
    intents = s.on_data(ctx)
    # Whether or not a signal fires, verify that if it does it uses notional
    for intent in intents:
        assert intent.notional is not None
        assert intent.quantity is None
        assert intent.notional == 15.0


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------

def test_cooldown_suppresses_signal():
    """After a signal fires, further signals are suppressed during cooldown."""
    s = DerivV1()

    params = {"sma_period": 5, "rsi_period": 5, "stake": 10.0, "cooldown_ticks": 100,
              "rsi_oversold": 30, "rsi_overbought": 70}

    # Seed the prev_rsi with a value below oversold so next call detects a crossover
    s._prev_rsi["EUR/USD"] = 25.0
    # Force cooldown counter to be past cooldown so signal can fire
    s._ticks_since_trade["EUR/USD"] = 100

    # Craft prices where RSI is now above 30 and price > SMA → should trigger BUY
    prices_recovery = [1.0] * 10 + [0.99, 0.98, 0.97, 0.96, 0.95, 0.96, 0.97, 0.98, 0.99, 1.0, 1.01, 1.02]
    result1 = s.on_data(_ctx(prices_recovery, params=params))
    assert len(result1) == 1  # should fire
    assert result1[0].side.value == "buy"

    # Second call immediately → still in cooldown (counter was reset to 0)
    result2 = s.on_data(_ctx(prices_recovery, params=params))
    assert result2 == []  # suppressed


# ---------------------------------------------------------------------------
# Invalid params
# ---------------------------------------------------------------------------

def test_invalid_params():
    s = DerivV1()
    prices = [1.0] * 30
    assert s.on_data(_ctx(prices, params={"sma_period": 0})) == []
    assert s.on_data(_ctx(prices, params={"rsi_period": -1})) == []
    assert s.on_data(_ctx(prices, params={"stake": 0})) == []
