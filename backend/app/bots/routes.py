import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.auth.deps import require
from app.auth.models import User
from app.bots import service as bot_service
from app.bots.models import Bot
from app.configs import service as config_service
from app.core.eventbus import get_event_bus
from app.execution import persistence as exec_persistence
from app.runtime.manager import get_runtime_manager
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/bots", tags=["bots"])


class CreateBotBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.get("")
async def list_bots(_: User = Depends(require("bot:read"))) -> list[Bot]:
    bots = bot_service.list_bots()
    return [bot_service.refresh_state_from_config(b) for b in bots]


@router.post("", status_code=201)
async def create_bot(body: CreateBotBody, user: User = Depends(require("bot:create"))) -> Bot:
    return bot_service.create(
        name=body.name,
        owner_email=user.email,
        actor_email=user.email,
        actor_role=user.role.value,
    )


@router.get("/{bot_id}")
async def get_bot(bot_id: str, _: User = Depends(require("bot:read"))) -> Bot:
    bot = bot_service.get(bot_id)
    if bot is None:
        raise HTTPException(404, "bot not found")
    return bot_service.refresh_state_from_config(bot)


@router.post("/{bot_id}/start")
async def start_bot(bot_id: str, user: User = Depends(require("bot:start"))) -> Bot:
    try:
        bot = bot_service.start(bot_id, actor_email=user.email, actor_role=user.role.value)
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        await get_runtime_manager().start(bot)
    except Exception as e:  # noqa: BLE001
        # roll the state back to ready so the operator can retry
        try:
            bot_service.stop(bot_id, actor_email=user.email, actor_role=user.role.value)
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(500, f"runtime start failed: {e}")
    return bot


@router.post("/{bot_id}/pause")
async def pause_bot(bot_id: str, user: User = Depends(require("bot:stop"))) -> Bot:
    try:
        bot = bot_service.pause(bot_id, actor_email=user.email, actor_role=user.role.value)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await get_runtime_manager().stop(bot_id)
    return bot


@router.post("/{bot_id}/stop")
async def stop_bot(bot_id: str, user: User = Depends(require("bot:stop"))) -> Bot:
    try:
        bot = bot_service.stop(bot_id, actor_email=user.email, actor_role=user.role.value)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await get_runtime_manager().stop(bot_id)
    return bot


@router.post("/{bot_id}/archive")
async def archive_bot(bot_id: str, user: User = Depends(require("bot:archive"))) -> Bot:
    try:
        bot = bot_service.archive(bot_id, actor_email=user.email, actor_role=user.role.value)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await get_runtime_manager().stop(bot_id)
    return bot


@router.get("/{bot_id}/positions")
async def positions(bot_id: str, _: User = Depends(require("bot:read"))) -> list[dict]:
    if bot_service.get(bot_id) is None:
        raise HTTPException(404, "bot not found")
    return exec_persistence.list_positions(bot_id)


@router.get("/{bot_id}/orders")
async def orders(bot_id: str, limit: int = 100, _: User = Depends(require("bot:read"))) -> list[dict]:
    if bot_service.get(bot_id) is None:
        raise HTTPException(404, "bot not found")
    return exec_persistence.list_orders(bot_id, limit=limit)


@router.get("/{bot_id}/fills")
async def fills(bot_id: str, limit: int = 100, _: User = Depends(require("bot:read"))) -> list[dict]:
    if bot_service.get(bot_id) is None:
        raise HTTPException(404, "bot not found")
    return exec_persistence.list_fills(bot_id, limit=limit)


@router.get("/{bot_id}/active-config")
async def active_config(bot_id: str, _: User = Depends(require("config:read"))):
    bot = bot_service.get(bot_id)
    if bot is None:
        raise HTTPException(404, "bot not found")
    active = config_service.active_version(bot_id)
    return active.model_dump() if active else None


@router.get("/{bot_id}/stream")
async def stream_events(bot_id: str, request: Request, token: str = Query(...)):
    """SSE endpoint — streams real-time order/fill/position events.

    Auth is via ?token= query param because EventSource cannot send headers.
    """
    from app.auth.jwt import decode_token

    try:
        user = decode_token(token)
    except Exception:
        raise HTTPException(401, "invalid token")

    if bot_service.get(bot_id) is None:
        raise HTTPException(404, "bot not found")

    bus = get_event_bus()

    async def event_generator():
        # Send an initial heartbeat so the client knows the connection is live
        yield f"event: connected\ndata: {json.dumps({'bot_id': bot_id})}\n\n"
        async for event_type, data in bus.subscribe(bot_id):
            if await request.is_disconnected():
                break
            yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
