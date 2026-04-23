# CURSOR_MISSING_SPEC.md

## Purpose

This document resolves the major **UNSPECIFIED** items left in the current paper-trading-first reference pack so implementation can proceed without ambiguity.

This addendum does **not** authorize live trading. It completes the missing defaults and operating rules required for a robust, unattended, production-grade **paper-trading** system, and defines the minimum gates that must exist before any future live-trading design is even discussed. The existing pack already establishes paper-only mode, the adapter boundary, deterministic testing, and the phased build model; this document fills in the remaining engineering defaults.

---

## 1. Canonical build target

Build a **single-tenant, paper-trading-first crypto spot trading platform** with:

- backend: FastAPI, Python 3.11+
- frontend: Next.js App Router, TypeScript
- market/exchange adapter: CCXT async support, runtime only
- primary database: PostgreSQL
- cache / ephemeral state / rate-limit coordination: Redis
- background jobs / event fanout: Redis Streams first, upgradeable later
- containerization: Docker Compose for local and single-node deployment
- deployment target: single VPS first, cloud migration later
- logging: structured JSON logs
- metrics: Prometheus-format metrics endpoint
- dashboards: Grafana
- alert transport: Telegram first, email second
- scheduler: APScheduler inside backend for MVP, replaceable later
- auth model: single-user local admin for MVP
- strategy runtime: in-process worker loop with deterministic config snapshot
- mode: **paper trading only**

---

## 2. Explicit non-negotiable rules

These rules inherit and extend the current pack.

- Paper trading only.
- No live order placement.
- No withdrawal, transfer, or private account mutation beyond read-only balance/market metadata needed for paper configuration.
- Strategies must never call CCXT directly.
- All strategy execution must go through a single execution boundary.
- No network access in unit tests or integration tests unless explicitly marked end-to-end and run against a local mock service.
- Every config change must use draft -> validate -> apply -> audit.
- All runtime decisions must be reproducible from stored config version + code version + data version + run manifest.
- If state is uncertain, do nothing and emit an alert.
- No secret may appear in logs, frontend bundles, screenshots, exports, or audit diffs.

---

## 3. Resolved architecture decisions

### 3.1 System style

Use an **event-driven core with polling fallback**.

Decision:
- Realtime market updates enter via websocket where available.
- Historical ingestion and reconciliation jobs use polling.
- Strategy evaluation is triggered by normalized feed events.
- Critical services must continue operating if websocket is unavailable by degrading to REST polling with increased staleness warnings.

### 3.2 Services

Use these modules:

- `api`: REST endpoints, auth, health, config management, dashboards
- `core`: settings, types, time, ids, errors, safe-mode assertions
- `adapters`: CCXT market-data adapter, fixture adapter
- `data`: normalization, validation, persistence, replay feed
- `strategies`: strategy interface, strategy registry, parameter schemas
- `risk`: pre-trade checks, exposure engine, drawdown guards, kill switch
- `execution`: paper OMS, order state machine, fill simulator, ledger
- `portfolio`: balances, positions, valuation, realized/unrealized PnL
- `research`: backtest/replay orchestration, manifests, metrics
- `ops`: logs, metrics, alerts, audit trail, incidents
- `scheduler`: background jobs, heartbeats, reconciliation cadence
- `ui`: admin/config/monitoring frontend

### 3.3 Repo structure

```text
repo/
  backend/
    app/
      api/
        routes/
        deps/
        schemas/
      core/
        config.py
        enums.py
        ids.py
        time.py
        safety.py
        logging.py
      adapters/
        market_data/
          base.py
          ccxt_adapter.py
          fixture_adapter.py
      data/
        models/
        repositories/
        normalization/
        validation/
        replay/
        services/
      strategies/
        base.py
        registry.py
        configs/
        implementations/
      risk/
        policies/
        engine.py
        limits.py
        kill_switch.py
      execution/
        oms/
        simulator/
        ledger/
        services/
      portfolio/
        valuation.py
        positions.py
        pnl.py
      research/
        manifests/
        metrics/
        runners/
      ops/
        audit.py
        alerts.py
        metrics.py
        incidents.py
      scheduler/
        jobs/
        runner.py
      main.py
    tests/
      unit/
      integration/
      contract/
      replay/
      e2e_local/
    alembic/
    pyproject.toml
    Dockerfile

  frontend/
    app/
      status/
      configs/
      bots/
      runs/
      incidents/
      audit/
    components/
    lib/
    tests/
    package.json
    Dockerfile

  docs/
    CURSOR_MISSING_SPEC.md
    RUNBOOK.md
    INCIDENTS.md
    CONFIG_SCHEMA.md
    ALERTS.md
    DEPLOYMENT.md

  infra/
    docker/
    compose/
    prometheus/
    grafana/
    nginx/

  scripts/
    dev/
    test/
    seed/
    replay/
```

---

## 4. Resolved infrastructure defaults

### 4.1 Deployment model

Use **single VPS** first.

Minimum host:
- 4 vCPU
- 8 GB RAM
- 160 GB SSD
- Ubuntu LTS
- Docker Engine + Docker Compose plugin
- daily off-host backups of PostgreSQL and config/audit tables

Services:
- reverse proxy
- backend
- frontend
- postgres
- redis
- prometheus
- grafana

Do not begin with Kubernetes.

### 4.2 Environments

Define exactly three environments:

- `local`
- `staging`
- `prod-paper`

No `prod-live`.

### 4.3 Secrets

Use environment variables injected at runtime from:
- `.env.local` for development only, gitignored
- host-level secret files or systemd environment on VPS
- never store secrets in database except encrypted-at-rest future extension

Required secrets:
- `APP_SECRET_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- optional market data API credentials if a vendor requires them

### 4.4 CI/CD

Use GitHub Actions if repo is on GitHub; otherwise replicate the same pipeline elsewhere.

Required pipeline stages:
- lint
- type-check
- backend unit/integration tests
- frontend unit tests
- replay reproducibility tests
- build Docker images
- migration dry run
- config schema compatibility check

No automatic deploy from failing tests.

---

## 5. Resolved data-layer defaults

### 5.1 Asset class and venue scope

Initial scope:
- crypto spot only
- symbols:
  - BTC/USDT
  - ETH/USDT
  - SOL/USDT
- initial venue model:
  - one exchange adapter active at a time per bot
- internal symbol canonical format:
  - `BASE/QUOTE`

### 5.2 Symbol normalization policy

Canonical mappings:
- `BTCUSDT` -> `BTC/USDT`
- `ETHUSDT` -> `ETH/USDT`
- `SOLUSDT` -> `SOL/USDT`
- `XBT/USD` -> reject unless explicitly mapped in `symbol_registry`
- any ambiguous vendor symbol -> reject

### 5.3 Allowed timeframes

Initial allowed set:
- `1m`
- `5m`
- `15m`
- `1h`
- `4h`
- `1d`

No strategy may request other timeframes until centrally added and tested.

### 5.4 Historical source

Use CCXT OHLCV for MVP historical data ingestion through adapter boundary.

### 5.5 Realtime sources

Use:
- websocket ticker / best bid ask if exchange supports it cleanly through chosen adapter layer
- REST polling fallback every 5 seconds for ticker and every 10 seconds for book top

### 5.6 Staleness thresholds

Default thresholds:
- ticker stale: 15 seconds
- best-bid-ask stale: 10 seconds
- order book top stale for execution reference: 5 seconds
- candle close grace window:
  - 1m candle: 8 seconds
  - 5m candle: 20 seconds
  - 15m+ candle: 45 seconds

Behavior:
- stale feed -> strategy NOOP
- stale execution reference -> reject new simulated orders
- repeated stale condition for 3 consecutive checks -> emit warning
- 10 consecutive stale checks -> pause affected bot

### 5.7 Storage backend

Use PostgreSQL as system of record.

Tables required:
- `market_candles`
- `market_tickers`
- `market_book_top`
- `ingestion_batches`
- `symbol_registry`
- `bot_configs`
- `bot_config_versions`
- `audit_events`
- `paper_orders`
- `paper_order_fills`
- `ledger_entries`
- `positions`
- `balance_snapshots`
- `equity_snapshots`
- `strategy_runs`
- `run_manifests`
- `run_metrics`
- `incident_events`

Redis uses:
- latest market cache
- strategy heartbeat cache
- lock keys
- idempotency short-lived keys
- queue / stream coordination

### 5.8 Raw retention policy

Retain raw vendor payloads for 7 days in compressed object storage or filesystem archive for debugging.
Retain normalized records indefinitely unless pruning policy is added.

---

## 6. Resolved execution and OMS defaults

### 6.1 Order types

Supported in MVP:
- market
- limit

Not supported in MVP:
- stop-market
- stop-limit
- trailing-stop
- OCO

### 6.2 Time in force

Supported:
- `GTC`
- `IOC`

Default:
- market -> `IOC`
- limit -> `GTC`

### 6.3 Client order id format

```text
po_<bot_id>_<strategy_id>_<utc_ms>_<nonce6>
```

Rules:
- max 64 chars
- ASCII only
- unique per submission attempt
- retry of same logical order keeps same `client_order_id`
- corrected replacement order must use new `client_order_id` and reference `replaces_order_id`

### 6.4 Order state machine

Required states:
- `created`
- `accepted`
- `partially_filled`
- `filled`
- `canceled`
- `rejected`
- `expired`
- `failed_unknown`

State transitions must be explicit and audited.

### 6.5 Partial fill simulation

Market order fill model:
- if order notional <= `top_of_book_notional_limit`, fill immediately at effective price
- else fill in slices against synthetic liquidity tiers

Default synthetic liquidity tiers:
- level 1: 2,500 USDT
- level 2: 5,000 USDT additional at +3 bps / -3 bps
- level 3: 10,000 USDT additional at +8 bps / -8 bps

For buys:
- worse price moves upward by tier
For sells:
- worse price moves downward by tier

### 6.6 Retry policy

Retries allowed only for:
- adapter timeout
- temporary rate limit
- transient Redis/Postgres connection interruption

Retry schedule:
- 250 ms
- 1 s
- 3 s
- then fail closed

If order state after submission is uncertain:
- set order to `failed_unknown`
- block strategy from resubmitting same intent automatically
- emit critical alert
- require reconciliation job to resolve

### 6.7 Idempotency

Every logical order submission must include:
- `client_order_id`
- `intent_hash`
- `config_version`
- `bot_run_id`

Idempotency window:
- 24 hours in Postgres
- 1 hour hot cache in Redis

Unique index:
- `(bot_id, client_order_id)`

### 6.8 Reconciliation job

Run every 60 seconds:
- verify no impossible order state transitions
- verify fill totals <= original qty
- verify ledger balances reconcile to order/fill history
- verify positions reconcile to ledger
- verify realized PnL snapshots are reproducible

If any check fails:
- pause affected bot
- emit incident
- require operator acknowledgement

---

## 7. Resolved risk defaults

### 7.1 Portfolio currency

Base portfolio currency:
- `USDT`

### 7.2 Sizing defaults

Initial sizing method:
- fixed fraction of equity

Default:
- `risk_fraction = 0.01`
- `max_notional_per_trade = 0.05 * equity`
- `min_order_notional = 25 USDT`

Volatility-scaled sizing:
- supported for strategies that declare ATR or rolling-vol input
- default volatility target:
  - annualized 15%
- if vol estimate unavailable -> fallback to fixed fraction

### 7.3 Exposure limits

Per bot:
- max 3 open symbols
- max 20% equity allocated to one symbol
- max 35% gross deployed notional
- max 10% pending order notional
- max 5 active resting limit orders

Portfolio-wide:
- max 50% deployed notional across all bots
- max 2 bots per symbol

### 7.4 Drawdown controls

Bot-level:
- warn at 5% drawdown from local equity peak
- soft pause at 8%
- hard pause at 10%

Portfolio-level:
- warn at 7%
- hard kill switch at 12%

Daily loss:
- if daily realized + unrealized PnL <= -3% of start-of-day equity:
  - pause new orders
  - allow only cancel/flatten simulation logic

### 7.5 Trade frequency guards

Per bot:
- max 12 orders/hour
- cooldown after any loss-making exit: 5 minutes
- cooldown after 3 consecutive losses: 30 minutes

### 7.6 Data/risk guard linkage

Pre-trade checks must fail if:
- stale price reference
- missing latest valuation
- config version mismatch
- kill switch engaged
- run manifest missing
- exposure limit violated
- drawdown breaker active
- bot heartbeat stale > 30 seconds

### 7.7 Kill switch

Sources that may trigger kill switch:
- operator manual action
- portfolio drawdown hard threshold
- reconciliation failure
- repeated unknown order state
- database write failure on order/fill/ledger path
- repeated stale market data for 10 consecutive checks

Kill switch behavior:
- reject new orders
- cancel resting simulated orders
- mark bots paused
- emit critical alert
- write immutable audit event

---

## 8. Resolved strategy-system defaults

### 8.1 Strategy interface contract

```python
class Strategy(Protocol):
    strategy_id: str
    version: str

    def parameter_schema(self) -> dict: ...
    def warmup_requirements(self) -> dict: ...
    def on_event(self, ctx: "StrategyContext", event: "MarketEvent") -> list["OrderIntent"]: ...
    def on_timer(self, ctx: "StrategyContext", now_ms: int) -> list["OrderIntent"]: ...
```

### 8.2 StrategyContext contract

```python
class StrategyContext(Protocol):
    bot_id: str
    config_version: str
    now_ms: int

    def latest_price(self, symbol: str) -> float | None: ...
    def latest_book_top(self, symbol: str) -> "OrderBookTop | None": ...
    def latest_candle(self, symbol: str, timeframe: str) -> "Candle | None": ...
    def position(self, symbol: str) -> "Position | None": ...
    def cash_equity(self) -> float: ...
    def portfolio_equity(self) -> float: ...
    def risk_state(self) -> "RiskState": ...
```

Strategies must return `OrderIntent` objects only. They must not mutate balances, place orders directly, or reach adapters.

### 8.3 Initial strategy set

Allowed first strategies:
- moving-average crossover
- mean reversion on z-score of returns
- DCA scheduler
- TWAP paper executor
- simple breakout with volatility filter

Do not begin with:
- market making
- cross-exchange arbitrage
- reinforcement learning
- LLM-generated trading decisions
- any strategy needing level-2 depth modeling beyond current simulator

### 8.4 Parameter schema standard

Every parameter must declare:
- name
- type
- unit
- bounds
- default
- description

No hidden parameters.

### 8.5 Strategy promotion states

Use:
- `draft`
- `researching`
- `paper_candidate`
- `paper_active`
- `paused`
- `rejected`
- `graveyarded`

Any rejected or paused strategy must be appended to the graveyard with evidence.

---

## 9. Resolved research and backtesting defaults

### 9.1 Backtest engine choice

Use the internal replay engine built on normalized canonical records.
Do not bind to a third-party backtest framework in MVP.

### 9.2 Required run artifact layout

```text
experiments/
  run_YYYYMMDD_HHMMSS_<strategy_id>/
    manifest.yaml
    metrics.json
    fills.csv
    orders.csv
    equity_curve.csv
    event_summary.json
    logs.jsonl
    plots/
```

### 9.3 Required metrics

Every run must compute:
- total return
- CAGR
- Sharpe ratio
- Sortino ratio
- max drawdown
- Calmar ratio
- win rate
- profit factor
- expectancy per trade
- average win
- average loss
- turnover
- fees paid
- slippage paid
- exposure time
- trade count
- daily loss breaches
- rejected-order count
- stale-data event count

### 9.4 Walk-forward policy

Default split:
- 60% train / tune
- 20% validation
- 20% holdout

Walk-forward:
- minimum 3 folds
- parameters chosen on validation
- final report must include untouched holdout metrics

### 9.5 Acceptance thresholds for unattended paper promotion

A strategy may move to `paper_active` only if all are true:
- at least 200 simulated trades or 90 days equivalent runtime
- net profit after fees and slippage > 0
- profit factor >= 1.15
- Sharpe >= 0.8
- max drawdown <= 8%
- no single month responsible for > 60% of total profit
- performance positive in at least 2 distinct market regimes
- zero unresolved reconciliation anomalies
- zero safety-gate violations in last qualification run

If any fail:
- remain `researching` or move to `paused/rejected`

### 9.6 Reproducibility test

For each strategy:
- same dataset + same manifest + same seed + same code hash must produce identical:
  - orders
  - fills
  - final equity
  - metrics summary

This must run in CI.

---

## 10. Resolved admin/config governance defaults

### 10.1 Role model

Single-user MVP mapping:
- local admin user acts as Admin + Reviewer + Operator
- Auditor is represented by immutable audit log, not a separate human role yet

Future multi-user mode may split roles later.

### 10.2 Configuration objects

All applied runtime behavior must derive from versioned config objects:

- exchange connection config
- symbol allowlist
- risk profile
- strategy parameters
- bot schedule
- staleness thresholds
- alert routing
- feature flags

### 10.3 Validation requirements

Validation must include:
- schema validation
- type validation
- range validation
- invariants
- dependency validation
- dry-run compatibility against current code version

Example invariants:
- max_notional_per_trade <= max_symbol_exposure
- hard drawdown > soft drawdown
- strategy symbol subset of global symbol allowlist
- timeframes belong to allowed central set
- paper-only flag always true

### 10.4 Apply rules

Applying config:
- creates immutable new version
- stamps actor, timestamp, diff summary
- triggers strategy restart only if affected domains changed
- never mutates historical applied versions

### 10.5 Rollback rules

Rollback means:
- create a new applied version cloned from a previous known-good version
- do not re-activate old version in place

---

## 11. Resolved observability defaults

### 11.1 Logging

Use structured JSON logs with required fields:
- timestamp
- level
- service
- env
- bot_id
- strategy_id
- run_id
- config_version
- event_type
- correlation_id
- message

Never log:
- secrets
- raw auth headers
- full env dumps
- unredacted payloads with credentials

### 11.2 Metrics endpoint

Expose `/metrics` from backend.

Required gauges/counters:
- bot_status
- bot_heartbeat_age_seconds
- market_data_stale_total
- orders_submitted_total
- orders_rejected_total
- orders_partially_filled_total
- reconciliation_failures_total
- kill_switch_activations_total
- strategy_pnl_realized
- strategy_pnl_unrealized
- portfolio_equity
- drawdown_pct
- alert_delivery_failures_total

### 11.3 Alerts

Severity levels:
- `info`
- `warning`
- `critical`

Telegram required for:
- kill switch activation
- reconciliation failure
- database write failure in execution path
- unknown order state
- portfolio drawdown hard threshold
- repeated stale data pause

Email required for:
- daily summary
- weekly incident report

### 11.4 Dashboards

Minimum dashboards:
- portfolio overview
- bot status board
- order/fill activity
- PnL and drawdown
- data freshness
- incidents and alerts
- config version history

---

## 12. Resolved testing matrix

### 12.1 Unit tests

Must cover:
- normalization rules
- staleness rules
- risk checks
- order-state transitions
- fill simulator math
- fee/slippage calculations
- strategy signal generation
- config invariant validation
- kill switch conditions

### 12.2 Integration tests

Must cover:
- strategy -> risk -> execution -> ledger path
- config draft -> validate -> apply -> audit
- replay engine deterministic stepping
- stale feed causing NOOP
- reconciliation detecting mismatch
- alert emission on critical faults

### 12.3 Contract tests

Must cover:
- adapter outputs to canonical schemas
- API schema stability
- manifest and metrics schema stability
- frontend/backend DTO compatibility

### 12.4 Replay reproducibility tests

Must verify same run manifest reproduces same outputs.

### 12.5 End-to-end local tests

Run against local Docker Compose only.
Must cover:
- create bot config
- start paper bot
- ingest fixture data
- generate orders/fills
- view equity and audit trail
- pause bot
- rollback config

---

## 13. Resolved paper-operations runbook defaults

### 13.1 Bot states

Use:
- `created`
- `validated`
- `ready`
- `running`
- `paused`
- `halted`
- `error`

### 13.2 Daily operator checklist

- confirm all running bots heartbeat < 30s
- confirm no stale data warnings open > 15 min
- confirm reconciliation job clean
- confirm equity snapshots updated
- confirm alerts channel healthy
- review previous-day drawdown and rejected orders
- review any config changes applied since last check

### 13.3 Incident severities

- `SEV1`: kill switch, execution-path DB failure, corrupted ledger suspicion
- `SEV2`: repeated stale data pauses, reconciliation mismatch isolated to one bot
- `SEV3`: dashboard issue, delayed non-critical metrics, failed daily email

### 13.4 Incident response

For any `SEV1`:
- pause all bots
- preserve logs and manifests
- snapshot relevant tables
- open incident record
- require manual restart checklist before resuming

---

## 14. Minimum security baseline

### 14.1 Backend

- bind services to private network behind reverse proxy
- enable HTTPS at proxy
- restrict Grafana access by basic auth or VPN
- admin routes require authenticated session
- CSRF protection on state-changing browser routes
- strict CORS allowlist
- rate-limit login and mutation endpoints

### 14.2 Frontend

- no secret in client env
- no direct exchange access
- all mutations through backend
- hide sensitive internal IDs where unnecessary

### 14.3 Data

- PostgreSQL daily backup
- backup retention 14 daily / 8 weekly
- Redis treated as cache, not source of truth
- audit and ledger tables append-only or logically immutable

---

## 15. Future live-trading gates

Live trading remains forbidden. Before any live-routing design can begin, all of the following must already exist and pass:

- 90+ consecutive days of unattended paper runtime
- zero unresolved reconciliation anomalies
- full OMS idempotency and restart recovery proven
- complete incident runbooks exercised
- alerting proven through drills
- exchange-specific precision, limits, and fee rules implemented and tested
- real order acknowledgement/reconciliation design reviewed
- auth and RBAC hardened beyond single-user
- separate prod-live environment defined
- legal/regulatory review completed
- explicit live-trading approval document created

---

## 16. Required implementation order from here

Implement in this sequence:

1. Freeze config and settings system with all defaults from this document.
2. Implement PostgreSQL + Redis foundation.
3. Implement canonical market-data schemas, normalization, validation, and staleness handling.
4. Implement paper OMS, fill simulator, ledger, and reconciliation.
5. Implement risk engine and kill switch.
6. Implement strategy registry and first two baseline strategies.
7. Implement replay engine, run manifests, metrics, and reproducibility tests.
8. Implement audit trail, alerts, dashboards, and operator workflow.
9. Implement config draft/validate/apply/rollback UI.
10. Run 30-day paper soak test on fixture + live-read market data.
11. Promote selected strategies to unattended paper if thresholds pass.

---

## 17. Cursor execution instruction

When implementing from this addendum:

- Treat every default here as authoritative unless a future document explicitly supersedes it.
- Do not ask for missing values that are resolved here.
- If a requested change conflicts with this document, preserve safety and mark the conflicting request clearly.
- Output changes in small atomic slices.
- Write failing tests first.
- Stop after each requested slice.

---

## 18. Immediate first slice to implement

Task:
Implement the configuration and settings foundation that codifies all defaults from `CURSOR_MISSING_SPEC.md`.

Deliverables:
- typed backend settings
- versioned config schemas for risk, data, bot, and strategy
- schema/invariant validator
- draft -> validate -> apply -> audit flow
- tests for valid/invalid configs
- seed default paper config matching this document exactly

Stop after this slice.
