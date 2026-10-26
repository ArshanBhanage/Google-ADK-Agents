# Milestone ledger

Started 2026-10-26 (America/Los_Angeles). Existing repository retained on main.
No application or live integration is complete at initialization.

| Gate | Goal | Status | Acceptance |
|---|---|---|---|
| 0 | Runtime, configuration, auth/session foundation, API/UI, CI | PASSED | Local checks, persistent sessions, API/UI and dependency diagnostics |
| A1 | Lead research architecture | NOT_STARTED | ADK load, real retrieval, schemas |
| A2 | Lead research end-to-end | NOT_STARTED | Grounded live query, UI and matching CSV |
| B1 | Restricted Gemini CLI tool | NOT_STARTED | Actual CLI invocation and negative tests |
| B2 | CLI ADK pipeline | NOT_STARTED | Real trace and UI |
| C1 | MCP tools | NOT_STARTED | Handshake and authorized issue search |
| C2 | Bug workflow | NOT_STARTED | Evidence and approval boundaries |
| D1 | Review analysis | NOT_STARTED | Real source/PR and deterministic diagnostics |
| D2 | Review pipeline | NOT_STARTED | Grounded review and isolation controls |
| E1 | Merchant/AlloyDB/Toolbox | NOT_STARTED | Real catalog sync and MCP query |
| E2 | Commerce workflow | NOT_STARTED | Owned carts and genuine checkout handoff |
| F | Integration | NOT_STARTED | All five live gates and documentation |
| G | Publish | NOT_STARTED | Verified public GitHub URL and clean index |

## Foundation checklist

- [x] Read complete prompt; inspect existing Git repository and tools.
- [x] Resolve all supplied reference URLs; record changes in references.md.
- [x] Lock dependencies and verify installed ADK signatures.
- [x] Create ignored .env files without overwriting user values.
- [x] Implement authenticated session API and connection-status UI.
- [x] Run formatting, type checks, tests, frontend build and secret checks.
- [x] Record evidence and commit the verified scope.

Command evidence, blockers and commit references will be appended after execution.

## Gate 0 results — 2026-10-26 (America/Los_Angeles)

- `make check`: exit 0; 7 tests passed, Ruff/mypy/TypeScript passed, secret scan
  found zero findings, Vite build passed. Evidence: `evidence/foundation-check.txt`.
- `npm --prefix web run test:e2e`: initial exit 1 for mobile horizontal overflow;
  fixed grid minimum sizing. Rerun exit 0, 1 browser test passed against real API.
  Evidence: `evidence/foundation-browser.txt` and actual desktop/mobile PNGs.
- `docker build -f infra/containers/api.Dockerfile -t adk-suite-foundation .`:
  exit 0. Image manifest sha256:a4a5a20efd67f51ca2f67b674dc7c779969b518cf3f2ffb4069a08d3b83bf9b7.
- `docker run --rm --network none adk-suite-foundation python -c
  'import os; from api.main import app; print("uid", os.getuid()); print("routes", len(app.routes))'`:
  exit 0, UID 10001, 9 routes. Actual import without network or mounted secrets.
- Installed ADK workflow types and Runner import successfully. There is no part-specific
  root_agent until A1; the foundation check does not claim agent execution.
- Known warnings: Starlette TestClient's httpx transport and ADK template-workflow
  deprecations. No failures were suppressed.
- GCloud and Gemini CLI absent (later phases). Gemini credentials absent (A1 live
  gate). Google identity verification configured in code but not live-verified.
- No public remote, cloud resource or video has been created.
- Commit: the milestone commit containing this ledger; exact SHA recorded in the next update.
