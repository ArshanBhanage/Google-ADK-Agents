# Setup and current blockers

Install the versions in `.python-version` and `.node-version`, and uv 0.12.10.
Run `make setup`; it installs locked dependencies and creates private, ignored
.env files without overwriting user edits. Run `make check`, then `make run-api`
and `make run-web` in separate terminals. Open http://127.0.0.1:5173.

For session tests through the browser, generate a private access token locally
(e.g. `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`), paste it into
root `.env` as LOCAL_ACCESS_TOKEN, restart the API, then enter it in the UI.
This is a local single-user credential, not a substitute for deployed user login.
Do not paste any keys in chat.

For upcoming Part A, obtain a Gemini Developer API key from Google AI Studio and
set GOOGLE_API_KEY plus GEMINI_MODEL in root `.env`. The selected model must be
available to the project and support Google Search grounding. No key is needed
for foundation tests. Key presence alone never passes a live gate.

Google login mode requires AUTH_MODE=google, GOOGLE_CLIENT_ID, and
ALLOWED_GOOGLE_SUBJECTS. Use an ID token obtained for that OAuth audience.
Server verification is implemented; a browser Google sign-in flow and live
identity verification are not yet delivered.

Developer browser check:

```sh
cd web
npx playwright install chromium
npm run test:e2e
```

The browser check uses the actual API and blank configuration, with no provider
mocks. It launches its own servers; stop existing servers on ports 8000/5173 first.
For this execution only, runtime installations are under /private/tmp/adk-python
and /private/tmp/node-v24.22.1-darwin-arm64. These are temporary; a normal clean
checkout uses installed runtimes. Python .venv can be recreated with `uv sync`.

GCloud and Gemini CLI installation are deferred to their phases. Shopify and a
billing-enabled AlloyDB project are required for E; no chargeable resources have
been created. The course deadline timezone still needs confirmation in Canvas.
