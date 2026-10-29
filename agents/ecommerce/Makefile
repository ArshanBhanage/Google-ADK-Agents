PYTHON := .venv/bin/python

.PHONY: check readiness local-check
check:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	.venv/bin/mypy --config-file pyproject.toml .
	.venv/bin/pytest -q

readiness:
	cd ../.. && agents/ecommerce/$(PYTHON) -m agents.ecommerce.cli readiness

local-check:
	cd ../.. && agents/ecommerce/$(PYTHON) -m agents.ecommerce.local_check

setup:
	cd ../.. && agents/ecommerce/$(PYTHON) -m agents.ecommerce.runtime setup
sync:
	cd ../.. && agents/ecommerce/$(PYTHON) -m agents.ecommerce.cli sync
toolbox:
	cd ../.. && agents/ecommerce/$(PYTHON) -m agents.ecommerce.runtime toolbox
serve:
	cd ../.. && agents/ecommerce/$(PYTHON) -m uvicorn agents.ecommerce.server:app --host 127.0.0.1 --port 8085 --no-access-log
live-check:
	cd ../.. && agents/ecommerce/$(PYTHON) -m agents.ecommerce.live_check
