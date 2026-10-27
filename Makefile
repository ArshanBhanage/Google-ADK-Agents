UV ?= uv
NPM ?= npm
export UV_CACHE_DIR ?= $(CURDIR)/.cache/uv

.PHONY: setup lint typecheck test check run-api run-web check-secrets check-container check-node setup-gemini-cli preflight-cli verify-cli verify-cli-pipeline
setup:
	$(UV) sync --locked
	$(NPM) --prefix web ci
	./scripts/setup-env
lint:
	$(UV) run --frozen ruff check .
	$(UV) run --frozen ruff format --check .
check-node:
	./scripts/check-node
typecheck: check-node
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

setup-gemini-cli: check-node
	$(NPM) --prefix infra/gemini-cli install --no-audit --no-fund
	infra/gemini-cli/node_modules/.bin/gemini --version
preflight-cli:
	$(UV) run --frozen python -m scripts.cli-preflight
verify-cli:
	$(UV) run --frozen python -m scripts.cli-preflight --live
verify-cli-pipeline:
	$(UV) run --frozen python -m scripts.cli-pipeline-smoke
