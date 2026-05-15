from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path

from app.strategies.base import Strategy
from app.strategies.bollinger import BollingerV1
from app.strategies.dca import DcaV1
from app.strategies.deriv import DerivV1
from app.strategies.grid import GridV1
from app.strategies.grid_v2 import GridV2
from app.strategies.macd import MacdV1
from app.strategies.market_making import MarketMakingV1
from app.strategies.orb import OrbV1
from app.strategies.range import RangeV1
from app.strategies.regime import RegimeV1
from app.strategies.scalp import ScalpV1
from app.strategies.trend import TrendV1
from app.strategies.vol_breakout import VolBreakoutV1

log = logging.getLogger("strategies")

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "trend_v1": TrendV1,
    "deriv_v1": DerivV1,
    "bollinger_v1": BollingerV1,
    "macd_v1": MacdV1,
    "regime_v1": RegimeV1,
    "grid_v1": GridV1,
    "grid_v2": GridV2,
    "dca_v1": DcaV1,
    "orb_v1": OrbV1,
    "vol_breakout_v1": VolBreakoutV1,
    "scalp_v1": ScalpV1,
    "range_v1": RangeV1,
    "mm_v1": MarketMakingV1,
}


def _load_user_plugins() -> None:
    """Discover any user-supplied strategies in app/strategies/user/ and register them.

    A plugin is a module that defines one or more classes with `id: str` (string
    constant) and `PARAM_SCHEMA: dict`. It must also implement `on_data(ctx)`
    and ideally `debug_state(ctx)`. Drop a file in app/strategies/user/ and
    restart the backend — no further registration required.

    Failures during plugin import are logged but do not block startup; a
    broken plugin must not bring down the platform.
    """
    user_dir = Path(__file__).parent / "user"
    if not user_dir.is_dir():
        return
    for mod_info in pkgutil.iter_modules([str(user_dir)]):
        full = f"app.strategies.user.{mod_info.name}"
        try:
            mod = importlib.import_module(full)
        except Exception as e:  # noqa: BLE001
            log.warning("plugin import failed %s: %s", full, e)
            continue
        for attr in dir(mod):
            obj = getattr(mod, attr)
            if not isinstance(obj, type):
                continue
            sid = getattr(obj, "id", None)
            if not isinstance(sid, str):
                continue
            if not callable(getattr(obj, "on_data", None)):
                continue
            if sid in STRATEGY_REGISTRY:
                log.warning("plugin %s tried to override built-in strategy %r", full, sid)
                continue
            STRATEGY_REGISTRY[sid] = obj
            log.info("registered user strategy %s from %s", sid, full)


_load_user_plugins()


def is_known_strategy(strategy_id: str) -> bool:
    return strategy_id in STRATEGY_REGISTRY


def list_strategies() -> list[str]:
    return sorted(STRATEGY_REGISTRY.keys())


def get_param_schema(strategy_id: str) -> dict[str, object]:
    """Return the strategy's accepted params and their defaults.

    Empty dict if the strategy is unknown or doesn't declare a schema.
    """
    cls = STRATEGY_REGISTRY.get(strategy_id)
    if cls is None:
        return {}
    return dict(getattr(cls, "PARAM_SCHEMA", {}))


def list_strategy_schemas() -> dict[str, dict[str, object]]:
    """Return param schemas for every registered strategy."""
    return {sid: get_param_schema(sid) for sid in list_strategies()}


def create_strategy(strategy_id: str) -> Strategy:
    try:
        cls = STRATEGY_REGISTRY[strategy_id]
    except KeyError as e:
        raise ValueError(f"unknown strategy: {strategy_id}") from e
    return cls()
