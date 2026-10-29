# Part C milestones

## C1 — PASSED 2026-10-29T05:07Z (America/Los_Angeles)

ADK `McpToolset` over Streamable HTTP to the official remote GitHub MCP server, using
the issues toolset on its `/readonly` path. Scope enforced three times: URL path check
before connecting, `X-MCP-Readonly: true`, and filtering advertised tools against an
allowlist with any write marker aborting the connection.

Repository targets are admitted only through `GITHUB_ALLOWED_REPOSITORIES`, because
owner and repo can originate from a model or from issue text. An empty allowlist blocks
everything rather than defaulting open.

- `make preflight-bug` unconfigured: exit 2, `BLOCKED_GITHUB_TOKEN`.
- `make verify-bug`: `handshake_ms=1891`, 6 tools advertised and 6 admitted
  (`get_label`, `issue_read`, `list_issue_fields`, `list_issue_types`, `list_issues`,
  `search_issues`), no write tool present, then a real `search_issues` lookup in
  1220 ms returning 10,465 characters.
  Evidence: `../../docs/evidence/c1-mcp-gate.txt`.
- 27 unit tests. `McpToolset` is used rather than the deprecated `MCPToolset` alias.
- Added `google-adk[mcp]`; the `mcp` package was absent.

## C2 — PASSED 2026-10-29T06:03Z (America/Los_Angeles)

`SequentialAgent` of `issue_triage` (LlmAgent, one MCP-backed tool), `issue_verifier`
(plain BaseAgent, no model) and `issue_drafter`, behind an `AgentTool`. Two
authenticated API routes and a UI panel with the stage timeline, verified duplicates as
real links, and the draft with its content digest.

Credentials were moved into `agents/bug_assistant/.env` via a component-scoped
`BugSettings` reading root then component. The deliverable contract puts
component-specific credentials in the component's own file, and the shared root
`Settings` should never have owned a GitHub token.

Write path gated four ways: its own opt-in, its own token, its own non-`/readonly`
endpoint on GitHub's host, and a single-use approval grant bound to the SHA-256 of the
exact previewed content plus the repository and the user.

- 40 further unit tests, 67 for Part C, 190 across the repository.
- `make verify-triage`: `mcp_actually_used=True`, 12 issues searched, `severity=high`,
  one verified duplicate. Evidence: `../../docs/evidence/c2-triage-gate.txt`.
- End-to-end through the API, `../../docs/evidence/c2-api-e2e.txt`:
  - no credential `401`; a 5-character description `422`.
  - a forged write with no approval: **`403 BLOCKED_NO_APPROVAL`**.
  - `POST triage` `200` in 56 s over three real MCP search calls, 14 issues searched,
    one verified duplicate `google/adk-python#7800`.
  - a real approval token with the title edited: **`403 BLOCKED_CONTENT_CHANGED`**.
  - a matching approval while writes are disabled: **`409 BLOCKED_WRITE_DISABLED`**.
- `google/adk-python#7800` independently confirmed with `gh issue view` as OPEN with the
  same title and URL.

Bug found by the live run and fixed: `verify_triage` computed its limitations and then
discarded them, so reports presented a root-cause hypothesis without ever labelling it
unconfirmed. Regression test added.

No issue has been created in any repository. `GITHUB_WRITE_ENABLED` is false, and the
optional write proof is left for an explicit decision rather than manufacturing evidence
with a spam ticket.
