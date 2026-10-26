# Technical decisions

Verified 2026-10-26, America/Los_Angeles. See `uv.lock` and `web/package-lock.json`
for exact direct/transitive resolutions. No tutorial source code was copied.

- Retain the existing Git repository and its `main` branch. Publication is gate G.
- Python 3.12.14, uv 0.12.10, ADK 2.13.0 with the `db` extra. The initial plain
  ADK installation could not import DatabaseSessionService; the installed error
  explicitly required `google-adk[db]`. The extra resolved that failure.
- Node 24.22.1 LTS instead of the host's EOL Node 25.2.1. The official tarball's
  SHA-256 was checked against nodejs.org SHASUMS256.txt before extraction.
- FastAPI 0.162.0; Pydantic Settings 2.16.1; pytest 9.1.1; Ruff 0.17.2;
  mypy 2.4.0. Frontend uses React, TypeScript and Vite with exact npm pins.
- Actual ADK DatabaseSessionService with SQLite for persistent *local sessions*.
  This is not the commerce database. Cloud sessions require a durable shared
  database; commerce requires PostgreSQL/AlloyDB and its own verification gate.
- Sessions use server-derived subjects. Local bearer mode is single-user,
  loopback development only; Google mode validates signed ID tokens and an
  explicit subject allowlist. Google verification is implemented but not live-tested.
- No agent module is manufactured in milestone 0. Agent pages honestly show
  NOT_STARTED. Session creation proves storage/auth, not agent execution.
- Installed ADK 2.13.0 exposes Runner.run_async, Agent, SequentialAgent and
  ParallelAgent. Workflow templates emit deprecation warnings recommending
  Workflow, with an explicit limitation that Workflow cannot yet be an LlmAgent
  sub-agent. Choose supported composition when implementing A, document any
  compatibility use, and do not claim old tutorial APIs are current defaults.
- Google Search documentation isolates search in its own tool-only agent and
  requires displaying returned search suggestions. Grounding evidence and search
  suggestion rendering are required in A; not verified by foundation tests.
- Official MCP Toolbox URL redirects from `googleapis/genai-toolbox` to
  `googleapis/mcp-toolbox`. Verify its version/protocol in E before installation.
- Shopify's current Storefront reference displays 2026-10. Confirm exact operations
  and token scopes again in E; no merchant access or Shopify integration is claimed.
- No service keys were found in relevant environment variables. Actual local .env
  files have blank secrets and mode 0600. Setup does not overwrite existing values.
- Docker Desktop was initially stopped; starting the installed app restored its
  daemon. GCloud and Gemini CLI are absent and deferred to their gated phases.
- GitHub auth succeeds outside the execution sandbox; the initial sandbox check
  misleadingly reported invalid authentication. No remote is configured yet.

References: [ADK](https://adk.dev/),
[sessions](https://adk.dev/sessions/session/),
[Google Search](https://adk.dev/integrations/google-search/),
[package metadata](https://pypi.org/project/google-adk/),
[Node release policy](https://nodejs.org/en/about/previous-releases).
