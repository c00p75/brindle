"""Execution service — the single gateway between strategies and adapters.

Strategies MUST NOT call adapters directly. This service:
1. Runs risk checks
2. Routes to the bot's bound broker adapter
3. Records normalized results and audit
"""
from __future__ import annotations

from app.adapters.brokers.base import AdapterHealth, BrokerAdapter
from app.alerts.models import Severity
from app.alerts.service import emit as emit_alert
from app.audit.service import record as audit
from app.execution.models import (
    ExecutionResult,
    ExecutionStatus,
    OrderIntent,
)
from app.risk.engine import PortfolioSnapshot, RiskEngine


class ExecutionService:
    def __init__(self, *, adapter: BrokerAdapter, risk: RiskEngine, actor_email: str = "system", actor_role: str = "system") -> None:
        self.adapter = adapter
        self.risk = risk
        self.actor_email = actor_email
        self.actor_role = actor_role

    async def execute(self, intent: OrderIntent, portfolio: PortfolioSnapshot, mark_price: float) -> ExecutionResult:
        # 1) Health gate
        health = await self.adapter.health_check()
        if health in {AdapterHealth.DISCONNECTED, AdapterHealth.ERROR}:
            emit_alert(
                severity=Severity.CRITICAL,
                source="execution",
                message=f"adapter '{self.adapter.id}' unhealthy: {health}",
                bot_id=intent.bot_id,
            )
            result = ExecutionResult(
                status=ExecutionStatus.REJECTED,
                client_order_id=intent.client_order_id,
                reason=f"adapter unhealthy: {health.value}",
                adapter_id=self.adapter.id,
                bot_id=intent.bot_id,
                config_version=intent.config_version,
            )
            self._audit(intent, result)
            return result

        # 2) Risk gate
        decision = self.risk.check(intent, portfolio, mark_price)
        if not decision.allowed:
            emit_alert(
                severity=Severity.WARNING,
                source="risk",
                message=f"risk rejection: {decision.reason}",
                bot_id=intent.bot_id,
            )
            result = ExecutionResult(
                status=ExecutionStatus.REJECTED,
                client_order_id=intent.client_order_id,
                reason=f"risk: {decision.reason}",
                adapter_id=self.adapter.id,
                bot_id=intent.bot_id,
                config_version=intent.config_version,
            )
            self._audit(intent, result)
            return result

        # 3) Route
        result = await self.adapter.place_order(intent)
        self._audit(intent, result)
        return result

    def _audit(self, intent: OrderIntent, result: ExecutionResult) -> None:
        audit(
            actor_email=self.actor_email,
            actor_role=self.actor_role,
            action="execution.attempt",
            resource_type="order",
            resource_id=result.client_order_id,
            metadata={
                "adapter": self.adapter.id,
                "bot_id": intent.bot_id,
                "config_version": intent.config_version,
                "symbol": intent.symbol,
                "side": intent.side.value,
                "order_type": intent.order_type.value,
                "status": result.status.value,
                "reason": result.reason,
            },
            outcome="ok" if result.status in {ExecutionStatus.ACCEPTED, ExecutionStatus.FILLED, ExecutionStatus.PARTIALLY_FILLED} else "error",
        )
