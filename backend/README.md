# Backend — Brindle Platform

FastAPI + Pydantic. Python 3.11+.

## Run

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

OpenAPI docs: <http://localhost:8000/docs>

## Test

```bash
.venv/bin/python -m pytest -q
```

## Key boundaries

- **Strategies** produce `OrderIntent` only — never call adapters directly.
- **`ExecutionService`** is the single gateway: health → risk → adapter.
- **`BrokerAdapter`** (Protocol) hides all broker-specific translation.
  Raw broker payloads never cross this boundary — only `ExecutionResult`.
- **Config** is versioned, immutable once applied, and mutation flows through
  `draft → validate → (approve) → apply → audit`.
- **Audit** is append-only; every service-level action writes a record.

## Layout

See root [README.md](../README.md).
