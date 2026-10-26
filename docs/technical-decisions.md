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

## A1 implementation checkpoint

The installed GoogleSearchTool accepts Gemini model identifiers generally, while
one ADK docs paragraph still says Gemini 2 only. Keep search isolated, choose a
current model from https://ai.google.dev/gemini-api/docs/models, and require a
real grounding run before claiming compatibility. The load-time default is
`gemini-3.8-flash`, but execution fails closed until GEMINI_MODEL is explicitly set.

For intake-controlled AgentTool composition, use pinned supported template agents;
the installed deprecation warning documents that Workflow cannot yet be an
LlmAgent sub-agent. The graph alternative is not silently assumed compatible.
No hidden chain-of-thought is exposed. Future A2 must enforce final citations,
rank deterministically and render Google search suggestions before completion.

## A1 provider findings, 2026-10-26T23:48Z

Measured against the user's own Gemini Developer API key, not inferred from docs.

- Model availability is per-key. `gemini-2.5-flash` and `gemini-2.5-pro` return
  `404` with "no longer available to new users" and a pointer to `gemini-3.8-flash`.
  The configured `gemini-3.6-flash` is valid for this key. Enumerate the key's own
  entitlement from the `models` endpoint rather than hardcoding a model name; the
  load-time default stays `gemini-3.8-flash` and execution fails closed unless
  `GEMINI_MODEL` is set explicitly.
- Grounding entitlement is separate from model entitlement. Plain `generateContent`
  succeeds while the identical request with the built-in `google_search` tool returns
  `429 RESOURCE_EXHAUSTED`. Reproduced on `gemini-3.6-flash`, `gemini-3.8-flash` and
  `gemini-3.1-flash-lite`, which rules out a model-specific cause. Readiness checks
  must therefore probe the capability, not just the presence of a key, which is why
  `scripts/lead-preflight.py` has a `--live` mode and why the configuration-only
  mode reports `CONFIGURED_NOT_VERIFIED` rather than a pass.
- Transient `503 UNAVAILABLE` on plain calls is common enough to matter. Each agent
  gets its own `Gemini` model instance carrying
  `types.HttpRetryOptions(attempts=6, initial_delay=5, exp_base=2, max_delay=90,
  jitter=1, http_status_codes=[429, 500, 502, 503, 504])`. This is the documented
  genai client retry surface, used in preference to a hand-rolled loop. A 429 that
  outlives the backoff is raised as `ProviderBlocked`, never degraded into a
  partial or substituted result.
- Parallel discovery doubles the instantaneous request rate, which is what first
  surfaced the rate limit. The shape is kept because the two evidence angles are
  genuinely independent, and the cost is documented rather than hidden by
  serialising the pipeline.
- Qualification was moved out of the model into `EvidenceRanker`, a plain
  `BaseAgent`. Citations are only accepted when the excerpt appears verbatim in the
  page actually retrieved for that URL and the page names the company; digests and
  timestamps are overwritten with observed values so a model cannot assert them.
