from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.adapters.brokers.base import BrokerConfig
from app.risk.models import RiskLimits


class BotState(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    HALTED = "halted"
    ERROR = "error"
    ARCHIVED = "archived"


class StrategyConfig(BaseModel):
    strategy_id: str  # reference into the strategy registry
    params: dict = Field(default_factory=dict)


class BotConfig(BaseModel):
    """The full, validated configuration for a single bot version."""

    bot_id: str
    version: int
    name: str
    description: str | None = None
    strategy: StrategyConfig
    risk: RiskLimits
    broker: BrokerConfig
    symbols: list[str]  # canonical symbols this bot trades


class Bot(BaseModel):
    id: str
    name: str
    owner_email: str
    state: BotState = BotState.DRAFT
    active_config_version: int | None = None
    allocation: float | None = None
    created_at_ms: int
    updated_at_ms: int
    starting_balance: float | None = None
    starting_balance_currency: str | None = None
    starting_balance_at_ms: int | None = None
