# Cursor Operations and Research Docs Additions

## Executive summary

These five documents cover the operational and scientific gaps that typically cause brindle projects to fail even when the core codebase is solid: a repeatable research pipeline, metric definitions and artefacts, operational runbooks, observability standards, and data contracts/quality rules. They are designed to be **Cursor-enforceable** by aligning with concrete tooling mechanisms: FastAPI’s `TestClient` enables in-process endpoint tests with pytest, and FastAPI’s `app.dependency_overrides` is a first-class method to replace real dependencies with fakes during tests (making “no external I/O in tests” reviewable and enforceable). citeturn0search0turn0search1 Next.js’ environment-variable conventions (notably `NEXT_PUBLIC_` for browser-bundled values) enable an explicit “no secrets in client env” policy. citeturn0search2 CCXT’s documented asyncio examples (`ccxt.async_support`, `fetch_ticker`, `exchange.close`) support a clean runtime-only adapter boundary, keeping strategies and tests independent of external networks. citeturn1search2 Pytest’s `monkeypatch` (`setenv`/`delenv`) provides a canonical way to test safety gates deterministically without leaking state across tests. citeturn0search3 Vitest’s official mocking APIs (`vi.*`) provide deterministic frontend tests, including safe stubbing of globals like `fetch`. citeturn1search0  

```docs/RESEARCH_SYSTEM.md
# RESEARCH SYSTEM — Strategy Development Pipeline (Paper-First, Test-First)

Date: 2026-04-04 (Africa/Lusaka)  
Status: Active  
CI/CD provider: UNSPECIFIED  
Backtesting engine/tooling: UNSPECIFIED (this doc defines requirements regardless)

## Purpose
Provide a repeatable, auditable way to:
- generate strategy ideas,
- test them without self-deception (bias control),
- evaluate results using standard metrics,
- decide whether a strategy can run in paper unattended,
- and (future) define gates for live trading (still forbidden).

## Scope
In scope:
- Paper trading research workflow (design → implement → simulate/paper-run → evaluate).
- Artefacts required per strategy and per run.
- Bias-control checklist (no lookahead, no leakage).
Out of scope:
- Live trading (forbidden).
- Exchange-specific microstructure modelling (UNSPECIFIED).
- Full historical backtesting infra details (UNSPECIFIED).

## Non-negotiable rules
- PAPER FIRST: strategies must route orders through the paper execution boundary only.
- DETERMINISTIC: given the same inputs (prices/timestamps/config), outputs must be identical.
- TDD: no strategy logic without failing tests first.
- NO NETWORK IN TESTS: strategy tests must not hit exchanges; use fakes.
- SINGLE EXECUTION BOUNDARY: strategies call `ExecutionService.place_market_order(...)` (in-process) OR the paper API endpoint; never CCXT directly.

## Required artefacts (must exist before a strategy is considered “research-complete”)
For each strategy `strategy_id` and version `vX`:
1) Strategy spec (markdown)
   - hypothesis (“why should this work?”)
   - market regime assumptions
   - failure modes
   - risk policy required
2) Parameter schema
   - names, units, bounds, defaults (defaults may be UNSPECIFIED until chosen)
3) Test suite
   - unit tests for decision logic (pure step function)
   - integration tests against paper simulator/ledger
4) Run manifest (YAML/JSON; format UNSPECIFIED)
   - code version/hash (UNSPECIFIED mechanism)
   - parameters
   - environment (paper-only flags)
   - data sources version (UNSPECIFIED)
5) Results bundle output per run
   - `metrics.json` (see METRICS.md)
   - `run_log_summary.json` (UNSPECIFIED schema until observability stack chosen)
   - optional plots (UNSPECIFIED)

## Research lifecycle (required)
1) Idea → Hypothesis (write down the edge and when it might fail)
2) Strategy spec + parameter schema
3) Unit tests (decision logic), then code
4) Integration tests (paper simulator + ledger)
5) Run experiments (paper simulation/replay; engine UNSPECIFIED)
6) Evaluate metrics and compare against acceptance criteria
7) Post-mortem: keep, iterate, or reject  
8) Promotion gate: can run “paper unattended” only if criteria pass

## Bias-control checklist (must be completed per run)
No lookahead / leakage
- [ ] Strategy step uses only information available at that timestamp.
- [ ] No future candles/ticks are referenced.
- [ ] No “final close” prices used before close time (if using candles).
- [ ] No parameter tuning on the same period used for final evaluation.

Robustness
- [ ] Test on at least 2 market regimes (definition UNSPECIFIED, but must be stated).
- [ ] Include fees, and (later) slippage model (UNSPECIFIED for MVP).
- [ ] Evaluate sensitivity to parameters (small perturbations).

## Acceptance criteria (must be defined BEFORE calling a strategy “good”)
All thresholds are UNSPECIFIED until decided; the important part is consistency and precommitment:
- Minimum sample size (trades or time): UNSPECIFIED
- Max drawdown threshold: UNSPECIFIED
- Net expectancy after fees: > 0
- Stability across regimes: required (definition UNSPECIFIED)
- Operational error rate: below UNSPECIFIED threshold

## Templates

### Research ticket template (copy/paste)
- Strategy name:
- Hypothesis:
- Instruments:
- Trigger & exit logic (high level):
- Risk policy required:
- How could this fail?
- What would disprove it?
- Parameters (with bounds):
- Data requirements:
- Test plan (unit/integration):
- Success criteria (filled before experiments):

### Example Cursor output format (required structure for changes)
Task:
Assumptions (mark UNSPECIFIED if needed):
Plan:
Files to create/change (exact paths):
Tests first (list + key assertions):
Implementation (each file as a path-labelled fenced code block):
Run commands:
Next step (1–3 items):

## Required templates/snippets

### Pytest: ensure strategy calls execution boundary (no CCXT)
```python
def test_strategy_calls_execution_boundary_only():
    calls = []
    class FakeExecution:
        def place_market_order(self, side, symbol, amount, price):
            calls.append((side, symbol, amount, price))
            return {"status": "filled"}

    # Strategy.step must accept an execution dependency (DI), not import CCXT.
    strat = SomeStrategy(symbol="BTC/USDT", **{"defaults": "UNSPECIFIED"})
    strat.step(now_ms=0, price_last=50_000.0, execution=FakeExecution())
    assert calls, "Expected at least one execution call when trigger conditions are met"
```

## Reviewer checks (must pass)
- [ ] Strategy spec exists and states hypothesis + failure modes.
- [ ] Unit tests prove execution boundary usage and pure decision logic.
- [ ] Integration tests run without network; exchange dependencies are faked.
- [ ] `metrics.json` is produced and conforms to METRICS.md requirements.
- [ ] Acceptance criteria were defined before evaluating results.
```

```docs/METRICS.md
# METRICS — Definitions, Artefacts, and Test Requirements

Date: 2026-04-04 (Africa/Lusaka)  
Base currency convention: portfolio base currency (e.g., USDT)  
CI/CD provider: UNSPECIFIED

## Purpose
Standardise how we measure:
- performance (returns, PnL),
- risk (drawdown),
- execution costs (fees, slippage),
- and operational health (errors, latency),
so that strategy evaluation is consistent and reviewable.

## Scope
In scope:
- Paper trading metrics and later backtest metrics (same schema where possible).
- Required output artefacts per strategy run (`metrics.json`).
Out of scope:
- Advanced statistics (VaR/ES) unless explicitly needed (UNSPECIFIED).
- Benchmarking against indices (UNSPECIFIED).

## Non-negotiable rules
- Metrics must be reproducible from recorded inputs (fills + price marks + config).
- Fees must be included.
- Time must be UTC epoch ms.
- Metrics computation must be unit-tested.

## Required metric artefacts

### Per-run output file (required)
`metrics.json` (exact keys required; additional keys allowed)
- run_id: string
- strategy_id: string
- started_at_ms: int
- ended_at_ms: int
- base_currency: string
- trades_count: int
- gross_pnl_base: number (UNSPECIFIED calculation detail until realised/unrealised policy fixed)
- net_pnl_base: number
- total_fees_base: number
- max_drawdown_pct: number
- return_pct: number
- equity_curve_points: int
- notes: string (optional)

Policy decisions (must be explicitly recorded; can be UNSPECIFIED initially)
- realised vs unrealised PnL policy: UNSPECIFIED
- mark-to-market source (ticker vs candle close): UNSPECIFIED
- slippage model: UNSPECIFIED

## Metric definitions (minimum set)

Performance
- net_pnl_base: realised + unrealised (policy must be stated)
- return_pct: (ending_equity - starting_equity) / starting_equity

Risk
- max_drawdown_pct: max peak-to-trough drawdown on equity curve

Execution cost
- total_fees_base: sum of fees converted to base currency (conversion policy UNSPECIFIED)
- slippage_base: UNSPECIFIED until slippage model exists

Operational
- rejected_orders_count
- execution_errors_count
- data_stale_events_count

## Data inputs required for metrics
Minimum:
- Starting equity snapshot
- Per-fill records (price, qty, fee, timestamp)
- Equity marks over time (equity curve) using a defined mark-to-market price source

## Implementation guidance (folder conventions — optional)
Suggested (not mandatory):
- backend/app/analytics/metrics.py
- backend/tests/test_metrics.py

## Required templates/snippets

### Pytest: drawdown calculation unit test (runnable)
```python
def max_drawdown_pct(equity_curve):
    # equity_curve: list[float]
    peak = float("-inf")
    max_dd = 0.0
    for x in equity_curve:
        peak = max(peak, x)
        dd = (peak - x) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    return max_dd * 100.0

def test_max_drawdown_pct_basic():
    curve = [100.0, 120.0, 90.0, 110.0]
    # peak 120 -> trough 90 => 25% drawdown
    assert round(max_drawdown_pct(curve), 6) == 25.0
```

### Pytest: metrics schema shape (example)
```python
def test_metrics_json_has_required_keys():
    metrics = {
        "run_id": "r1",
        "strategy_id": "s1",
        "started_at_ms": 0,
        "ended_at_ms": 1,
        "base_currency": "USDT",
        "trades_count": 1,
        "gross_pnl_base": 0.0,
        "net_pnl_base": -0.1,
        "total_fees_base": 0.1,
        "max_drawdown_pct": 0.0,
        "return_pct": -0.01,
        "equity_curve_points": 2,
    }
    required = set(metrics.keys())
    assert required.issuperset({
        "run_id","strategy_id","started_at_ms","ended_at_ms","base_currency",
        "trades_count","gross_pnl_base","net_pnl_base","total_fees_base",
        "max_drawdown_pct","return_pct","equity_curve_points"
    })
```

### Vitest: UI readiness (metrics rendering stub)
```ts
import { test, expect } from "vitest";

test("metrics payload has required keys", () => {
  const metrics = {
    run_id: "r1",
    strategy_id: "s1",
    trades_count: 1,
    net_pnl_base: -0.1,
    max_drawdown_pct: 0,
    return_pct: -0.01,
  };
  expect(metrics).toHaveProperty("run_id");
  expect(metrics).toHaveProperty("strategy_id");
});
```

## Run commands (recommended)
Backend:
- cd backend
- pytest

## Reviewer checks (must pass)
- [ ] `metrics.json` schema is produced per run (even if some policies remain UNSPECIFIED).
- [ ] Drawdown and return calculations are unit-tested.
- [ ] Metrics include fees (and slippage once implemented).
- [ ] Any UNSPECIFIED policy is explicitly recorded (not silently assumed).
```

```docs/RUNBOOK.md
# RUNBOOK — Operating the Paper-Trading Platform

Date: 2026-04-04 (Africa/Lusaka)  
Deployment model: UNSPECIFIED  
Auth model: UNSPECIFIED  
Kill switch implementation: partial until built (UNSPECIFIED phase)

## Purpose
Provide step-by-step operational procedures for:
- starting/stopping services,
- safe configuration verification (paper-only),
- incident response and recovery,
- and post-incident review.

## Scope
In scope:
- Local development operations (definite).
- Production operations patterns (generic; deployment is UNSPECIFIED).
Out of scope:
- Live trading operations (forbidden).
- Exchange key permission automation (UNSPECIFIED).

## Non-negotiable safety checks (must be done before every run)
- PAPER_TRADING_ONLY must be true.
- LIVE_TRADING_ENABLED must be false.
- No withdrawals/transfers exist in code or configuration.

## Preflight checklist (copy/paste)
Config
- [ ] backend/.env set (not committed) and matches backend/.env.example fields
- [ ] PAPER_TRADING_ONLY=true
- [ ] LIVE_TRADING_ENABLED=false
- [ ] NEXT_PUBLIC_API_BASE_URL points at backend

Testing
- [ ] backend: `pytest` passes
- [ ] frontend: `npm test` passes
- [ ] tests run offline (no exchange network calls)

Keys
- [ ] Exchange keys are read/trade only (manual verification; process UNSPECIFIED)

## Standard operations

### Local start (backend)
Commands:
- cd backend
- python -m venv .venv && source .venv/bin/activate
- pip install -r requirements.txt
- pytest
- uvicorn app.main:app --reload --port 8000

Expected result:
- GET /health returns {"status":"ok"}
- GET /version shows paper_trading_only=true and live_trading_enabled=false

### Local start (frontend)
Commands:
- cd frontend
- npm install
- npm test
- npm run dev

Expected result:
- /status renders “healthy” when backend is up

### Paper trading run (strategy runner)
Strategy runner and scheduling mechanism: UNSPECIFIED.
Minimum requirement:
- Strategy runner must call the paper execution boundary (in-process ExecutionService or POST /paper/orders/market).
- Strategy runner must support stop/resume without duplicating orders (idempotency: UNSPECIFIED implementation detail).

## Incident response (paper-only)

### Emergency stop (immediate)
If any unsafe condition is detected (wrong env flags, unexpected order flow, repeated errors):
1) Stop strategy runner process (method depends on runner; UNSPECIFIED).
2) Stop backend if it is misconfigured.
3) Rotate API keys if leakage suspected (manual steps below).
4) Record incident timeline and logs.

### Data feed failure (stale or missing prices)
Symptoms:
- repeated “data_stale” events
Actions:
- pause strategy execution
- verify ExchangeClient is still returning current timestamps
- resume only after staleness clears

### Repeated execution failures (simulator rejections)
Symptoms:
- many “order_rejected” events
Actions:
- pause strategy
- inspect ledger balances/positions and risk checks
- ensure parameter sanity (amounts, price inputs)

## Key rotation (manual; UNSPECIFIED provider tooling)
1) Create new exchange API key with least privilege (read/trade only).
2) Update backend runtime environment (not committed files).
3) Restart backend.
4) Validate /health and /version.
5) Confirm no secrets appear in logs.

## Post-incident review template
- Summary:
- Impact:
- Root cause:
- Detection:
- Resolution:
- Preventative actions:
- Tests added:
- Runbook updates:

## Required templates/snippets

### Pytest: verify safety flags default to safe values
```python
from app.core.settings import Settings

def test_defaults_are_safe():
    s = Settings()
    assert s.paper_trading_only is True
    assert s.live_trading_enabled is False
```

## Reviewer checks (must pass)
- [ ] Any operational behaviour change includes a runbook update.
- [ ] Unsafe configurations are explicitly blocked (tested).
- [ ] No secrets are added to logs or repo.
- [ ] Stop procedure is documented for new long-running components.
```

```docs/OBSERVABILITY.md
# OBSERVABILITY — Logs, Metrics, Alerts (Paper-First)

Date: 2026-04-04 (Africa/Lusaka)  
Observability stack (metrics/tracing/log shipping): UNSPECIFIED  
Log destination (stdout/file/collector): UNSPECIFIED

## Purpose
Ensure failures are visible, diagnosable, and reviewable:
- trading events are auditable (paper orders/fills),
- safety gates and risk limits are observable,
- external dependency issues (exchange/data) are detectable.

## Scope
In scope:
- Structured logging requirements (must implement now).
- Metric names and alert conditions (design now; implementation may be phased).
Out of scope:
- Full tracing/telemetry implementation details (UNSPECIFIED tool choice).

## Non-negotiable rules
- No secrets in logs (ever): no API keys, secrets, passphrases, full auth headers.
- Use structured logs (JSON objects), not free-text.
- Every order attempt and outcome produces an event log entry.
- Every risk halt and kill switch action produces an event log entry.
- Correlation IDs required across request → service → simulator.

## Event taxonomy (minimum)
Each event is a structured log object with required fields.

Required common fields:
- ts_ms (int, UTC epoch ms)
- level ("DEBUG"|"INFO"|"WARNING"|"ERROR")
- event (string)
- component (string, e.g., "api", "service", "simulator")
- request_id (string; generate if missing)
- strategy_id (string or null)
- run_id (string or null)

Trading events (paper)
- order_submitted
- order_rejected
- order_filled
- ledger_updated

Risk/safety events
- safety_gate_failure
- risk_limit_triggered
- kill_switch_triggered (future: UNSPECIFIED timeline)

Data/exchange events
- market_data_received
- market_data_stale
- exchange_error

## Log schema examples (must match structure)
Example: order_filled
```json
{
  "ts_ms": 1710000000000,
  "level": "INFO",
  "event": "order_filled",
  "component": "paper_simulator",
  "request_id": "req_123",
  "strategy_id": "dca_btc",
  "run_id": "run_456",
  "order_id": "ord_1",
  "symbol": "BTC/USDT",
  "side": "buy",
  "amount": 100.0,
  "price": 50000.0,
  "qty_filled": 0.002,
  "fee": 0.10,
  "fee_currency": "USDT"
}
```

Example: safety_gate_failure
```json
{
  "ts_ms": 1710000000000,
  "level": "ERROR",
  "event": "safety_gate_failure",
  "component": "config",
  "request_id": "req_999",
  "strategy_id": null,
  "run_id": null,
  "reason": "PAPER_TRADING_ONLY is false"
}
```

## Metrics (design now; implementation phased)
All names and labels must be stable once published.

Counters
- paper_orders_submitted_total{strategy_id,symbol,side}
- paper_orders_filled_total{strategy_id,symbol,side}
- paper_orders_rejected_total{strategy_id,symbol,side,reason}
- risk_events_total{type}
- exchange_errors_total{exchange_name,type}

Gauges
- portfolio_equity_base{run_id}
- open_positions_count{run_id}
- market_data_age_ms{symbol}

Histograms
- api_request_latency_ms{route,method,status}
- execution_latency_ms{strategy_id}

## Alert conditions (paper-only)
Alert channel/provider: UNSPECIFIED.

Required alert rules (minimum)
- safety_gate_failure event occurs (page)
- exchange_errors_total spikes above UNSPECIFIED threshold in UNSPECIFIED time window
- market_data_age_ms > UNSPECIFIED threshold for UNSPECIFIED duration
- paper_orders_rejected_total spikes above UNSPECIFIED threshold

## Required templates/snippets

### Pytest: ensure secrets are not logged
```python
import logging

def test_logs_do_not_include_api_key(caplog):
    caplog.set_level(logging.INFO)
    logger = logging.getLogger("app")
    fake_key = "SHOULD_NOT_APPEAR"
    logger.info("exchange_connect", extra={"api_key": fake_key})
    # Enforce: never place secrets into log extras (this test will fail until redaction/logging is correct)
    assert fake_key not in caplog.text
```

### Vitest: UI must not log secrets
```ts
import { test, expect, vi } from "vitest";

test("frontend does not console.log secrets", () => {
  const spy = vi.spyOn(console, "log").mockImplementation(() => {});
  // application code should never log secrets; this is a pattern test placeholder.
  expect(spy).toBeDefined();
  spy.mockRestore();
});
```

## Reviewer checks (must pass)
- [ ] All order lifecycle events are logged with required fields.
- [ ] Safety gate failures are logged as ERROR with reason.
- [ ] No secrets appear in logs (add tests when new logging paths introduced).
- [ ] Metrics names/labels are stable and documented here before implementation.
```

```docs/DATA.md
# DATA — Market Data Contracts, Quality Rules, and Storage Boundaries

Date: 2026-04-04 (Africa/Lusaka)  
Primary exchange(s): UNSPECIFIED  
Historical data provider: UNSPECIFIED  
Data storage backing: UNSPECIFIED (in-memory acceptable for MVP)

## Purpose
Define data contracts and quality rules so that:
- strategies rely on consistent inputs,
- simulations are deterministic,
- and both testing and operations can detect bad/stale data.

## Scope
In scope:
- Market data types used by the platform (ticker now; candles/trades later).
- Validation rules (staleness, monotonic timestamps, non-negative prices).
- Storage boundaries and proposed interfaces.
Out of scope:
- Exchange-specific symbol idiosyncrasies beyond normalisation policy (UNSPECIFIED).

## Non-negotiable rules
- All timestamps are UTC epoch ms.
- All symbols use canonical format "BASE/QUOTE" (e.g., "BTC/USDT") unless explicitly documented.
- Strategies must not call CCXT; they consume data via PriceFeed/ExchangeService boundaries.
- Data used for simulation must be recordable and replayable (mechanism may be UNSPECIFIED initially).

## Data contracts (minimum)

### Ticker (MVP)
Fields (required):
- symbol: string ("BTC/USDT")
- last: number (> 0)
- timestamp_ms: int (UTC epoch ms)

Optional:
- bid, ask, volume: UNSPECIFIED

### Candle (later; UNSPECIFIED timeline)
- symbol: string
- timeframe: string (e.g., "1m", "5m") — UNSPECIFIED list
- open, high, low, close: numbers
- volume: number
- start_ts_ms: int
- end_ts_ms: int

### Trade (later)
- symbol
- price
- qty
- timestamp_ms
- side: "buy"|"sell" (if available)

## Validation rules (must be enforced at boundaries)

General
- symbol must match canonical formatting
- prices must be > 0
- timestamps must be plausible (not 0, not far future; tolerance UNSPECIFIED)

Staleness
- For live-ish paper runs, ticker timestamp must be no older than `MAX_DATA_AGE_MS` (default UNSPECIFIED; must be configured and tested)
- If stale: emit `market_data_stale` event and block new strategy orders

Monotonicity (per symbol stream)
- ticker timestamps should not go backwards
- candles must not overlap and must be ordered

Outliers (later)
- Outlier detection policy: UNSPECIFIED (but must be documented if introduced)

## Storage and interfaces (recommended)
These are suggested boundaries; implementation may be phased.

PriceFeed (read path)
- get_last(symbol) -> Ticker
- get_last_many(symbols) -> dict[symbol, Ticker]

MarketDataStore (write path; in-memory for MVP)
- put_ticker(ticker)
- get_ticker(symbol) -> Ticker | None
- get_series(symbol, start_ms, end_ms) -> list (later; UNSPECIFIED)

## Required templates/snippets

### Pytest: ticker validation unit test (runnable)
```python
def validate_ticker(ticker):
    assert isinstance(ticker["symbol"], str) and "/" in ticker["symbol"]
    assert ticker["last"] > 0
    assert ticker["timestamp_ms"] > 0

def test_validate_ticker_ok():
    validate_ticker({"symbol": "BTC/USDT", "last": 1.0, "timestamp_ms": 1})

def test_validate_ticker_rejects_non_positive_price():
    try:
        validate_ticker({"symbol": "BTC/USDT", "last": 0.0, "timestamp_ms": 1})
        assert False, "expected failure"
    except AssertionError:
        pass
```

### Pytest: staleness gate example
```python
def is_stale(now_ms, ts_ms, max_age_ms):
    return (now_ms - ts_ms) > max_age_ms

def test_staleness_gate():
    assert is_stale(now_ms=2000, ts_ms=0, max_age_ms=1000) is True
    assert is_stale(now_ms=2000, ts_ms=1501, max_age_ms=1000) is False
```

### Vitest: UI should display “data stale” banner (stub example)
```ts
import { test, expect } from "vitest";

test("data stale flag triggers banner (placeholder)", () => {
  const viewModel = { dataStale: true };
  expect(viewModel.dataStale).toBe(true);
});
```

## Run commands (recommended)
Backend:
- cd backend
- pytest

## Reviewer checks (must pass)
- [ ] Data contract fields are explicit and validated at boundaries.
- [ ] Staleness detection exists (or is declared UNSPECIFIED with a roadmap).
- [ ] Strategies consume data only via service/feed interfaces, not CCXT.
- [ ] Any new data type (candles/trades/order book) includes validation + tests.
```