from tests.conftest import auth_headers


def make_config(bot_id: str) -> dict:
    return {
        "bot_id": bot_id,
        "version": 1,  # server will override
        "name": "fx-test",
        "description": "test bot",
        "strategy": {"strategy_id": "trend_v1", "params": {"lookback": 20}},
        "risk": {
            "max_position_notional": 5000,
            "max_total_exposure": 20000,
            "max_daily_loss": 500,
            "max_drawdown_pct": 10,
            "max_open_orders": 5,
            "kill_switch": False,
        },
        "broker": {
            "type": "paper",
            "environment": "paper",
            "account_id": "acct-1",
            "credential_ref": "secret://paper/none",
            "symbol_namespace": "paper",
        },
        "symbols": ["EUR/USD"],
    }


def test_full_config_workflow(client, admin_token, reviewer_token):
    # create bot
    r = client.post("/api/bots", json={"name": "alpha"}, headers=auth_headers(admin_token))
    assert r.status_code == 201, r.text
    bot_id = r.json()["id"]

    # draft
    r = client.post(f"/api/bots/{bot_id}/configs", json=make_config(bot_id), headers=auth_headers(admin_token))
    assert r.status_code == 201, r.text
    v = r.json()["version"]
    assert r.json()["status"] == "draft"

    # validate
    r = client.post(f"/api/bots/{bot_id}/configs/{v}/validate", headers=auth_headers(admin_token))
    assert r.status_code == 200
    assert r.json()["status"] == "validated"
    assert r.json()["validation_errors"] == []

    # first apply: creating active config is itself risky (broker diff from nothing)
    r = client.post(
        f"/api/bots/{bot_id}/configs/{v}/apply",
        json={"typed_confirmation": "APPLY RISK CHANGE"},
        headers=auth_headers(admin_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "applied"

    # bot now READY
    r = client.get(f"/api/bots/{bot_id}", headers=auth_headers(admin_token))
    assert r.json()["state"] == "ready"
    assert r.json()["active_config_version"] == v

    # create second draft, tweak a non-risky field (description)
    cfg2 = make_config(bot_id)
    cfg2["description"] = "updated"
    r = client.post(f"/api/bots/{bot_id}/configs", json=cfg2, headers=auth_headers(admin_token))
    v2 = r.json()["version"]

    # validate + apply (non-risky, no confirmation needed)
    client.post(f"/api/bots/{bot_id}/configs/{v2}/validate", headers=auth_headers(admin_token))
    r = client.post(f"/api/bots/{bot_id}/configs/{v2}/apply", json={}, headers=auth_headers(admin_token))
    assert r.status_code == 200, r.text

    # Audit trail must include draft, validate, apply
    r = client.get("/api/audit", headers=auth_headers(admin_token))
    actions = [e["action"] for e in r.json()]
    assert "bot.create" in actions
    assert "config.draft.create" in actions
    assert "config.validate" in actions
    assert "config.apply" in actions


def test_risky_change_requires_approval_or_confirmation(client, admin_token):
    r = client.post("/api/bots", json={"name": "beta"}, headers=auth_headers(admin_token))
    bot_id = r.json()["id"]
    cfg = make_config(bot_id)

    r = client.post(f"/api/bots/{bot_id}/configs", json=cfg, headers=auth_headers(admin_token))
    v = r.json()["version"]
    client.post(f"/api/bots/{bot_id}/configs/{v}/validate", headers=auth_headers(admin_token))

    # try to apply risky initial config without confirmation
    r = client.post(f"/api/bots/{bot_id}/configs/{v}/apply", json={}, headers=auth_headers(admin_token))
    assert r.status_code == 400
    assert "risky" in r.json()["detail"].lower()


def test_invalid_config_rejected_by_validation(client, admin_token):
    r = client.post("/api/bots", json={"name": "gamma"}, headers=auth_headers(admin_token))
    bot_id = r.json()["id"]
    bad = make_config(bot_id)
    # oanda namespace does not map BTC/USDT — validation must fail
    bad["broker"]["symbol_namespace"] = "oanda"
    bad["symbols"] = ["BTC/USDT"]
    r = client.post(f"/api/bots/{bot_id}/configs", json=bad, headers=auth_headers(admin_token))
    v = r.json()["version"]
    r = client.post(f"/api/bots/{bot_id}/configs/{v}/validate", headers=auth_headers(admin_token))
    assert r.json()["status"] == "draft"
    assert r.json()["validation_errors"]
