"""Persistence proof: data written through the service layer survives a
simulated restart (engine reset + re-init on the SAME backing file)."""
from __future__ import annotations

import os
import tempfile

import pytest

from app.auth.service import seed_default_users
from app.core.settings import get_settings
from app.db.engine import init_db, reset_engine


@pytest.fixture
def reset_store():
    # Skip the global autouse in-memory DB for this module.
    yield


@pytest.fixture(autouse=True)
def sqlite_file(tmp_path, monkeypatch):
    path = tmp_path / "persist.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path}")
    monkeypatch.setenv("SUPER_ADMIN_EMAIL", "persist-admin@example.com")
    monkeypatch.setenv("SUPER_ADMIN_PASSWORD", "persist12345")
    monkeypatch.setenv("SEED_DEMO_USERS", "false")
    get_settings.cache_clear()
    reset_engine()
    init_db()
    seed_default_users()
    yield
    reset_engine()
    get_settings.cache_clear()


def test_bot_and_config_survive_restart():
    from app.bots import service as bot_service
    from app.bots.models import BotConfig
    from app.configs import service as config_service

    bot = bot_service.create(
        name="persist-bot",
        owner_email="persist-admin@example.com",
        actor_email="persist-admin@example.com",
        actor_role="admin",
    )
    cfg = BotConfig.model_validate({
        "bot_id": bot.id,
        "version": 1,
        "name": "persist",
        "strategy": {"strategy_id": "trend_v1", "params": {}},
        "risk": {
            "max_position_notional": 1000,
            "max_total_exposure": 5000,
            "max_daily_loss": 200,
            "max_drawdown_pct": 10,
            "max_open_orders": 3,
            "kill_switch": False,
        },
        "broker": {
            "type": "paper",
            "environment": "paper",
            "account_id": "a",
            "credential_ref": "secret://paper/none",
            "symbol_namespace": "paper",
        },
        "symbols": ["EUR/USD"],
    })
    draft = config_service.create_draft(
        actor_email="persist-admin@example.com", actor_role="admin", config=cfg
    )
    validated = config_service.validate(
        actor_email="persist-admin@example.com",
        actor_role="admin",
        bot_id=bot.id,
        version=draft.version,
    )
    assert validated.validation_errors == []
    applied = config_service.apply(
        actor_email="persist-admin@example.com",
        actor_role="admin",
        bot_id=bot.id,
        version=draft.version,
        typed_confirmation="APPLY RISK CHANGE",
    )
    assert applied.status.value == "applied"
    bot_id = bot.id

    # Simulate a process restart: drop the engine, rebuild against the SAME file.
    reset_engine()
    init_db()

    reloaded_bot = bot_service.get(bot_id)
    assert reloaded_bot is not None
    assert reloaded_bot.name == "persist-bot"

    versions = config_service.list_versions(bot_id)
    assert len(versions) == 1
    assert versions[0].status.value == "applied"
    assert config_service.active_version(bot_id).version == 1

    from app.audit.service import list_events
    actions = [e.action for e in list_events()]
    assert "bot.create" in actions
    assert "config.apply" in actions
