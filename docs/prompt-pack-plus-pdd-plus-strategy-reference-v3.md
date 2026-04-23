This /docs pack is designed to make Cursor behave like an **execution contract**: strict slice scoping, deterministic tests, and hard safety gates that prevent accidental live trading, network-coupled tests, or secret leakage. The enforcement hooks map directly to primary tooling features: FastAPI’s official testing guidance uses `TestClient` with pytest, and FastAPI’s documented `app.dependency_overrides` provides a mechanical way to replace real dependencies with fakes in tests (enforcing “mock all exchange calls”). citeturn0search0turn0search1turn0search4 Next.js’ official environment-variable rules (`NEXT_PUBLIC_` for browser-bundled variables) support an enforceable “no secrets in client” policy. citeturn0search2turn0search10 CCXT’s official async examples (`ccxt.async_support`, `fetch_ticker`, `exchange.close`) support a clean “runtime-only adapter” boundary. citeturn0search3 Pytest’s `monkeypatch` fixture (`setenv`/`delenv`) is the canonical way to test safety gates without global side effects, and Vitest’s official mocking APIs (`vi.fn`, `vi.mock`, `vi.spyOn`) support deterministic frontend tests (including mocked globals such as `fetch`). citeturn1search0turn1search1turn1search7

```docs/README.md
# /docs — Trading Bot Prompt Pack + PDD + Strategy Reference (Paper-Trading-First)

Date: 2026-04-04 (Africa/Lusaka)  
Purpose: an enforceable Cursor prompt pack (paper-trading-first) + engineering handoff docs (PDD + strategy reference).

## How to use (recommended)
1) Paste `docs/MASTER_PROMPT.md` into Cursor as the project/system prompt.
2) Copy `docs/CURSOR_RULES.md` into repo-root `.cursorrules`.
3) Implement one slice at a time from `docs/PHASE_PROMPTS.md` (paste ONE phase prompt per session).
4) Review every change using `docs/REVIEWER_CHECKLIST.md` and `docs/RISK_CHECKLIST.md`.
5) Use `docs/PRODUCT_DESIGN.md` as product/engineering scope.
6) Use `docs/STRATEGY_REFERENCE.md` as the canonical guide for strategy design + tests (paper-first).

## What is deliberately UNSPECIFIED
- CI/CD provider and pipeline: UNSPECIFIED
- Deployment platform (cloud/VPS/containers): UNSPECIFIED
- Secrets manager choice: UNSPECIFIED
- Observability stack (APM/log shipping): UNSPECIFIED
- Authentication/authorisation model (single-user vs multi-user): UNSPECIFIED
- Supported exchanges list and sandbox approach: UNSPECIFIED

## Document index
- MASTER_PROMPT.md — enforceable master prompt (≤ ~400 words) + first task
- CURSOR_RULES.md — concise `.cursorrules` content
- PHASE_PROMPTS.md — paste-ready prompts (skeleton → exchange mocks → paper ledger/simulator)
- REVIEWER_CHECKLIST.md — copy/paste PR checklist
- RISK_CHECKLIST.md — one-page risk checklist + mandatory safety gates (pre-live)
- ENV_TEMPLATES.md — backend/.env.example and frontend/.env.example
- TEST_SNIPPETS.md — runnable pytest + vitest snippets used in phases
- ARCHITECTURE.md — architecture + phase timeline (mermaid)
- CHANGELOG_FOR_PROMPT_PACK.md — v0.1 and v0.2 notes
- PRODUCT_DESIGN.md — Product Design Document (PDD) for engineering handoff
- STRATEGY_REFERENCE.md — strategy principles, canonical strategies, simulator behaviours, and tests
```

```docs/MASTER_PROMPT.md
# MASTER PROMPT (paste into Cursor)

Paste the block below as-is. Do not paraphrase it.

## Master prompt (≤ ~400 words)
~~~text
You are a safety-first trading-systems engineer building a crypto trading-bot platform.

HARD RULES (non-negotiable)
- PAPER TRADING ONLY: any “place order” operation must call the paper order simulator; live exchange order APIs are forbidden. Do not generate or enable live trading code, endpoints, configs, or docs.
- No withdrawals/transfers, ever.
- No test may perform real HTTP/WebSocket/network calls. All exchange I/O must be behind a dependency-injected interface; tests must use fakes/mocks.
- TDD: write failing tests first (Red → Green → Refactor). No business logic without a failing test.
- No secrets in code or logs. Use environment variables only. Provide .env.example files, never real values.
- Least privilege by design: assume exchange keys are read/trade only. Do not implement permission escalation.
- Small diffs only. Change the minimum set of files; never refactor unrelated code. No scope creep.

STACK (fixed for now)
Backend: FastAPI (Python 3.11+).
Frontend: Next.js App Router (TypeScript).
Exchange adapter: CCXT async_support (runtime only).
DB/Cache: PostgreSQL + Redis (may be UNSPECIFIED in early slices).

WORKING STYLE
- Ask no questions unless strictly required; if something is unspecified, write “UNSPECIFIED” and proceed with the safest minimal default.
- Prefer thin routes, typed schemas, a service layer, and adapter boundaries.
- Stop after completing the requested slice.

RESPONSE OUTPUT FORMAT (exact headings; no extra sections)
Task:
Assumptions (mark UNSPECIFIED if needed):
Plan:
Files to create/change (exact paths):
Tests first (list + key assertions):
Implementation (each file as a path-labelled fenced code block):
Run commands:
Next step (1–3 items):

FIRST TASK (stop after completion)
Create the paper-trading-only foundation:
- Monorepo: /backend and /frontend
- Backend: FastAPI app with GET /health and GET /version; settings from env; ExchangeService stub injected via dependency provider; no CCXT networking
- Frontend: Next.js app with /status page that fetches backend /health and displays healthy/unhealthy
- Tests:
  - Backend: pytest setup; minimum 2 tests: /health and /version paper-only defaults
  - Frontend: vitest + React Testing Library; minimum 1 test: /status renders “healthy” when fetch is mocked
- Provide backend/.env.example and frontend/.env.example
STOP after this slice.
~~~

## Output-shape example (must match headings)
Task:
Assumptions (mark UNSPECIFIED if needed):
Plan:
Files to create/change (exact paths):
Tests first (list + key assertions):
Implementation (each file as a path-labelled fenced code block):
Run commands:
Next step (1–3 items):
```

```docs/CURSOR_RULES.md
# CURSOR RULES (copy into repo-root .cursorrules)

Copy/paste this entire block into `.cursorrules` at the repository root.

~~~text
PRIORITY: Safety > Testability > Simplicity > Features.

ABSOLUTE PROHIBITIONS
- Live trading is forbidden (no live order APIs, configs, or docs).
- No withdrawals/transfers.
- Never hardcode or log secrets. Use env vars; commit only .env.example.

TEST RULES
- Red→Green→Refactor. Add/modify tests before implementation.
- Tests must not perform network I/O. Mock/fake all exchange calls.
- Prefer FastAPI dependency injection; use app.dependency_overrides in API tests.

SCOPE RULES
- Make small, atomic changes only.
- Do not add features outside the current slice.

FORMAT
- Always respond using the master prompt output headings.
- For files: output path-labelled fenced code blocks containing full file contents.
~~~
```

```docs/PHASE_PROMPTS.md
# PHASE PROMPTS (paste-ready)

Precondition: `docs/MASTER_PROMPT.md` is loaded into Cursor.

Rules for using phases:
- Paste ONE phase prompt at a time.
- Require the assistant to STOP after completing the slice.
- CI/CD provider: UNSPECIFIED.

Each phase includes:
- Goal
- Exact deliverables
- Files to create/change (exact paths)
- Tests to write (with example pytest + vitest snippets)
- Forbidden actions
- Run instructions
- Exact paste-ready phase prompt text

---

## Phase: project-skeleton

### Goal
Bootstrap a minimal monorepo (FastAPI + Next.js) with paper-only defaults and tests.

### Exact deliverables
Backend:
- GET /health -> {"status":"ok"}
- GET /version -> {version, paper_trading_only:true, live_trading_enabled:false}
- Settings from env with safe defaults (paper-only)
Frontend:
- /status page displays healthy/unhealthy based on backend /health

### Files to create/change (exact paths)
- backend/app/__init__.py
- backend/app/main.py
- backend/app/core/__init__.py
- backend/app/core/settings.py
- backend/app/services/__init__.py
- backend/app/services/exchange_service.py
- backend/tests/test_health.py
- backend/tests/test_version.py
- backend/requirements.txt
- backend/pyproject.toml
- backend/.env.example
- frontend/app/status/page.tsx
- frontend/components/StatusClient.tsx
- frontend/components/__tests__/StatusClient.test.tsx
- frontend/package.json
- frontend/vitest.config.ts
- frontend/.env.example

### Tests to write (examples)
Pytest:
~~~python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

def test_version_defaults_paper_only_true():
    r = client.get("/version")
    assert r.status_code == 200
    assert r.json()["paper_trading_only"] is True
    assert r.json()["live_trading_enabled"] is False
~~~

Vitest + RTL:
~~~ts
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import StatusClient from "../StatusClient";

vi.stubGlobal("fetch", vi.fn(async () =>
  new Response(JSON.stringify({ status: "ok" }), { status: 200 })
));

test("renders healthy when API returns ok", async () => {
  render(<StatusClient apiBaseUrl="http://localhost:8000" />);
  expect(await screen.findByText(/healthy/i)).toBeInTheDocument();
});
~~~

### Forbidden actions
- No CCXT imports or networking.
- No DB/Redis/websockets/auth/strategies.
- No live trading functionality.

### Run instructions
Backend:
- cd backend
- python -m venv .venv && source .venv/bin/activate
- pip install -r requirements.txt
- pytest
- uvicorn app.main:app --reload --port 8000

Frontend:
- cd frontend
- npm install
- npm test
- npm run dev

### Paste-ready phase prompt (exact text)
~~~text
GOAL
Create a minimal monorepo skeleton with a paper-trading-only FastAPI backend and a Next.js frontend, plus tests.

EXACT DELIVERABLES
Backend:
- GET /health -> {"status":"ok"}
- GET /version -> {"version": "...", "paper_trading_only": true, "live_trading_enabled": false}
- Settings from env with safe defaults: PAPER_TRADING_ONLY=true; LIVE_TRADING_ENABLED=false
- ExchangeService stub wired via dependency provider (no CCXT)

Frontend:
- /status page fetches GET {NEXT_PUBLIC_API_BASE_URL}/health and renders “healthy” or “unhealthy”

FILES TO CREATE/CHANGE (EXACT PATHS)
- backend/app/__init__.py
- backend/app/main.py
- backend/app/core/__init__.py
- backend/app/core/settings.py
- backend/app/services/__init__.py
- backend/app/services/exchange_service.py
- backend/tests/test_health.py
- backend/tests/test_version.py
- backend/requirements.txt
- backend/pyproject.toml
- backend/.env.example
- frontend/app/status/page.tsx
- frontend/components/StatusClient.tsx
- frontend/components/__tests__/StatusClient.test.tsx
- frontend/package.json
- frontend/vitest.config.ts
- frontend/.env.example

TESTS TO WRITE FIRST
- Backend: /health and /version default paper-only behaviour
- Frontend: StatusClient renders “healthy” when fetch is mocked to return {status:"ok"}

FORBIDDEN ACTIONS
- Do not add CCXT imports or networking.
- Do not add DB/Redis/websockets/auth/strategies.
- Do not add any live trading code or docs.

RUN INSTRUCTIONS
Backend: cd backend → venv → pip install → pytest → uvicorn
Frontend: cd frontend → npm install → npm test → npm run dev

OUTPUT REQUIRED
Respond using the MASTER PROMPT OUTPUT FORMAT headings exactly.
STOP after completing this slice.
~~~

---

## Phase: exchange-service-with-mocks

### Goal
Add an ExchangeClient boundary + ExchangeService; add a market-data endpoint; enforce fakes via dependency overrides in tests.

### Exact deliverables
Backend:
- ExchangeClient interface/protocol: async fetch_ticker(symbol) -> dict
- ExchangeService depends on ExchangeClient (DI)
- CCXTExchangeClient exists but is runtime-only; tests must not use it
- GET /market/ticker?symbol=BTC/USDT returns {symbol,last,timestamp}
Tests:
- Unit test ExchangeService with FakeExchangeClient (async)
- API test overrides dependency to FakeExchangeClient (no network)

### Files to create/change (exact paths)
- backend/app/adapters/__init__.py
- backend/app/adapters/exchange_client.py
- backend/app/adapters/ccxt_exchange_client.py
- backend/app/services/exchange_service.py
- backend/app/api/__init__.py
- backend/app/api/routes/__init__.py
- backend/app/api/routes/market.py
- backend/app/main.py
- backend/tests/test_exchange_service.py
- backend/tests/test_market_api.py

### Tests to write (examples)
Pytest (async unit):
~~~python
import pytest
from app.services.exchange_service import ExchangeService

class FakeExchangeClient:
    async def fetch_ticker(self, symbol: str) -> dict:
        return {"symbol": symbol, "last": 123.45, "timestamp": 111}

@pytest.mark.anyio
async def test_exchange_service_normalises_ticker():
    svc = ExchangeService(exchange_client=FakeExchangeClient())
    out = await svc.get_ticker("BTC/USDT")
    assert out["symbol"] == "BTC/USDT"
    assert out["last"] == 123.45
~~~

Pytest (API dependency override):
~~~python
from fastapi.testclient import TestClient
from app.main import app, get_exchange_client

class FakeExchangeClient:
    async def fetch_ticker(self, symbol: str) -> dict:
        return {"symbol": symbol, "last": 1.0, "timestamp": 1}

def test_market_ticker_uses_fake_dependency():
    app.dependency_overrides[get_exchange_client] = lambda: FakeExchangeClient()
    client = TestClient(app)
    r = client.get("/market/ticker", params={"symbol": "BTC/USDT"})
    assert r.status_code == 200
    assert r.json()["last"] == 1.0
    app.dependency_overrides.clear()
~~~

Vitest (minimal fetch stub example):
~~~ts
import { vi, test, expect } from "vitest";
vi.stubGlobal("fetch", vi.fn(async () =>
  new Response(JSON.stringify({ symbol: "BTC/USDT", last: 1, timestamp: 1 }), { status: 200 })
));
test("fetch mock returns ticker", async () => {
  const r = await fetch("http://x/market/ticker?symbol=BTC/USDT");
  expect((await r.json()).last).toBe(1);
});
~~~

### Forbidden actions
- No order creation endpoints or live order APIs.
- No private account endpoints (balances/trades) yet.
- No websockets; rate limiting/retries are UNSPECIFIED.

### Run instructions
- cd backend
- pytest (must pass offline)
- uvicorn app.main:app --reload --port 8000

### Paste-ready phase prompt (exact text)
~~~text
GOAL
Introduce an ExchangeClient boundary and an ExchangeService that is always mockable in tests; add a market-data endpoint that uses fakes during tests.

EXACT DELIVERABLES
- ExchangeClient interface/protocol: async fetch_ticker(symbol) -> dict
- ExchangeService depends on ExchangeClient via DI
- CCXTExchangeClient exists but is runtime-only (tests must not use it)
- GET /market/ticker?symbol=BTC/USDT -> {symbol,last,timestamp}
- API tests override the ExchangeClient dependency using dependency overrides

FILES TO CREATE/CHANGE (EXACT PATHS)
- backend/app/adapters/__init__.py
- backend/app/adapters/exchange_client.py
- backend/app/adapters/ccxt_exchange_client.py
- backend/app/services/exchange_service.py
- backend/app/api/__init__.py
- backend/app/api/routes/__init__.py
- backend/app/api/routes/market.py
- backend/app/main.py
- backend/tests/test_exchange_service.py
- backend/tests/test_market_api.py

TESTS TO WRITE FIRST
- ExchangeService unit test with FakeExchangeClient (async)
- /market/ticker API test with dependency override to FakeExchangeClient

FORBIDDEN ACTIONS
- No create order / place order logic.
- No private endpoints (balances/trades).
- No websockets. Rate limiting/retries: UNSPECIFIED.

RUN INSTRUCTIONS
- cd backend
- pytest (must pass without network)
- uvicorn app.main:app --reload --port 8000

OUTPUT REQUIRED
Respond using the MASTER PROMPT OUTPUT FORMAT headings exactly.
STOP after completing this slice.
~~~

---

## Phase: paper-ledger-simulator

### Goal
Implement a deterministic paper ledger + market-order simulator (paper-only) with strong unit tests and minimal API.

### Exact deliverables
Domain:
- Ledger: balances + positions
- Market simulator:
  - market_buy(symbol, quote_amount, price, fee_bps)
  - market_sell(symbol, base_qty, price, fee_bps)
- Safety: hard fail if PAPER_TRADING_ONLY is false
API:
- POST /paper/orders/market {side,symbol,amount,price}
- GET /paper/portfolio -> balances + positions
Storage:
- In-memory repo behind an interface (DB is UNSPECIFIED)

### Files to create/change (exact paths)
- backend/app/domain/__init__.py
- backend/app/domain/models.py
- backend/app/domain/ledger.py
- backend/app/domain/order_simulator.py
- backend/app/repositories/__init__.py
- backend/app/repositories/ledger_repo.py
- backend/app/api/routes/paper.py
- backend/app/main.py
- backend/tests/test_order_simulator.py
- backend/tests/test_paper_api.py

### Tests to write (examples)
Pytest (unit):
~~~python
import pytest
from app.domain.ledger import Ledger
from app.domain.order_simulator import OrderSimulator

def test_market_buy_updates_balance_and_position():
    ledger = Ledger.initial(base_currency="USDT", balances={"USDT": 1000.0})
    sim = OrderSimulator(fee_bps=10)  # 0.10%
    fill = sim.market_buy(ledger, symbol="BTC/USDT", quote_amount=100.0, price=50_000.0)
    assert ledger.balances["USDT"] < 1000.0
    assert ledger.positions["BTC"].qty > 0
    assert fill.symbol == "BTC/USDT"

def test_rejects_insufficient_funds():
    ledger = Ledger.initial(base_currency="USDT", balances={"USDT": 10.0})
    sim = OrderSimulator(fee_bps=10)
    with pytest.raises(ValueError):
        sim.market_buy(ledger, "BTC/USDT", quote_amount=100.0, price=50_000.0)
~~~

Pytest (env safety gate):
~~~python
from app.core.settings import Settings

def test_paper_trading_gate(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ONLY", "false")
    s = Settings()
    assert s.paper_trading_only is False
~~~

Vitest (portfolio fetch stub):
~~~ts
import { vi, test, expect } from "vitest";
vi.stubGlobal("fetch", vi.fn(async () =>
  new Response(JSON.stringify({ balances: { USDT: 900 }, positions: { BTC: { qty: 0.002 } } }), { status: 200 })
));
test("portfolio mock returns balances", async () => {
  const r = await fetch("http://x/paper/portfolio");
  expect((await r.json()).balances.USDT).toBe(900);
});
~~~

### Forbidden actions
- No live trading code or “enable live trading”.
- No strategy bots (DCA/grid) yet.
- No DB migrations/Redis queues (UNSPECIFIED).

### Run instructions
- cd backend
- pytest
- uvicorn app.main:app --reload --port 8000

### Paste-ready phase prompt (exact text)
~~~text
GOAL
Implement a deterministic paper-trading ledger + market order simulator (paper-only) with unit tests and minimal API.

EXACT DELIVERABLES
Domain:
- Ledger (balances + positions)
- Market simulator:
  - market_buy(symbol, quote_amount, price, fee_bps)
  - market_sell(symbol, base_qty, price, fee_bps)
- Safety: hard fail if PAPER_TRADING_ONLY is false
API:
- POST /paper/orders/market {side,symbol,amount,price}
- GET /paper/portfolio -> balances + positions
Storage:
- In-memory repo behind an interface (DB: UNSPECIFIED)

FILES TO CREATE/CHANGE (EXACT PATHS)
- backend/app/domain/__init__.py
- backend/app/domain/models.py
- backend/app/domain/ledger.py
- backend/app/domain/order_simulator.py
- backend/app/repositories/__init__.py
- backend/app/repositories/ledger_repo.py
- backend/app/api/routes/paper.py
- backend/app/main.py
- backend/tests/test_order_simulator.py
- backend/tests/test_paper_api.py

TESTS TO WRITE FIRST
- market_buy updates balances/positions deterministically
- insufficient funds rejected
- paper-trading gate is env-driven and test-covered

FORBIDDEN ACTIONS
- No live trading code or docs.
- No strategies (DCA/grid).
- No DB migrations/Redis queues (UNSPECIFIED).

RUN INSTRUCTIONS
- cd backend
- pytest
- uvicorn app.main:app --reload --port 8000

OUTPUT REQUIRED
Respond using the MASTER PROMPT OUTPUT FORMAT headings exactly.
STOP after completing this slice.
~~~
```

```docs/REVIEWER_CHECKLIST.md
# REVIEWER CHECKLIST (copy/paste)

Use this checklist for every PR/slice.

## Safety (must pass)
- [ ] Paper trading only: no live order placement APIs, adapters, configs, or docs.
- [ ] No withdrawals/transfers exist anywhere (code, routes, docs).
- [ ] Secrets: no API keys/tokens/passwords committed; no secrets printed in logs.
- [ ] Default settings remain safe: PAPER_TRADING_ONLY=true; LIVE_TRADING_ENABLED=false.

## Tests (must pass)
- [ ] TDD evidence: tests exist for new/changed behaviour; assertions cover failure paths.
- [ ] Backend tests run offline: no network I/O; exchange calls mocked/faked.
- [ ] FastAPI API tests use dependency overrides for external dependencies.
- [ ] Frontend tests stub `fetch`/API calls and do not hit a real server.

## Architecture (must pass)
- [ ] Thin routes: endpoints delegate to services.
- [ ] External I/O behind adapters/interfaces (especially CCXT).
- [ ] Domain logic (ledger/simulator) is deterministic and independently tested.

## Scope control
- [ ] No unrelated refactors; changes are small and local.
- [ ] No features outside the current phase prompt.

## Operability
- [ ] Run commands provided in the change description work from a clean checkout.
- [ ] Any unspecified choices are labelled as UNSPECIFIED (no silent assumptions).
```

```docs/RISK_CHECKLIST.md
# RISK CHECKLIST (one-page) + mandatory safety gates (pre-live)

This project is PAPER TRADING ONLY by default. Live trading work is forbidden until all gates below are met.

## One-page risk checklist (quick audit)
Secrets & key handling
- [ ] No secrets committed (only .env.example files).
- [ ] No secrets in logs (API keys, secrets, passphrases, DB URLs with passwords).
- [ ] No secrets in frontend env vars (NEXT_PUBLIC_* must be safe for browsers).

Permissions & blast radius
- [ ] No withdrawals/transfers implemented anywhere.
- [ ] Exchange keys assumed least-privilege (read/trade only).
- [ ] Permission verification process: UNSPECIFIED (manual until defined).

Correctness & determinism
- [ ] Paper ledger and order simulator are deterministic and covered by unit tests (fees + rounding rules tested).
- [ ] Failure modes are tested: insufficient funds, invalid quantities, missing settings, paper-only gate failure.

Test isolation & reliability
- [ ] All tests pass offline (no exchange HTTP/WebSocket calls).
- [ ] Exchange dependency is mocked/faked in tests via DI overrides.
- [ ] UI tests stub fetch; do not depend on a running backend.

Operational safety (paper-only)
- [ ] “Place order” paths only hit simulator (single execution boundary).
- [ ] Audit trail exists for simulated orders (structured logs; persistence: UNSPECIFIED).

## Mandatory safety gates before ANY live trading changes
Gate 0 — Separate design change
- [ ] Live trading work must be a separate, explicitly reviewed design PR (not “just a toggle”). Owner: UNSPECIFIED.

Gate 1 — Single execution boundary (required)
- [ ] Exactly one order execution interface exists. Strategies cannot bypass it.

Gate 2 — Kill switch + hard limits (required)
- [ ] Global kill switch implemented and tested.
- [ ] Risk limits implemented and tested: max drawdown halt, daily loss limit, max position sizing, max open positions.

Gate 3 — Observability (required)
- [ ] Structured logs for every order, fill, rejection, and risk halt.
- [ ] Monitoring/alerting stack: UNSPECIFIED (must be chosen and tested).

Gate 4 — Staging + dry-run (required)
- [ ] Staging environment: UNSPECIFIED.
- [ ] Dry-run mode validates exchange order formatting without financial risk: UNSPECIFIED.

Gate 5 — Human sign-off (required)
- [ ] Manual verification of exchange key permissions (no withdrawal).
- [ ] Security review confirms no secret exposure and safe defaults.

If any gate is unmet: live trading remains forbidden.
```

```docs/ENV_TEMPLATES.md
# ENV TEMPLATES (.env.example)

Rules:
- Never commit real `.env` files. Commit only `.env.example`.
- Frontend must not contain secrets. Only NEXT_PUBLIC_* values belong there.

## backend/.env.example
~~~dotenv
APP_ENV=local
LOG_LEVEL=INFO

# SAFETY GATES (must remain locked by default)
PAPER_TRADING_ONLY=true
LIVE_TRADING_ENABLED=false

# Connectivity (may be unused in early phases)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/tradingbot
REDIS_URL=redis://localhost:6379/0

# Exchange identity (never log secrets)
EXCHANGE_NAME=binance
EXCHANGE_API_KEY=__REPLACE__
EXCHANGE_API_SECRET=__REPLACE__
EXCHANGE_API_PASSPHRASE=
~~~

## frontend/.env.example
~~~dotenv
# Public: safe to expose in browser bundles
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
~~~
```

```docs/TEST_SNIPPETS.md
# TEST SNIPPETS (runnable) — pytest + vitest

These snippets are used across phases 1–3. They are designed to run offline.

## How to run (local)
Backend:
- cd backend
- pytest

Frontend:
- cd frontend
- npm test

## Pytest: FastAPI endpoint test (/health)
~~~python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
~~~

## Pytest: dependency override (mock ExchangeClient in API test)
~~~python
from fastapi.testclient import TestClient
from app.main import app, get_exchange_client

class FakeExchangeClient:
    async def fetch_ticker(self, symbol: str) -> dict:
        return {"symbol": symbol, "last": 1.0, "timestamp": 1}

def test_market_ticker_uses_fake_dependency():
    app.dependency_overrides[get_exchange_client] = lambda: FakeExchangeClient()
    client = TestClient(app)
    r = client.get("/market/ticker", params={"symbol": "BTC/USDT"})
    assert r.status_code == 200
    assert r.json()["last"] == 1.0
    app.dependency_overrides.clear()
~~~

## Pytest: async unit test (AnyIO marker)
~~~python
import pytest
from app.services.exchange_service import ExchangeService

class FakeExchangeClient:
    async def fetch_ticker(self, symbol: str) -> dict:
        return {"symbol": symbol, "last": 123.45, "timestamp": 111}

@pytest.mark.anyio
async def test_exchange_service_normalises_ticker():
    svc = ExchangeService(exchange_client=FakeExchangeClient())
    out = await svc.get_ticker("BTC/USDT")
    assert out["symbol"] == "BTC/USDT"
    assert out["last"] == 123.45
~~~

## Pytest: env safety gate using monkeypatch
~~~python
from app.core.settings import Settings

def test_paper_trading_gate(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ONLY", "false")
    s = Settings()
    assert s.paper_trading_only is False
~~~

## Vitest: mock fetch for a React component
~~~ts
import { render, screen } from "@testing-library/react";
import { vi, test, expect, afterEach } from "vitest";
import StatusClient from "../StatusClient";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("renders healthy when API returns ok", async () => {
  vi.stubGlobal("fetch", vi.fn(async () =>
    new Response(JSON.stringify({ status: "ok" }), { status: 200 })
  ));

  render(<StatusClient apiBaseUrl="http://localhost:8000" />);
  expect(await screen.findByText(/healthy/i)).toBeInTheDocument();
});
~~~
```

```docs/ARCHITECTURE.md
# ARCHITECTURE (paper-trading-first)

## Diagram: architecture
Caption: CCXT is behind an adapter for market data. All “place order” flows go to the paper simulator until pre-live safety gates are met.

~~~mermaid
flowchart LR
  UI[Next.js UI<br/>App Router] -->|HTTP| API[FastAPI API]
  API --> SVC[Service Layer]
  SVC --> EXS[ExchangeService<br/>(market data only)]
  EXS --> EXC[ExchangeClient Interface]
  EXC -->|runtime only| CCXT[CCXT async_support]
  SVC --> SIM[Paper Order Simulator]
  SIM --> LED[Paper Ledger]
  LED --> REP[In-memory Repo<br/>(DB: UNSPECIFIED)]
~~~

## Diagram: phase timeline
Caption: Build in small slices. Live trading is a separate gated design change, not a toggle.

~~~mermaid
flowchart TD
  A[Phase 1<br/>Project skeleton] --> B[Phase 2<br/>Exchange service + mocks]
  B --> C[Phase 3<br/>Paper ledger + simulator]
  C --> D[Later: strategies (DCA/Grid/TWAP/MM-lite)]
  D --> E[Later: risk engine + kill switch]
  E --> F[Later: persistence + observability + CI/CD (UNSPECIFIED)]
  F --> G[Pre-live safety gates satisfied?]
  G -->|No| C
  G -->|Yes (future)| H[Consider live trading as a separate gated design]
~~~
```

```docs/CHANGELOG_FOR_PROMPT_PACK.md
# CHANGELOG — Prompt pack

## v0.1 (initial)
- Drafted paper-trading-first master prompt and baseline guardrails.
- Established strict output headings and “stop after slice” discipline.

## v0.2 (tightened rules + phases)
- Tightened hard rules for enforceability (paper-only bound to simulator; no tests with network I/O; TDD enforced).
- Added three phase prompts with exact files, tests, forbidden actions, and run commands.
- Added reviewer checklist, one-page risk checklist, env templates, test snippets, architecture diagrams, PDD, and strategy reference.
```

```docs/PRODUCT_DESIGN.md
# PRODUCT DESIGN DOCUMENT (PDD) — Paper-Trading-First Trading Bot Platform

Date: 2026-04-04 (Africa/Lusaka)  
Status: Draft for engineering handoff  
Owners: UNSPECIFIED  
CI/CD: UNSPECIFIED  
Deployment: UNSPECIFIED  
Auth model: UNSPECIFIED (single-user vs multi-user)

## Product goals
- Provide a safe platform to build and run automated strategies starting with PAPER TRADING ONLY.
- Deliver deterministic paper execution (ledger + simulator) as the substrate for strategies.
- Make the system testable, reviewable, and hard to misconfigure into unsafe behaviour.

## Non-goals (MVP)
- Live trading, withdrawals/transfers.
- Backtesting/optimisation tooling (later).
- Multi-tenant auth (UNSPECIFIED).

## Target users (personas)
| Persona | Needs | Notes |
|---|---|---|
| Builder (dev/quant) | deterministic sim + tests | wants iteration speed safely |
| Hobbyist | simple dashboard + paper results | must be protected by defaults |
| Operator | logs + safe controls | later: kill switch + alerts |

## Core user journeys (MVP)
1) Open UI → see status (calls /health)  
2) View version & safety mode (calls /version)  
3) View market ticker (calls /market/ticker)  
4) Place paper market order (calls /paper/orders/market)  
5) View paper portfolio (calls /paper/portfolio)

## Feature list
### MVP (aligned to PHASE_PROMPTS)
| Phase | Feature | Output |
|---|---|---|
| 1 | Health/version + UI status | /health, /version, /status page + tests |
| 2 | Market data boundary | ExchangeClient + ExchangeService + /market/ticker + tests |
| 3 | Paper execution core | ledger + simulator + /paper/orders/market + /paper/portfolio + tests |

### Later (gated; UNSPECIFIED details)
- Strategies: DCA, Grid, TWAP, Market-maker-lite (paper first)
- Risk engine + kill switch (must exist before any live trading work)
- Persistence: PostgreSQL; cache/queues: Redis
- Realtime updates (WebSocket/SSE): UNSPECIFIED
- Auth (single-user/multi-user): UNSPECIFIED
- Observability stack: UNSPECIFIED
- Backtesting harness and strategy evaluation: UNSPECIFIED
- Live trading design (separate gated change; forbidden until safety gates)

## System overview (MVP)
- Frontend: Next.js pages call backend JSON endpoints.
- Backend: FastAPI routes are thin; behaviour in services/domain.
- Exchange I/O: behind ExchangeClient; CCXT adapter runtime-only.
- Paper orders: simulator updates ledger via repository abstraction (in-memory first).

## Data model (MVP entities)
- Ledger
  - base_currency: str
  - balances: map[str, float]
  - positions: map[str, Position] (e.g., BTC)
  - updated_at_ms: int
- Position
  - asset: str
  - qty: float
  - avg_entry_price: float (UNSPECIFIED for MVP; optional)
- Fill
  - order_id: str
  - symbol: str
  - side: "buy"|"sell"
  - price: float
  - qty: float
  - fee: float
  - fee_currency: str (UNSPECIFIED; decide and test)
  - timestamp_ms: int

Later entities (UNSPECIFIED until needed):
- Strategy, StrategyRun, RiskPolicy, RiskEvent, ExchangeConnection, AuditLog, User

## API surface (MVP)
All endpoints are paper-safe; no live order endpoints.

Phase 1:
- GET /health -> {"status":"ok"}
- GET /version -> {"version":"0.1.0","paper_trading_only":true,"live_trading_enabled":false}

Phase 2:
- GET /market/ticker?symbol=BTC/USDT -> {"symbol":"BTC/USDT","last":123.45,"timestamp":...}

Phase 3:
- POST /paper/orders/market
  - Request: {"side":"buy","symbol":"BTC/USDT","amount":100.0,"price":50000.0}
  - Semantics: buy amount=quote_amount; sell amount=base_qty
  - Response (example): {"order_id":"...","status":"filled","fill":{...}}
- GET /paper/portfolio -> {"base_currency":"USDT","balances":{...},"positions":{...}}

Status codes for rejections: UNSPECIFIED (must be consistent and test-covered).

## Acceptance criteria (MVP)
- Tests pass offline; exchange is always mocked/faked in tests.
- Ledger/simulator deterministic; errors for invalid amounts and insufficient funds.
- No secrets committed; only .env.example.
- No live trading endpoints/config/docs exist.

## Non-functional requirements
Security
- Paper-only lock default; no withdrawals/transfers; no secrets in code/logs.
Scalability
- Single instance acceptable for MVP. Horizontal scale: UNSPECIFIED.
Observability
- Structured logging for orders/fills/rejections; metrics/tracing: UNSPECIFIED.
Reliability
- Runtime exchange calls safe-fail; retries/timeouts policy: UNSPECIFIED.

## Test plan
- Unit: domain ledger + simulator; service normalisation.
- Integration: API endpoints via FastAPI TestClient; dependency overrides for fakes.
- UI: Vitest + RTL; stub fetch.
- E2E tooling: UNSPECIFIED.

## Rollout plan (paper-only)
- Local dev: phases 1–3.
- CI: pytest + vitest (provider UNSPECIFIED).
- Staging/production: UNSPECIFIED; must remain paper-only.

## Roadmap (aligned to PHASE_PROMPTS)
- Phase 1: skeleton
- Phase 2: exchange service + mocks
- Phase 3: paper ledger + simulator
Next (gated):
- Strategies (paper) → risk engine + kill switch → persistence/observability/auth → (future) live trading design

## Open decisions (UNSPECIFIED)
- CI/CD provider
- Deployment model
- Auth model
- Fee currency + rounding/precision policy
- Realtime transport
- Supported exchanges list
```

```docs/STRATEGY_REFERENCE.md
# STRATEGY REFERENCE (paper-first, test-first)

Date: 2026-04-04 (Africa/Lusaka)  
Scope: strategy design patterns for PAPER TRADING ONLY. Live trading strategy execution is forbidden until safety gates are met.

## Strategy principles (non-negotiable)
- Paper-first: strategies must route all orders through the paper execution boundary (simulator API/service). No direct CCXT usage in strategies.
- Deterministic simulation: given the same inputs (prices, timestamps, config), outputs must be repeatable.
- Risk limits first: every strategy step must pass risk checks before creating a simulated order.

## Execution boundary (mandatory)
Strategies must call ONE interface only:

Option A (in-process service, preferred):
- `ExecutionService.place_market_order(side, symbol, amount, price) -> Fill`

Option B (HTTP to backend, for external runners):
- POST `/paper/orders/market` with `{side,symbol,amount,price}`

Forbidden:
- calling CCXT order methods
- writing to ledger/DB directly
- bypassing risk checks

## Required simulator behaviours
MVP (must implement now)
- Fees: apply a consistent fee model (fee_bps). Fee currency: UNSPECIFIED (choose and test).
- Validation: reject non-positive amounts/prices; reject insufficient funds.
- Fills: market orders are filled immediately at provided `price` (deterministic).

Later (required for realism; UNSPECIFIED dates)
- Slippage model: deterministic (e.g., bps spread or impact curve).
- Partial fills: support partial fill + remaining unfilled amount.
- Time-in-force and latency: UNSPECIFIED.

## Risk constraints (must exist before strategies can run unattended)
Defaults: UNSPECIFIED (must be defined in config + tests)
- Per-trade max notional (quote) size
- Max position size per asset
- Max open positions (if later adding limit orders)
- Daily loss limit
- Global max drawdown halt
- Circuit breaker on repeated execution failures
- Global kill switch (stop new orders immediately)

## Canonical simple strategies (paper-safe)

### DCA (Dollar-Cost Averaging)
Goal: accumulate a target asset by buying fixed quote amounts at fixed intervals.

Parameters (defaults UNSPECIFIED)
- symbol (e.g., "BTC/USDT")
- quote_amount_per_step (e.g., 50 USDT)
- interval_seconds
- max_total_quote_spend
- start_time_ms, end_time_ms (optional)

Pseudocode:
~~~text
if now < next_due_time: return NOOP
if spent_quote + quote_amount_per_step > max_total_quote_spend: STOP
risk_check(quote_amount_per_step)
price = price_feed.last(symbol)
execution.place_market_order("buy", symbol, quote_amount_per_step, price)
update next_due_time = now + interval_seconds
~~~

Expected ledger effects (buy step)
- balances[quote] decreases by quote_amount + fee (if fee in quote)
- positions[base].qty increases by (quote_amount / price) minus fee (if fee in base)
- a Fill record is appended

Example pytest snippet (unit; execution boundary only):
~~~python
def test_dca_places_buy_via_execution_boundary():
    calls = []
    class FakeExec:
        def place_market_order(self, side, symbol, amount, price):
            calls.append((side, symbol, amount, price))
            return {"status": "filled"}

    strat = DcaStrategy(symbol="BTC/USDT", quote_amount=50.0, interval_s=60, max_spend=200.0)
    strat.step(now_ms=0, price_last=50_000.0, execution=FakeExec())
    assert calls == [("buy", "BTC/USDT", 50.0, 50_000.0)]
~~~

---

### Grid (simple long-only grid)
Goal: buy lower and sell higher around a reference price using fixed grid spacing.

Parameters (defaults UNSPECIFIED)
- symbol
- grid_spacing_bps
- grid_levels
- order_quote_amount (per buy)
- reference_price (seed; else use current)
- inventory_target (optional)

Pseudocode (simplified, market orders only for MVP):
~~~text
p = price_feed.last(symbol)
for each level i in 1..grid_levels:
  buy_trigger  = reference_price * (1 - i*grid_spacing_bps)
  sell_trigger = reference_price * (1 + i*grid_spacing_bps)

if p <= nearest_buy_trigger not yet acted:
    risk_check(order_quote_amount)
    execution.place_market_order("buy", symbol, order_quote_amount, p)
if p >= nearest_sell_trigger and have_base_qty:
    base_qty = compute_sell_qty_from_positions(...)
    risk_check(base_qty)
    execution.place_market_order("sell", symbol, base_qty, p)
~~~

Expected ledger effects
- buys increase base position; sells reduce base position and increase quote balance
- reference price may update: UNSPECIFIED (fixed vs trailing)

Example pytest snippet (unit; buy trigger):
~~~python
def test_grid_buys_when_price_below_trigger():
    calls = []
    class FakeExec:
        def place_market_order(self, side, symbol, amount, price):
            calls.append((side, symbol, amount, price))
            return {"status": "filled"}

    strat = GridStrategy(symbol="BTC/USDT", ref_price=100.0, spacing_bps=100, levels=1, order_quote=10.0)
    # price below 99 triggers buy
    strat.step(price_last=98.0, execution=FakeExec(), positions={"BTC": 0.0})
    assert calls and calls[0][0] == "buy"
~~~

---

### TWAP (Time-Weighted Average Price)
Goal: execute a target notional over time by slicing into equal parts.

Parameters (defaults UNSPECIFIED)
- symbol
- side ("buy" or "sell")
- total_amount (quote for buy; base for sell) — semantic must be explicit
- slices
- schedule_seconds
- max_price_deviation_bps (optional guard)

Pseudocode:
~~~text
if slice_index >= slices: STOP
if now < next_due: return NOOP
slice_amount = total_amount / slices
risk_check(slice_amount)
p = price_feed.last(symbol)
if deviation(p) > max_price_deviation_bps: return NOOP (or HALT)  # UNSPECIFIED
execution.place_market_order(side, symbol, slice_amount, p)
slice_index += 1
next_due = now + schedule_seconds
~~~

Expected ledger effects
- repeated small fills; ledger updates as per side

Example pytest snippet (unit; completes slices):
~~~python
def test_twap_places_exact_number_of_slices():
    calls = []
    class FakeExec:
        def place_market_order(self, side, symbol, amount, price):
            calls.append(amount)
            return {"status": "filled"}

    strat = TwapStrategy(symbol="BTC/USDT", side="buy", total_amount=100.0, slices=4, every_s=60)
    for t in [0, 60, 120, 180, 240]:
        strat.step(now_ms=t*1000, price_last=10.0, execution=FakeExec())
    assert len(calls) == 4
    assert all(a == 25.0 for a in calls)
~~~

---

### Market-maker-lite (paper-safe, spread capture)
Goal: place symmetric buy/sell intents around mid price; in MVP (market-only) it becomes an approximation:
- buy small amount when price dips below mid - spread
- sell small amount when price rises above mid + spread

Parameters (defaults UNSPECIFIED)
- symbol
- half_spread_bps
- order_size_quote (for buys)
- min_inventory_base, max_inventory_base

Pseudocode (market approximation):
~~~text
mid = price_feed.last(symbol)
if price <= mid * (1 - half_spread_bps) and base_inventory < max_inventory:
    risk_check(order_size_quote)
    execution.place_market_order("buy", symbol, order_size_quote, price)
if price >= mid * (1 + half_spread_bps) and base_inventory > min_inventory:
    base_qty = compute_small_sell_qty(...)
    risk_check(base_qty)
    execution.place_market_order("sell", symbol, base_qty, price)
~~~

Expected ledger effects
- oscillating inventory within bounds; quote and base balances fluctuate; fees reduce PnL

Example pytest snippet (unit; respects inventory bounds):
~~~python
def test_mm_lite_does_not_buy_above_max_inventory():
    calls = []
    class FakeExec:
        def place_market_order(self, side, symbol, amount, price):
            calls.append(side)
            return {"status": "filled"}

    strat = MmLiteStrategy(symbol="BTC/USDT", half_spread_bps=50, order_quote=10.0, max_base=1.0, min_base=0.0)
    strat.step(price_last=99.0, mid=100.0, base_inventory=1.0, execution=FakeExec())
    assert calls == []  # blocked by max inventory
~~~

## Strategy testing requirements (must be enforced)
Unit tests (required)
- Strategy step is pure: given (time, price, config, current positions), it either NOOPs or calls execution boundary once with correct args.
- Risk checks block orders (verify no execution calls).
- State progression is deterministic (next_due_time, slice counters, etc.).

Integration tests (required once simulator exists)
- Run strategy step against:
  - in-memory ledger repo
  - paper simulator execution service
  - fixed price feed
- Assert ledger deltas are correct after N steps (balances/positions/fills count).

Example integration test outline (paper ledger + DCA):
~~~python
def test_dca_integration_updates_ledger_via_paper_execution():
    # Arrange: ledger with USDT, execution service wired to simulator, fixed price
    # Act: run N dca steps
    # Assert: USDT decreases, BTC increases, fills == N
    pass  # implement when Phase 3 exists
~~~

## Unspecified decisions (must be declared before production strategy runs)
- Risk threshold defaults (per-trade, drawdown, daily loss): UNSPECIFIED
- Fee currency and precision/rounding policy: UNSPECIFIED
- Slippage and partial fill model: UNSPECIFIED
- Strategy scheduling mechanism (cron/worker/loop): UNSPECIFIED
- Persistence and audit log schema: UNSPECIFIED
- CI/CD provider: UNSPECIFIED
```