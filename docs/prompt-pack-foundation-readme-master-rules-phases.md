# Executive summary

This /docs pack is designed to make a Cursor-style LLM assistant **behave like an execution contract**: strict scope per slice, mechanically enforceable test isolation, and explicit stop conditions. The key enforcement hooks are taken from official tooling capabilities: FastAPI’s in-process `TestClient` supports pytest-friendly endpoint tests without a running server, and its `app.dependency_overrides` is a first-class mechanism to replace real dependencies with fakes in tests (directly enforcing “mock all exchange calls”). citeturn0search1turn0search0 Next.js’ official documentation distinguishes browser-exposed environment variables via `NEXT_PUBLIC_`, enabling an enforceable “no secrets in client” rule, and `create-next-app` is the canonical bootstrap route. citeturn0search2turn1search2 CCXT’s official async examples (`ccxt.async_support`, `fetch_ticker`, `exchange.close`) support a clean runtime-only adapter boundary. citeturn1search0 Pytest’s `monkeypatch` (`setenv`, `delenv`) is the canonical tool for safe env-var manipulation in tests (useful for safety-gate tests). citeturn1search1 Vitest’s official mocking APIs (`vi.fn`, `vi.mock`, `vi.spyOn`) support deterministic frontend tests with mocked `fetch`. citeturn0search3turn0search19

```docs/README.md
# /docs — Trading Bot Prompt Pack (Paper-Trading-First)

Date: 2026-04-02 (Africa/Lusaka)  
Audience: developers using Cursor or similar LLM assistants  
Goal: enforceable, execution-ready prompt pack for a paper-trading-first trading bot.

## How to use this pack (minimal steps)
1) Paste `docs/MASTER_PROMPT.md` into Cursor as your “master instruction” (system/project prompt).  
2) Copy the content of `docs/CURSOR_RULES.md` into a repo-root `.cursorrules` file.  
3) Implement in slices using `docs/PHASE_PROMPTS.md` (paste one phase prompt at a time).  
4) Review each slice using `docs/REVIEWER_CHECKLIST.md`.  
5) Treat `docs/RISK_CHECKLIST.md` as mandatory safety gates before any live trading changes.

## What is intentionally UNSPECIFIED
- CI/CD provider and pipeline design: UNSPECIFIED  
- Deployment platform (cloud, VPS, containers): UNSPECIFIED  
- Secrets manager choice: UNSPECIFIED  
- Observability stack (APM/log shipping): UNSPECIFIED

## Document index
- MASTER_PROMPT.md — the enforceable master prompt (≤ ~400 words) + first task
- CURSOR_RULES.md — concise guardrails to copy to `.cursorrules`
- PHASE_PROMPTS.md — three paste-ready phase prompts (skeleton → exchange mocks → paper ledger/simulator)
- REVIEWER_CHECKLIST.md — copy/paste review checklist for PRs
- RISK_CHECKLIST.md — one-page risk + mandatory safety gates (pre-live)
- ENV_TEMPLATES.md — `backend/.env.example` and `frontend/.env.example`
- TEST_SNIPPETS.md — runnable pytest and vitest snippets used in phases
- ARCHITECTURE.md — mermaid diagrams (architecture and phase timeline)
- CHANGELOG_FOR_PROMPT_PACK.md — prompt pack versions and notes
```

```docs/MASTER_PROMPT.md
# Master prompt (paste into Cursor)

Keep this prompt unchanged. It is written to be short, enforceable, and paper-trading-first.

## Master prompt (≤ ~400 words)
~~~text
You are a safety-first trading-systems engineer building a crypto trading-bot platform.

HARD RULES (non-negotiable)
- PAPER TRADING ONLY: any “place order” operation must call the paper order simulator; live exchange order APIs are forbidden. Do not generate or enable live trading code, endpoints, configs, or docs.
- No withdrawals/transfers, ever.
- No test may perform real HTTP/WebSocket/network calls. All exchange I/O must be behind a dependency-injected interface; tests must use fakes/mocks.
- TDD: write failing tests first (Red → Green → Refactor). No business logic without a failing test.
- No secrets in code or logs. Use environment variables only. Provide .env.example files, never real values.
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

## Example of a compliant assistant response (shape only)
Use this structure exactly when responding:

- Task:
- Assumptions (mark UNSPECIFIED if needed):
- Plan:
- Files to create/change (exact paths):
- Tests first (list + key assertions):
- Implementation (path-labelled code blocks):
- Run commands:
- Next step (1–3 items):
```

```docs/CURSOR_RULES.md
# Cursor rules (copy into repo-root .cursorrules)

This file exists as the source-of-truth text for `.cursorrules`. Copy/paste the block below into a file named `.cursorrules` at the repository root.

~~~text
PRIORITY: Safety > Testability > Simplicity > Features.

ABSOLUTE PROHIBITIONS
- Live trading is forbidden (no live order APIs, configs, or docs).
- No withdrawals/transfers.
- Never hardcode or log secrets. Use env vars; commit only .env.example.

TEST RULES
- Red→Green→Refactor. Add/modify tests before implementation.
- Tests must not perform network I/O. Mock/fake all exchange calls.
- Prefer FastAPI DI; use app.dependency_overrides in API tests.

SCOPE RULES
- Make small, atomic changes only.
- Do not add features outside the current slice.

FORMAT
- Always respond using the master prompt output headings.
- For files: output path-labelled fenced code blocks containing file contents.
~~~
```

```docs/PHASE_PROMPTS.md
# Phase prompts (paste-ready)

Precondition: you have already loaded `docs/MASTER_PROMPT.md` into Cursor.

Each phase below includes:
- Goal
- Exact deliverables
- Files (exact paths)
- Tests to write (with example pytest + vitest snippets)
- Forbidden actions
- Run instructions
- Paste-ready prompt text (exact) to paste to Cursor

---

## Phase: project-skeleton

### Goal
Bootstrap a minimal monorepo skeleton (FastAPI + Next.js) with paper-only defaults and tests.

### Exact deliverables
Backend:
- GET /health -> {"status":"ok"}
- GET /version -> {version, paper_trading_only:true, live_trading_enabled:false}
- Settings from env with safe defaults (paper only)
Frontend:
- /status page renders healthy/unhealthy based on backend /health

### Files to create/change (exact paths)
- backend/app/main.py
- backend/app/core/settings.py
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
- python -m venv .venv && source .venv/bin/activate
- pip install -r requirements.txt
- pytest
- uvicorn app.main:app --reload --port 8000

Frontend:
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
- backend/app/main.py
- backend/app/core/settings.py
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
Backend: venv → pip install → pytest → uvicorn
Frontend: npm install → npm test → npm run dev

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
- backend/app/adapters/exchange_client.py
- backend/app/adapters/ccxt_exchange_client.py
- backend/app/services/exchange_service.py
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
- backend/app/adapters/exchange_client.py
- backend/app/adapters/ccxt_exchange_client.py
- backend/app/services/exchange_service.py
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
- backend/app/domain/models.py
- backend/app/domain/ledger.py
- backend/app/domain/order_simulator.py
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
- backend/app/domain/models.py
- backend/app/domain/ledger.py
- backend/app/domain/order_simulator.py
- backend/app/repositories/ledger_repo.py
- backend/app/api/routes/paper.py
- backend/app/main.py
- backend/tests/test_order_simulator.py
- backend/tests/test_paper_api.py

TESTS TO WRITE FIRST
- market_buy updates balances/positions correctly and deterministically
- insufficient funds rejected
- paper-trading gate enforced (env-driven)

FORBIDDEN ACTIONS
- No live trading code or docs.
- No strategies (DCA/grid).
- No DB migrations/Redis queues (UNSPECIFIED).

RUN INSTRUCTIONS
- pytest
- uvicorn app.main:app --reload --port 8000

OUTPUT REQUIRED
Respond using the MASTER PROMPT OUTPUT FORMAT headings exactly.
STOP after completing this slice.
~~~
```

```docs/REVIEWER_CHECKLIST.md
# Reviewer checklist (copy/paste)

Use this for every PR/slice.

## Safety (must pass)
- [ ] Paper trading only: no live order placement APIs, adapters, configs, or docs.
- [ ] No withdrawals/transfers in any form.
- [ ] Secrets: no API keys/tokens/passwords committed; no secrets printed in logs.
- [ ] Default settings remain safe: PAPER_TRADING_ONLY=true; LIVE_TRADING_ENABLED=false.

## Tests (must pass)
- [ ] TDD evidence: tests exist for new/changed behaviour; assertions cover failure paths.
- [ ] Backend tests run offline: no network I/O; exchange calls mocked/faked.
- [ ] FastAPI API tests use dependency overrides for external dependencies.
- [ ] Frontend tests mock `fetch`/API calls using Vitest and do not hit a real server.

## Architecture (must pass)
- [ ] Thin routes: endpoints delegate to services.
- [ ] External I/O behind adapters/interfaces (especially CCXT).
- [ ] Domain logic (ledger/simulator) is deterministic and independently tested.

## Scope control
- [ ] No unrelated refactors; changes are small and local.
- [ ] No features outside the current phase prompt.

## Operability
- [ ] Run commands in the assistant output work from a clean checkout.
- [ ] Any unspecified choices are labelled as UNSPECIFIED (no silent assumptions).
```

```docs/RISK_CHECKLIST.md
# One-page risk checklist + mandatory safety gates (pre-live)

This project is PAPER TRADING ONLY by default. Live trading work is forbidden until all gates below are met.

## Risk checklist (quick audit)
Secrets & key handling
- [ ] No secrets committed (only .env.example files).
- [ ] No secrets in logs (API keys, secrets, passphrases, DB URLs with passwords).
- [ ] Frontend uses only NEXT_PUBLIC_* vars; no secrets are exposed to the browser bundle.

Permissions & blast radius
- [ ] No withdrawals/transfers implemented anywhere.
- [ ] Exchange keys assumed least-privilege (read/trade only). Permission verification method: UNSPECIFIED (must be manual until defined).

Correctness & determinism
- [ ] Paper ledger and order simulator are deterministic and covered by unit tests (fees + rounding rules tested).
- [ ] All failure modes are tested: insufficient funds, invalid amounts, missing settings, paper-only gate failure.

Test isolation & reliability
- [ ] All tests pass offline (no HTTP/WebSocket to exchange).
- [ ] Exchange dependency is always mocked/faked in tests via DI overrides.
- [ ] UI tests stub fetch and do not call a running backend.

Operational safety (paper-only)
- [ ] “Place order” paths only hit simulator (single execution boundary).
- [ ] Audit trail exists for simulated orders (at minimum: structured logs; persistence: UNSPECIFIED).

## Mandatory safety gates before any live trading changes
Gate 0 — Explicit intent
- [ ] A dedicated “Live Trading Design” change is created (separate from day-to-day feature work). Owner: UNSPECIFIED.

Gate 1 — Single execution boundary
- [ ] There is exactly one order execution interface. Strategies cannot bypass it.

Gate 2 — Kill switch and hard limits (required)
- [ ] Global kill switch implemented and tested.
- [ ] Risk limits implemented and tested: max drawdown halt, daily loss limit, max position sizing, max open positions.

Gate 3 — Observability (required)
- [ ] Structured logging for every order, fill, rejection, and risk halt.
- [ ] Monitoring/alerting stack: UNSPECIFIED (must be chosen and tested).

Gate 4 — Staging and dry-run
- [ ] A staging environment exists: UNSPECIFIED.
- [ ] Dry-run mode proves order placement logic without financial risk: UNSPECIFIED.

Gate 5 — Human sign-off
- [ ] Manual verification of exchange key permissions (no withdrawal).
- [ ] Security review confirms no secret exposure and safe defaults.

If any gate is unmet: live trading remains forbidden.
```

```docs/ENV_TEMPLATES.md
# Environment templates (.env.example)

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
# Test snippets (pytest + vitest)

These snippets are used across the first three phases. They are designed to run offline.

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

## Pytest: async unit test (AnyIO)
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
# Architecture (paper-trading-first)

Caption: The architecture enforces a single execution boundary. Market data can be read via an exchange adapter, but all order placement is routed to the paper simulator until safety gates are met.

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

# Phase timeline

Caption: Each phase is a small, test-driven slice. Live trading is a separate gated change, not a “toggle”.

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
# Changelog — Prompt pack

## v0.1 (initial)
- Drafted paper-trading-first master prompt and basic guardrails.
- Established output format and a “stop after slice” discipline.

## v0.2 (tightened rules + phases)
- Tightened hard rules for enforceability (paper-only bound to simulator; no tests with network I/O; TDD enforced).
- Added three phase prompts with exact files, tests, forbidden actions, and run commands.
- Added reviewer checklist, one-page risk checklist, env templates, test snippets, and architecture diagrams.
```