"""Config validation. Deterministic, produces a report. No side effects."""
from __future__ import annotations

from app.adapters.brokers.registry import validate_broker_config
from app.adapters.symbols.mapping import get_mapper
from app.bots.models import BotConfig


def validate_bot_config(cfg: BotConfig) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    # Broker
    errors.extend(validate_broker_config(cfg.broker))

    # Symbols map cleanly in the chosen namespace
    try:
        mapper = get_mapper(cfg.broker.symbol_namespace)
        for s in cfg.symbols:
            try:
                mapper.to_native(s)
            except ValueError as e:
                errors.append(str(e))
    except ValueError as e:
        errors.append(str(e))

    # Risk invariants (pydantic already enforces basics, repeat cross-checks)
    if cfg.risk.max_total_exposure < cfg.risk.max_position_notional:
        errors.append("risk.max_total_exposure must be >= risk.max_position_notional")

    if cfg.risk.max_drawdown_pct > 50:
        warnings.append("risk.max_drawdown_pct > 50% is unusually permissive")

    if not cfg.symbols:
        errors.append("symbols must be non-empty")

    if not cfg.strategy.strategy_id:
        errors.append("strategy.strategy_id is required")
    else:
        from app.strategies.registry import is_known_strategy
        if not is_known_strategy(cfg.strategy.strategy_id):
            errors.append(f"unknown strategy_id: {cfg.strategy.strategy_id}")

    return errors, warnings
