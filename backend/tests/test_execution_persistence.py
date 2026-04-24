import pytest

from app.adapters.brokers.base import BrokerConfig
from app.adapters.brokers.factory import create_adapter
from app.execution import persistence as exec_persistence
from app.execution.models import OrderIntent, OrderType, Side
from app.execution.service import ExecutionService
from app.risk.engine import PortfolioSnapshot, RiskEngine
from app.risk.models import RiskLimits


def _paper_adapter():
    return create_adapter(BrokerConfig(
        type="paper", environment="paper", account_id="a",
        credential_ref="secret://paper/none", symbol_namespace="paper",
    ))


def _exec_service():
    risk = RiskEngine(RiskLimits(
        max_position_notional=10_000, max_total_exposure=50_000,
        max_daily_loss=1_000, max_drawdown_pct=20, max_open_orders=10,
    ))
    return ExecutionService(adapter=_paper_adapter(), risk=risk)


def _intent(client_order_id: str, qty: float, side: Side = Side.BUY) -> OrderIntent:
    return OrderIntent(
        bot_id="bot_persist",
        strategy_id="trend_v1",
        client_order_id=client_order_id,
        symbol="EUR/USD",
        side=side,
        order_type=OrderType.MARKET,
        quantity=qty,
        config_version=1,
    )


@pytest.mark.asyncio
async def test_filled_order_creates_order_fill_position():
    svc = _exec_service()
    await svc.adapter.connect()
    await svc.execute(_intent("c-1", 1000), PortfolioSnapshot(), 1.10)

    orders = exec_persistence.list_orders("bot_persist")
    fills = exec_persistence.list_fills("bot_persist")
    positions = exec_persistence.list_positions("bot_persist")
    assert len(orders) == 1 and orders[0]["status"] == "filled"
    assert len(fills) == 1 and fills[0]["quantity"] == 1000
    assert len(positions) == 1 and positions[0]["quantity"] == 1000


@pytest.mark.asyncio
async def test_position_closes_to_zero_and_realizes_pnl():
    svc = _exec_service()
    await svc.adapter.connect()
    await svc.execute(_intent("c-1", 1000, Side.BUY), PortfolioSnapshot(), 1.10)
    await svc.execute(_intent("c-2", 1000, Side.SELL), PortfolioSnapshot(), 1.10)

    positions = exec_persistence.list_positions("bot_persist")
    assert len(positions) == 1
    assert positions[0]["quantity"] == 0.0
    assert positions[0]["avg_price"] is None
    # realized_pnl computed; sign depends on tick movement, just check it's a number
    assert isinstance(positions[0]["realized_pnl"], float)


@pytest.mark.asyncio
async def test_risk_rejected_attempt_persisted_with_reason():
    risk = RiskEngine(RiskLimits(
        max_position_notional=100, max_total_exposure=1000,
        max_daily_loss=100, max_drawdown_pct=10, max_open_orders=10,
    ))
    svc = ExecutionService(adapter=_paper_adapter(), risk=risk)
    await svc.adapter.connect()
    await svc.execute(_intent("c-block", 5000), PortfolioSnapshot(), 1.10)

    orders = exec_persistence.list_orders("bot_persist")
    assert len(orders) == 1
    assert orders[0]["status"] == "rejected"
    assert "risk" in orders[0]["reason"].lower()
