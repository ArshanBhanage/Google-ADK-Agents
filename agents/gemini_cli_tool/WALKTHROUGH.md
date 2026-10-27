# Part B walkthrough

## Prerequisites

Node 24.22.1 active (`nvm use 24.22.1`), `gcloud auth application-default login`
completed, `GOOGLE_CLOUD_PROJECT` set and `GOOGLE_CLOUD_LOCATION=global` in the local
root `.env`, and a `LOCAL_ACCESS_TOKEN` of at least 32 characters.

```sh
make setup-gemini-cli          # expect: 0.65.0
./scripts/stage-cli-workspace  # copy the printed path into GEMINI_WORKSPACE
make preflight-cli             # expect: gemini_cli_version=0.65.0, backend=vertex_ai
make verify-cli                # expect: VERIFIED exit=0
```

## Screen by screen

1. `make run-api` and `make run-web`, open the Vite URL, choose **B · Gemini CLI pipeline**.
2. Paste the `LOCAL_ACCESS_TOKEN`, press **Create session**.
3. Ask something that requires reading files, for example *Which modules define the
   HTTP routes and the session persistence, and how do they relate?* Press **Run
   pipeline**. Expect 90–150 seconds.
4. **Pipeline stages** is the panel to show on camera. Each step is labelled by what
   executed it: *ADK model step* for the planner, executor and synthesiser, *Gemini CLI
   subprocess* for the tool call and its outcome, and *ADK deterministic step (no
   model)* for the verifier. This is where the separation between ADK planning and CLI
   execution is visible.
5. **What the ADK planning step decided** shows the task text the planner produced,
   before any process started.
6. **Actual process invocation** shows the resolved executable, the argv, the
   workspace, the exit code, the duration and the CLI's own session id. Note the argv:
   `--approval-mode plan -o json -m <model> -p <task>`. The task is redacted so a
   prompt never lands in a log, and `--yolo` is absent.
7. **Answer** states whether the result is grounded, lists the paths that were verified
   to exist, lists any the CLI named that do not, and carries the limitations through.

## Failure paths worth demonstrating

- No credential, or a wrong one: `401`.
- Another identity's session id: `404`, ownership is server-side.
- A lead-research session id on this route: `404`, sessions are namespaced per agent.
- A question under 10 characters, or an extra JSON field: `422`, before any subprocess.
- Unset `GEMINI_WORKSPACE`: `BLOCKED_GEMINI_WORKSPACE`.
- Point `GEMINI_WORKSPACE` at any directory inside this repository: refused, because an
  ancestor `.env` would be loaded by the CLI.
- Stop the CLI responding and the tool reports `FAILED`; the pipeline then presents no
  answer as verified rather than inventing one.

## Why this is genuinely ADK, and the tradeoffs

The pipeline is a `SequentialAgent` behind an `AgentTool`, and the stages are different
kinds of component on purpose. `cli_planner` is an `LlmAgent` with an empty tool list,
so it cannot touch the workspace. `cli_executor` is an `LlmAgent` whose only tool is a
function that spawns the pinned executable. `cli_grounding` is a plain `BaseAgent` that
runs no model, for the same reason Part A's ranker is: a model must not be the judge of
whether its own output is grounded. Tests assert the planner has no tools, that exactly
one stage owns the subprocess, and that the verifier is not an `LlmAgent`.

Tradeoffs worth stating. Template workflow agents are used rather than the newer
`Workflow` type because `Workflow` cannot yet be an `LlmAgent` sub-agent in pinned ADK
2.13.0; the deprecation warnings are left visible. Latency is dominated by the CLI
itself: 82 seconds of the 107-second request, and a 97-file workspace exceeded a
180-second budget where a 17-file one answered in 82, which is why the staged workspace
is deliberately narrow. Grounding checks path existence only, which catches invented
files — the observed failure mode — but not inaccurate statements about real files.

## Measured

`docs/evidence/b2-api-e2e.txt`: `POST inspect` returned 200 in 107s. CLI exit 0,
`duration_ms=82140`. Five paths verified present (`api/main.py`,
`packages/agent_core/config.py`, `packages/agent_core/auth.py`,
`scripts/cli-pipeline-smoke.py`, `scripts/lead-live-smoke.py`), one named path absent
(`local/sessions.db`), and the synthesiser dropped the claim that depended on it and
recorded why.
