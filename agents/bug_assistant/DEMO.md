# Part C recording runbook (5–8 minutes)

## Before recording

```sh
make preflight-bug   # transport, URL, allowlist
make verify-bug      # VERIFIED, 6 tools, real lookup
```

Have `make run-api` and `make run-web` running. Keep `GITHUB_WRITE_ENABLED=false` unless
you have decided to film a real issue being filed.

## 0:00–0:45 · The claim

State it plainly: this is a real MCP connection, not a REST call named MCP. Run
`make verify-bug` on camera and read out the handshake time and the six tool names the
**server** advertised.

## 0:45–1:30 · The scope is a boundary, not a hope

Show `agents/bug_assistant/mcp.py`. Point out the three enforcement layers and say why:
the `/readonly` URL check, the `X-MCP-Readonly` header, and the write-marker abort. Then
temporarily set `GITHUB_MCP_URL` to the default `https://api.githubcopilot.com/mcp/` and
rerun — it refuses with `BLOCKED_WRITE_CAPABLE_URL`. Put it back.

## 1:30–4:00 · A real triage

Choose **C · MCP bug assistance**, create a session, enter an allowlisted repository and
a real defect description. Run it. While it works, explain the three stage kinds.

When it returns, go to **Pipeline stages** and point at the MCP tool calls. Then read
the severity rationale and the root cause, stressing the word hypothesis.

## 4:00–5:00 · The duplicate is real (the key moment)

Click the verified duplicate link. The real GitHub issue opens. Say that the number,
title, URL and state came from the provider's response and that the model's own values
are overwritten by the deterministic verifier — then show
`tests/unit/test_bug_verify.py::test_identity_fields_come_from_the_provider_not_the_model`,
which feeds deliberately wrong values and asserts all four are replaced.

## 5:00–6:30 · Refusing to write (the most persuasive part)

Show the **Draft issue** panel and its content SHA-256. Explain that approval is bound
to that digest. Then demonstrate, from a terminal:

- a write with a made-up approval token → `403 BLOCKED_NO_APPROVAL`
- the **real** approval token with one word changed in the title →
  `403 BLOCKED_CONTENT_CHANGED`
- the matching approval while writes are disabled → `409 BLOCKED_WRITE_DISABLED`

`docs/evidence/c2-api-e2e.txt` has all three recorded if you would rather read them out.

## 6:30–7:30 · Optional: file one real issue

Only if you have decided to. Set `GITHUB_WRITE_ENABLED=true` and add a second PAT with
write access to Issues on **one** repository you own. Approve the draft in the UI, and
show the returned issue number and URL opening on GitHub. Say that the number and URL
come from GitHub, not from the agent.

Then set `GITHUB_WRITE_ENABLED=false` again on camera.

## 7:30–8:00 · Tests and limits

Run `uv run pytest tests/unit/test_bug_mcp.py tests/unit/test_bug_writes.py
tests/unit/test_bug_verify.py tests/unit/test_bug_api.py -q` and show 67 passing. Close
with the honest limitation: the root cause is a hypothesis, not a diagnosis confirmed by
running the code.

## Do not

Do not show either PAT, the `.env` files, or the token field's contents. Do not file
issues into a repository you do not own. Do not create throwaway issues to make the UI
look busy.

YouTube video URL:
