# Milestone ledger

Started 2026-10-26 (America/Los_Angeles). Existing repository retained on main.
No application or live integration is complete at initialization.

| Gate | Goal | Status | Acceptance |
|---|---|---|---|
| 0 | Runtime, configuration, auth/session foundation, API/UI, CI | PASSED | Local checks, persistent sessions, API/UI and dependency diagnostics |
| A1 | Lead research architecture | BLOCKED (Google Search grounding quota) | ADK load, real retrieval, schemas |
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

## A1 checkpoint — 2026-10-26 (America/Los_Angeles)

Foundation commit: `6b5174174c40266bb954196f422d5f804253a62d`.

Implemented specialist ADK architecture, request/evidence schemas and constrained
public website retrieval. ADK AgentLoader loaded `lead_research` successfully.
Actual public retrieval: `evidence/lead-source-retrieval.json`; source title,
timestamp, digest and content length were observed, not invented.

`make preflight-lead`: exit 2, BLOCKED GOOGLE_API_KEY and GEMINI_MODEL. No model
call or grounded lead result is claimed. Configure those in root .env locally.
LOCAL_ACCESS_TOKEN is also needed for the authenticated shared UI session flow.

Remaining A1 work includes deterministic ranking and validated report output;
A2 results UI/export is not started. B–E remain untouched. A1 cannot be marked
PASSED from local tests or source retrieval alone.

Correction (see the next section): the sentence previously claiming this
checkpoint was committed was wrong. These files were still untracked at the time;
they are committed by the A1 credential-configured update below.

## A1 update — 2026-10-26T23:48Z (America/Los_Angeles)

Credentials are now present in the local root .env, so the gate was retested
against the real provider instead of being deferred.

- `make check`: exit 0. 30 unit tests, Ruff lint/format, mypy (15 files),
  TypeScript, secret scan 0 findings, Vite build. Two pre-existing failures found
  and fixed during this pass: a missing `dict` annotation in `ranking.py` that
  broke `mypy`, and a stale pipeline-shape assertion that predated the
  `evidence_ranker` stage.
- `make probe-lead`: exit 2. Observed `model=gemini-3.6-flash generation=OK
  google_search_grounding=429_RESOURCE_EXHAUSTED`. Plain generation answers; the
  built-in Google Search tool does not. Reproduced on `gemini-3.8-flash` and
  `gemini-3.1-flash-lite`, so this is an account-level grounding quota, not a
  model-name problem. Evidence: `evidence/a1-provider-probe.txt`.
- `uv run pytest -m live tests/integration/test_lead_live.py`: 3 errors, 0 passed,
  176s, after `HttpRetryOptions` retried 429/503 six times with exponential
  backoff. Reported as `BLOCKED_PROVIDER_QUOTA`, not as a skip and not as a pass.
  Evidence: `evidence/a1-live-gate.txt`.
- Also noted: `gemini-2.5-flash` and `gemini-2.5-pro` now return 404 "no longer
  available to new users" on this key, and plain calls intermittently return 503
  UNAVAILABLE, which the retry configuration absorbs.

A1 stays BLOCKED on an externally controlled quota. Per the execution order, A2
and Parts B–E are not started.
