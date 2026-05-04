from __future__ import annotations

from app.adapters.brokers.base import BrokerAdapter, BrokerConfig
from app.adapters.brokers.deriv_adapter import DerivAdapter
from app.adapters.brokers.paper_adapter import PaperAdapter

# Canonical adapter IDs. Unknown ids must fail validation.
ADAPTER_REGISTRY: dict[str, type[BrokerAdapter]] = {
    "paper": PaperAdapter,
    "deriv": DerivAdapter,
}


def is_known_adapter(adapter_id: str) -> bool:
    return adapter_id in ADAPTER_REGISTRY


def list_adapters() -> list[str]:
    return sorted(ADAPTER_REGISTRY.keys())


def adapter_class(adapter_id: str) -> type[BrokerAdapter]:
    try:
        return ADAPTER_REGISTRY[adapter_id]
    except KeyError as e:
        raise ValueError(f"unknown adapter: {adapter_id}") from e


# Allowed environments per adapter. "live" is explicitly forbidden
# platform-wide while PAPER_TRADING_ONLY is set.
ALLOWED_ENVIRONMENTS: dict[str, set[str]] = {
    "paper": {"paper"},
    "deriv": {"demo"},
}


def validate_environment(adapter_id: str, environment: str) -> None:
    allowed = ALLOWED_ENVIRONMENTS.get(adapter_id, set())
    if environment not in allowed:
        raise ValueError(
            f"environment '{environment}' not allowed for adapter '{adapter_id}'. "
            f"allowed: {sorted(allowed)}"
        )


def validate_broker_config(config: BrokerConfig) -> list[str]:
    """Return list of validation errors. Empty list = valid."""
    errors: list[str] = []
    if not is_known_adapter(config.type):
        errors.append(f"unknown adapter type: {config.type}")
        return errors
    try:
        validate_environment(config.type, config.environment)
    except ValueError as e:
        errors.append(str(e))
    if not config.account_id:
        errors.append("account_id is required")
    if not config.credential_ref:
        errors.append("credential_ref is required")
    if config.type != "paper" and not config.credential_ref.startswith("secret://"):
        errors.append("credential_ref must be a secret reference (secret://...)")
    if not config.symbol_namespace:
        errors.append("symbol_namespace is required")
    return errors
