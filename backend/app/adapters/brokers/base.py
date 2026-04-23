from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.execution.models import ExecutionResult, OrderIntent


class AdapterHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class BrokerConfig(BaseModel):
    """Per-bot adapter configuration.

    `credential_ref` is ALWAYS a reference (e.g. "secret://...").
    Inline secrets are forbidden.
    """

    type: str  # adapter id in registry
    environment: str  # e.g. "demo" | "sandbox". Never "live" in paper-first mode.
    account_id: str
    credential_ref: str
    symbol_namespace: str
    app_id: str | None = None
    rate_limit_profile: str | None = None
    extra: dict = Field(default_factory=dict)


class Ticker(BaseModel):
    symbol: str  # canonical
    bid: float
    ask: float
    ts_ms: int


class Balance(BaseModel):
    currency: str
    available: float
    total: float


class Position(BaseModel):
    symbol: str  # canonical
    quantity: float
    avg_price: float | None = None


@runtime_checkable
class BrokerAdapter(Protocol):
    """Unified broker contract. All adapters must implement this shape."""

    id: str

    async def connect(self) -> None: ...
    async def close(self) -> None: ...

    async def get_ticker(self, symbol: str) -> Ticker: ...
    async def get_balance(self) -> list[Balance]: ...
    async def get_positions(self) -> list[Position]: ...
    async def get_open_orders(self) -> list[dict]: ...

    async def place_order(self, intent: OrderIntent) -> ExecutionResult: ...
    async def cancel_order(self, broker_order_id: str) -> bool: ...

    async def health_check(self) -> AdapterHealth: ...
