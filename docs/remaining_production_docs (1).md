```docs/DATA_PIPELINE.md
# DATA PIPELINE

Date: 2026-04-09  
Status: Draft, implementation-ready  
Trading mode: **Paper trading only**  
Live trading: **Forbidden unless explicit safety gates are met**  
Storage backend: **UNSPECIFIED**  
Historical data vendor: **UNSPECIFIED**  
Realtime stream source: **UNSPECIFIED**

## 1. Purpose

This document defines the data architecture required to support a deterministic, paper-trading-first trading system. It establishes how market data is ingested, validated, normalized, versioned, replayed, stored, and served to strategies, analytics, and risk systems.

The data pipeline exists to guarantee:
- reproducible research runs,
- deterministic paper execution,
- consistent symbol and timestamp handling,
- explicit failure behavior when data is missing, stale, malformed, or ambiguous.

## 2. Goals

The data pipeline must:
- provide a single canonical source of truth for market data inside the system,
- separate external vendor/exchange payloads from internal normalized formats,
- support both historical replay and paper-live simulation,
- expose deterministic feeds to strategies and simulators,
- prevent strategies from reading raw exchange payloads directly,
- support offline testing with fixture-based data.

## 3. Non-negotiable rules

- Strategies must never access CCXT or raw exchange payloads directly.
- All timestamps must be normalized to UTC epoch milliseconds.
- All symbols must be normalized into canonical internal representation.
- All external data must pass validation before entering the internal pipeline.
- Missing or stale data must cause NOOP or a controlled halt, never undefined behavior.
- Paper trading only: all downstream consumers must remain paper-only until safety gates are met.
- Live trading data path must not be introduced implicitly.

## 4. Scope

In scope:
- Historical candles
- Realtime ticker snapshots
- Realtime best bid/ask snapshots
- Optional trade prints (later)
- Data normalization
- Data validation
- Replay feeds
- Data contracts for strategies and execution simulator

Out of scope:
- Alternative data
- On-chain data
- News/sentiment feeds
- ML feature stores
- Vendor selection

## 5. Data domains

### 5.1 Raw market data
External data exactly as returned by exchange/vendor APIs.

Examples:
- CCXT ticker payloads
- exchange OHLCV arrays
- websocket event payloads

Raw data is not trusted and must not be consumed directly by strategies.

### 5.2 Normalized market data
Internal canonical representations derived from raw payloads.

Examples:
- `TickerSnapshot`
- `OrderBookTop`
- `Candle`
- `TradePrint`

This is the only format allowed across service boundaries.

### 5.3 Derived data
Computed internal values.

Examples:
- returns
- moving averages
- volatility estimates
- staleness flags
- regime labels

Derived data must always reference the normalized source and generation rules.

## 6. Canonical schemas

### 6.1 Candle
```yaml
Candle:
  symbol: string        # BTC/USDT
  timeframe: string     # 1m, 5m, 1h
  open_time_ms: integer
  close_time_ms: integer
  open: float
  high: float
  low: float
  close: float
  volume_base: float
  source: string
  source_version: string | null
```

### 6.2 TickerSnapshot
```yaml
TickerSnapshot:
  symbol: string
  ts_ms: integer
  last: float
  bid: float | null
  ask: float | null
  volume_24h_base: float | null
  source: string
```

### 6.3 OrderBookTop
```yaml
OrderBookTop:
  symbol: string
  ts_ms: integer
  bid_price: float
  bid_size: float
  ask_price: float
  ask_size: float
  source: string
```

### 6.4 TradePrint
```yaml
TradePrint:
  symbol: string
  ts_ms: integer
  price: float
  qty_base: float
  side: buy | sell | unknown
  source: string
```

## 7. Symbol normalization

All symbols must be represented internally as `BASE/QUOTE`.

Examples:
- `BTCUSDT` → `BTC/USDT`
- `XBT/USD` → canonical mapping policy is **UNSPECIFIED**

Rules:
- Internal symbol registry must map vendor symbols to canonical symbols.
- If a symbol cannot be normalized deterministically, data must be rejected.
- Strategy configs must use canonical symbols only.

## 8. Timestamp rules

- Canonical timestamp = UTC epoch milliseconds.
- Exchange-local or ISO timestamps must be converted immediately at ingestion.
- Candle timestamps must define whether they refer to open or close. Internal rule: both `open_time_ms` and `close_time_ms` must be stored.
- Replay systems must emit timestamps monotonically.

## 9. Timeframes

Allowed timeframes are system-configured.
Initial allowed list is **UNSPECIFIED**.

Rules:
- Timeframes must be enumerated centrally.
- No strategy may invent unsupported timeframes.
- Cross-timeframe aggregation rules must be explicit and tested.

## 10. Data quality requirements

Every normalized record must satisfy:
- positive prices where applicable,
- non-negative volume,
- monotonic timestamps per symbol/timeframe stream,
- no malformed symbol,
- no NaN or infinite numeric values.

Additional candle constraints:
- `high >= max(open, close, low)`
- `low <= min(open, close, high)`
- `open_time_ms < close_time_ms`

## 11. Staleness policy

Staleness thresholds are configuration-driven and currently **UNSPECIFIED**.

Example policy:
- Ticker stale if `now_ms - ts_ms > ticker_stale_threshold_ms`
- Order book top stale if `now_ms - ts_ms > book_stale_threshold_ms`
- Candle stale if expected close time has passed and new candle not received within grace window

Behavior on stale data:
- strategies must NOOP,
- execution simulator must reject orders that depend on stale prices,
- observability must emit `data_stale` event,
- repeated staleness may trigger a circuit breaker.

## 12. Historical data ingestion

Historical ingestion pipeline:
1. Fetch raw historical data from approved source.
2. Validate payload structure.
3. Normalize symbols and timestamps.
4. Validate domain constraints.
5. Persist raw copy if raw retention enabled.
6. Persist normalized canonical records.
7. Record source metadata and ingestion batch id.

Historical imports must be versioned.

### 12.1 Historical data invariants
- Same source + same parameters + same version must produce the same normalized output.
- Import jobs must be idempotent.
- Partial imports must be marked incomplete and not treated as valid research input.

## 13. Realtime ingestion

Realtime ingestion pipeline:
1. Fetch or receive raw event.
2. Validate shape.
3. Normalize.
4. Stamp ingest metadata.
5. Update latest market state cache.
6. Append to event stream if configured.
7. Expose to downstream consumers via feed service.

## 14. Replay engine requirements

Replay is mandatory for deterministic research and testing.

Replay engine must:
- consume historical normalized records,
- emit events in timestamp order,
- preserve causal order,
- support clock advancement,
- support deterministic stepping,
- support symbol filtering,
- support timeframe filtering,
- support fixed-seed behavior if randomness is introduced later.

### 14.1 Replay modes
- step mode: one event/candle at a time
- timed mode: simulated wall-clock progression
- fast-forward mode: process without delays

### 14.2 Replay invariants
- No future data leakage.
- Strategy at timestamp `t` sees only records with `ts_ms <= t`.
- Replay output must be reproducible from the same dataset and manifest.

## 15. Service boundaries

### 15.1 External adapter layer
Responsible for pulling raw market data.

Examples:
- `CCXTMarketDataAdapter`
- `FixtureMarketDataAdapter`

### 15.2 Data normalization layer
Responsible for converting raw records into canonical schemas.

### 15.3 Data quality layer
Responsible for validation, anomaly checks, and staleness flags.

### 15.4 Feed service layer
Exposes normalized data to strategies, execution simulator, and analytics.

Strategies must only depend on the feed service, never on adapters.

## 16. Feed service interface

Example interface:
```python
class MarketDataFeed(Protocol):
    def get_last_ticker(self, symbol: str) -> TickerSnapshot: ...
    def get_top_of_book(self, symbol: str) -> OrderBookTop: ...
    def get_recent_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]: ...
    def is_stale(self, symbol: str) -> bool: ...
```

## 17. Storage requirements

Storage backend is **UNSPECIFIED**, but the logical layout must support:
- raw data retention (optional)
- normalized data tables/collections
- replayable ordered event access
- symbol/timeframe indexing
- source/version metadata

Recommended logical partitions:
- raw_market_events
- normalized_candles
- normalized_tickers
- normalized_orderbook_top
- ingestion_batches
- data_quality_events

## 18. Versioning

Every dataset used in research must record:
- source name
- source version or retrieval timestamp
- normalization code version
- ingestion batch id

Research runs must reference dataset identity in manifest.

## 19. Failure handling

### 19.1 Missing data
- Reject run start if required historical window is incomplete.
- NOOP strategy step if realtime record missing.
- Emit `data_missing` event.

### 19.2 Malformed data
- Reject record at normalization layer.
- Increment validation failure metrics.
- Preserve raw payload only if safe and configured.

### 19.3 Non-monotonic timestamps
- Reject or quarantine record.
- Emit `data_ordering_violation` event.

### 19.4 Vendor outage
- Mark feed degraded.
- Pause dependent strategies.
- Trigger alert.

## 20. Testing requirements

### Unit tests
- symbol normalization
- timestamp normalization
- candle validation
- staleness checks
- replay ordering

### Integration tests
- adapter → normalization → feed
- replay engine + strategy step
- stale data blocks execution

### Fixture requirements
- canonical valid dataset
- malformed payload examples
- stale data examples
- duplicate/out-of-order timestamp examples

## 21. Example pseudocode

### Normalization
```python
def normalize_ticker(raw: dict, source: str) -> TickerSnapshot:
    symbol = normalize_symbol(raw)
    ts_ms = normalize_timestamp(raw)
    last = float(raw["last"])
    if last <= 0:
        raise ValueError("invalid last price")
    return TickerSnapshot(
        symbol=symbol,
        ts_ms=ts_ms,
        last=last,
        bid=_maybe_float(raw.get("bid")),
        ask=_maybe_float(raw.get("ask")),
        volume_24h_base=_maybe_float(raw.get("baseVolume")),
        source=source,
    )
```

### Staleness gate
```python
def require_fresh_ticker(ticker: TickerSnapshot, now_ms: int, stale_threshold_ms: int) -> None:
    if now_ms - ticker.ts_ms > stale_threshold_ms:
        raise RuntimeError("data_stale")
```

## 22. Reviewer checklist

- [ ] Strategies consume canonical feed service only
- [ ] Symbols normalized centrally
- [ ] UTC epoch ms used everywhere
- [ ] Replay engine prevents lookahead
- [ ] Data quality checks are explicit
- [ ] Staleness policy blocks unsafe execution
- [ ] Dataset/version identity captured in manifests

## 23. Future work

- order-book depth replay
- multi-source reconciliation
- feature store for research
- data lineage dashboard
- vendor failover policy
```

```docs/STRATEGY_RUNNER.md
# STRATEGY RUNNER

Date: 2026-04-09  
Status: Draft, implementation-ready  
Trading mode: **Paper trading only**  
Live trading: **Forbidden unless explicit safety gates are met**  
Scheduler: **UNSPECIFIED**

## 1. Purpose

The strategy runner is the runtime orchestration layer that loads manifests, initializes strategies, advances them against market data, applies risk gates, calls the paper execution boundary, and records run artifacts.

## 2. Goals

The runner must:
- execute strategies deterministically,
- provide a single runtime control plane,
- isolate strategies from infrastructure details,
- support replay and paper-live modes,
- support start, pause, resume, and stop semantics,
- preserve idempotency and auditability.

## 3. Non-negotiable rules

- Paper-only mode is mandatory.
- Strategies must not place orders directly; only through execution service.
- One runner instance must not double-submit the same logical order.
- State transitions must be explicit and logged.
- Every run must emit artifacts and metrics.

## 4. Responsibilities

The runner is responsible for:
- loading strategy manifests,
- validating safety flags,
- instantiating strategy + dependencies,
- consuming feed updates,
- calling risk engine before execution,
- invoking paper execution service,
- collecting events, metrics, and final run state.

## 5. Non-responsibilities

The runner is not responsible for:
- exchange-specific API semantics,
- raw market data fetching,
- frontend rendering,
- manual governance decisions,
- live order routing.

## 6. Runtime modes

### 6.1 Replay mode
- deterministic
- consumes historical normalized data
- used for research, validation, and regression testing

### 6.2 Paper-live mode
- consumes current market data feed
- routes orders only to simulator
- used for unattended paper validation

## 7. State machine

Run states:
- `created`
- `initializing`
- `running`
- `paused`
- `stopping`
- `stopped`
- `failed`
- `completed`

Allowed transitions:
- created → initializing
- initializing → running | failed
- running → paused | stopping | failed | completed
- paused → running | stopping
- stopping → stopped
- failed → stopped

## 8. Manifest contract

Each run must have a manifest with at minimum:
```yaml
schema: run_manifest.v1
run_id: string
strategy_id: string
strategy_version: string
paper_trading_only: true
live_trading_enabled: false
symbols: [string]
params: {}
window:
  start_ms: integer | null
  end_ms: integer | null
mode: replay | paper_live
code_version: string | null
data_source: string | null
```

## 9. Core interfaces

### 9.1 Strategy interface
```python
class Strategy(Protocol):
    def on_start(self, ctx: StrategyContext) -> None: ...
    def on_event(self, event: MarketEvent, ctx: StrategyContext) -> None: ...
    def on_stop(self, ctx: StrategyContext) -> None: ...
```

### 9.2 StrategyContext
Must expose only approved services:
- market data feed
- paper execution service
- risk engine
- event logger
- clock
- run metadata

### 9.3 Runner interface
```python
class StrategyRunner(Protocol):
    def start(self, manifest: RunManifest) -> RunHandle: ...
    def pause(self, run_id: str) -> None: ...
    def resume(self, run_id: str) -> None: ...
    def stop(self, run_id: str) -> None: ...
```

## 10. Execution loop

High-level algorithm:
1. Validate manifest.
2. Validate paper-only flags.
3. Load strategy implementation.
4. Initialize context and services.
5. Transition to running.
6. For each market event:
   - update feed state,
   - call strategy `on_event`,
   - strategy may request action,
   - risk engine evaluates request,
   - paper execution handles approved request,
   - logs and metrics updated.
7. On stop or completion:
   - flush metrics,
   - persist artifacts,
   - transition to completed/stopped.

## 11. Action request model

Strategies should not call execution directly from deep internals. Preferred model:
- strategy emits an `ActionRequest`
- runner submits it through risk + execution pipeline

Example:
```yaml
ActionRequest:
  action_id: string
  run_id: string
  ts_ms: integer
  strategy_id: string
  side: buy | sell
  symbol: string
  amount: float
  order_type: market
  rationale: string | null
```

## 12. Idempotency

Each action must be uniquely identified.

Rules:
- repeated same `action_id` must not create multiple fills,
- runner restart must preserve idempotency behavior,
- idempotency backend is **UNSPECIFIED**, but logical contract is mandatory.

## 13. Persistence requirements

Persist at minimum:
- run metadata
- state transitions
- submitted actions
- execution results
- error events
- metrics snapshots

Storage backend is **UNSPECIFIED**.

## 14. Failure handling

### 14.1 Strategy exception
- capture error
- mark run failed
- stop further actions
- emit structured event

### 14.2 Data feed degraded
- pause strategy actions
- continue monitoring if appropriate
- emit alert and event

### 14.3 Risk violation
- reject action
- record reason
- continue or halt based on policy

### 14.4 Execution service error
- do not retry blindly
- emit execution_error
- respect idempotency rules
- escalate to circuit breaker if threshold breached

## 15. Scheduling

Scheduling mechanism is **UNSPECIFIED**, but runner must support:
- single-run local execution,
- periodic research jobs,
- long-lived paper validation jobs.

## 16. Control operations

### Start
- validate manifest
- validate dependencies
- emit `run_started`

### Pause
- no new actions accepted
- in-flight deterministic processing completes
- emit `run_paused`

### Resume
- continue from persisted state if available
- emit `run_resumed`

### Stop
- cease accepting new events
- flush metrics/logs
- emit `run_stopped`

## 17. Testing requirements

### Unit tests
- manifest validation
- state transitions
- action idempotency
- pause/resume behavior
- risk-blocked action behavior

### Integration tests
- replay mode end-to-end
- paper-live mode with fixture feed
- run artifact generation

## 18. Example pseudocode

```python
def run_strategy(manifest: RunManifest) -> None:
    validate_manifest(manifest)
    enforce_paper_only(manifest)
    strategy = load_strategy(manifest.strategy_id, manifest.strategy_version)
    ctx = build_context(manifest)
    transition(manifest.run_id, "running")
    strategy.on_start(ctx)

    for event in ctx.feed.events():
        if ctx.state.is_paused:
            continue
        if ctx.state.is_stopping:
            break
        try:
            strategy.on_event(event, ctx)
        except Exception as exc:
            record_error(manifest.run_id, exc)
            transition(manifest.run_id, "failed")
            break

    strategy.on_stop(ctx)
    finalize_run(manifest.run_id)
```

## 19. Reviewer checklist

- [ ] runner enforces paper-only mode
- [ ] strategies run through context only
- [ ] state machine is explicit and tested
- [ ] idempotency is defined and enforced
- [ ] artifacts are always emitted
- [ ] failure modes are controlled and logged
```

```docs/OBSERVABILITY_STACK.md
# OBSERVABILITY STACK

Date: 2026-04-09  
Status: Draft, implementation-ready  
Trading mode: **Paper trading only**  
Live trading: **Forbidden unless explicit safety gates are met**  
Monitoring backend: **UNSPECIFIED**  
Alert transport: **UNSPECIFIED**

## 1. Purpose

This document defines the observability requirements for the trading platform: structured logs, operational metrics, strategy metrics, risk events, alerts, and dashboards.

The goal is not merely to collect logs, but to make the system explainable, debuggable, and auditable.

## 2. Goals

The observability layer must:
- make every important decision traceable,
- surface safety and risk violations immediately,
- support incident response,
- support experiment analysis,
- support deterministic post-mortems.

## 3. Non-negotiable rules

- All important events must be structured, not ad hoc strings.
- No secrets may appear in logs.
- Every action rejection must include a machine-readable reason.
- Observability must work in local development and offline replay.
- Paper-only mode must be visible in system status output.

## 4. Observability pillars

### 4.1 Logs
Append-only structured event records.

### 4.2 Metrics
Numeric series for health, strategy behavior, execution, and risk.

### 4.3 Alerts
Threshold or rule-based notifications for urgent conditions.

### 4.4 Traces
Optional and currently **UNSPECIFIED**. If introduced, must follow service boundary semantics.

## 5. Structured logging standard

All logs should be JSON-compatible records.

Required fields:
```yaml
LogEvent:
  ts_ms: integer
  level: DEBUG | INFO | WARN | ERROR
  event_type: string
  service: string
  run_id: string | null
  strategy_id: string | null
  symbol: string | null
  message: string
  details: object
```

## 6. Event taxonomy

### System events
- system_started
- system_stopped
- config_loaded
- unsafe_mode_detected

### Run events
- run_created
- run_started
- run_paused
- run_resumed
- run_stopped
- run_failed
- run_completed

### Data events
- data_received
- data_normalized
- data_stale
- data_missing
- data_validation_failed
- data_ordering_violation

### Strategy events
- strategy_initialized
- strategy_step
- action_requested
- action_skipped
- action_rejected

### Execution events
- order_submitted
- order_filled
- order_rejected
- duplicate_order_blocked
- execution_error

### Risk events
- risk_check_passed
- risk_check_failed
- drawdown_limit_breached
- daily_loss_limit_breached
- circuit_breaker_triggered
- kill_switch_triggered

## 7. Metrics instrumentation

### 7.1 System health metrics
- process_uptime_seconds
- runs_active
- runs_failed_total
- event_queue_depth (if applicable; UNSPECIFIED runtime design)
- config_load_failures_total

### 7.2 Data metrics
- data_events_total
- data_validation_failures_total
- stale_data_events_total
- data_latency_ms

### 7.3 Strategy metrics
- strategy_steps_total
- action_requests_total
- action_rejections_total
- action_noop_total

### 7.4 Execution metrics
- paper_orders_submitted_total
- paper_orders_filled_total
- paper_orders_rejected_total
- duplicate_orders_blocked_total
- execution_errors_total

### 7.5 Risk metrics
- risk_failures_total
- kill_switch_triggers_total
- drawdown_breaches_total
- daily_loss_breaches_total

## 8. Alert definitions

Alert thresholds are **UNSPECIFIED**, but alert categories are mandatory.

### Critical alerts
- unsafe mode detected
- repeated execution errors
- kill switch triggered
- circuit breaker triggered
- persistent stale data

### Warning alerts
- elevated action rejection rate
- missing metrics artifact after run completion
- repeated validation failures

## 9. Dashboard requirements

Minimum dashboards:
- system health dashboard
- run status dashboard
- strategy metrics dashboard
- risk event dashboard
- data quality dashboard

Dashboard tooling is **UNSPECIFIED**.

## 10. Artifact requirements

Each run must emit:
- `metrics.json`
- `events.jsonl` or equivalent structured log artifact
- final run summary

## 11. Correlation rules

Every event should include relevant correlation identifiers:
- run_id
- strategy_id
- action_id when applicable
- client_order_id when applicable

## 12. Failure mode observability

The following conditions must always produce observable evidence:
- strategy exception
- stale data block
- risk gate rejection
- duplicate order block
- paper execution rejection
- manifest validation failure

## 13. Example log records

### Order rejected
```json
{
  "ts_ms": 1775400000000,
  "level": "WARN",
  "event_type": "order_rejected",
  "service": "execution_service",
  "run_id": "run_001",
  "strategy_id": "dca_btc",
  "symbol": "BTC/USDT",
  "message": "Order rejected by risk engine",
  "details": {
    "reason": "daily_loss_limit_breached",
    "action_id": "act_123"
  }
}
```

### Data stale
```json
{
  "ts_ms": 1775400001000,
  "level": "WARN",
  "event_type": "data_stale",
  "service": "market_data_feed",
  "run_id": "run_001",
  "strategy_id": null,
  "symbol": "BTC/USDT",
  "message": "Ticker exceeds stale threshold",
  "details": {
    "ticker_ts_ms": 1775399990000,
    "threshold_ms": 5000
  }
}
```

## 14. Testing requirements

### Unit tests
- log schema generation
- redaction/sanitization
- event type consistency
- correlation id propagation

### Integration tests
- run emits events + metrics artifact
- risk failure produces alert-worthy event
- stale data produces warning event

## 15. Redaction policy

Logs must redact or omit:
- API keys
- API secrets
- passwords
- auth tokens
- full raw payloads if they contain secrets

## 16. Reviewer checklist

- [ ] structured logs defined centrally
- [ ] no secrets in logs
- [ ] key events have machine-readable reasons
- [ ] run artifacts always emitted
- [ ] alert categories defined
- [ ] dashboards mapped to operational questions
```

```docs/GLOBAL_RISK_ENGINE.md
# GLOBAL RISK ENGINE

Date: 2026-04-09  
Status: Draft, implementation-ready  
Trading mode: **Paper trading only**  
Live trading: **Forbidden unless explicit safety gates are met**  
Persistence backend: **UNSPECIFIED**

## 1. Purpose

This document defines the central risk governance layer for the trading platform. It is responsible for evaluating every requested action against account-level, strategy-level, and system-level constraints before the paper execution service may accept it.

## 2. Goals

The risk engine must:
- enforce hard limits consistently,
- aggregate exposure across strategies,
- centralize rejection logic,
- provide deterministic results,
- emit machine-readable rejection reasons,
- support auditing and post-mortem analysis.

## 3. Non-negotiable rules

- Every action request must pass through the risk engine before execution.
- Strategies must not bypass the risk engine.
- Risk decisions must be deterministic for the same state and input.
- Rejections must be explicit and logged.
- Hard safety breaches may halt the run or trigger a circuit breaker.
- Paper-only mode is mandatory.

## 4. Scope

In scope:
- per-order validation
- drawdown protection
- daily loss limits
- max concurrent positions
- max notional per trade
- max exposure per asset
- kill switch and circuit breaker

Out of scope:
- portfolio optimization
- margin-specific risk models
- derivatives liquidation models
- live broker risk APIs

## 5. Risk decision model

Input:
- current portfolio state
- current strategy state
- current system state
- incoming action request
- current market data snapshot

Output:
```yaml
RiskDecision:
  allowed: bool
  reason_code: string | null
  severity: INFO | WARN | ERROR | CRITICAL
  halt_required: bool
  details: object
```

## 6. Risk checks

### 6.1 Kill switch
If kill switch is enabled:
- reject all new action requests,
- emit `kill_switch_triggered` if first trigger not already recorded.

### 6.2 Max drawdown
If current portfolio drawdown exceeds configured threshold:
- reject new actions,
- optionally halt run.

Threshold: **UNSPECIFIED**

### 6.3 Daily loss limit
If daily realized/unrealized loss exceeds threshold:
- reject new actions,
- optionally halt run.

Threshold: **UNSPECIFIED**

### 6.4 Max concurrent positions
If number of open positions >= configured limit:
- reject opening actions,
- allow reducing/closing actions if policy permits.

Threshold: **UNSPECIFIED**

### 6.5 Max notional per trade
If requested notional > limit:
- either reject or clamp based on policy.
Policy currently recommended: reject.

Threshold: **UNSPECIFIED**

### 6.6 Max exposure per asset
If resulting position would exceed asset exposure cap:
- reject.

Threshold: **UNSPECIFIED**

### 6.7 Data freshness dependency
If required market data is stale:
- reject action request.

### 6.8 Duplicate order protection
If action_id or client_order_id already exists:
- reject as duplicate,
- do not forward to execution.

## 7. State required by risk engine

- portfolio equity
- drawdown state
- daily PnL state
- open positions by symbol
- pending/processed action ids
- kill switch state
- circuit breaker state

## 8. Circuit breaker

Circuit breaker is a system-level failsafe.

Triggers may include:
- repeated execution errors
- repeated stale data incidents
- repeated risk anomalies
- inconsistent state detection

Parameters are **UNSPECIFIED**.

Effects:
- halt new action requests,
- mark run degraded,
- require operator intervention or cooldown.

## 9. Invariants

The following must always hold:
- no action reaches execution without risk evaluation,
- risk decision references current known state,
- duplicate action ids do not create new orders,
- reducing risk must never be blocked by position-count rule unless explicitly justified,
- paper-only mode violation is fatal.

## 10. Service interface

```python
class RiskEngine(Protocol):
    def evaluate(self, request: ActionRequest, state: RiskState) -> RiskDecision: ...
```

## 11. Example pseudocode

```python
def evaluate(request: ActionRequest, state: RiskState) -> RiskDecision:
    if state.kill_switch_enabled:
        return reject("kill_switch", halt_required=True)
    if state.data_is_stale(request.symbol):
        return reject("data_stale")
    if state.is_duplicate(request.action_id):
        return reject("duplicate_action")
    if state.drawdown_pct > state.max_drawdown_pct:
        return reject("max_drawdown_breached", halt_required=True)
    if state.daily_pnl < -state.daily_loss_limit:
        return reject("daily_loss_limit_breached", halt_required=True)
    if opens_new_position(request) and state.open_positions_count >= state.max_open_positions:
        return reject("max_open_positions")
    if requested_notional(request, state.market_price(request.symbol)) > state.max_notional_per_trade:
        return reject("max_notional_per_trade")
    return allow()
```

## 12. Testing requirements

### Unit tests
- each risk rule independently
- duplicate protection
- reducing-risk request handling
- deterministic same-input same-output behavior

### Integration tests
- runner + risk engine + execution boundary
- stale data blocks action
- drawdown breach halts run

## 13. Audit requirements

Each risk decision must record:
- request id
- timestamp
- result
- reason_code
- relevant threshold snapshot
- relevant portfolio snapshot id

## 14. Reviewer checklist

- [ ] all actions pass through risk engine
- [ ] rejection reasons are machine-readable
- [ ] system-level and strategy-level limits are separated
- [ ] duplicate protection exists
- [ ] circuit breaker behavior is defined
- [ ] critical breaches can halt execution
```

```docs/LIVE_PROMOTION_GATES.md
# LIVE PROMOTION GATES

Date: 2026-04-09  
Status: Draft, governance-ready  
Current system mode: **Paper trading only**

## 1. Purpose

This document defines the governance required before any live trading design or implementation work may begin.

## 2. Current rule

Live trading is forbidden.

No code, configuration, endpoint, or operational workflow may enable live order routing until this document's gates are explicitly approved.

## 3. Required gates before live design work

### Gate 1: Research maturity
- strategy has passed documented research criteria
- repeatable results exist
- graveyard and experiment log discipline in place

### Gate 2: Runtime maturity
- strategy runner is stable
- data pipeline deterministic
- observability complete
- risk engine complete

### Gate 3: Operational maturity
- runbook validated
- incident response rehearsed
- key rotation documented
- deployment model chosen

### Gate 4: Governance maturity
- capital allocation rules approved
- stop conditions approved
- on-call/owner model defined
- review board defined

### Gate 5: Security maturity
- auth model defined
- secret management defined
- permission model defined
- audit logging complete

## 4. Current status

All gates: **UNSATISFIED** until explicitly reviewed.

## 5. Reviewer checklist

- [ ] no live code exists
- [ ] no implicit live toggle exists
- [ ] live promotion requires explicit written approval
- [ ] paper-only default remains enforced
```


```docs/UI_CONFIGURATION_GUIDELINES.md
# UI CONFIGURATION GUIDELINES

Date: 2026-04-09  
Status: Draft, implementation-ready  
Audience: Product, design, frontend, backend, and Cursor-assisted implementation workflows  
System mode: **Paper trading only**  
Live trading controls: **Forbidden unless explicit safety gates are met**

## 1. Purpose

This document defines how the admin-facing UI must support configuration, management, and controlled change of bot behavior. The goal is to make the system highly configurable without making it unsafe, inconsistent, or opaque.

The admin UI must allow authorized users to:
- create bot configurations,
- modify existing configurations,
- pause, resume, duplicate, and archive configurations,
- adjust strategy parameters, risk settings, scheduling, and run modes,
- review the impact of changes before applying them,
- maintain an audit trail of all changes.

This document does **not** authorize live trading controls. All UI-driven configuration must remain paper-trading-first until live safety gates are formally satisfied.

## 2. Core design principle

The UI must support **maximum controlled configurability**.

That means:
- admins can configure nearly everything that is safe to configure,
- but the system must prevent invalid, unsafe, contradictory, or unverifiable settings,
- and every change must be explicit, reviewable, and recoverable.

The UI is not just a form layer. It is a **configuration governance surface**.

## 3. Product requirement summary

The admin should be able to manually configure or change configurations whenever they want, including:
- bot identity and metadata,
- selected strategy,
- strategy parameter values,
- market symbols,
- run schedule,
- data source options,
- risk limits,
- sizing rules,
- paper execution behavior,
- stop conditions,
- observability options,
- configuration versioning and rollback.

However:
- changes must be validated,
- changes must be permission-controlled,
- changes must be logged,
- changes must not silently mutate active runs unless explicitly allowed.

## 4. Non-negotiable rules

- UI must default to **paper trading only**.
- UI must not expose a live trading toggle unless live promotion gates are satisfied and separately approved.
- UI must prevent invalid configurations from being saved.
- UI must distinguish between draft changes and applied changes.
- UI must show what changed, who changed it, and when.
- UI must require confirmation for high-impact configuration changes.
- UI must preserve historical configuration versions.
- UI must support reverting to a previous known-good configuration.

## 5. Admin capabilities

### 5.1 Create configuration
Admin can create a new bot configuration from:
- blank template,
- predefined strategy template,
- clone of an existing bot,
- archived configuration snapshot.

### 5.2 Edit configuration
Admin can change:
- general settings,
- strategy selection,
- strategy parameters,
- risk limits,
- execution settings,
- scheduling,
- symbols/instruments,
- labels/tags/notes.

### 5.3 Apply configuration
Admin can:
- save as draft,
- validate,
- apply to new run,
- schedule application,
- compare with current applied version,
- rollback to previous version.

### 5.4 Lifecycle controls
Admin can:
- pause bot,
- resume bot,
- stop bot,
- archive bot,
- duplicate bot,
- rename bot,
- assign ownership (if multi-user auth exists; currently **UNSPECIFIED**).

## 6. UI philosophy

The UI must be:
- powerful for admins,
- safe by default,
- explicit about consequences,
- optimized for clarity over cleverness,
- structured around reviewability.

A good admin UI should let users configure anything important **without needing to edit raw code**, while still preserving engineering discipline.

## 7. Information architecture

Recommended primary navigation:
- Dashboard
- Bots
- Strategies
- Runs
- Configurations
- Risk
- Data
- Logs / Events
- Settings

Recommended bot-level tabs:
- Overview
- Configuration
- Risk Controls
- Schedule
- Runtime Status
- Metrics
- Logs
- Versions / History

## 8. Configuration model

Every bot configuration should have three states:
- **Draft** — editable, not active
- **Applied** — currently used by runtime
- **Archived** — inactive historical record

Optional future state:
- **Pending Approval** — if approval workflow is added (currently **UNSPECIFIED**)

## 9. Configuration object model

Example logical shape:
```yaml
BotConfiguration:
  config_id: string
  bot_id: string
  version: integer
  status: draft | applied | archived
  name: string
  description: string | null
  strategy:
    strategy_id: string
    strategy_version: string
    params: object
  symbols:
    - string
  mode:
    paper_trading_only: true
    live_trading_enabled: false
  risk:
    max_drawdown_pct: number | null
    daily_loss_limit: number | null
    max_open_positions: integer | null
    max_notional_per_trade: number | null
  schedule:
    run_mode: replay | paper_live
    cadence: string | null
  execution:
    fee_bps: number | null
    slippage_bps: number | null
  observability:
    log_level: string | null
    emit_run_artifacts: boolean
  metadata:
    created_by: string | null
    created_at_ms: integer
    updated_by: string | null
    updated_at_ms: integer
```

## 10. UI sections and required behaviors

### 10.1 General settings panel
Fields:
- bot name
- description
- owner/team (if available)
- tags
- environment label

Rules:
- name required
- description optional
- immutable ids hidden from casual editing but visible in advanced mode

### 10.2 Strategy configuration panel
Fields:
- strategy selector
- strategy version selector
- strategy parameter editor
- preset/template selector

Requirements:
- parameters must be rendered from strategy schema, not hardcoded UI fields
- field types must be inferred from schema: boolean, enum, integer, float, string, array
- invalid values must be blocked inline
- bounds must be visible in the UI
- default values must be shown clearly

### 10.3 Symbol selection panel
Fields:
- symbol picker
- canonical symbol display
- validation against supported symbol registry

Requirements:
- only canonical symbols allowed
- unsupported symbols rejected before save
- symbol changes shown in diff review

### 10.4 Risk controls panel
Fields:
- max drawdown
- daily loss limit
- max open positions
- max notional per trade
- max exposure per asset
- kill switch visibility/status

Requirements:
- unsafe empty values must be flagged if policy requires them
- high-risk changes must show warnings
- changes to applied configurations must require explicit confirmation

### 10.5 Execution settings panel
Fields:
- fee model inputs
- slippage assumptions
- execution mode (market-only initially)
- duplicate-order protection visibility

Requirements:
- no live order routing controls
- if a control is not implemented, mark it as unavailable rather than silently hiding system behavior

### 10.6 Schedule panel
Fields:
- run mode (`replay`, `paper_live`)
- cadence/schedule expression
- start time
- end time
- cooldown / pause policy

Requirements:
- schedule validation must happen before apply
- invalid or conflicting schedules blocked

### 10.7 Version history panel
Must show:
- version number
- author
- timestamp
- summary of changes
- ability to compare versions
- rollback action

### 10.8 Runtime status panel
Must show:
- current state
- last run id
- current config version
- current strategy
- current symbols
- current risk posture
- recent events

## 11. Draft vs applied configuration behavior

This is critical.

The UI must not assume that editing a form immediately changes runtime behavior.

Rules:
- changes are first saved as a draft,
- applying a configuration is a separate action,
- applied config must be immutable for audit purposes,
- editing an applied config should create a new draft version, not mutate in place.

## 12. Change review UX

Before applying changes, the admin must see:
- field-by-field diff,
- high-risk fields highlighted,
- validation summary,
- whether the change affects active runtime,
- whether restart/reload is required.

Example review sections:
- Changed fields
- Risk impact
- Schedule impact
- Strategy impact
- Runtime effect

## 13. Validation requirements

Validation must exist at three layers:

### 13.1 Field validation
Examples:
- max drawdown must be numeric
- max open positions must be integer
- symbols must be known canonical values

### 13.2 Schema validation
Entire configuration must match backend schema.

### 13.3 Business rule validation
Examples:
- live mode cannot be enabled
- end time cannot precede start time
- replay mode requires a time window
- strategy params must satisfy declared bounds

## 14. High-impact change handling

High-impact changes include:
- strategy change
- strategy version change
- risk limit loosening
- symbol set change
- schedule change affecting active run
- any future live-mode related field

Requirements:
- must display confirmation dialog,
- must show summary of impact,
- may require reason/note entry,
- must be logged in audit history.

## 15. Configuration versioning

Every applied config must have version identity.

Rules:
- version number increments on apply,
- versions are immutable once applied,
- rollback creates a new version derived from an old version,
- version history is append-only.

## 16. Audit trail requirements

Every configuration change must record:
- config id
- version
- actor
- timestamp
- changed fields
- old values summary
- new values summary
- action type (`created`, `edited`, `applied`, `rolled_back`, `archived`)
- optional reason/note

## 17. Permissions model

Authorization model is currently **UNSPECIFIED**, but the UI must be designed for role-aware behavior.

Recommended future roles:
- viewer
- operator
- admin
- owner

Until role system exists, assume admin-only configuration editing.

## 18. Manual override support

The admin explicitly wants the ability to manually configure or change configurations whenever needed.

Therefore the UI must support:
- free manual editing within schema bounds,
- advanced mode for raw parameter inspection,
- manual override reason capture,
- reversible changes,
- immediate visibility into what has changed.

Manual override does **not** mean bypassing validation or safety rules.

## 19. Advanced mode

Advanced mode may expose:
- raw JSON/YAML configuration view,
- strategy parameter object,
- manifest preview,
- config diff raw view,
- export/import of config.

Rules:
- advanced mode edits still pass validation,
- import must be schema-validated,
- secrets must never appear in exported config.

## 20. UX rules for forms

- Use grouped sections, not one giant form.
- Autosave draft is acceptable if clearly indicated.
- Apply action must be explicit.
- Show inline validation and summary validation.
- Preserve unsaved changes warning.
- Use sensible defaults from schema.
- Do not hide invalid state silently.

## 21. UX rules for dangerous actions

Dangerous actions:
- apply to active bot
- stop bot
- archive bot
- rollback config
- loosen risk settings

These must require:
- clear confirmation,
- visible consequences,
- optional typed confirmation for severe changes,
- logging.

## 22. Error state requirements

The UI must handle:
- validation errors
- save failure
- apply failure
- schema mismatch
- stale version conflict
- unauthorized action
- backend unavailable

Each error should be:
- human-readable,
- machine-mappable,
- non-destructive to unsaved work where possible.

## 23. Concurrency and conflict handling

If two admins edit the same config:
- stale draft detection required,
- applied version mismatch must be shown,
- conflict resolution workflow is required,
- last-write-wins without notice is forbidden.

## 24. Recommended screens

### Bot list
- search
- filter by status
- quick actions: duplicate, archive, pause

### Bot detail
- overview cards
- current config summary
- latest metrics
- latest risk state
- latest run status

### Config editor
- sectioned form
- schema-driven fields
- draft/apply workflow
- diff sidebar

### Version history
- timeline of changes
- compare versions
- rollback button

## 25. API expectations for backend support

The backend should expose endpoints or service contracts for:
- list bots
- get bot detail
- get current config
- create draft config
- validate config
- apply config
- list config versions
- compare config versions
- rollback config
- archive config

Exact route naming is **UNSPECIFIED**, but these capabilities are mandatory.

## 26. Testing requirements

### Frontend unit tests
- field rendering from schema
- inline validation
- draft/apply workflow
- diff rendering
- high-impact confirmation flow
- version history rendering

### Frontend integration tests
- create new config
- edit existing config
- validation failure path
- apply draft path
- rollback path

### Backend integration tests
- config schema validation
- version increment behavior
- immutable applied config behavior
- rollback semantics
- audit event creation

## 27. Example UX flow

### Create and apply a bot config
1. Admin opens Bots.
2. Clicks “New Bot”.
3. Chooses template.
4. Enters metadata.
5. Selects strategy.
6. Fills strategy params.
7. Configures risk.
8. Selects symbols.
9. Saves draft.
10. Reviews diff/summary.
11. Clicks Apply.
12. Confirms.
13. System creates new applied version and records audit trail.

## 28. Example configuration diff model

```yaml
ConfigDiff:
  config_id: string
  from_version: integer
  to_version: integer
  changes:
    - field: strategy.params.interval_seconds
      old: 60
      new: 120
      severity: medium
    - field: risk.max_drawdown_pct
      old: 5
      new: 8
      severity: high
```

## 29. Reviewer checklist

- [ ] UI supports manual configuration changes safely
- [ ] draft/apply distinction is explicit
- [ ] applied configs are immutable
- [ ] version history and rollback are supported
- [ ] schema-driven forms are used for strategy params
- [ ] risk changes are highlighted and confirmed
- [ ] audit trail is captured
- [ ] no live trading controls are exposed

## 30. Future extensions

- approval workflow
- multi-admin collaboration with comments
- staged rollout of configs
- config simulation before apply
- policy engine for role-based constraints
```

