# HealthyVytals — task shortcuts (macOS/Linux).
#
# Thin mirror of scripts/*.sh so you can type `make dev` etc. Windows users run
# the PowerShell scripts in scripts/ directly (see README).

.DEFAULT_GOAL := help
.PHONY: help setup dev migrate seed reset-db test lint

VENV_PY := .venv/bin/python

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Create venv, install deps, migrate, and seed
	./scripts/setup.sh

dev: ## Run the app (web UI + API) on http://localhost:8000
	./scripts/dev.sh

migrate: ## Apply database migrations (alembic upgrade head)
	./scripts/migrate.sh

seed: ## Load demo seed data (idempotent)
	./scripts/seed.sh

reset-db: ## Drop the SQLite DB, re-migrate, and re-seed
	./scripts/reset-db.sh

test: ## Run the test suite
	cd backend && ../$(VENV_PY) -m pytest

lint: ## Lint with ruff
	cd backend && ../$(VENV_PY) -m ruff check .
