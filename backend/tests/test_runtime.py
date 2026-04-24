import asyncio

import pytest

from tests.conftest import auth_headers


def make_config(bot_id: str) -> dict:
    return {
        "bot_id": bot_id,
        "version": 1,
        "name": "rt-test",
        "strategy": {"strategy_id": "trend_v1", "params": {"fast": 2, "slow": 4, "qty": 1000}},
        "risk": {
            "max_position_notional": 50_000,
            "max_total_exposure": 200_000,
            "max_daily_loss": 5_000,
            "max_drawdown_pct": 50,
            "max_open_orders": 20,
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
    }


@pytest.mark.asyncio
async def test_runtime_starts_stops_via_lifecycle(client, admin_token):
    r = client.post("/api/bots", json={"name": "rt"}, headers=auth_headers(admin_token))
    bot_id = r.json()["id"]
    r = client.post(f"/api/bots/{bot_id}/configs", json=make_config(bot_id), headers=auth_headers(admin_token))
    v = r.json()["version"]
    client.post(f"/api/bots/{bot_id}/configs/{v}/validate", headers=auth_headers(admin_token))
    client.post(
        f"/api/bots/{bot_id}/configs/{v}/apply",
        json={"typed_confirmation": "APPLY RISK CHANGE"},
        headers=auth_headers(admin_token),
    )

    r = client.post(f"/api/bots/{bot_id}/start", headers=auth_headers(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "running"

    from app.runtime.manager import get_runtime_manager
    assert get_runtime_manager().is_running(bot_id)

    # let the loop tick at least once
    await asyncio.sleep(1.5)

    r = client.post(f"/api/bots/{bot_id}/stop", headers=auth_headers(admin_token))
    assert r.status_code == 200
    assert r.json()["state"] == "halted"
    assert not get_runtime_manager().is_running(bot_id)


@pytest.mark.asyncio
async def test_unknown_strategy_id_fails_validation(client, admin_token):
    r = client.post("/api/bots", json={"name": "x"}, headers=auth_headers(admin_token))
    bot_id = r.json()["id"]
    cfg = make_config(bot_id)
    cfg["strategy"]["strategy_id"] = "nonexistent_strategy"
    r = client.post(f"/api/bots/{bot_id}/configs", json=cfg, headers=auth_headers(admin_token))
    v = r.json()["version"]
    r = client.post(f"/api/bots/{bot_id}/configs/{v}/validate", headers=auth_headers(admin_token))
    assert r.json()["status"] == "draft"
    assert any("strategy_id" in e for e in r.json()["validation_errors"])


def test_strategies_endpoint_exposes_registry(client, admin_token):
    r = client.post("/api/bots", json={"name": "y"}, headers=auth_headers(admin_token))
    bot_id = r.json()["id"]
    r = client.get(f"/api/bots/{bot_id}/configs/strategies", headers=auth_headers(admin_token))
    assert r.status_code == 200
    assert "trend_v1" in r.json()
