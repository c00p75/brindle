from __future__ import annotations

from app.adapters.brokers.base import BrokerAdapter, BrokerConfig
from app.adapters.brokers.registry import adapter_class, validate_broker_config
from app.core.settings import get_settings


def create_adapter(config: BrokerConfig) -> BrokerAdapter:
    """Construct a broker adapter from validated config.

    Fails closed on invalid config, unknown type, or live-trading
    attempts while PAPER_TRADING_ONLY is set.
    """
    errors = validate_broker_config(config)
    if errors:
        raise ValueError("invalid broker config: " + "; ".join(errors))

    settings = get_settings()
    if settings.paper_trading_only and config.environment not in {"paper", "demo", "sandbox", "practice"}:
        raise ValueError(
            f"environment '{config.environment}' not permitted under "
            "PAPER_TRADING_ONLY"
        )
    if not settings.live_trading_enabled and config.environment in {"live", "prod", "production", "real"}:
        raise ValueError("live environments are disabled on this deployment")

    cls = adapter_class(config.type)
    return cls(config)  # type: ignore[call-arg]
