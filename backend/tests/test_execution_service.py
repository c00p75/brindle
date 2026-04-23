import pytest

from app.adapters.brokers.base import BrokerConfig
from app.adapters.brokers.factory import create_adapter
from app.execution.models import OrderIntent, OrderType, Side
from app.execution.service import ExecutionService
from app.risk.engine import PortfolioSnapshot, RiskEngine
from app.risk.models import RiskLimits


@pytest.mark.asyncio
async def test_execution_service_routes_to_adapter_after_risk():
    adapter = create_adapter(BrokerConfig(
        type="paper", environment="paper", account_id="a",
        credential_ref="secret://paper/none", symbol_namespace="paper",
    ))
    await adapter.connect()
    risk = RiskEngine(RiskLimits(
        max_position_notional=10_000, max_total_exposure=50_000,
        max_daily_loss=1_000, max_drawdown_pct=20, max_open_orders=10,
    ))
    svc = ExecutionService(adapter=adapter, risk=risk)
    intent = OrderIntent(
        bot_id="bot_1", strategy_id="s", client_order_id="c-1",
        symbol="EUR/USD", side=Side.BUY, order_type=OrderType.MARKET,
        notional=5_000, config_version=1,
    )
    r = await svc.execute(intent, PortfolioSnapshot(), 1.10)
    assert r.status.value == "filled"
    assert r.adapter_id == "paper"


@pytest.mark.asyncio
async def test_execution_service_blocks_risk_violation():
    adapter = create_adapter(BrokerConfig(
        type="paper", environment="paper", account_id="a",
        credential_ref="secret://paper/none", symbol_namespace="paper",
    ))
    await adapter.connect()
    risk = RiskEngine(RiskLimits(
        max_position_notional=1_000, max_total_exposure=50_000,
        max_daily_loss=1_000, max_drawdown_pct=20, max_open_orders=10,
    ))
    svc = ExecutionService(adapter=adapter, risk=risk)
    intent = OrderIntent(
        bot_id="bot_1", strategy_id="s", client_order_id="c-2",
        symbol="EUR/USD", side=Side.BUY, order_type=OrderType.MARKET,
        notional=5_000, config_version=1,
    )
    r = await svc.execute(intent, PortfolioSnapshot(), 1.10)
    assert r.status.value == "rejected"
    assert "risk" in (r.reason or "").lower()
