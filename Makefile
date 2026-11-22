.PHONY: up down install mcp spend-init test lint e2e types migrate

up:
	docker compose up -d --wait db

down:
	docker compose down

install:
	cd api && uv sync --locked
	cd web && npm ci

# Installs the pinned accounting MCP server. Lifecycle scripts stay off (review before enabling).
mcp:
	cd mcp && npm ci --ignore-scripts --no-audit --no-fund

# Create the spend ledger once ($5 cap for the whole build). Never resets it.
spend-init:
	cd api && uv run python -m getpaid.spend_init

test: install up
	cd api && uv run pytest -q
	cd web && npx vitest run

lint: install
	cd api && uv run ruff check . && uv run ruff format --check . && uv run mypy src tests
	cd web && npx tsc --noEmit && npm run lint

e2e: install up
	cd web && npx playwright test

# Regenerate web/openapi.json and the TypeScript types from the API.
types:
	cd api && uv run python -m getpaid.export_openapi
	cd web && npm run types

migrate:
	cd api && uv run alembic upgrade head
