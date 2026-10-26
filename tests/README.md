# Verification

`make test` exercises real local auth, schema validation, environment setup and
ADK SQLite persistence without provider mocks. Random credentials are generated
inside each test and never written to evidence. The API tests use the actual app
through Starlette's ASGI test client; database operations are real.

`npm --prefix web run test:e2e` uses Chromium and real API/web processes with blank
provider configuration. It captures the actual connection-error interface.

## Live tests

`tests/integration/test_lead_live.py` carries the `live` marker and is excluded
from `make test`. Run it with `make integration-lead`, which first runs
`make probe-lead` so a quota or entitlement problem is named before any assertion
runs. It calls the real ADK `Runner` over the real pipeline and asserts three
things: that grounding metadata was actually observed, that every lead surviving
qualification cites a URL present in the session's retrieved evidence, and that
the report is deduplicated and ordered.

Absence is reported honestly and never as a pass. Unset credentials produce
`SKIPPED (credentials missing)`. A provider that is reachable but refuses the
capability raises `ProviderBlocked`, which the fixture converts into an explicit
failure carrying the unblock instructions.

Current outcome: 3 errors, 0 passed. The configured key answers plain generation
but returns 429 for `google_search`. See `docs/evidence/a1-live-gate.txt`.

No ADK evaluation transcript exists yet; one requires a real reviewed session,
which cannot happen while discovery is blocked.
