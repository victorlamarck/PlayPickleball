.DEFAULT_GOAL := help
.PHONY: help up down migrate run relay seed simulate viewer test lint fmt

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

up: ## Start Postgres and the Firestore emulator
	docker compose up -d --wait postgres firestore

down: ## Stop local services
	docker compose down

migrate: ## Apply database migrations
	uv run alembic upgrade head

run: ## Run the API with auto-reload
	uv run uvicorn app.main:app --reload

relay: ## Run the outbox relay loop (dev)
	uv run python -m app.outbox

seed: ## Create the demo tournament
	uv run python scripts/seed.py

simulate: ## Play the demo tournament (pass ARGS="--tournament <id> --speed 5")
	uv run python scripts/simulate.py $(ARGS)

viewer: ## Run the Flutter viewer in Chrome against the local emulator
	cd client_flutter && flutter run -d chrome

test: ## Run the test suite
	uv run pytest

lint: ## Lint, check formatting and type-check
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	uv run mypy scripts

fmt: ## Auto-fix lint issues and format
	uv run ruff check --fix .
	uv run ruff format .
