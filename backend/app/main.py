from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.alerts.routes import router as alerts_router
from app.audit.routes import router as audit_router
from app.auth.routes import router as auth_router
from app.auth.service import seed_default_users
from app.bots.routes import router as bots_router
from app.configs.routes import router as configs_router
from app.core.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed default dev users. Remove before production.
    seed_default_users()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Trading Bot Platform",
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

    @app.get("/api/health", tags=["meta"])
    async def health() -> dict:
        return {
            "status": "ok",
            "paper_trading_only": settings.paper_trading_only,
            "live_trading_enabled": settings.live_trading_enabled,
        }

    app.include_router(auth_router)
    app.include_router(bots_router)
    app.include_router(configs_router)
    app.include_router(audit_router)
    app.include_router(alerts_router)
    return app


app = create_app()
