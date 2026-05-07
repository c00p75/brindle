"""Strategy contract.

Strategies are pure-ish functions that take a `StrategyContext` and return
a (possibly empty) list of `OrderIntent`s. They MUST NOT call broker APIs,
DBs, or networks. The runtime feeds them data and routes their intents
through the execution service.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.execution.models import OrderIntent


class Bar(BaseModel):
    """A single OHLCV bar at some timeframe."""

    symbol: str  # canonical
    ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class StrategyContext(BaseModel):
    """Read-only view passed to a strategy on each tick."""

    bot_id: str
    strategy_id: str
    symbol: str  # canonical
    config_version: int
    params: dict = Field(default_factory=dict)
    bars: list[Bar]  # most recent first not assumed; treat as time-ordered ascending
    current_position_qty: float = 0.0
    mark_price: float
    allocation: float | None = None
    effective_balance: float = 0.0
    risk_per_trade_pct: float | None = None
    open_contract_count: int = 0
    last_trade_at_ms: int | None = None


@runtime_checkable
class Strategy(Protocol):
    id: str

    def on_data(self, ctx: StrategyContext) -> list[OrderIntent]: ...
