.PHONY: backend frontend test install dev

install:
	cd backend && python3.11 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r requirements.txt
	cd frontend && npm install

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/python -m pytest -q
	cd frontend && npx tsc --noEmit

dev:
	@echo "Run 'make backend' and 'make frontend' in two terminals."
