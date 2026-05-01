from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.adapters.brokers.registry import list_adapters
from app.strategies.registry import get_param_schema, list_strategies
from app.auth.deps import require
from app.auth.models import User
from app.bots import service as bot_service
from app.bots.models import BotConfig
from app.configs import service as config_service
from app.configs.diff import diff as compute_diff
from app.configs.models import ConfigVersion

router = APIRouter(prefix="/api/bots/{bot_id}/configs", tags=["configs"])


class ApplyBody(BaseModel):
    typed_confirmation: str | None = Field(
        default=None,
        description="Must be 'APPLY RISK CHANGE' for risky diffs without prior approval.",
    )


@router.get("/adapters")
async def available_adapters(bot_id: str, _: User = Depends(require("config:read"))) -> list[str]:
    bot_service.get(bot_id) or _not_found()
    return list_adapters()


@router.get("/strategies")
async def available_strategies(bot_id: str, _: User = Depends(require("config:read"))) -> list[str]:
    bot_service.get(bot_id) or _not_found()
    return list_strategies()


@router.get("/strategies/{strategy_id}/params")
async def strategy_params(
    bot_id: str, strategy_id: str, _: User = Depends(require("config:read"))
) -> dict[str, object]:
    """Return the param schema (name → default) for a strategy.

    Used by the config UI to render sensible defaults when a user picks a
    strategy, instead of leaving them to guess key names.
    """
    bot_service.get(bot_id) or _not_found()
    schema = get_param_schema(strategy_id)
    if not schema:
        raise HTTPException(404, f"unknown strategy or no schema: {strategy_id}")
    return schema


@router.get("")
async def list_versions(bot_id: str, _: User = Depends(require("config:read"))) -> list[ConfigVersion]:
    bot_service.get(bot_id) or _not_found()
    return config_service.list_versions(bot_id)


@router.post("", status_code=201)
async def create_draft(bot_id: str, body: BotConfig, user: User = Depends(require("config:draft"))) -> ConfigVersion:
    bot = bot_service.get(bot_id) or _not_found()
    if body.bot_id != bot.id:
        raise HTTPException(400, "config.bot_id must match route bot_id")
    return config_service.create_draft(
        actor_email=user.email, actor_role=user.role.value, config=body
    )


@router.get("/active")
async def active(bot_id: str, _: User = Depends(require("config:read"))) -> ConfigVersion | None:
    bot_service.get(bot_id) or _not_found()
    return config_service.active_version(bot_id)


@router.get("/{version}")
async def get_version(bot_id: str, version: int, _: User = Depends(require("config:read"))) -> ConfigVersion:
    bot_service.get(bot_id) or _not_found()
    v = config_service.get_version(bot_id, version)
    if v is None:
        raise HTTPException(404, "version not found")
    return v


@router.get("/{version}/diff")
async def version_diff(bot_id: str, version: int, _: User = Depends(require("config:read"))) -> dict:
    v = config_service.get_version(bot_id, version)
    if v is None:
        raise HTTPException(404, "version not found")
    active = config_service.active_version(bot_id)
    before = active.config.model_dump() if active else None
    return {"changes": compute_diff(before, v.config.model_dump())}


@router.post("/{version}/validate")
async def validate(bot_id: str, version: int, user: User = Depends(require("config:validate"))) -> ConfigVersion:
    try:
        return config_service.validate(
            actor_email=user.email, actor_role=user.role.value, bot_id=bot_id, version=version
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{version}/request-approval")
async def request_approval(bot_id: str, version: int, user: User = Depends(require("config:draft"))) -> ConfigVersion:
    try:
        return config_service.request_approval(
            actor_email=user.email, actor_role=user.role.value, bot_id=bot_id, version=version
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{version}/approve")
async def approve(bot_id: str, version: int, user: User = Depends(require("config:approve"))) -> ConfigVersion:
    try:
        return config_service.approve(
            actor_email=user.email, actor_role=user.role.value, bot_id=bot_id, version=version
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{version}/apply")
async def apply(bot_id: str, version: int, body: ApplyBody, user: User = Depends(require("config:apply"))) -> ConfigVersion:
    try:
        return config_service.apply(
            actor_email=user.email,
            actor_role=user.role.value,
            bot_id=bot_id,
            version=version,
            typed_confirmation=body.typed_confirmation,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/rollback/{to_version}")
async def rollback(bot_id: str, to_version: int, user: User = Depends(require("config:rollback"))) -> ConfigVersion:
    try:
        return config_service.rollback(
            actor_email=user.email,
            actor_role=user.role.value,
            bot_id=bot_id,
            to_version=to_version,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


def _not_found():
    raise HTTPException(404, "bot not found")
