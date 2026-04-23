from app.execution.models import OrderIntent, OrderType, Side
from app.risk.engine import PortfolioSnapshot, RiskEngine
from app.risk.models import RiskLimits


def make_intent(notional: float) -> OrderIntent:
    return OrderIntent(
        bot_id="bot_1",
        strategy_id="s",
        client_order_id="c-1",
        symbol="EUR/USD",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        notional=notional,
        config_version=1,
    )


def default_limits() -> RiskLimits:
    return RiskLimits(
        max_position_notional=10_000,
        max_total_exposure=50_000,
        max_daily_loss=1_000,
        max_drawdown_pct=20,
        max_open_orders=10,
    )


def test_risk_allows_within_limits():
    r = RiskEngine(default_limits())
    d = r.check(make_intent(5_000), PortfolioSnapshot(), 1.0)
    assert d.allowed, d.reason


def test_risk_blocks_oversize_position():
    r = RiskEngine(default_limits())
    d = r.check(make_intent(20_000), PortfolioSnapshot(), 1.0)
    assert not d.allowed
    assert "max_position_notional" in d.reason


def test_risk_blocks_exposure():
    r = RiskEngine(default_limits())
    d = r.check(make_intent(5_000), PortfolioSnapshot(gross_exposure=48_000), 1.0)
    assert not d.allowed
    assert "max_total_exposure" in d.reason


def test_risk_blocks_daily_loss():
    r = RiskEngine(default_limits())
    d = r.check(make_intent(1_000), PortfolioSnapshot(day_pnl=-1_200), 1.0)
    assert not d.allowed
    assert "daily loss" in d.reason


def test_kill_switch_blocks_all():
    lim = default_limits().model_copy(update={"kill_switch": True})
    d = RiskEngine(lim).check(make_intent(1_000), PortfolioSnapshot(), 1.0)
    assert not d.allowed
    assert "kill switch" in d.reason
