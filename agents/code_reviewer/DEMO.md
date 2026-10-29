# Part D recording runbook (5–8 minutes)

## Before recording

```sh
make preflight-review
make verify-review PR=google/adk-python#7801
docker info >/dev/null && echo "sandbox available"
```

Keep `REVIEW_COMMENT_ENABLED=false` unless you have decided to post a real comment, and
only ever to a pull request in a repository you own.

## 0:00–0:45 · The claim

One model stage, two deterministic ones. Open `agents/code_reviewer/agent.py` and point
at `ReviewAnalysis` and `ReviewAssembler` being `BaseAgent`, not `LlmAgent`.

## 0:45–2:00 · Deterministic analysis first

Run `make verify-review PR=google/adk-python#7801`. Read out the head commit, the hunk
ranges, the tool versions, and that 31 of 35 findings were suppressed for falling
outside the changed lines.

## 2:00–4:00 · The pipeline in the UI

Choose **D · Code review**, create a session, review `google/adk-python` `7801`. Walk
the stage list, then the verdict, then **Verified** versus **Unverified** findings.
Stress that a verified finding carries the rule code of a tool that actually ran.

## 4:00–5:00 · The sandbox is real (the strongest segment)

```sh
uv run pytest -m live tests/integration/test_sandbox_live.py -v
```

Nine tests. Point at the three that matter: the container cannot reach the internet,
cannot run as root, and cannot write to the project mount — each asserted by code
*inside* the container trying and failing. Then show the UI's isolation record and say
that executing a contributor's tests is refused by policy, which is why the status is
`tests_not_run`.

## 5:00–6:15 · Refusing to comment

Show the comment panel and its SHA-256. Then from a terminal:

- a post with a made-up token → `403 BLOCKED_NO_APPROVAL`
- the real token with one line added to the body → `403 BLOCKED_CONTENT_CHANGED`
- the matching approval while posting is disabled → `409 BLOCKED_COMMENT_DISABLED`

`docs/evidence/d2-api-e2e.txt` records all three.

## 6:15–7:00 · Optional: post one real comment

Only against a pull request in your own repository. Set `REVIEW_COMMENT_ENABLED=true`
and a `REVIEW_COMMENT_TOKEN` scoped to write Pull Requests there, approve in the UI, and
open the returned comment URL. Say that the id and URL come from GitHub. Then disable it
again on camera.

## 7:00–8:00 · Tests and limits

```sh
uv run pytest tests/unit/test_review_diff.py tests/unit/test_review_report.py -q
```

87 passing. Close on the real limitations: only Python is analysed, no pull request's
tests have been executed, Ruff `--isolated` ignores the project's own rule choices, and
nothing here is cloud-deployed.

## Do not

Do not show either token or the `.env` files. Do not post comments on strangers' pull
requests. Do not claim the review executed tests.

YouTube video URL:
