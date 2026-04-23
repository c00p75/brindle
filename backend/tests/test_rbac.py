from tests.conftest import auth_headers


def test_viewer_cannot_create_bot(client):
    r = client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer12345"})
    token = r.json()["access_token"]
    r = client.post("/api/bots", json={"name": "x"}, headers=auth_headers(token))
    assert r.status_code == 403


def test_operator_can_start_but_not_create(client, admin_token):
    # admin creates the bot first
    r = client.post("/api/bots", json={"name": "ops"}, headers=auth_headers(admin_token))
    bot_id = r.json()["id"]

    r = client.post("/api/auth/login", json={"email": "operator@example.com", "password": "operator12345"})
    op_token = r.json()["access_token"]

    r = client.post("/api/bots", json={"name": "nope"}, headers=auth_headers(op_token))
    assert r.status_code == 403

    # start without config should 400 (not 403) — operator has start permission
    r = client.post(f"/api/bots/{bot_id}/start", headers=auth_headers(op_token))
    assert r.status_code == 400


def test_unauthenticated_rejected(client):
    r = client.get("/api/bots")
    assert r.status_code == 401
