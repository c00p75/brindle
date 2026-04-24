# Trading Bot Platform

Paper-trading-first, broker-agnostic trading bot platform with a full-stack
control UI. Build, configure, and operate multiple bots — each bound to its
own broker adapter — without writing code.

## Hard safety rules (enforced)

- **Paper trading only.** `PAPER_TRADING_ONLY=true` is verified at boot; live
  environments are rejected by the adapter factory.
- **No direct broker access from strategies.** Everything flows through
  `ExecutionService → BrokerAdapter`.
- **Config is immutable once applied.** Changes create a new version; the
  workflow is `draft → validate → (approve) → apply → audit`.
- **Risk checks run before every execution.** Position, exposure, daily-loss,
  drawdown, open-orders, and kill-switch gates are all enforced centrally.
- **No secrets in UI, logs, or responses.** Broker credentials use
  `secret://…` references only.
- **Every state change is audited.** Append-only log with actor, action,
  resource, diff, outcome.

## Architecture

```
Strategy
  → OrderIntent
    → RiskEngine
      → ExecutionService
        → BrokerAdapter (paper | oanda | deriv | mt5 | ctrader)
          → Broker API / Simulator
```

Each bot is bound to its own adapter via validated config; multiple adapters
run simultaneously in the same deployment (see
[docs/MULTI_ADAPTER_BROKER_SYSTEM.md](docs/MULTI_ADAPTER_BROKER_SYSTEM.md)).

## Project layout

```
backend/                     FastAPI + Pydantic
  app/
    auth/                   JWT, RBAC, routes
    bots/                   Bot lifecycle & state machine
    configs/                Draft→validate→approve→apply→rollback, diff
    adapters/
      brokers/              base.py, registry.py, factory.py, paper_adapter.py
      symbols/              canonical ↔ native symbol mapping
    execution/              OrderIntent, ExecutionResult, ExecutionService
    risk/                   RiskLimits, RiskEngine
    audit/                  Append-only audit log
    alerts/                 Alerts & acknowledgements
    core/                   settings, ids, time
    db/                     Pluggable store (in-memory for skeleton)
    main.py                 FastAPI app factory
  tests/                    unit + integration (no network)

frontend/                    Next.js 14 (App Router) + TypeScript
  app/
    login/                  Email/password sign-in
    dashboard/              Metrics & safety posture
    bots/                   List + create + details
      [id]/
        page.tsx            Bot details, versions, audit
        config/page.tsx     Draft→validate→apply editor with live diff
    audit/                  Audit log
    alerts/                 Alerts & ack
  components/               AuthGuard, Navigation, ConfigDiff
  lib/                      api client, RBAC, TS types
```

## Quickstart

Prerequisites: Python 3.11+, Node 18+.

```bash
# one-time
make install

# terminal 1 — backend on :8000
make backend

# terminal 2 — frontend on :3000
make frontend
```

Open <http://localhost:3000>.

Bootstrap auth account (seeded on boot):

| Role        | Email                           | Password |
|-------------|----------------------------------|----------|
| super-admin | georgecoopmsapenda@gmail.com    | John16:33 |

Optional demo users can be seeded by setting `SEED_DEMO_USERS=true`.

### Run tests

```bash
make test                 # backend pytest + frontend tsc --noEmit
```

## Config workflow (end-to-end)

1. **Admin** creates a bot → `POST /api/bots`
2. **Admin** drafts a config → `POST /api/bots/{id}/configs`
3. **Admin/Reviewer** validates → `POST .../validate`
4. **Reviewer** approves → `POST .../approve` (required for risk/strategy/broker changes)
5. **Admin** applies → `POST .../apply`
   - Risky diffs without approval require the typed confirmation
     `APPLY RISK CHANGE`.
6. All five steps are recorded in the audit log.
7. **Operator** starts the bot → `POST /api/bots/{id}/start`.

## Adding a new broker adapter

1. Implement `BrokerAdapter` protocol in `backend/app/adapters/brokers/<id>_adapter.py`.
2. Register it in `adapters/brokers/registry.py`:
   ```python
   ADAPTER_REGISTRY["oanda"] = OandaAdapter
   ALLOWED_ENVIRONMENTS["oanda"] = {"demo", "practice"}
   ```
3. Add a symbol mapping namespace in `adapters/symbols/mapping.py`.
4. Write unit + integration tests (no network — mock the broker client).
5. The UI adapter dropdown picks it up automatically from
   `GET /api/bots/{id}/configs/adapters`.

## Roles & permissions (RBAC)

| Capability          | Admin | Operator | Reviewer | Viewer |
|---------------------|:-----:|:--------:|:--------:|:------:|
| bot:create          |  ✔︎   |          |          |        |
| bot:start / stop    |  ✔︎   |   ✔︎    |          |        |
| config:draft        |  ✔︎   |          |          |        |
| config:validate     |  ✔︎   |          |    ✔︎   |        |
| config:approve      |       |          |    ✔︎   |        |
| config:apply        |  ✔︎   |          |          |        |
| config:rollback     |  ✔︎   |          |    ✔︎   |        |
| audit:read          |  ✔︎   |          |    ✔︎   |   ✔︎   |
| alert:ack           |  ✔︎   |   ✔︎    |          |        |
| bot:read / config:read |  ✔︎ |   ✔︎    |    ✔︎   |   ✔︎   |

## Safety invariants (see `/api/health`)

```json
{
  "status": "ok",
  "paper_trading_only": true,
  "live_trading_enabled": false
}
```

These flags cannot be flipped from the API/UI; they're env-only and the app
refuses to boot if `PAPER_TRADING_ONLY` is false.

## Not yet implemented (next slices)

- Persistent DB (`app/db/store.py` is currently in-memory).
- OANDA / Deriv / MT5 / cTrader adapters (paper is wired).
- Strategy runtime loop (strategies themselves — this skeleton provides the
  plumbing from OrderIntent → ExecutionResult).
- Market data ingest + staleness detection.
- MFA, email verification, password reset.
- Replay/backtest runner and run-artefact pipeline
  (see `docs/algorithms-trading-system-primitives-paper-first.md`).
