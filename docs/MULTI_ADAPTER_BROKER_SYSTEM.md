# MULTI_ADAPTER_BROKER_SYSTEM.md

## Purpose

This document defines how the trading platform should support **multiple broker/platform adapters** and allow users to switch between them safely through configuration.

The goal is to make the system **broker-agnostic**, so that:
- one bot can run on paper mode,
- another bot can run on OANDA,
- another bot can run on Deriv,
- and the system can switch adapters per bot without changing strategy code.

This design preserves the existing safety-first, config-driven, paper-trading-first architecture.

---

## Core principle

Do **not** switch the whole system globally between brokers.

Instead:

> bind each bot instance to a specific adapter via config

This means the system can support:
- one adapter per bot
- multiple adapters loaded in the same deployment
- per-user or per-bot broker selection
- clean separation between strategy logic and broker-specific execution logic

---

## Design goals

The multi-adapter system must:

- support multiple broker/platform integrations at the same time
- allow per-bot adapter selection through config
- isolate strategies from broker-specific APIs
- normalize symbols, balances, positions, and execution requests
- support safe restart/rebinding when adapter config changes
- preserve auditability and reproducibility
- support both paper and broker-backed modes
- keep live trading disabled unless future live gates are explicitly satisfied

---

## Non-negotiable rules

- Strategies must never call broker APIs directly.
- All execution must flow through the execution service and broker adapter interface.
- Adapter choice must come from validated config only.
- Switching adapters must require config validation + apply + audit.
- Symbol mapping must be explicit and deterministic.
- If adapter state is uncertain, do nothing and emit an alert.
- Paper adapter must remain supported at all times.
- No broker adapter may bypass risk checks.
- No secrets may be logged, rendered, or stored in plaintext.

---

## High-level architecture

```text
Strategy
  -> OrderIntent
    -> Risk Engine
      -> Execution Service
        -> Broker Adapter Factory
          -> Concrete Broker Adapter
            -> Broker API / Platform
```

The strategy produces **OrderIntent** objects only.

The execution service selects the correct adapter based on bot configuration.

The adapter translates the generic internal intent into broker-specific actions.

---

## Required broker adapter interface

All broker/platform adapters must implement a unified contract.

```python
class BrokerAdapter(Protocol):
    async def connect(self) -> None: ...
    async def close(self) -> None: ...

    async def get_ticker(self, symbol: str): ...
    async def get_balance(self): ...
    async def get_positions(self): ...
    async def get_open_orders(self): ...

    async def place_order(self, intent): ...
    async def cancel_order(self, broker_order_id: str): ...
    async def health_check(self): ...
```

### Notes

- `place_order(intent)` is the core adapter boundary.
- Adapters may internally translate the intent into:
  - market/limit orders
  - contract proposals
  - position modifications
  - broker-specific API workflows
- The rest of the system must not care how the adapter talks to the broker.

---

## Required adapter registry

Maintain a central registry of supported adapters.

```python
ADAPTER_REGISTRY = {
    "paper": PaperAdapter,
    "oanda": OandaAdapter,
    "deriv": DerivAdapter,
    "mt5": MT5Adapter,
    "ctrader": CTraderAdapter,
}
```

### Rules

- Registry keys are canonical adapter IDs.
- Config must reference adapter IDs from this registry.
- Unknown adapter type must fail validation.
- Registry must be testable and import-safe.

---

## Required adapter factory

The factory creates the adapter for a specific bot from validated config.

```python
def create_adapter(config: BrokerConfig) -> BrokerAdapter:
    adapter_cls = ADAPTER_REGISTRY[config.type]
    return adapter_cls(config)
```

### Factory requirements

- Must only construct adapters from validated config.
- Must fail closed on unknown type or incomplete config.
- Must return a broker adapter implementing the standard interface.
- Must not create network side effects during validation-only operations.

---

## Required config model

Each bot must declare its adapter in config.

### Example

```json
{
  "bot_id": "bot_fx_001",
  "broker": {
    "type": "deriv",
    "environment": "demo",
    "account_id": "demo-account-001",
    "credential_ref": "secret://deriv/demo-account-001",
    "symbol_namespace": "deriv"
  }
}
```

### Broker config fields

Required fields:
- `type`
- `environment`
- `account_id`
- `credential_ref`

Optional fields:
- `symbol_namespace`
- `app_id`
- `session_policy`
- `reconnect_policy`
- `rate_limit_profile`

### Validation rules

- `type` must exist in the adapter registry.
- `environment` must be allowed for that adapter.
- `credential_ref` must exist and be resolvable at runtime.
- Broker config cannot be applied unless full validation passes.
- Config diffs affecting broker selection must trigger bot restart/rebind.

---

## Per-bot adapter binding

Adapter choice must be **per bot**, not global.

### Correct model

| Bot ID | Adapter |
|--------|---------|
| bot_001 | paper |
| bot_002 | oanda |
| bot_003 | deriv |
| bot_004 | mt5 |

### Why this is required

- allows multiple brokers in one deployment
- avoids global state conflicts
- supports user choice safely
- isolates failures to a single bot
- enables side-by-side testing of paper vs broker-backed modes

### Forbidden design

Do not implement a single global “current broker” switch.

---

## Execution routing model

The execution service must route requests to the correct adapter for that bot.

```python
class ExecutionService:
    def __init__(self, adapter: BrokerAdapter):
        self.adapter = adapter

    async def execute(self, intent):
        return await self.adapter.place_order(intent)
```

### Required routing rules

- Resolve adapter from current applied bot config.
- Run risk checks before routing.
- Ensure adapter and bot config versions are recorded on every execution attempt.
- If adapter is unhealthy, reject new orders and emit incident/alert.
- If config changes, adapter instance must be recreated from new config.

---

## Normalized internal models

The internal system must remain broker-agnostic.

### Internal canonical symbol format

Use one canonical internal symbol format, for example:

```text
EUR/USD
GBP/USD
USD/JPY
BTC/USD
```

Adapters must translate between canonical internal symbols and broker-native symbols.

### Example symbol mappings

```text
Canonical: EUR/USD

OANDA:  EUR_USD
MT5:    EURUSD
Deriv:  frxEURUSD
cTrader: EURUSD
```

### Symbol mapping requirements

- mapping must be explicit and versioned
- mapping must be test-covered
- unsupported symbol mapping must fail validation
- strategies must use canonical symbols only

---

## Order intent normalization

The strategy and risk layers must operate on a generic intent model.

### Example internal intent

```python
class OrderIntent:
    bot_id: str
    strategy_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float | None
    notional: float | None
    limit_price: float | None
    time_in_force: str | None
```

### Why this matters

Different brokers/platforms interpret execution differently:

- OANDA / MT5 / cTrader:
  - mostly order-oriented
- Deriv:
  - more contract/proposal-oriented

The adapter is responsible for translating internal intent into the broker-specific workflow.

---

## Adapter-specific translation layer

Each adapter must implement a translation boundary.

### Example

```text
OrderIntent
  -> PaperAdapter -> simulated fill
  -> OandaAdapter -> broker order payload
  -> MT5Adapter -> EA/bridge command
  -> DerivAdapter -> proposal + buy contract flow
```

### Rules

- Translation must be deterministic.
- Any unsupported internal intent must be rejected clearly.
- Adapter must return normalized execution result objects.

---

## Normalized adapter result model

Adapters must return a normalized result object, regardless of broker specifics.

### Example

```python
class ExecutionResult:
    status: str
    broker_order_id: str | None
    client_order_id: str
    filled_qty: float | None
    avg_price: float | None
    fees: float | None
    raw_reference: str | None
    reason: str | None
```

### Rules

- Adapter-specific payloads may be attached separately under `extra`.
- The rest of the system consumes only normalized results.
- Raw broker payloads must not leak across service boundaries.

---

## Required adapters

### 1. PaperAdapter

Purpose:
- default simulator
- testing
- research
- qualification

Requirements:
- always supported
- deterministic
- zero external network dependency in tests
- used as fallback safe mode where appropriate

### 2. OandaAdapter

Purpose:
- forex-focused broker adapter
- traditional order-oriented REST integration

Requirements:
- symbol translation
- account session handling
- order submission
- balance and position reads
- health checks
- safe error translation

### 3. MT5Adapter

Purpose:
- integration through a bridge/service for MT5-backed execution

Requirements:
- symbol translation
- command bridge interface
- account and position sync
- health checks
- restart/reconnect policy

### 4. DerivAdapter

Purpose:
- support Deriv broker flows

Requirements:
- account auth/session flow
- WebSocket lifecycle
- proposal/contract translation
- result normalization
- reconnect policy
- safe error translation

### 5. CTraderAdapter

Purpose:
- support cTrader Open API / cBot integration

Requirements:
- symbol mapping
- order lifecycle integration
- position sync
- health checks
- result normalization

---

## Auth and session handling

Each adapter owns its own auth/session lifecycle.

### Required responsibilities per adapter

- connect using adapter-specific credentials
- renew/reconnect sessions safely
- detect stale or broken sessions
- close sessions on shutdown/rebind
- emit adapter health status

### Rules

- Secrets must come from secret references, never inline config
- Auth/session logic must stay inside adapter boundary
- Session failures must fail closed
- Reconnects must not duplicate orders

---

## Health and failover behavior

Each adapter must expose health state.

### Required health states

- `healthy`
- `degraded`
- `disconnected`
- `error`

### Required behavior

- `healthy`: adapter can serve reads and execution
- `degraded`: allow reads if safe, reject risky execution
- `disconnected`: reject all new execution
- `error`: reject execution, emit incident, require recovery path

### If adapter state is uncertain

- do not place order
- preserve intent/audit trail
- emit alert
- mark bot paused if needed

---

## Switching adapters

Users must be able to switch adapters safely through config.

### Switching flow

1. user edits bot broker config draft
2. system validates adapter type and broker config
3. system validates symbol namespace/mappings
4. system validates required credentials exist
5. user applies config
6. bot stops current adapter session
7. system instantiates new adapter via factory
8. bot restarts with new adapter
9. audit record is written

### Rules

- switching adapters must require apply + audit
- switching must not mutate historical run state
- switching must not happen silently
- switching must restart/rebind the bot cleanly

---

## UI requirements for adapter switching

The UI must support safe adapter selection.

### Required UI features

- broker adapter dropdown
- environment selection
- broker-specific config fields
- validation preview
- symbol compatibility warnings
- “current adapter” badge
- audit diff showing adapter changes
- typed confirmation for broker changes if the bot is active

### Required UI behavior

- invalid adapter selection cannot be saved
- broker-specific fields appear only for selected adapter type
- secret values are never displayed
- apply action must trigger audit logging

---

## Persistence requirements

Store adapter-related data in versioned config and bot runtime state.

### Required persisted data

- adapter type
- environment
- account reference
- symbol namespace
- config version
- runtime adapter health state
- last successful connect time
- last adapter error summary
- audit records for broker changes

---

## Testing requirements

### Unit tests

- adapter registry lookup
- adapter factory creation
- symbol mapping
- broker config validation
- translation from internal intent to adapter request
- translation from broker response to normalized result

### Integration tests

- bot binds to correct adapter from config
- switching adapter creates a new adapter instance
- stale/unhealthy adapter blocks execution
- same strategy works unchanged across paper + one real adapter
- broker change produces audit record

### End-to-end local tests

- create bot with paper adapter
- run strategy
- switch to mock OANDA/Deriv adapter
- validate restart/rebind
- confirm bot continues through same internal execution path

---

## Suggested repo structure

```text
backend/
  app/
    adapters/
      brokers/
        base.py
        registry.py
        factory.py
        paper_adapter.py
        oanda_adapter.py
        mt5_adapter.py
        deriv_adapter.py
        ctrader_adapter.py
      symbols/
        mapping.py
        registry.py
    execution/
      services/
        execution_service.py
    configs/
      broker_config.py
    tests/
      unit/
      integration/
```

---

## Required implementation phases

### Phase 1
Implement:
- BrokerAdapter interface
- adapter registry
- adapter factory
- broker config schema
- paper adapter integration

### Phase 2
Implement:
- symbol mapping layer
- execution routing by bot config
- adapter health model
- tests for multi-adapter binding

### Phase 3
Implement first real broker adapter:
- recommended first: OANDA
- then Deriv
- then MT5 / cTrader

### Phase 4
Implement:
- UI for adapter selection
- broker change validation
- restart/rebind flow
- audit trail visibility

---

## Recommended first real adapter

Start with **OANDA** first.

Reason:
- closer to standard forex order models
- easier fit with current internal OMS assumptions
- simpler path before Deriv

Then implement **Deriv** second, because it requires broker-specific contract/proposal translation.

---

## Important design insight

If you implement this correctly, you are no longer building just a single trading bot.

You are building:

> a broker-agnostic trading platform with pluggable execution adapters

That is the right long-term architecture.

---

## Immediate first slice to implement

Task:
Implement the broker adapter foundation.

Deliverables:
- BrokerAdapter interface
- adapter registry
- adapter factory
- broker config schema
- paper adapter wired through the new interface
- tests for adapter creation and per-bot adapter binding

Stop after this slice.
