# Part B milestones

## B1 — PASSED 2026-10-27T17:52Z (America/Los_Angeles)

Pinned `@google/gemini-cli` 0.65.0 with a lockfile in `infra/gemini-cli`, and a
subprocess adapter using `asyncio.create_subprocess_exec` with no shell, the task as a
single `-p` argument, a fixed `--approval-mode plan`, `-o json` parsing, output and
time limits, and process-group kill on timeout.

Flags were confirmed from the installed binary's own `--help`, not from documentation.
Three behaviours were found by running it, each of which would have made an assumed
implementation wrong or unsafe; all three are recorded in
`../../docs/technical-decisions.md`:

1. Exit 55 for an untrusted folder, which also silently downgrades
   `--approval-mode plan` to `default`.
2. `GOOGLE_API_KEY`/`GEMINI_API_KEY` take precedence over Vertex credentials. A stray
   key billed an unrelated project and returned `403 BILLING_DISABLED`.
3. A project `.env` is loaded from the working directory **and every ancestor**, and a
   trusted workspace loads all of it. Proven with a bogus key in a parent directory
   overriding the credentials passed in the child environment.

An attempted mitigation through `advanced.excludedEnvVars` supplied via
`GEMINI_CLI_SYSTEM_SETTINGS_PATH` had no effect in 0.65.0 and was removed rather than
shipped as a control that does not work.

- `make verify-cli`: exit 0. `gemini_cli_version=0.65.0`, `backend=vertex_ai`,
  `duration_ms=12411`. Evidence: `../../docs/evidence/b1-cli-gate.txt`.
- 46 unit tests covering injection kept as one argv element, fixed approval mode and
  absence of `--yolo`, env allowlisting observed from the child's own view, workspace
  and executable validation, ancestor and subtree credential refusal, malformed and
  error JSON, non-zero exit, untrusted-folder exit, output limit, and a hanging process
  tree being killed.

Also fixed here: `.node-version` pinned 24.22.1 while the active runtime was 25.2.1 and
24.22.1 had never been installed, so earlier frontend builds ran on an unpinned
runtime. `scripts/check-node` now fails `make typecheck` on a mismatch, and it
immediately caught the nvm default alias changing to Node 20 mid-session.

## B2 — PASSED 2026-10-27T18:24Z (America/Los_Angeles)

ADK `SequentialAgent` of `cli_planner` (LlmAgent, no tools), `cli_executor` (LlmAgent,
one tool that spawns the executable), `cli_grounding` (plain BaseAgent, no model) and
`cli_synthesiser` (LlmAgent), behind an `AgentTool`. Authenticated API route and a UI
timeline that labels each stage by what executed it.

- 10 further unit tests: pipeline stage order and kinds, planner has no tools, exactly
  one stage owns the subprocess, verifier is not an `LlmAgent`, request bounds, path
  extraction and deduplication, workspace escape refusal, grounded acceptance, invented
  paths sinking the verdict, and an answer naming no file not counting as grounded.
- 112 unit tests pass across the repository.
- `make verify-cli-pipeline`: `cli_actually_ran=True`, six labelled stages.
  Evidence: `../../docs/evidence/b2-pipeline-run.json`.
- End-to-end through the authenticated API,
  `../../docs/evidence/b2-api-e2e.txt`: `422` for a 5-character question, `401` without
  a credential, `422` for an unexpected field, then `200` in 107s with CLI exit 0 in
  82s. argv recorded as `--approval-mode plan -o json -m gemini-3.6-flash -p <task>`.
  Five paths verified present, `local/sessions.db` named but absent, and the
  synthesiser dropped the dependent claim and recorded why.

Observed limitation: grounding verifies path existence, not the accuracy of statements
about file contents. The reports state this rather than implying more.
