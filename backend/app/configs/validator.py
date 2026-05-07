"""Config validation. Deterministic, produces a report. No side effects."""
from __future__ import annotations

from app.adapters.brokers.registry import validate_broker_config
from app.adapters.symbols.mapping import get_mapper
from app.bots.models import BotConfig


def validate_bot_config(cfg: BotConfig, bot_allocation: float | None = None) -> tuple[list[str], list[str]]:
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

    if bot_allocation is not None:
        if cfg.risk.max_position_notional > bot_allocation * 5:
            warnings.append(
                f"risk.max_position_notional (${cfg.risk.max_position_notional:.0f}) "
                f"is much larger than allocation (${bot_allocation:.0f})"
            )

        stake_est = _estimate_intent_notional(cfg)
        if stake_est is not None and stake_est > cfg.risk.max_position_notional:
            errors.append(
                f"strategy will produce intents of ~${stake_est:.0f}, "
                f"exceeds risk.max_position_notional (${cfg.risk.max_position_notional:.0f}) — "
                f"every order will be rejected"
            )

    if not cfg.symbols:
        errors.append("symbols must be non-empty")

    if not cfg.strategy.strategy_id:
        errors.append("strategy.strategy_id is required")
    else:
        from app.strategies.registry import get_param_schema, is_known_strategy
        if not is_known_strategy(cfg.strategy.strategy_id):
            errors.append(f"unknown strategy_id: {cfg.strategy.strategy_id}")
        else:
            errors.extend(_validate_strategy_params(
                cfg.strategy.strategy_id,
                cfg.strategy.params,
                get_param_schema(cfg.strategy.strategy_id),
            ))

    return errors, warnings


def _estimate_intent_notional(cfg: BotConfig) -> float | None:
    params = cfg.strategy.params or {}

    # 1. Notional-based strategies (Deriv specific)
    if cfg.strategy.strategy_id in {"deriv_v1", "scalp_v1"}:
        stake = params.get("stake")
        return float(stake) if stake is not None else None

    # 2. Quantity-based strategies (Trend, Bollinger, etc.)
    # If risk_per_trade_pct is set, the strategy will ignore 'qty' and size dynamically.
    # In that case, we can't estimate a static notional easily without a price.
    if cfg.risk.risk_per_trade_pct is not None and cfg.risk.risk_per_trade_pct > 0:
        return None

    qty = params.get("qty")
    if qty is not None:
        # We don't have mark_price here, so we treat 1.0 as a floor (e.g. for crypto/forex)
        # or just return the quantity as a 'notional proxy' if the symbol is USD-denominated.
        return float(qty)

    return None


def _validate_strategy_params(
    strategy_id: str,
    params: dict,
    schema: dict[str, object],
) -> list[str]:
    """Reject unknown keys and type-incompatible values for strategy params.

    Numeric flexibility: ints satisfy floats (5 is a valid float).
    Bool is intentionally NOT treated as a valid number.
    """
    errors: list[str] = []
    if not schema:
        return errors

    for key, value in params.items():
        if key not in schema:
            allowed = ", ".join(sorted(schema.keys()))
            errors.append(
                f"strategy.params: unknown key '{key}' for {strategy_id} "
                f"(allowed: {allowed})"
            )
            continue
        expected = schema[key]
        if not _value_matches_type(value, expected):
            errors.append(
                f"strategy.params.{key}: expected {type(expected).__name__}, "
                f"got {type(value).__name__}"
            )

    return errors


def _value_matches_type(value: object, default: object) -> bool:
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, int) and not isinstance(default, bool):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(default, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, type(default))
