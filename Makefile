UV ?= uv
NPM ?= npm
export UV_CACHE_DIR ?= $(CURDIR)/.cache/uv

.PHONY: setup lint typecheck test check run-api run-web check-secrets check-container check-node check-ecommerce verify-all setup-gemini-cli preflight-cli verify-cli verify-cli-pipeline preflight-bug verify-bug verify-triage preflight-review verify-review verify-review-pipeline
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
	# agents/ecommerce is a self-contained component with its own pyproject, lockfile
	# and stricter mypy settings. It is checked by `make check-ecommerce`, which runs
	# its own configuration, rather than under this one.
	$(UV) run --frozen mypy packages api agents --exclude 'agents/ecommerce'
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
preflight-bug:
	$(UV) run --frozen python -m scripts.bug-preflight
verify-bug:
	$(UV) run --frozen python -m scripts.bug-preflight --live
verify-triage:
	$(UV) run --frozen python -m scripts.bug-triage-smoke $(BUG_REPO)
preflight-review:
	$(UV) run --frozen python -m scripts.review-preflight
verify-review:
	$(UV) run --frozen python -m scripts.review-preflight --pr $(PR)
verify-review-pipeline:
	$(UV) run --frozen python -m scripts.review-smoke $(PR)

check-ecommerce:
	$(MAKE) -C agents/ecommerce check
verify-all: check check-ecommerce
	@echo "Part A: make probe-lead && make verify-lead && make integration-lead"
	@echo "Part B: make verify-cli && make verify-cli-pipeline"
	@echo "Part C: make verify-bug && make verify-triage BUG_REPO=<owner/repo>"
	@echo "Part D: make verify-review PR=<owner/repo#n> && make verify-review-pipeline PR=<owner/repo#n>"
	@echo "Part D sandbox: $(UV) run --frozen pytest -m live tests/integration/test_sandbox_live.py"
	@echo "Part E: make -C agents/ecommerce local-check (and live-check with credentials)"
	@echo "Each live target costs real provider usage; run them deliberately, not in CI."
