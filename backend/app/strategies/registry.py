from __future__ import annotations

from app.strategies.base import Strategy
from app.strategies.deriv import DerivV1
from app.strategies.trend import TrendV1

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "trend_v1": TrendV1,
    "deriv_v1": DerivV1,
}


def is_known_strategy(strategy_id: str) -> bool:
    return strategy_id in STRATEGY_REGISTRY


def list_strategies() -> list[str]:
    return sorted(STRATEGY_REGISTRY.keys())


def create_strategy(strategy_id: str) -> Strategy:
    try:
        cls = STRATEGY_REGISTRY[strategy_id]
    except KeyError as e:
        raise ValueError(f"unknown strategy: {strategy_id}") from e
    return cls()
