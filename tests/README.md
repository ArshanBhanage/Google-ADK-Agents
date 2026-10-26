# Verification

`make test` exercises real local auth, schema validation, environment setup and
ADK SQLite persistence without provider mocks. Random credentials are generated
inside each test and never written to evidence. The API tests use the actual app
through Starlette's ASGI test client; database operations are real.

`npm --prefix web run test:e2e` uses Chromium and real API/web processes with blank
provider configuration. It captures the actual connection-error interface.

No live model/provider test or ADK evaluation transcript exists yet. Future live
tests will require real credentials and explicitly report absence as blocked/skipped.
