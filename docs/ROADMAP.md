# ROADMAP — Trading Bot Platform

Living document. **Tool-agnostic.** Any AI assistant (Claude, Cursor, Copilot,
Codeium, etc.) or human contributor must read this before making non-trivial
changes. Update this file in the same PR that completes a slice.

Last updated: 2026-04-27

---

## How to use this doc

1. **Read the "Architecture invariants" section first.** These are
   non-negotiable. Any change that violates them must be rejected.
2. Find the next unchecked slice under "Slice plan" and read its
   "Definition of done".
3. Make a branch, ship one slice, mark it ✅, update "Status snapshot",
   commit this file in the same PR.
4. If you change scope or add a slice, write *why* in the changelog at the
   bottom — not just *what*.

---

## Status snapshot

| Layer            | Status            | Notes |
|------------------|-------------------|-------|
| Auth + RBAC      | ✅ shipped        | Bootstrap super-admin via env. JWT. Capability matrix mirrored backend/frontend. |
| Broker adapter system | ✅ shipped (paper only) | Registry + factory + per-bot binding. Symbol mapping for paper/oanda/deriv namespaces. |
| Execution service | ✅ shipped       | Health + risk gates run before every order. Audit on every attempt. |
| Risk engine      | ✅ shipped        | Position / exposure / daily-loss / drawdown / open-orders / kill-switch gates. |
| Config workflow  | ✅ shipped        | Draft → validate → (approve) → apply → rollback. Risky-change gating. |
| Audit + alerts   | ✅ shipped        | Append-only audit, alerts with ack. |
| Persistence      | ✅ shipped (slice 1) | SQLAlchemy 2 + SQLite. `DATABASE_URL` swaps to Postgres. |
| Frontend control | ✅ shipped (basic) | Login, dashboard, bots, config editor with live diff and typed-confirmation. |
| Deployment       | ✅ shipped        | Droplet + Vercel. See `project_deployment` memory or commit history. |
| **Strategy runtime** | ✅ shipped (slice 2) | trend_v1 SMA crossover. Synthetic feed. Per-bot asyncio task. Positions/orders/fills persisted + shown in UI. |
| Real broker adapters | ✅ shipped (slice 3) | OANDA v20 REST (practice/demo). 24 mock-based tests. |
| Secrets resolver | ✅ shipped (slice 3) | `secret://env/VAR` and `secret://paper/none`. Slice 4 adds Vault/file backends. |
| Market data ingest | ✅ shipped (slice 5) | SyntheticSource + LiveAdapterSource. MarketDataSource protocol. Staleness NOOP + alert. |
| Approvals / rollback UI | ✅ shipped (slice 6) | Approve button, rollback button, pending-approvals amber panel. |
| Positions / PnL / equity charts | ✅ shipped (slice 6) | Equity curve (SVG sparkline) + fills table on bot details. |
| Strategy dropdown + symbol picker | ✅ shipped (slice 6) | Chip picker for paper FX pairs + custom entry. |
| MFA / password reset | ✅ shipped (slice 7) | TOTP setup/verify/disable on Profile page. Forgot/reset password flow. |
| Replay / backtest runner | ✅ shipped (slice 8) | Research page: runner UI, metrics grid, past-runs table. Backend runner saves to `experiments/`. |
| Observability    | ✅ shipped (slice 9) | Structured JSON logs, Prometheus metrics fully wired, RUNBOOK.md. |
| Postgres + Alembic migrations | ✅ shipped (slice 10) | Alembic migration tree, `DATABASE_URL` env selects SQLite or Postgres. |

---

## Architecture invariants (non-negotiable)

These come from `docs/MULTI_ADAPTER_BROKER_SYSTEM.md`,
`docs/discipline-governance-admin-config-controls.md`, and
`docs/algorithms-trading-system-primitives-paper-first.md`. Read those for
context.

1. **Paper trading only.** `PAPER_TRADING_ONLY=true` is asserted at boot
   in `backend/app/core/settings.py`. The adapter factory rejects any
   "live" environment. **Do not add code paths that bypass either.**
2. **Strategies never call broker APIs.** They produce `OrderIntent` only.
   The single execution gateway is `app/execution/service.py:ExecutionService.execute()`.
3. **Per-bot adapter binding.** Every bot picks its own adapter via
   validated config. **No global "current broker" switch.** Adapter registry
   is `app/adapters/brokers/registry.py`.
4. **Config is immutable once applied.** Every change creates a new version.
   Workflow: `draft → validate → (approve) → apply → audit`. Risky changes
   (broker / risk / strategy_id) require Reviewer approval OR the typed
   confirmation `APPLY RISK CHANGE`.
5. **Risk runs before execution, every time.** Position, exposure, daily
   loss, drawdown, open-order count, and kill-switch are all evaluated
   in `app/risk/engine.py:RiskEngine.check()` before the order reaches
   the adapter.
6. **No secrets in UI, logs, responses, or inline config.** Broker
   credentials are `secret://…` references resolved server-side only.
7. **Append-only audit.** Every state-changing service call writes a row
   in `audit_events` with actor, action, resource, diff, outcome.
8. **Uncertainty → NOOP.** If state is uncertain (adapter unhealthy,
   data stale, validation ambiguous), reject + alert. **Never guess.**
9. **No network calls in tests.** All adapters mockable; `PaperAdapter`
   is dependency-free.

If a proposed change forces an exception to any of these, **stop and write
a design note** before coding. Update this doc; don't paper over.

---

## Slice plan

Each slice is sized for **one focused PR (≤ ~600 lines diff)**. If a slice
grows bigger, split it.

### ✅ Slice 0 — Skeleton (shipped)
Backend skeleton, frontend skeleton, deployment to droplet + Vercel.
Commits: initial repo through `d630f75`.

### ✅ Slice 1 — Persistence (shipped)
SQLAlchemy 2 + SQLite. All services moved off the in-memory store.
22 tests pass. Live data survives restart.
Commit: `b6c1cc7`.

### ✅ Slice 2 — Strategy runtime (shipped)
**Why now:** Without this, the platform has plumbing but doesn't trade.

**Scope:**
- `app/strategies/base.py` — `Strategy` protocol + `StrategyContext`
  (current bars, position, mark price, config params).
- `app/strategies/registry.py` — `STRATEGY_REGISTRY` keyed by
  `strategy_id`. Validation rejects unknown ids in
  `app/configs/validator.py`.
- `app/strategies/trend.py` — `trend_v1` (simple SMA crossover).
- `app/marketdata/feed.py` — deterministic synthetic tick generator
  for paper mode (seeded by `(bot_id, symbol)` so replays are
  reproducible).
- `app/runtime/manager.py` — async per-bot task: pulls bars from feed,
  invokes strategy, sends intents through `ExecutionService`. Exits
  cleanly on bot pause/stop/halt.
- ORM additions: `OrderRow`, `FillRow`, `PositionRow` in `app/db/orm.py`.
  Service layer in `app/execution/persistence.py`.
- Wire `bots.service.start/pause/stop` to `runtime.manager`.
- New routes: `GET /api/bots/{id}/positions`, `/orders`, `/fills`.
- Frontend: positions + recent orders panel on bot details page.

**Definition of done:**
- Starting a bot from the UI causes orders to appear within seconds.
- Pausing/stopping the bot terminates the runtime task within 1 tick.
- Risk-blocked intents appear in the audit log with reason.
- Restarting the backend service restores positions and order history.
- Tests: strategy unit, runtime lifecycle, fill persistence.
- 25+ tests pass.

### ✅ Slice 3 — OANDA adapter (shipped)
**Why:** Spec says OANDA first because its order model is closest to ours.

**Scope:**
- `app/adapters/brokers/oanda_adapter.py` — implements `BrokerAdapter`,
  uses OANDA v20 REST. Demo / practice environments only.
- Symbol mapping namespace already exists at
  `app/adapters/symbols/mapping.py:OANDA_NAMESPACE`.
- `ALLOWED_ENVIRONMENTS["oanda"] = {"demo", "practice"}` already set.
- Mock-based unit tests (no network).
- Integration test using OANDA's practice sandbox (env-gated, off in CI).
- Frontend adapter dropdown picks it up automatically.

**Definition of done:**
- A bot configured with `broker.type = oanda` executes against the
  practice account through `ExecutionService` end-to-end.
- All adapter tests pass without network.
- Audit records include `adapter_id=oanda` on every execution attempt.

### ✅ Slice 4 — Secrets resolver (shipped)
**Why:** `credential_ref: secret://...` must resolve to actual creds.

**Scope:**
- `app/secrets/resolver.py` — pluggable backend.
- Default: env-backed (`secret://env/OANDA_TOKEN_BOT_001` →
  `os.environ["OANDA_TOKEN_BOT_001"]`).
- Follow-up backends: file-based (`secret://file/...`), HashiCorp
  Vault, AWS Secrets Manager — interface only.
- Resolver invoked by adapter factory at adapter construction time;
  result is held in adapter instance, never logged or serialised.
- Admin UI: list + rotate secret references (refs only, never values).

**Definition of done:**
- OANDA adapter authenticates using a `secret://` reference.
- Logs never contain a resolved secret value (verified by test).
- Rotating a secret + adapter restart picks up the new value with no
  code change.

### ✅ Slice 5 — Market data + staleness detection (shipped)
**Why:** Strategies need real data; staleness must NOOP per spec.

**Scope:**
- `app/marketdata/source.py` — `MarketDataSource` protocol with
  paper / oanda implementations.
- Per-symbol last-tick timestamps tracked in memory.
- Staleness threshold per market type; staleness → NOOP + alert.
- Integration into `runtime.manager`: feed switches from synthetic
  to real source based on bot's broker config.

**Definition of done:**
- Stale data blocks new intents (test with simulated clock skew).
- Recovery from stale → fresh resumes execution.
- Alert emitted on first stale detection per bot per symbol.

### ✅ Slice 6 — UI completeness (shipped)
**Why:** Several backend endpoints lack UI counterparts.

**Scope:**
- Reviewer approvals queue (`/approvals`).
- One-click rollback button on bot details.
- Positions / open orders / fills panels on bot details.
- Equity curve + drawdown chart on dashboard.
- Strategy presets (template chooser when creating a config).
- Symbol picker that filters by selected adapter's namespace.

**Definition of done:**
- A non-developer can complete every workflow from the docs without
  touching the API directly.

### ✅ Slice 7 — Auth hardening (shipped)
**Why:** Currently password-only.

**Scope:**
- Email verification (token-link flow, console logger to start).
- Password reset.
- TOTP MFA (pyotp + QR code on profile page).
- Optional Google OAuth (env-gated).
- Rate limiting on `/api/auth/login`.

**Definition of done:**
- Brute-force on `/api/auth/login` is rate-limited (test).
- MFA can be enabled per user; login requires the second factor when
  set.

### ✅ Slice 8 — Replay / backtest runner (shipped)
**Why:** Spec mandates an experiment-log + metrics pipeline.

**Scope:**
- `app/research/runner.py` — runs a strategy against historical bars
  and produces an `experiments/<run_id>/` directory with `manifest.yaml`,
  `metrics.json`, `events.jsonl`.
- Deterministic results (seed + frozen code version recorded).
- CLI: `python -m app.research.run --manifest path/to/manifest.yaml`.
- Manifest schema validation.
- UI: list runs, view metrics.json.

**Definition of done:**
- Two runs of the same manifest produce byte-identical metrics.json.
- The append-only `EXPERIMENT_LOG.md` workflow from the spec is
  enforceable (validation rejects runs without metrics.json).

### ✅ Slice 9 — Observability (shipped)
**Why:** Spec has a whole observability doc not yet wired.

**Scope:**
- Structured JSON logs (one event per action, fields: timestamp,
  actor, resource, latency_ms, outcome).
- Prometheus metrics endpoint at `/metrics` (request count + latency
  histograms + bot count + audit-event rate + risk-block rate).
- Optional OpenTelemetry traces (env-gated).
- Runbook updates in `docs/`.

**Definition of done:**
- Risk rejection rate is queryable from a Grafana panel.
- Logs are parseable as JSON; no f-string log statements.

### ✅ Slice 10 — Postgres + Alembic (shipped)
**Why:** SQLite is fine for low-traffic single-node; Postgres for HA.

**Scope:**
- Alembic migration tree (`backend/alembic/versions/`).
- CI step that runs `alembic upgrade head` against an empty Postgres.
- Connection-pooling tuning (NullPool for SQLite, default for PG).
- Update droplet to managed Postgres (or container).
- Backup script (cron or DO managed-DB snapshots).

**Definition of done:**
- A fresh Postgres instance + `alembic upgrade head` produces the
  same schema as `Base.metadata.create_all`.
- Switching `DATABASE_URL` from SQLite to Postgres on the droplet
  works without code changes.

---

## Reference docs

In `docs/`:

- `MULTI_ADAPTER_BROKER_SYSTEM.md` — broker adapter contract & registry.
  Authoritative for slice 3.
- `FRONTEND_PRODUCT_REQUIREMENTS.md` — UX scope. Authoritative for
  slice 6.
- `discipline-governance-admin-config-controls.md` — config workflow,
  RBAC, audit. Authoritative for any UX change touching configs.
- `algorithms-trading-system-primitives-paper-first.md` — replay /
  experiment-log primitives. Authoritative for slice 8.
- `research-system-additions-research-metrics-runbook-observability-data.md`
  — observability / runbook. Authoritative for slice 9.
- `prompt-pack-foundation-readme-master-rules-phases.md` — meta rules
  for any AI prompt acting on this repo. Read once.

---

## Coding conventions any agent must follow

- **Tests first** for every behavioural change. Existing tests are at
  `backend/tests/`. Use `pytest -q`.
- **Small diffs.** No drive-by refactors. If a refactor is needed,
  it's a separate PR.
- **No comments unless the WHY is non-obvious.** Names + types should
  carry meaning.
- **Strict typing.** Pydantic for domain types; SQLAlchemy `Mapped[…]`
  for ORM rows; TypeScript strict mode on the frontend.
- **No mocks for the database.** Use the in-memory SQLite test fixture
  (`backend/tests/conftest.py:reset_store`).
- **Keep `Store` deleted.** All persistence flows through SQLAlchemy
  sessions in `app/db/engine.py:session_scope()`.
- **Keep `app/db/store.py` from coming back.** If you need a quick
  cache, put it in the service module with a clear comment.

---

## Deploy / operate

Production URLs and ops procedures are documented in
`backend/deploy/README.md`. Summary:

- Backend: `systemd` unit `trading-bot-backend` on the droplet, port 8000.
  Update: `git pull && systemctl restart trading-bot-backend`.
- Frontend: Vercel project `trading-bot-frontend` (team
  `ballo-innovations`). Update: `cd frontend && vercel deploy --prod --yes`.
- DB: SQLite at `/opt/trading-bot/backend/data/trading-bot.db`,
  `chown -R www-data:www-data /opt/trading-bot`.

---

## Changelog

- **2026-04-27** — Slices 9–10 shipped. Production hardening: JWT-secret boot
  guard, rate limits on TOTP/forgot-password, pinned all deps, demo passwords
  moved to `SEED_DEMO_PASSWORD` env var. Prometheus metrics fully wired
  (audit_events_total, backtest_runs_total). RUNBOOK.md added. Alembic.ini
  updated with DATABASE_URL guidance.
- **2026-04-25** — Slices 3–8 marked shipped. TOTP profile UI, password
  reset flow, equity curve chart, symbol picker, strategy dropdown,
  approvals/rollback UI, and research backtest runner all live.
- **2026-04-24** — Slice 1 shipped (persistence). Roadmap created.
  Persistence-layer caveat removed from README.
- **2026-04-23** — Slice 0 shipped (skeleton). Initial deployment to
  droplet + Vercel. README, deploy docs, project memory in place.
