This /docs pack is designed to make a Cursor-style assistant behave like an **execution contract**: strict slice scoping, deterministic tests, and hard safety gates that prevent accidental live trading, network-coupled tests, or secret leakage. Enforcement is aligned to primary tooling mechanisms: FastAPI’s official testing guidance recommends using `TestClient` with pytest, and FastAPI’s documented `app.dependency_overrides` allows replacing real dependencies with fakes for tests (a mechanical way to enforce “mock all exchange calls”). citeturn0search0turn0search1 Next.js officially supports `.env` loading and the `NEXT_PUBLIC_` convention (to prevent secrets from being bundled client-side), and its official `create-next-app` CLI is the canonical bootstrap path. citeturn0search2turn1search2 CCXT’s official async examples (`ccxt.async_support`, `fetch_ticker`, `exchange.close`) support a clean “runtime-only adapter” boundary. citeturn0search3 Pytest’s official `monkeypatch` documentation provides canonical `setenv/delenv` patterns to test safety gates without global side effects, and Vitest’s official mocking guide documents `vi.fn/vi.mock/vi.spyOn` for deterministic frontend tests with stubbed `fetch`. citeturn1search0turn1search1

```docs/README.md
# /docs — Brindle Prompt Pack + PDD (Paper-Trading-First)

Date: 2026-04-04 (Africa/Lusaka)  
Purpose: a concise, enforceable prompt + phase pack for Cursor, plus a Product Design Document (PDD) for engineering handoff.

## How to use (recommended)
1) Paste `docs/MASTER_PROMPT.md` into Cursor as the project/system prompt.
2) Copy `docs/CURSOR_RULES.md` into repo-root `.cursorrules`.
3) Implement one slice at a time from `docs/PHASE_PROMPTS.md` (paste ONE phase prompt per session).
4) Review every change using `docs/REVIEWER_CHECKLIST.md`.
5) Treat `docs/RISK_CHECKLIST.md` as mandatory safety gates (pre-live).

## What is deliberately UNSPECIFIED
- CI/CD provider and pipeline: UNSPECIFIED
- Deployment platform (cloud/VPS/containers): UNSPECIFIED
- Secrets manager choice: UNSPECIFIED
- Observability stack (APM/log shipping): UNSPECIFIED
- Authentication/authorisation model (single-user vs multi-user): UNSPECIFIED

## Document index
- MASTER_PROMPT.md — enforceable master prompt (≤ ~400 words) + first task
- CURSOR_RULES.md — concise `.cursorrules` content
- PHASE_PROMPTS.md — paste-ready prompts for 3 slices (skeleton → exchange mocks → paper ledger/simulator)
- REVIEWER_CHECKLIST.md — copy/paste PR checklist
- RISK_CHECKLIST.md — one-page risk checklist + mandatory safety gates (pre-live)
- ENV_TEMPLATES.md — backend/.env.example and frontend/.env.example
- TEST_SNIPPETS.md — runnable pytest + vitest snippets used in phases
- ARCHITECTURE.md — architecture + phase timeline (mermaid)
- CHANGELOG_FOR_PROMPT_PACK.md — v0.1 and v0.2 notes
- PRODUCT_DESIGN.md — comprehensive Product Design Document (PDD)
```

```docs/MASTER_PROMPT.md
# MASTER PROMPT (paste into Cursor)

Paste the block below as-is. Do not paraphrase it.

## Master prompt (≤ ~400 words)
~~~text
You are a safety-first trading-systems engineer building a crypto brindle platform.

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

Each phase below includes:
- Goal
- Exact deliverables
- Files to create/change (exact paths)
- Tests to write (examples)
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
- [ ] No secrets in frontend environment variables (NEXT_PUBLIC_* must be safe for browsers).

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
- [ ] Audit trail exists for simulated orders (at minimum: structured logs; persistence: UNSPECIFIED).

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
  C --> D[Later: strategies (DCA/Grid)]
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
- Added reviewer checklist, one-page risk checklist, env templates, test snippets, architecture diagrams, and PDD.
```

```docs/PRODUCT_DESIGN.md
# PRODUCT DESIGN DOCUMENT (PDD) — Paper-Trading-First Brindle Platform

Date: 2026-04-04 (Africa/Lusaka)  
Status: Draft for engineering handoff  
Owners: UNSPECIFIED  
CI/CD: UNSPECIFIED  
Deployment: UNSPECIFIED  
Auth model: UNSPECIFIED (single-user vs multi-user)

## Product goals
- Provide a safe platform to build and run automated strategies starting with PAPER TRADING ONLY.
- Deliver deterministic paper execution (ledger + simulator) as a substrate for later bots (DCA/Grid).
- Make the system testable, reviewable, and hard to misconfigure into unsafe behaviour.

## Non-goals (for MVP)
- Live trading, live order placement, withdrawals/transfers.
- Profit optimisation, ML, strategy backtesting, portfolio optimisation.
- Exchange-specific private endpoints beyond what’s required for market data.

## Target users (personas)
| Persona | Primary needs | Risk tolerance |
|---|---|---|
| Builder (dev/quant) | iterate quickly with TDD; deterministic sim | low for unsafe automation |
| Hobbyist trader | simple dashboard; paper runs | medium, but must be protected |
| Operator | clear logs, safe defaults, kill controls | very low |

## Core user journeys (MVP)
1) Open dashboard → view system status (backend /health)  
2) View version/safety mode (paper-only indicator)  
3) Fetch market ticker (paper-safe market data read)  
4) Place simulated market order (paper ledger updates)  
5) View paper portfolio (balances + positions)

Later journeys (post-MVP, gated):
- Configure strategies (DCA/Grid) → run/stop → monitor performance
- Trigger kill switch → halt strategy + cancel pending paper orders (and later live orders)
- Risk engine halts on drawdown/daily loss

## Feature list
### MVP (aligned to PHASE_PROMPTS)
| Phase | Feature | Description |
|---|---|---|
| 1 | Health + version | /health and /version; safe defaults; UI status page |
| 2 | Market data boundary | ExchangeClient + ExchangeService; /market/ticker with fakes in tests |
| 3 | Paper execution core | Paper ledger + market order simulator; /paper/orders/market + /paper/portfolio |

### Later phases (not in current prompts; gated)
- DCA strategy runner (paper first)
- Grid strategy runner (paper first)
- Risk engine: max drawdown halt, daily loss, position sizing, max positions
- Global kill switch (stop + cancel)
- Persistence (PostgreSQL), caching/rate limiting (Redis)
- Observability: structured logs, metrics, tracing (stack UNSPECIFIED)
- Authentication/authorisation (UNSPECIFIED model)
- WebSockets/SSE for live dashboard updates (UNSPECIFIED transport)
- Backtesting harness (paper simulation reuse) and strategy optimisation tooling
- Only after safety gates: live trading design (separate gated change)

## System overview (MVP)
- Frontend: Next.js renders status and (later) portfolio pages by calling backend JSON endpoints.
- Backend: FastAPI routes are thin; core behaviour lives in services and domain modules.
- Exchange I/O: behind ExchangeClient (CCXT adapter runtime-only; never used in unit tests).
- Paper orders: domain-level simulator updates a ledger via a repository abstraction (in-memory first).

## Data model (entities and key fields)
MVP domain entities (phase 3):
- Ledger
  - base_currency: str (e.g., "USDT")
  - balances: map[str, float]
  - positions: map[str, Position] (keyed by base asset, e.g., "BTC")
  - updated_at: int (epoch ms)
- Position
  - asset: str
  - qty: float
  - avg_entry_price: float (optional; phase-3 may be UNSPECIFIED)
- PaperOrder (in-memory record; optional at phase 3)
  - id: str
  - symbol: str ("BTC/USDT")
  - side: "buy" | "sell"
  - qty/amount: float (meaning depends on side; see API contracts)
  - price: float (input price for deterministic sim)
  - status: "filled" | "rejected"
  - created_at: int
- Fill
  - order_id: str
  - symbol: str
  - price: float
  - qty: float
  - fee: float
  - fee_currency: str (UNSPECIFIED until fixed)
  - timestamp: int

Phase-2 transient data:
- Ticker
  - symbol: str
  - last: float
  - timestamp: int

Later entities (UNSPECIFIED until needed):
- User, ExchangeConnection, Strategy, StrategyRun, RiskPolicy, RiskEvent, AuditLog

## API surface (MVP endpoints + schemas)
Notes:
- All responses are JSON.
- Schemas are enforced via typed models (Pydantic) in implementation.

### Phase 1 endpoints
- GET /health
  - 200 response:
    ~~~json
    {"status":"ok"}
    ~~~
- GET /version
  - 200 response:
    ~~~json
    {"version":"0.1.0","paper_trading_only":true,"live_trading_enabled":false}
    ~~~

### Phase 2 endpoint
- GET /market/ticker?symbol=BTC/USDT
  - Query:
    - symbol: string (required)
  - 200 response:
    ~~~json
    {"symbol":"BTC/USDT","last":123.45,"timestamp":1710000000000}
    ~~~
  - Errors:
    - 400 for missing/invalid symbol
    - 503 if market data provider fails (runtime only)

### Phase 3 endpoints
- POST /paper/orders/market
  - Request body:
    ~~~json
    {"side":"buy","symbol":"BTC/USDT","amount":100.0,"price":50000.0}
    ~~~
  - Semantics:
    - side=buy: amount is quote_amount (e.g., 100 USDT)
    - side=sell: amount is base_qty (e.g., 0.002 BTC)
  - 200 response (filled):
    ~~~json
    {"order_id":"...","status":"filled","fill":{"symbol":"BTC/USDT","price":50000.0,"qty":0.002,"fee":0.000002,"timestamp":1710000000000}}
    ~~~
  - Errors (examples):
    - 400 invalid amount/price/side
    - 409 insufficient funds (or 400; choice UNSPECIFIED—must be consistent and tested)
    - 500 if PAPER_TRADING_ONLY is false (hard fail by rule; status code choice UNSPECIFIED)

- GET /paper/portfolio
  - 200 response:
    ~~~json
    {"base_currency":"USDT","balances":{"USDT":900.0},"positions":{"BTC":{"asset":"BTC","qty":0.002}}}
    ~~~

## Acceptance criteria (MVP)
Phase 1:
- /health and /version respond correctly with safe defaults.
- Frontend /status renders healthy/unhealthy with fetch mocked in tests.
- All tests pass offline.

Phase 2:
- ExchangeClient boundary exists; ExchangeService tested with FakeExchangeClient.
- /market/ticker API test uses dependency override (no network).
- CCXT adapter is runtime-only and not exercised in unit tests.

Phase 3:
- Paper ledger + simulator deterministic; fee/rounding rule documented and tested.
- Insufficient funds and invalid amount paths covered by tests.
- Paper-only safety gate test exists (env-driven).

Global (all phases):
- No live trading endpoints, configs, or docs exist.
- No secrets committed; only .env.example.

## Non-functional requirements (NFRs)
Security
- No secrets in code/logs; env-driven config; least privilege by design.
- Paper-trading-only lock is default and must be hard to bypass.

Scalability
- MVP may be single-instance.
- Later: stateless API + persistent storage + background workers (UNSPECIFIED implementation).

Reliability
- Runtime exchange calls must have timeouts and safe failure behaviour (later; UNSPECIFIED exact policy).
- Deterministic simulator must not depend on external state.

Observability
- Structured logs for key events (requests, simulated orders/fills, rejections, safety gate failures).
- Metrics/tracing stack: UNSPECIFIED.

## Test plan
Unit tests
- Domain: ledger + simulator invariants (fees, rounding, funds checks).
- Services: ExchangeService normalises ticker and handles fake client errors.

Integration tests
- API endpoints via FastAPI TestClient.
- Dependency overrides enforce fake ExchangeClient in tests.

E2E tests
- Minimal UI: status page renders correctly under mocked fetch.
- Later: portfolio and orders flows (UNSPECIFIED tooling choice).

## Rollout plan (paper-only)
- Dev (local): phases 1–3.
- CI: run backend pytest + frontend vitest (provider UNSPECIFIED).
- Staging: UNSPECIFIED.
- Production: paper-only; no live keys required.

## Roadmap (aligned to PHASE_PROMPTS)
- Phase 1: project skeleton (API health/version + UI status + tests)
- Phase 2: exchange service with mocks (market ticker)
- Phase 3: paper ledger + simulator + paper order/portfolio endpoints
Next (not in phase prompts; gated):
- Phase 4+: strategies (DCA/Grid) paper-only + risk engine + kill switch
- Phase 5+: persistence + realtime updates + observability + auth (UNSPECIFIED choices)
- Phase 6 (future): live trading design (separate gated change; only after safety gates)

## Open decisions (UNSPECIFIED)
- CI/CD provider and pipeline steps
- Deployment platform and runtime (containers vs VM)
- Auth model (single-user vs multi-tenant)
- Persistence schema and migration tooling
- Fee model (fee currency, rounding rules, precision policy)
- Risk thresholds defaults and configuration UI
- Realtime transport (WebSocket vs SSE) for dashboard
- Exchange(s) supported beyond initial target
```