# Milestone ledger

Started 2026-10-26 (America/Los_Angeles). Existing repository retained on main.
No application or live integration is complete at initialization.

| Gate | Goal | Status | Acceptance |
|---|---|---|---|
| 0 | Runtime, configuration, auth/session foundation, API/UI, CI | PASSED | Local checks, persistent sessions, API/UI and dependency diagnostics |
| A1 | Lead research architecture | PASSED | ADK load, real retrieval, schemas |
| A2 | Lead research end-to-end | PASSED | Grounded live query, UI and matching CSV |
| B1 | Restricted Gemini CLI tool | PASSED | Actual CLI invocation and negative tests |
| B2 | CLI ADK pipeline | PASSED | Real trace and UI |
| C1 | MCP tools | PASSED | Handshake and authorized issue search |
| C2 | Bug workflow | PASSED | Evidence and approval boundaries |
| D1 | Review analysis | PASSED | Real source/PR and deterministic diagnostics |
| D2 | Review pipeline | PASSED | Grounded review and isolation controls |
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

## A1 — PASSED 2026-10-27T06:55Z (America/Los_Angeles)

The blocker was a billing track, not a quota. Gemini Developer API usage from an AI
Studio key is not covered by Google Cloud Free Trial credits, and that backend's free
tier does not offer Google Search grounding at all. Switching to Vertex AI on a
credit-eligible project unblocked it. Two further real obstacles were found and fixed
by measurement rather than assumption:

- Gemini 3 models return `404 NOT_FOUND` on regional Vertex endpoints such as
  `us-central1`; they are served from `location=global`. The default was changed.
- Vertex rejected `LeadReport` as a response schema with `400 INVALID_ARGUMENT`.
  Bisecting showed no single unsupported keyword: `Citation` and `Lead` were each
  accepted alone, and `pattern`, `minLength`, `maxItems`, enums and `date-time` all
  passed individually. The nested whole was refused. Rather than keep probing a paid
  API, the validator now emits a minimal `CandidateReport` wire contract and the
  deterministic stage maps it to the strict `LeadReport`.

That change tightened the evidence rules as a side effect. `CandidateCitation` has no
digest or timestamp field and `CandidateLead` has no score, confidence or verification
field, so the model is now structurally unable to assert provenance or rank itself. A
test asserts those fields are absent from the wire contract.

Commands and observed results:

- `make check`: exit 0. 31 unit tests, Ruff, mypy (16 files), TypeScript, secret scan
  0 findings, Vite build.
- `make probe-lead`: exit 0.
  `backend=vertex_ai model=gemini-3.6-flash project=refined-clarity-512906-a5
  location=global generation=OK google_search_grounding=OK`.
  Evidence: `evidence/a1-provider-probe.txt`.
- `make integration-lead`: **3 passed**, 106s. Asserts grounding metadata was actually
  observed, that every surviving lead cites a URL present in the session's retrieved
  evidence, and that the report is deduplicated and ordered.
  Evidence: `evidence/a1-live-gate.txt`.
- `make verify-lead`: exit 0. `events=9 search_used=True retrieved_sources=4
  verified_leads=2`. Evidence: `evidence/a1-live-run.txt` and
  `evidence/a1-live-grounded-run.json`.

Two real Ohio machine shops were returned with excerpts quoted from pages this code
fetched itself, each pinned to the retrieval timestamp and the SHA-256 of the actual
response body. Three further candidates were reported unverified with specific
reasons (cross-origin redirect, robots crawl-delay requirement, per-session retrieval
budget) and one was discarded for failing excerpt matching. Nothing was substituted
for missing data.

Measured cost of one run, from `usage_metadata` rather than estimated:
33,885 prompt tokens, 4,984 output, 5,857 thinking, and 17 billable search queries.
At the published Flash rates that is $0.066 in tokens. Search dominates: at the
Developer API's $14/1,000 the run is about $0.30, and about $0.66 if Vertex charges
$35/1,000. The authoritative Vertex grounding rate is still unconfirmed, so the
actual billing report must be checked before running at volume. Reducing the number
of grounded stages is the lever that matters, not token trimming.

Known deprecation: installed ADK warns that `GOOGLE_GENAI_USE_VERTEXAI` is superseded
by `GOOGLE_GENAI_USE_ENTERPRISE`. Both are now exported.

A2 is next. No part of B–E has been started.

## A2 — PASSED 2026-10-27T07:12Z (America/Los_Angeles)

User criteria through grounded research, qualification, cited results and CSV, behind
authentication, with the UI and walkthrough complete.

Implemented: `agents/lead_research/export.py`; two authenticated API routes; the React
criteria form with an explicit confirmation step, results with per-citation excerpt,
link, timestamp and digest, limitations, search suggestions and an observed trace;
`tests/unit/test_lead_export.py` and `tests/unit/test_lead_api.py`.

- `make check`: exit 0. **49 unit tests**, Ruff, mypy (17 files), TypeScript, secret
  scan 0 findings, Vite build.
- End-to-end against a running `make run-api`, recorded in
  `evidence/a2-api-e2e.txt`:
  - `GET /api/readiness` → 200, `status=CONFIGURED_NOT_VERIFIED`, `missing=[]`.
  - `POST /api/sessions` with no credential → 401; with the credential → 201.
  - `POST /api/agents/lead_research/{id}/research` → 200 in 95s. 2 verified leads,
    15 billable searches, 4 pages retrieved and hashed, 3 search-suggestion blocks,
    54,348 prompt / 4,626 output / 6,371 thinking tokens.
  - `GET .../export.csv` → 200, `text/csv; charset=utf-8`, `cache-control: no-store`,
    attachment filename set. **2 rows for 2 displayed leads, and name, domain, score,
    source URLs and digests assert equal to the API response field for field.**
  - `GET .../export.csv` before any run → 409, not an empty file.
- Results were FM Machine Co. (`fmmachine.com`) and Wagner Machine, Inc.
  (`wagnermachine.com`), each cited to a capability or equipment page fetched by this
  code. Three candidates were reported unverified with specific reasons and one
  discarded for failing excerpt matching.

Two defects found and fixed during this gate:

- Unit tests were not hermetic. `pydantic-settings` reads `os.environ` even with
  `_env_file=None`, so a provider variable exported in the shell satisfied a Settings
  object a test intended to leave unconfigured, and the readiness fail-closed
  assertion passed or failed depending on the developer's shell. `tests/conftest.py`
  now strips those variables for every test.
- CSV export was vulnerable to spreadsheet formula injection, since lead names come
  from untrusted pages. Values beginning `=`, `+`, `-`, `@` or a control character are
  prefixed, with a test using a hostile `=HYPERLINK(...)` name.

Security position recorded in `security.md`: the one place provider markup is rendered
as HTML is the Search Suggestions block, which Google's grounding terms require
verbatim. Every other untrusted value is escaped by React, and outbound links carry
`rel="noreferrer noopener"`.

Gate A is complete. B1 is next; B–E remain unstarted.

## B1 and B2 — PASSED 2026-10-27 (America/Los_Angeles)

Full detail in `../agents/gemini_cli_tool/MILESTONES.md`; CLI behaviour findings in
`technical-decisions.md`.

- B1, `make verify-cli`: exit 0, `gemini_cli_version=0.65.0`, `backend=vertex_ai`,
  `duration_ms=12411`. Evidence: `evidence/b1-cli-gate.txt`.
- B2, `make verify-cli-pipeline`: `cli_actually_ran=True` with six labelled stages.
  Evidence: `evidence/b2-pipeline-run.json`.
- B2 end-to-end through the authenticated API: `422` for a 5-character question, `401`
  without a credential, `422` for an unexpected field, then `200` in 107s with CLI exit
  0 in 82s and argv `--approval-mode plan -o json -m gemini-3.6-flash -p <task>`. Five
  paths verified present, one named path absent with the dependent claim dropped.
  Evidence: `evidence/b2-api-e2e.txt`.
- 112 unit tests pass. The Node pin is now enforced by `scripts/check-node`, which
  caught the nvm default alias changing to Node 20 mid-session.

Verification is **scoped**, not repository-wide: `make check` is red because of
concurrent Part E work under `agents/ecommerce/` owned by another session, which this
work has not touched. Two findings there, for its owner: ruff `E501` at
`agents/ecommerce/database.py:44` and `:50`, and a detect-secrets `Basic Auth
Credentials` report at `agents/ecommerce/tests/test_config.py:14`. Both will fail
`make check` and CI for the whole repository until resolved.

Gate order note: Part E exists in the working tree without C and D having started,
which departs from the prompt's strict order. That work is not owned here and has been
left untouched.

## C1 and C2 — PASSED 2026-10-29 (America/Los_Angeles)

Full detail in `../agents/bug_assistant/MILESTONES.md`.

- C1, `make verify-bug`: `handshake_ms=1891`, 6 tools advertised and admitted over
  Streamable HTTP to `https://api.githubcopilot.com/mcp/x/issues/readonly`, no write
  tool present, then a real lookup in 1220 ms. Unconfigured it exits 2 with
  `BLOCKED_GITHUB_TOKEN`. Evidence: `evidence/c1-mcp-gate.txt`.
- C2 end-to-end, `evidence/c2-api-e2e.txt`: `POST triage` 200 in 56 s over three real
  MCP search calls, 14 issues searched, severity high, one verified duplicate
  `google/adk-python#7800` — independently confirmed with `gh issue view` as OPEN with
  the same title and URL.
- Authorization negatives all observed: `401` without a credential, `404` for another
  identity's or another agent's session, `422` for invalid input,
  `403 BLOCKED_NO_APPROVAL` for a forged write, `403 BLOCKED_CONTENT_CHANGED` for a
  real approval with the title edited, and `409 BLOCKED_WRITE_DISABLED` for a matching
  approval while writes are off.
- 190 unit tests pass, 67 of them for Part C.

Part C credentials live in `agents/bug_assistant/.env` through a component-scoped
`BugSettings`, which is where the deliverable contract puts component-specific secrets.
The shared root `Settings` no longer owns a GitHub token.

No issue has been created in any repository. The optional write proof is left for an
explicit decision rather than manufacturing evidence with a spam ticket.

Verification remains **scoped**, not repository-wide: `make check` is red from
concurrent Part E work under `agents/ecommerce/`, owned by another session and untouched
here. Its two blockers for that owner are unchanged: ruff `E501` at
`agents/ecommerce/database.py:44` and `:50`, and a detect-secrets `Basic Auth
Credentials` report at `agents/ecommerce/tests/test_config.py:14`.

## D1 and D2 — PASSED 2026-10-29 (America/Los_Angeles)

Full detail in `../agents/code_reviewer/MILESTONES.md`.

- D1, `make verify-review PR=google/adk-python#7801`: fetched in 1464 ms, 2 Python
  files, hunk ranges per file, analysed in 88 ms with ruff 0.17.2 and python-ast
  3.12.14. 4 of 35 findings inside changed lines, 31 suppressed, 86 test-file
  diagnostics dropped. Evidence: `evidence/d1-review-gate.txt`.
- D2 sandbox, `evidence/d2-sandbox-gate.txt`: **9 live tests passed**. The container
  fails attempts to reach the internet, run as root and write to the project mount;
  missing dependencies are `tests_not_run`, not `failed`.
- D2 end-to-end, `evidence/d2-api-e2e.txt`: `401` without a credential, `422` for
  `pull_request: 0`, `409 BLOCKED_REPOSITORY` outside the allowlist,
  `403 BLOCKED_NO_APPROVAL` for a forged post, `200` in 17 s for the review,
  `403 BLOCKED_CONTENT_CHANGED` for a real approval with an edited body, and
  `409 BLOCKED_COMMENT_DISABLED` for a matching approval while posting is off.
- 277 unit tests pass, 87 for Part D, plus 9 live sandbox tests.

No comment has been posted to any repository. Executing a pull request's tests is
refused by policy, so `test_status` is `tests_not_run` with the isolation controls still
reported.

Verification remains **scoped**: `make check` is red from concurrent Part E work under
`agents/ecommerce/`, owned by another session and untouched here.
