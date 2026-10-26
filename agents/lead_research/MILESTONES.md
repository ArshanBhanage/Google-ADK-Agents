# Part A milestones

## A1 — BLOCKED (updated 2026-10-26T23:48Z, America/Los_Angeles)

Implemented: root_agent, intake/market/parallel-discovery/source-validation
architecture, deterministic evidence ranking stage, typed request and evidence
contracts, public-site adapter, and a reusable Runner path (`run.py`) that returns
a validated `LeadReport` plus an observable `ResearchTrace`.

Verified locally: ADK AgentLoader import, `make check` exit 0 (30 unit tests, Ruff,
mypy, TypeScript, secret scan, Vite build), actual public-page retrieval with
timestamp and digest. Ranking is covered by deterministic tests for domain
normalisation, dedup ordering, digest replacement, and discarding of unsupported
claims.

Blocker: the configured `GOOGLE_API_KEY` has no usable Google Search grounding
quota. `make probe-lead` observes `generation=OK` and
`google_search_grounding=429_RESOURCE_EXHAUSTED` on `gemini-3.6-flash`; the same
429 reproduces on `gemini-3.8-flash` and `gemini-3.1-flash-lite`, so it is an
account quota limit rather than a model choice. Evidence:
`../../docs/evidence/a1-provider-probe.txt` and `../../docs/evidence/a1-live-gate.txt`.

The live gate therefore reports 3 errors and 0 passes, after the configured
retry/backoff was exhausted. No lead result, grounded query or CSV is claimed.

Unblock by enabling paid-tier billing for this key's project (then rerun
`make probe-lead`) or by supplying credentials for another authorized real search
API. A1 cannot be marked PASSED, and A2 and Parts B–E stay untouched until it is.

## A2 — NOT_STARTED

Requires A1 to pass. Then implement the authenticated end-to-end API/UI, matching
CSV download, complete live walkthrough and search-suggestion display.
