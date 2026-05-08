import os
from dotenv import load_dotenv

load_dotenv()

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.alerts.routes import router as alerts_router
from app.chat.routes import router as chat_router
from app.audit.routes import router as audit_router
from app.auth.routes import router as auth_router
from app.research.routes import router as research_router
from app.auth.service import seed_default_users
from app.bots.routes import router as bots_router
from app.configs.routes import router as configs_router
from app.llm.routes import router as llm_router
from app.brokers.routes import router as brokers_router
from app.core.logging_config import configure_logging
from app.core.metrics import bots_running, http_request_duration_seconds, http_requests_total
from app.core.settings import get_settings
from app.db.engine import init_db
from app.runtime.manager import get_runtime_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_db()
    seed_default_users()
    await _resume_running_bots()
    yield
    await get_runtime_manager().stop_all()


async def _resume_running_bots() -> None:
    """Re-attach runtime loops for bots that were running before a restart.

    The runtime manager is in-memory only. Any bot persisted as RUNNING needs
    its loop re-spawned on startup, otherwise it shows as live in the UI but
    never processes ticks.
    """
    import logging
    log = logging.getLogger("startup")
    from app.bots.models import BotState
    from app.bots.service import list_bots
    mgr = get_runtime_manager()
    for bot in list_bots():
        if bot.state == BotState.RUNNING:
            try:
                await mgr.start(bot)
                log.info("auto-resumed bot=%s name=%s", bot.id, bot.name)
            except Exception as exc:  # noqa: BLE001
                log.error("failed to auto-resume bot=%s: %s", bot.id, exc)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Brindle Platform",
        version="0.1.0",
        description="Paper-trading-first, broker-agnostic trading bot platform",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _metrics_middleware(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        # Normalise dynamic path params so cardinality stays low
        path = request.url.path
        http_requests_total.labels(
            method=request.method, path=path, status=response.status_code
        ).inc()
        http_request_duration_seconds.labels(
            method=request.method, path=path
        ).observe(duration)
        return response

    @app.get("/api/health", tags=["meta"])
    async def health() -> dict:
        return {
            "status": "ok",
            "paper_trading_only": settings.paper_trading_only,
            "live_trading_enabled": settings.live_trading_enabled,
        }

    @app.get("/metrics", tags=["meta"], include_in_schema=False)
    async def metrics() -> Response:
        mgr = get_runtime_manager()
        bots_running.set(len(mgr.running_ids()))
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(auth_router)
    app.include_router(bots_router)
    app.include_router(configs_router)
    app.include_router(audit_router)
    app.include_router(alerts_router)
    app.include_router(research_router)
    app.include_router(chat_router)
    app.include_router(llm_router)
    app.include_router(brokers_router)
    return app


app = create_app()
