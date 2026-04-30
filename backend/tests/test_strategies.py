import pytest

from app.strategies.base import Bar, StrategyContext
from app.strategies.registry import create_strategy, is_known_strategy, list_strategies
from app.strategies.trend import TrendV1


def test_registry_lists_known():
    assert "trend_v1" in list_strategies()
    assert "deriv_v1" in list_strategies()
    assert is_known_strategy("trend_v1")
    assert is_known_strategy("deriv_v1")
    assert not is_known_strategy("nope")


def test_factory_unknown_raises():
    with pytest.raises(ValueError):
        create_strategy("nope")


def _bars(prices: list[float], symbol: str = "EUR/USD") -> list[Bar]:
    return [
        Bar(symbol=symbol, ts_ms=1000 + i, open=p, high=p, low=p, close=p)
        for i, p in enumerate(prices)
    ]


def _ctx(prices: list[float], position: float = 0.0) -> StrategyContext:
    return StrategyContext(
        bot_id="b1",
        strategy_id="trend_v1",
        symbol="EUR/USD",
        config_version=1,
        # Disable guardrails for legacy tests so crossover behavior is tested
        params={"fast": 2, "slow": 4, "qty": 100, "min_cross_pct": 0.0, "cooldown_ticks": 0},
        bars=_bars(prices),
        current_position_qty=position,
        mark_price=prices[-1],
    )


def test_trend_v1_no_signal_when_insufficient_data():
    s = TrendV1()
    assert s.on_data(_ctx([1.0, 1.0, 1.0])) == []


def test_trend_v1_buy_on_cross_up_from_flat():
    s = TrendV1()
    # Slow lookback 4 + 1 = 5 bars min. Crafted so fast crosses above slow on the last bar.
    intents = s.on_data(_ctx([1.0, 1.0, 1.0, 1.0, 1.5]))
    assert len(intents) == 1
    assert intents[0].side.value == "buy"
    assert intents[0].quantity == 100


def test_trend_v1_sell_on_cross_down_from_flat():
    s = TrendV1()
    intents = s.on_data(_ctx([1.0, 1.0, 1.0, 1.0, 0.5]))
    assert len(intents) == 1
    assert intents[0].side.value == "sell"
    assert intents[0].quantity == 100


def test_trend_v1_flips_when_already_long():
    s = TrendV1()
    intents = s.on_data(_ctx([1.0, 1.0, 1.0, 1.0, 0.5], position=100))
    assert len(intents) == 1
    # was +100, target -100, delta -200 → sell 200
    assert intents[0].side.value == "sell"
    assert intents[0].quantity == 200


def test_trend_v1_cooldown_suppresses():
    """After a signal, further signals are suppressed during cooldown."""
    s = TrendV1()
    params = {"fast": 2, "slow": 4, "qty": 100, "min_cross_pct": 0.0, "cooldown_ticks": 5}
    ctx1 = StrategyContext(
        bot_id="b1", strategy_id="trend_v1", symbol="EUR/USD", config_version=1,
        params=params, bars=_bars([1.0, 1.0, 1.0, 1.0, 1.5]),
        current_position_qty=0.0, mark_price=1.5,
    )
    result1 = s.on_data(ctx1)
    assert len(result1) == 1  # should fire

    # Second call immediately → still in cooldown
    ctx2 = StrategyContext(
        bot_id="b1", strategy_id="trend_v1", symbol="EUR/USD", config_version=1,
        params=params, bars=_bars([1.0, 1.0, 1.0, 1.0, 1.5, 2.0]),
        current_position_qty=100.0, mark_price=2.0,
    )
    result2 = s.on_data(ctx2)
    assert result2 == []  # suppressed


def test_trend_v1_min_cross_pct_filters_noise():
    """Tiny crossovers below min_cross_pct are filtered out."""
    s = TrendV1()
    # This crossover is only ~0.01% which is way below a 1% threshold
    params = {"fast": 2, "slow": 4, "qty": 100, "min_cross_pct": 1.0, "cooldown_ticks": 0}
    ctx = StrategyContext(
        bot_id="b1", strategy_id="trend_v1", symbol="EUR/USD", config_version=1,
        params=params, bars=_bars([1.0, 1.0, 1.0, 1.0, 1.0001]),
        current_position_qty=0.0, mark_price=1.0001,
    )
    assert s.on_data(ctx) == []
