"""Canonical, broker-agnostic execution primitives.

Strategies produce OrderIntent. Adapters translate to broker-specific
requests and return ExecutionResult. Raw broker payloads must not cross
this boundary.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class TimeInForce(str, Enum):
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class ExecutionStatus(str, Enum):
    ACCEPTED = "accepted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    ERROR = "error"


class OrderIntent(BaseModel):
    """Strategy output. Broker-agnostic."""

    bot_id: str
    strategy_id: str
    client_order_id: str
    symbol: str  # canonical, e.g. "EUR/USD"
    side: Side
    order_type: OrderType
    quantity: float | None = None
    notional: float | None = None
    limit_price: float | None = None
    time_in_force: TimeInForce | None = None
    config_version: int

    @model_validator(mode="after")
    def _quantity_or_notional(self) -> "OrderIntent":
        if (self.quantity is None) == (self.notional is None):
            raise ValueError("exactly one of quantity or notional must be set")
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit orders require limit_price")
        if self.quantity is not None and self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.notional is not None and self.notional <= 0:
            raise ValueError("notional must be positive")
        return self


class ExecutionResult(BaseModel):
    """Broker-agnostic result. Raw adapter payloads live in `extra`."""

    status: ExecutionStatus
    broker_order_id: str | None = None
    client_order_id: str
    filled_qty: float | None = None
    avg_price: float | None = None
    fees: float | None = None
    raw_reference: str | None = None
    reason: str | None = None
    adapter_id: str
    bot_id: str
    config_version: int
    extra: dict[str, Any] = Field(default_factory=dict)
