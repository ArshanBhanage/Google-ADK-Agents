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
	$(UV) run --frozen mypy packages api agents
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

.PHONY: run-adk preflight-lead probe-lead integration-lead verify-lead
LEAD_REQUEST ?= docs/examples/lead-request.json
preflight-lead:
	$(UV) run --frozen python -m scripts.lead-preflight
probe-lead:
	$(UV) run --frozen python -m scripts.lead-preflight --live
run-adk: preflight-lead
	$(UV) run --frozen --env-file .env adk web agents --host 127.0.0.1 --port 8001
integration-lead: probe-lead
	$(UV) run --frozen pytest -m live tests/integration/test_lead_live.py -v
verify-lead: probe-lead
	$(UV) run --frozen python -m scripts.lead-live-smoke $(LEAD_REQUEST)
