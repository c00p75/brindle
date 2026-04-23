"""Risk engine. Runs BEFORE every execution. No broker calls here."""
from __future__ import annotations

from dataclasses import dataclass

from app.execution.models import OrderIntent
from app.risk.models import RiskLimits


@dataclass
class RiskDecision:
    allowed: bool
    reason: str | None = None


@dataclass
class PortfolioSnapshot:
    gross_exposure: float = 0.0
    open_orders: int = 0
    day_pnl: float = 0.0
    high_water_mark: float = 0.0
    equity: float = 0.0


class RiskEngine:
    def __init__(self, limits: RiskLimits) -> None:
        self.limits = limits

    def check(self, intent: OrderIntent, portfolio: PortfolioSnapshot, mark_price: float) -> RiskDecision:
        if self.limits.kill_switch:
            return RiskDecision(False, "kill switch active")

        if portfolio.open_orders >= self.limits.max_open_orders:
            return RiskDecision(False, "max_open_orders reached")

        notional = intent.notional
        if notional is None and intent.quantity is not None:
            notional = intent.quantity * mark_price
        if notional is None:
            return RiskDecision(False, "cannot compute intent notional")

        if notional > self.limits.max_position_notional:
            return RiskDecision(False, "exceeds max_position_notional")

        if portfolio.gross_exposure + notional > self.limits.max_total_exposure:
            return RiskDecision(False, "exceeds max_total_exposure")

        if -portfolio.day_pnl >= self.limits.max_daily_loss:
            return RiskDecision(False, "daily loss limit hit")

        if portfolio.high_water_mark > 0:
            dd_pct = (portfolio.high_water_mark - portfolio.equity) / portfolio.high_water_mark * 100
            if dd_pct >= self.limits.max_drawdown_pct:
                return RiskDecision(False, "max drawdown reached")

        return RiskDecision(True)
