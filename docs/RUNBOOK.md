# Operations Runbook

## Prometheus metrics

All metrics are exposed at `GET /metrics` (text/plain, Prometheus scrape format).

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `tradingbot_http_requests_total` | Counter | `method`, `path`, `status` | Every HTTP request served |
| `tradingbot_http_request_duration_seconds` | Histogram | `method`, `path` | Request latency (buckets: 5ms–2.5s) |
| `tradingbot_orders_total` | Counter | `bot_id`, `status` | Orders submitted via ExecutionService (`accepted`/`rejected`) |
| `tradingbot_risk_rejections_total` | Counter | `bot_id`, `reason` | Orders rejected by the risk engine |
| `tradingbot_bots_running` | Gauge | — | Number of bots in `running` state |
| `tradingbot_audit_events_total` | Counter | `action` | Audit events recorded (bot.start, config.approve, …) |
| `tradingbot_backtest_runs_total` | Counter | `strategy_id`, `outcome` | Backtest runs completed |

## Alert thresholds (recommended)

| Alert | Condition | Severity |
|-------|-----------|----------|
| High login error rate | `rate(tradingbot_http_requests_total{path="/api/auth/login",status="401"}[5m]) > 0.5` | warning |
| Risk engine rejecting all orders | `rate(tradingbot_risk_rejections_total[5m]) > 10` | critical |
| No bots running (if expected) | `tradingbot_bots_running == 0` | warning |
| High p99 latency | `histogram_quantile(0.99, tradingbot_http_request_duration_seconds) > 1` | warning |

## Health check

```
GET /healthz  →  {"status": "ok"}
```

Used by Nginx/load-balancer to determine backend availability. No auth required.

## Structured logs

The backend emits JSON to stdout. Each line is a complete JSON object:

```json
{"ts": 1714000000.123, "level": "INFO", "msg": "bot started", "bot_id": "bot_xyz", "request_id": "req_abc"}
```

Ship stdout to your log aggregator (Loki, Datadog, CloudWatch). Filter by `level=ERROR` for alerting.

## Deploying a new backend version

```bash
# On your local machine
rsync -az --delete backend/ user@<droplet-ip>:/opt/trading-bot/backend/

# On the droplet
cd /opt/trading-bot/backend
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
sudo systemctl restart trading-bot-backend
sudo systemctl status trading-bot-backend
```

Check logs: `sudo journalctl -u trading-bot-backend -f`

## Database migrations (Alembic)

```bash
# Generate a new migration after ORM changes
alembic revision --autogenerate -m "describe the change"

# Apply all pending migrations
alembic upgrade head

# Roll back one step
alembic downgrade -1
```

Set `DATABASE_URL` env var before running Alembic:

- **SQLite (dev):** `sqlite:////opt/trading-bot/backend/data/db.sqlite3`
- **Postgres (prod):** `postgresql+psycopg2://user:pass@host:5432/tradingbot`

## Required environment variables

| Variable | Description | Default (dev only) |
|----------|-------------|-------------------|
| `APP_ENV` | `development` or `production` | `development` |
| `JWT_SECRET` | Random 64-char secret for token signing | *(unsafe placeholder — boot fails in prod)* |
| `JWT_EXPIRE_MINUTES` | Token TTL | `60` |
| `SUPER_ADMIN_EMAIL` | Bootstrap admin account email | `admin@example.com` |
| `SUPER_ADMIN_PASSWORD` | Bootstrap admin password | `changeme` |
| `SEED_DEMO_USERS` | Create demo operator/reviewer/viewer accounts | `false` |
| `SEED_DEMO_PASSWORD` | Password for demo accounts | `demo-changeme-1` |
| `DATABASE_URL` | SQLAlchemy connection string | SQLite in `data/` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `http://localhost:3000` |

## Paper-trading safety invariants

`PAPER_TRADING_ONLY=true` and `LIVE_TRADING_ENABLED=false` are **hard-coded** and cannot be overridden from the API or UI. The server will refuse to start if they are changed. This is intentional.
