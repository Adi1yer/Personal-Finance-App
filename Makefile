.PHONY: install install-python install-frontend dev dev-all dev-api dev-ui migrate test lint seed reports setup launch stop mac-app build-ui restart

PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin
PIP := $(BIN)/pip

install: install-python install-frontend

install-python:
	mkdir -p data
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -e ".[dev]"

install-frontend:
	./scripts/build-ui.sh

# API only (Ctrl+C to stop)
dev: dev-api

dev-all:
	$(MAKE) -j2 dev-api dev-ui

dev-api:
	@echo "API: http://127.0.0.1:8000/docs  (Ctrl+C to stop)"
	$(BIN)/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --app-dir backend

dev-ui:
	cd frontend && npm run dev

migrate:
	cd backend && PYTHONPATH=. ../$(BIN)/alembic upgrade head

test:
	$(BIN)/pytest backend/tests -v

lint:
	$(BIN)/ruff check backend

build-ui:
	./scripts/build-ui.sh

seed:
	$(BIN)/finance seed-accounts

reports:
	$(BIN)/finance reports --year 2026 --quarter 1

setup:
	./scripts/setup.sh

trust-cert:
	@chmod +x ./scripts/ensure-dev-cert.sh
	@./scripts/ensure-dev-cert.sh

launch:
	./scripts/launch.sh

stop:
	./scripts/stop.sh

restart: stop launch

list-profiles:
	$(BIN)/finance list-profiles

reset-password:
	@test -n "$(EMAIL)" || (echo "Usage: make reset-password EMAIL=your-real@email.com" && exit 1)
	$(BIN)/finance reset-password "$(EMAIL)"

mac-app:
	./scripts/create-mac-app.sh

cloud-build:
	./scripts/build-ui.sh
	docker compose build

cloud-up:
	docker compose up -d

cloud-logs:
	docker compose logs -f api

cloud-sync:
	$(BIN)/finance sync-all-profiles
