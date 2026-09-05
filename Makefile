.PHONY: install data eval test lint api ui all

install:
	cd backend && uv venv && uv pip install -e ".[dev]"
	cd frontend && npm install

data:
	cd backend && .venv/bin/ringsentinel generate

eval:
	cd backend && .venv/bin/ringsentinel evaluate --from-disk

test:
	cd backend && .venv/bin/pytest tests/ -q

lint:
	cd backend && .venv/bin/ruff check ringsentinel/ tests/

api:
	cd backend && .venv/bin/python -m uvicorn ringsentinel.api.main:app --port 8000

ui:
	cd frontend && npm run dev

all: data eval test lint
