# Part D walkthrough

## Prerequisites

A fine-grained PAT with read access to **Pull Requests** and **Contents** on the
repositories you authorize, in `agents/code_reviewer/.env` with the allowlist. Docker
running, if you want to exercise the sandbox. Then:

```sh
make preflight-review                          # tools and allowlist; no network call
make verify-review PR=google/adk-python#7801   # D1: retrieval, mapping, analysis
```

## Screen by screen

1. `make run-api` and `make run-web`, open the Vite URL, choose **D · Code review**.
2. Paste the `LOCAL_ACCESS_TOKEN`, press **Create session**.
3. Enter an allowlisted owner, repository and pull request number. Press **Review**.
4. **Pipeline stages** shows three steps and labels two of them *ADK deterministic step
   (no model)*. Only the middle one is a model. That is the claim to make on camera:
   retrieval, diff mapping, Ruff, the AST parser, the sandbox decision, deduplication
   and the verdict are all plain code.
5. The report shows the verdict, the commit, the summary, then **Verified findings**
   with rule codes and **Unverified findings** labelled as the reviewer's reading.
6. **Tool evidence on changed lines** shows how many diagnostics were suppressed as
   outside the diff. On the sample PR that is 31 of 35.
7. **Test execution** shows `tests_not_run`, its reason, and the full isolation record
   that would have applied.
8. **Post this review as a comment** shows the exact Markdown and its SHA-256. Nothing
   has been posted.

## Failure paths worth demonstrating

- No credential: `401`. Another identity's session: `404`. `pull_request: 0`: `422`.
- A repository outside the allowlist: `409 BLOCKED_REPOSITORY`, even though the token
  could read it.
- A post with a made-up approval token: `403 BLOCKED_NO_APPROVAL`.
- The real approval token with one line added to the body:
  **`403 BLOCKED_CONTENT_CHANGED`**.
- A matching approval while posting is disabled: `409 BLOCKED_COMMENT_DISABLED`.
- The sandbox refusals: `uv run pytest -m live tests/integration/test_sandbox_live.py -v`
  shows the container failing attempts to reach the network, become root and write to
  the project mount.

## Why this is ADK, and the tradeoffs

The pipeline is a `SequentialAgent` behind an `AgentTool` with one model stage between
two deterministic ones. The reasoner is given the admissible line ranges and the
diagnostics that ran, and can do nothing else: it has no tools and no network. The
assembler then discards comments outside the diff, deduplicates by path, line and
category, matches comments to diagnostics within two lines to decide verified versus
unverified, and refuses a blocking verdict that no high or critical finding supports.
Tests cover each of those rules, including that a model asking to block on style is
overruled.

Tradeoffs. Ruff `--isolated` means the project's deliberate rule choices are ignored,
which trades false positives for the guarantee that a pull request cannot silence its
own review. The two-line match window was chosen because diagnostics often land a line
off the construct a human would point at; too wide and unrelated issues merge, too
narrow and genuine matches look unverified. Only Python is analysed, and the report says
so rather than implying wider coverage. Executing a contributor's tests is refused, which
costs behavioural confidence and buys not running untrusted code.

## Measured

`docs/evidence/d2-api-e2e.txt`: `POST review` returned 200 in 17 s for
`google/adk-python#7801`, with 2 verified comments carrying `UP045` and `SIM117`, 4 tool
findings inside changed lines, 31 suppressed, `blocking=False`, and
`test_status=tests_not_run`. `docs/evidence/d2-sandbox-gate.txt`: 9 live isolation tests
passed. Nothing was posted to GitHub.
