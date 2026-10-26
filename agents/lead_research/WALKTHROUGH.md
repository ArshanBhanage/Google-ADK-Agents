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
