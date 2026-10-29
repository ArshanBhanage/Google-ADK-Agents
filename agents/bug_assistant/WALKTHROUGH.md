# Part C walkthrough

## Prerequisites

A fine-grained PAT with **read-only Issues** permission on the repositories you intend
to expose, in `agents/bug_assistant/.env` along with the allowlist. Vertex credentials
as for Part A. Then:

```sh
make preflight-bug   # transport, URL and allowlist; makes no network call
make verify-bug      # expect: VERIFIED, 6 tools, a real lookup
```

`make verify-bug` prints the handshake time, every tool the server advertised, which of
them were admitted, and the size of a real search response. If the token is absent it
exits 2 with `BLOCKED_GITHUB_TOKEN` rather than degrading to anything offline.

## Screen by screen

1. `make run-api` and `make run-web`, open the Vite URL, choose **C · MCP bug assistance**.
2. Paste the `LOCAL_ACCESS_TOKEN`, press **Create session**.
3. Enter an allowlisted owner and repository and describe the bug in at least 20
   characters. Press **Triage against live issues**; expect 40–90 seconds.
4. **Pipeline stages** labels each step by what ran it: *ADK model step* for triage and
   drafting, *MCP tool call* for each search and its outcome, and *ADK deterministic
   step (no model)* for the verifier.
5. **Triage** shows severity with its rationale, the root cause as an explicit
   hypothesis, verified duplicates as real links, reproduction steps, the debugging
   checklist, the next action, and the limitations.
6. **Click a duplicate link.** It opens the real issue. That is the claim worth
   checking: the number, title, URL and state are taken from the provider's response,
   not from the model, and a test proves the model's own values are overwritten.
7. **Draft issue** shows the exact content a write would create, its content SHA-256 and
   the approval expiry. Nothing has been filed at this point.

## Failure paths worth demonstrating

```sh
# no credential, and a description under 20 characters
# a forged write with a made-up approval token
```

- No credential: `401`. Another identity's session, or a session created for a different
  agent: `404`. Invalid input: `422`, before any MCP call.
- A write with no approval in the session: **`403 BLOCKED_NO_APPROVAL`**.
- A real approval token with the title edited by one word:
  **`403 BLOCKED_CONTENT_CHANGED`**. This is the most important demonstration in Part C.
- A matching approval while the write path is disabled:
  **`409 BLOCKED_WRITE_DISABLED`**, naming the setting to change.
- A repository outside the allowlist: `BLOCKED_REPOSITORY`, even if the description asks
  for it, because the allowlist is checked server-side and the description is data.

## Why this is genuinely MCP, and the tradeoffs

The tools are discovered through the protocol handshake. `READ_ONLY_TOOLS` in the code
is pinned by a test to exactly the six names a real handshake returned, so if GitHub
changes that toolset the test fails rather than the agent drifting silently. A write
marker appearing on the read-only endpoint aborts the connection instead of being
filtered quietly, because silently dropping an unexpected capability hides a change that
deserves attention.

Verification is deliberately not a model's job. `issue_verifier` is a plain `BaseAgent`
that discards any claimed issue number absent from the retrieved set and overwrites the
identity fields from the recorded response, keeping only the model's reasoning about why
an issue looks similar. The same decision as Part A's ranker and Part B's grounding step.

Tradeoffs. Issue bodies arrive with a lot of API noise, so the model sees a bounded
1200-character excerpt per issue while the full record stays in session state for
verification; that caps cost but means long issues are judged on their opening. Searches
are capped at six per session and ten results per search. Template workflow agents are
used because `Workflow` cannot yet be an `LlmAgent` sub-agent in pinned ADK 2.13.0.

## Measured

`docs/evidence/c2-api-e2e.txt`: `POST triage` returned 200 in 56 s over three real MCP
search calls, searched 14 issues, and verified one duplicate,
`google/adk-python#7800`, confirmed independently with `gh issue view` as OPEN with the
same title and URL. `GITHUB_WRITE_ENABLED=false` throughout, and no issue was created in
any repository.
