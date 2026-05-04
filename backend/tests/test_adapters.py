import pytest

from app.adapters.brokers.base import AdapterHealth, BrokerConfig
from app.adapters.brokers.factory import create_adapter
from app.adapters.brokers.paper_adapter import PaperAdapter
from app.adapters.brokers.registry import (
    is_known_adapter,
    list_adapters,
    validate_broker_config,
)
from app.adapters.symbols.mapping import get_mapper
from app.execution.models import OrderIntent, OrderType, Side


def paper_config() -> BrokerConfig:
    return BrokerConfig(
        type="paper",
        environment="paper",
        account_id="acct-paper-1",
        credential_ref="secret://paper/none",
        symbol_namespace="paper",
    )


def test_registry_lists_known_adapters():
    assert "paper" in list_adapters()
    assert is_known_adapter("paper")
    assert not is_known_adapter("nope")


def test_factory_builds_paper_adapter():
    a = create_adapter(paper_config())
    assert isinstance(a, PaperAdapter)
    assert a.id == "paper"


def test_factory_rejects_unknown_type():
    cfg = paper_config().model_copy(update={"type": "unknown"})
    with pytest.raises(ValueError):
        create_adapter(cfg)


def test_validate_broker_config_requires_secret_ref_for_real_brokers():
    errs = validate_broker_config(BrokerConfig(
        type="deriv",
        environment="demo",
        account_id="a",
        credential_ref="inline-secret",
        symbol_namespace="deriv",
    ))
    assert any("secret reference" in e for e in errs)


def test_symbol_mapper_canonical_roundtrip():
    m = get_mapper("deriv")
    assert m.to_native("EUR/USD") == "frxEURUSD"
    assert m.to_canonical("frxEURUSD") == "EUR/USD"


def test_symbol_mapper_rejects_unmapped():
    m = get_mapper("deriv")
    with pytest.raises(ValueError):
        m.to_native("XYZ/ABC")


@pytest.mark.asyncio
async def test_paper_adapter_market_buy_fills_and_updates_position():
    adapter = create_adapter(paper_config())
    await adapter.connect()
    assert await adapter.health_check() == AdapterHealth.HEALTHY

    intent = OrderIntent(
        bot_id="bot_1",
        strategy_id="strat_1",
        client_order_id="coid-1",
        symbol="EUR/USD",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=1000.0,
        config_version=1,
    )
    result = await adapter.place_order(intent)
    assert result.status.value == "filled"
    assert result.filled_qty == 1000.0
    positions = await adapter.get_positions()
    assert positions[0].symbol == "EUR/USD"
    assert positions[0].quantity == 1000.0


@pytest.mark.asyncio
async def test_paper_adapter_limit_order_not_crossing_is_accepted_open():
    adapter = create_adapter(paper_config())
    await adapter.connect()
    ticker = await adapter.get_ticker("EUR/USD")
    intent = OrderIntent(
        bot_id="bot_1",
        strategy_id="strat_1",
        client_order_id="coid-2",
        symbol="EUR/USD",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=1000.0,
        limit_price=ticker.ask - 0.01,  # below ask -> not crossing
        config_version=1,
    )
    result = await adapter.place_order(intent)
    assert result.status.value == "accepted"
    open_orders = await adapter.get_open_orders()
    assert len(open_orders) == 1
