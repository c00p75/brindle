import httpx

def main():
    client = httpx.Client(base_url="http://localhost:8000")

    # 1. Login
    resp = client.post("/api/auth/login", json={"email": "georgecoopmsapenda@gmail.com", "password": "John16:33"})
    if resp.status_code != 200:
        print("Login failed", resp.text)
        return
    token = resp.json().get("access_token")
    client.headers.update({"Authorization": f"Bearer {token}"})

    # 2. Create Bot
    resp = client.post("/api/bots", json={"name": "Deriv API Test Bot"})
    bot_id = resp.json().get("id")
    print(f"Created bot {bot_id}")

    # 3. Create Draft Config
    cfg = {
        "bot_id": bot_id,
        "version": 1,
        "name": "deriv-cfg",
        "description": "test",
        "strategy": {"strategy_id": "trend_v1", "params": {"lookback": 20}},
        "risk": {
            "max_position_notional": 5000,
            "max_total_exposure": 20000,
            "max_daily_loss": 500,
            "max_drawdown_pct": 10,
            "max_open_orders": 5,
            "kill_switch": False
        },
        "broker": {
            "type": "deriv",
            "environment": "demo",
            "account_id": "demo-123",
            "credential_ref": "secret://env/DERIV_API_TOKEN",
            "symbol_namespace": "deriv"
        },
        "symbols": ["V75/USD"]
    }
    resp = client.post(f"/api/bots/{bot_id}/configs", json=cfg)
    print("Create Draft:", resp.text)

    # 4. Validate
    resp = client.post(f"/api/bots/{bot_id}/configs/1/validate")
    print("Validate:", resp.text)

    # 5. Apply
    resp = client.post(f"/api/bots/{bot_id}/configs/1/apply", json={"typed_confirmation": "APPLY RISK CHANGE"})
    print("Apply:", resp.text)

    # 6. Start
    resp = client.post(f"/api/bots/{bot_id}/start")
    print("Start:", resp.text)

main()
