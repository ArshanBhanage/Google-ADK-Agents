# Part D milestones

## D1 — PASSED 2026-10-29T06:18Z (America/Los_Angeles)

Read-only pull request retrieval over GitHub's REST API, unified diff parsing with
new-side line mapping, and real Ruff plus AST analysis of the changed files materialised
from the head commit. Credentials live in `agents/code_reviewer/.env` through a
component-scoped `ReviewSettings`; repository targets go through
`GITHUB_ALLOWED_REPOSITORIES`.

Ruff runs `--isolated` so the reviewed project's own configuration cannot disable the
checks that would flag it. Only Python has a configured analyser; every other language
is listed as unanalysed rather than reviewed by assertion.

- `make preflight-review`: `ruff=0.17.2`, allowlist printed, no network call.
- `make verify-review PR=google/adk-python#7801`: fetched in 1464 ms, 2 Python files,
  hunk ranges per file, analysed in 88 ms. 35 findings, 4 inside changed lines, 31
  suppressed as outside the diff, 86 test-file diagnostics dropped.
  Evidence: `../../docs/evidence/d1-review-gate.txt`, `d1-review-run.json`.
- 48 unit tests.

Two defects found while building this:

- `parse_patch` was off by one, appending `(hunk_start, new_line)` when `new_line`
  already pointed at the next unconsumed line, so every hunk admitted one line beyond
  its end — defeating the exact guarantee this gate provides. Caught by a parametrised
  boundary test that I initially assumed was wrong.
- `S101` was reported as a high-severity finding for `assert` in a test file. Rules that
  are correct in application code but noise in tests are now dropped there with the
  count reported; it cut raw diagnostics on the sample PR from 121 to 35.

## D2 — PASSED 2026-10-29T06:55Z (America/Los_Angeles)

`SequentialAgent` of `review_analysis` (BaseAgent: retrieval, mapping, tools, sandbox
decision), `review_reasoner` (the only LlmAgent) and `review_assembler` (BaseAgent:
discard, deduplicate, split verified from unverified, constrain the verdict). Two
authenticated API routes, a UI panel, and a machine-readable report that the Markdown
rendering and the UI both derive from.

Sandbox: ephemeral container, `--network none`, UID 65534, read-only root, read-only
project mount, `noexec,nosuid` tmpfs, 512 MB, 1 CPU, 128 PIDs, all capabilities dropped,
`no-new-privileges`. Executing a pull request's tests is refused by policy; the
isolation record is reported anyway so a reader sees the controls that would apply.

- 39 further unit tests, 87 for Part D, plus 9 live sandbox tests. 277 repository-wide.
- Sandbox gate, `../../docs/evidence/d2-sandbox-gate.txt`: **9 passed**. The container
  actively fails attempts to reach the internet, run as root, and write to the project
  mount; a suite importing third-party packages is `tests_not_run`, not `failed`; and
  collecting no tests is not a pass.
- Pipeline gate, `../../docs/evidence/d2-review-gate.txt`: three stages in the expected
  order, 2 verified comments carrying `UP045` and `SIM117`, 0 unverified, 0 discarded,
  `blocking=False`, 4 tool findings in-diff and 31 suppressed, `test_status=tests_not_run`.
- End-to-end, `../../docs/evidence/d2-api-e2e.txt`:
  - no credential `401`; `pull_request: 0` `422`; a non-allowlisted repository
    `409 BLOCKED_REPOSITORY`.
  - a forged post with no approval: **`403 BLOCKED_NO_APPROVAL`**.
  - `POST review` `200` in 17 s.
  - a real approval token with the body edited: **`403 BLOCKED_CONTENT_CHANGED`**.
  - a matching approval while posting is disabled: **`409 BLOCKED_COMMENT_DISABLED`**.

Cosmetic defects the live run exposed and fixed: the tool version rendered as
`ruff ruff 0.17.2`, and a limitation read `tests_not_run: tests_not_run: …`. A third was
that the policy-refusal path reported no isolation controls, leaving the UI section empty
and implying none existed.

No comment has been posted to any repository. `REVIEW_COMMENT_ENABLED` is false, and the
optional posting proof is left for an explicit decision against a repository the user
owns rather than commenting on a stranger's pull request.
