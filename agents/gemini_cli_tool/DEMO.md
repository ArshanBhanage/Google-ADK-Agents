# Part B recording runbook (5–8 minutes)

## Before recording

```sh
nvm use 24.22.1
make setup-gemini-cli           # shows 0.65.0
./scripts/stage-cli-workspace   # copy the path into GEMINI_WORKSPACE in root .env
make preflight-cli              # version, backend, workspace
```

Have `make run-api` and `make run-web` running in two terminals. Close anything showing
secrets; the readiness panel only ever prints variable names.

## 0:00–0:45 · The claim

State what is being proved: an ADK pipeline plans a task, a **separate real program**
inspects files, and a deterministic step checks the result. Show
`infra/gemini-cli/package.json` pinning `@google/gemini-cli` 0.65.0 and run
`infra/gemini-cli/node_modules/.bin/gemini --version` on camera.

## 0:45–1:45 · One real invocation, no ADK

Run `make verify-cli`. Point out `gemini_cli_version=0.65.0`, `backend=vertex_ai`,
`exit=0`. This establishes the executable works before any agent is involved.

## 1:45–4:00 · The pipeline in the UI

Choose **B · Gemini CLI pipeline**, create a session, ask *Which modules define the
HTTP routes and the session persistence, and how do they relate?* and run it.

While it runs, explain the four stages. When it returns, spend most of the time on
**Pipeline stages**: the planner, executor and synthesiser are labelled *ADK model
step*, the tool call and its outcome are labelled *Gemini CLI subprocess*, and the
verifier is labelled *ADK deterministic step (no model)*.

## 4:00–5:00 · The process metadata (30–60 seconds of real trace)

Open **Actual process invocation**. Read out the executable path, the argv
`--approval-mode plan -o json -m <model> -p <task>`, the workspace, exit code,
duration and the CLI's own session id. Say explicitly that the task is redacted to
`<task>` so prompts never reach logs, and that `--yolo` is never passed.

## 5:00–6:15 · Verification and honesty

Show the verified paths and open one in an editor to prove it exists. Then show a path
the CLI named that does not exist, and the limitation saying the dependent claim was
dropped. This is the most persuasive part: the system contradicts its own model.

## 6:15–7:15 · Security boundaries

Demonstrate two refusals live:

```sh
# a question that is too short, and an unexpected field, both 422 before any subprocess
# then set GEMINI_WORKSPACE to a directory inside this repository and run make verify-cli
```

Explain the finding behind that refusal: the CLI loads a project `.env` from the
working directory and every ancestor, so a key above the workspace overrides the
credentials passed to the child. Show the test that proves injection text stays a
single argv element.

## 7:15–8:00 · Tests and limits

Run `uv run pytest tests/unit/test_gemini_cli.py tests/unit/test_cli_pipeline.py -q`
and show 56 passing. Close by stating the real limitation: path existence is verified,
statement accuracy is not, and nothing here is cloud-deployed.

## Do not

Do not show `.env`, a token, or the Cloud project billing page. Do not claim a
deployment. Do not re-record over a failed run and present it as first-pass success.

YouTube video URL:
