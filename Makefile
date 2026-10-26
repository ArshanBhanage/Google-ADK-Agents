UV ?= uv
NPM ?= npm
export UV_CACHE_DIR ?= $(CURDIR)/.cache/uv

.PHONY: setup lint typecheck test check run-api run-web check-secrets check-container
setup:
	$(UV) sync --locked
	$(NPM) --prefix web ci
	./scripts/setup-env
lint:
	$(UV) run --frozen ruff check .
	$(UV) run --frozen ruff format --check .
typecheck:
	$(UV) run --frozen mypy packages api
	$(NPM) --prefix web run typecheck
test:
	$(UV) run --frozen pytest -m 'not live'
check-secrets:
	$(UV) run --frozen python scripts/check-secrets.py
check: lint typecheck test check-secrets
	$(NPM) --prefix web run build
run-api:
	$(UV) run --frozen uvicorn api.main:app --host 127.0.0.1 --port 8000 --no-access-log
run-web:
	$(NPM) --prefix web run dev
check-container:
	docker build -f infra/containers/api.Dockerfile -t adk-suite-foundation .
