# Part A walkthrough — current A1 checkpoint

1. Install repository runtime versions, run `make setup` and `make check`.
2. Open root `.env` locally. Set GOOGLE_API_KEY and GEMINI_MODEL; do not commit it.
3. Run `make preflight-lead` (configuration) and then `make probe-lead`, which makes
   two real calls and prints `generation=` and `google_search_grounding=`. Exit 2
   means BLOCKED; a populated `.env` is not a PASS.
4. Run `make run-adk`. Open 127.0.0.1:8001 and select lead_research.
5. Enter an industry, region, buyer profile and quantity, such as “Find 3 industrial
   robotics companies in California selling to small manufacturers.” Confirm the
   proposed criteria only if accurate.
6. Inspect ADK events for market_research, primary_discovery, secondary_discovery,
   source_validator and inspect_public_source. Show only tool calls, grounded
   summaries and evidence; never hidden reasoning or secret values.
7. Check that every purported company fact links to a real public source. Inspect
   the actual session's source_evidence timestamps/digests and any UNVERIFIED
   failures. Empty results are valid; invented results are not.
8. Do not mark A1 passed until actual model/search behavior is recorded and remaining
   ranking/report validation is implemented. Do not start A2 before that gate.

## Why this is ADK, and what the pipeline shape costs

The intake agent is an `LlmAgent` whose only tool is an `AgentTool` wrapping a
`SequentialAgent`. That boundary exists for a documented ADK constraint: a built-in
tool such as `google_search` cannot be combined with other tools on the same agent,
so each search specialist carries `google_search` alone and the fetch tool lives on
a separate validator agent. Discovery is a `ParallelAgent` because the two evidence
angles share no state; the tradeoff is that it doubles the instantaneous request
rate, which is what first exposed the free-tier rate limit. Template workflow agents
are used rather than the newer `Workflow` type because `Workflow` cannot yet be an
`LlmAgent` sub-agent in pinned ADK 2.13.0; the deprecation warnings are left visible
instead of being filtered.

Qualification deliberately sits outside the model. `EvidenceRanker` is a plain
`BaseAgent` that reads `candidate_report` and `source_evidence` from session state,
so a model cannot promote its own claim to verified, assert a content digest, or
decide the ordering. A test asserts the stage is not an `LlmAgent`.

## Observed status

Installed ADK loads the agent, a real public-page fetch succeeded, and `make check`
exits 0 with 30 unit tests including ranking, dedup and URL-security cases.

Provider credentials are now configured, and the gate was retested rather than
deferred. `make probe-lead` reports `generation=OK` with
`google_search_grounding=429_RESOURCE_EXHAUSTED`, so the key has no usable Google
Search grounding quota; the live gate consequently records 3 errors and 0 passes in
176 seconds after retries. Reproducible evidence:
`../../docs/evidence/a1-provider-probe.txt` and `../../docs/evidence/a1-live-gate.txt`.

No live company list, grounded response, CSV or evaluation transcript is supplied,
because none has been produced. The shared React results screen and CSV belong to
A2 and cannot be demonstrated yet. Unblock with paid-tier billing on the key's
project or credentials for another authorized real search API.

## A2 — the authenticated application

Prerequisites: `gcloud auth application-default login` completed, `GOOGLE_CLOUD_PROJECT`
set in the local root `.env`, `GOOGLE_CLOUD_LOCATION=global`, a `LOCAL_ACCESS_TOKEN`
of at least 32 characters, and `make probe-lead` printing `VERIFIED`.

1. `make run-api` in one terminal, `make run-web` in another. Open the Vite URL.
2. Choose **Deep research lead generation**. The readiness panel lists any unset
   variable by name and never shows a value.
3. Paste the `LOCAL_ACCESS_TOKEN` and press **Create session**. The session is
   persisted in the real ADK `DatabaseSessionService` and owned by your identity.
4. Fill industry, region, buyer profile and quantity. Press **Review criteria**, read
   the restated criteria, then **Confirm and run live search**. The confirmation step
   exists because each run issues real billable search queries; expect 60–120 seconds.
5. Inspect the result. Each lead shows its score, confidence, the normalised domain,
   the match explanation, and for every citation the quoted excerpt, the source link,
   the retrieval timestamp and the SHA-256 of the response body. Open a citation link
   and search the page for the quoted sentence: it is there, because a quote that the
   fetched page does not contain is discarded before display.
6. Read **Limitations**. It names candidates that could not be verified and why
   (cross-origin redirect, robots crawl-delay, per-session retrieval budget), and how
   many were discarded. An empty lead list with populated limitations is a correct
   outcome, not a failure.
7. Read **Google Search suggestions**, displayed as the grounding API returned them.
   Showing these is required by Google's grounding terms.
8. Read **Observed trace**: the model version, billable search count, token usage, the
   search queries actually issued, each retrieval outcome, and the pages hashed.
9. Press **Download CSV**. Open it and compare against the cards on screen. The file
   is generated from the report persisted in session state, so the values match by
   construction; `docs/evidence/a2-api-e2e.txt` records that assertion passing row for
   row against a real run.

### Failure paths worth demonstrating

- Omit the credential, or use a wrong one: every agent route answers `401`.
- Use another identity's session identifier: `404`, because ownership is derived
  server-side and never taken from the request.
- Request the CSV before running research: `409`, not an empty file.
- Send `quantity: 0` or omit `industry`: `422` before any billable call.
- If grounding is unavailable the route answers `503` carrying
  `BLOCKED_PROVIDER_QUOTA`, so an outage cannot be mistaken for an empty result.

### Measured, from a real run through the API

`POST research` returned `200` in 95 seconds: 2 verified leads, 15 billable search
queries, 4 pages retrieved and hashed, 3 search-suggestion blocks, and 54,348 prompt
/ 4,626 output / 6,371 thinking tokens. Search queries dominate the cost, not tokens.
Evidence: `../../docs/evidence/a2-api-e2e.txt`.
