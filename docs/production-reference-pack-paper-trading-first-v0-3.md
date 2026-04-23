# ALGORITHMS — Trading System Primitives (Paper-First, Enforceable)

Date: 2026-04-04 (Africa/Lusaka)  
Status: Paper trading only (live trading forbidden)  
Defaults (risk limits, slippage, fee model, exchanges, CI/CD): **UNSPECIFIED**

## Purpose

Define the **minimum set of algorithms** required for a safe, testable trading system: execution mechanics, sizing and risk enforcement, canonical baseline strategies, and research/evaluation procedures. This exists to prevent “strategy-first” development without reliable execution, controls, and validation.

## Scope

In:
- Execution algorithms (market/limit), partial fills, retries and safe failure.
- Position sizing algorithms (fixed % and volatility-adjusted).
- Risk enforcement gates (drawdown, daily loss, max positions, kill switch).
- Canonical simple strategies (paper-only) with asserted ledger effects.
- Research/evaluation algorithms (metrics, walk-forward, sensitivity checks).

Out:
- Live trading design/implementation (forbidden).
- Exchange-specific microstructure modelling (UNSPECIFIED).
- ML/AI signal generation (optional later, UNSPECIFIED).

## Non-negotiable rules

- **Paper only**: all “place order” operations must route to the paper simulator/execution boundary.
- **Single execution boundary**: strategies must call `ExecutionService.place_market_order(...)` (or paper API); never CCXT directly.
- **No network in tests**: exchange calls must be mocked/faked.
- **Deterministic simulation**: same inputs → same fills and ledger outcomes.
- **Risk gates before orders**: every order must pass risk checks; on violation → no order.
- **Safe failure**: if data is stale/invalid or dependencies fail → do nothing, emit an event.

## Execution algorithms

### Market order (paper simulator)
Algorithm:
- Validate inputs (side, symbol, amount, price > 0).
- Apply fee model (`fee_bps`: UNSPECIFIED default).
- Apply slippage model (MVP may be 0; must be stated as **UNSPECIFIED** if absent).
- Fill immediately at effective price.
- Update ledger balances/positions deterministically.

Expected ledger effects:
- **Buy (quote amount)**: quote balance decreases; base position increases.
- **Sell (base qty)**: base position decreases; quote balance increases.
- Fees reduce equity (fee currency policy: **UNSPECIFIED**).

### Limit order (later; simulator support required)
Algorithm (high level):
- Create resting order at limit price.
- Fill when market crosses limit (or per matching model: **UNSPECIFIED**).
- Support partial fills if configured (see below).

### Partial fills (required for realism; later phase)
Algorithm:
- Fill `min(remaining_qty, available_liquidity)` at each tick/candle.
- Continue until complete or expired (time-in-force: **UNSPECIFIED**).
- Ledger updates per fill; do not “teleport” full fills.

### Retries and idempotency (runtime)
- Retry only on transient failures (timeouts/rate limits); policy **UNSPECIFIED**.
- All order submissions must be idempotent using `client_order_id` (format **UNSPECIFIED**).
- If uncertain about state → **do nothing** and raise an alert/event.

## Position sizing algorithms

### Fixed % of equity (baseline)
- notional = equity_base * risk_fraction  
- clamp to max_notional_per_trade (UNSPECIFIED)

Pseudocode:
```python
def size_fixed_fraction(equity_base: float, risk_fraction: float, max_notional: float) -> float:
    notional = equity_base * risk_fraction
    return max(0.0, min(notional, max_notional))
```

### Volatility-adjusted sizing (baseline)
- Estimate volatility σ (window and estimator UNSPECIFIED).
- notional ∝ 1/σ, clamped to max_notional_per_trade.

Pseudocode:
```python
def size_vol_adj(equity_base, risk_budget, sigma, max_notional):
    if sigma <= 0: return 0.0
    notional = risk_budget / sigma
    return max(0.0, min(notional, max_notional))
```

## Risk enforcement algorithms

All risk checks must run **before** calling execution.

- Max drawdown halt:
  - if drawdown_pct(equity_curve) > MAX_DD_PCT (UNSPECIFIED) → halt orders.
- Daily loss limit:
  - if (today_pnl < -DAILY_LOSS_LIMIT) (UNSPECIFIED) → halt orders.
- Max open positions:
  - if open_positions_count >= MAX_OPEN_POSITIONS (UNSPECIFIED) → reject new positions.
- Kill switch:
  - if kill_switch_enabled → reject all new orders immediately (cancel logic later: UNSPECIFIED).

Pseudocode (risk gate):
```python
def risk_gate(ctx) -> None:
    if ctx.kill_switch: raise RuntimeError("kill_switch")
    if ctx.drawdown_pct > ctx.max_dd_pct: raise RuntimeError("max_drawdown")
    if ctx.daily_pnl < -ctx.daily_loss_limit: raise RuntimeError("daily_loss")
    if ctx.open_positions >= ctx.max_open_positions: raise RuntimeError("max_positions")
```

## Canonical simple strategies (paper-only baselines)

All strategies must:
- consume prices via a feed/service (not CCXT),
- call the execution boundary once per step (or NOOP),
- have deterministic state (timers/counters).

### DCA
Goal: accumulate base asset by buying fixed quote amounts periodically.  
Ledger effect: quote decreases; base increases.

Pseudocode:
```text
if now >= next_due and spent + step_amount <= max_spend:
  risk_gate()
  buy(step_amount)
  next_due = now + interval
```

### Grid (simplified)
Goal: buy lower / sell higher around a reference price.  
Ledger effect: buys add base; sells reduce base and add quote.

### TWAP
Goal: split a target amount into equal slices over time.  
Ledger effect: repeated small fills; smooth inventory change.

### Trend-following (baseline)
Goal: follow direction (e.g., MA crossover).  
Ledger effect: position increases when trend up; decreases/exits when trend down.

### Mean reversion (baseline)
Goal: bet on reversion to mean after deviations.  
Ledger effect: buy after negative deviation; sell after positive deviation.

## Research/evaluation algorithms

- Metrics computation (see METRICS.md): net/gross PnL, fees, return_pct, max_drawdown_pct.
- Walk-forward testing (required): train/validate/forward split (split policy thresholds UNSPECIFIED).
- Sensitivity checks (required): perturb parameters ± small delta; results should not collapse.

## Required templates/snippets

### Cursor response format (required for implementation work)
Task:  
Assumptions (mark UNSPECIFIED if needed):  
Plan:  
Files to create/change (exact paths):  
Tests first (list + key assertions):  
Implementation (each file as a path-labelled fenced code block):  
Run commands:  
Next step (1–3 items):  

### Pytest: enforce execution boundary + risk block (runnable pattern)
```python
import pytest

class FakeExecution:
    def __init__(self): self.calls = []
    def place_market_order(self, side, symbol, amount, price):
        self.calls.append((side, symbol, amount, price))
        return {"status": "filled"}

class ExampleStrategy:
    def step(self, *, price_last, execution, allow_trade: bool):
        if not allow_trade: return
        execution.place_market_order("buy", "BTC/USDT", 10.0, price_last)

def test_strategy_calls_execution_boundary_only():
    exe = FakeExecution()
    ExampleStrategy().step(price_last=50_000.0, execution=exe, allow_trade=True)
    assert exe.calls == [("buy", "BTC/USDT", 10.0, 50_000.0)]

def test_risk_blocks_order():
    exe = FakeExecution()
    ExampleStrategy().step(price_last=50_000.0, execution=exe, allow_trade=False)
    assert exe.calls == []
```

## Reviewer checks (exact, actionable)

- [ ] Strategies never import/call CCXT; only call the execution boundary.
- [ ] Every order path is preceded by risk_gate checks; violations cause NOOP and a recorded reason.
- [ ] Simulator applies fees deterministically; slippage policy is stated (may be UNSPECIFIED but explicit).
- [ ] Partial fills/limit orders are not implemented unless tests cover them.
- [ ] Sizing functions clamp notional and handle edge cases (sigma ≤ 0).
- [ ] Unit tests exist for: execution boundary call, sizing, and each risk gate.

## Example run commands

- Backend tests: `cd backend && pytest`  
- Frontend tests (if dashboard components exist): `cd frontend && npm test`  
- Strategy runner: `python -m app.tools.run_strategy --manifest <path>` (runner module/path **UNSPECIFIED**)

## Next steps

- Define UNSPECIFIED defaults: fee_bps, slippage model, max drawdown, daily loss, max positions.
- Implement limit order + partial fill simulation only after market-order paths are stable.
- Add walk-forward harness and parameter sensitivity runner (tooling UNSPECIFIED).