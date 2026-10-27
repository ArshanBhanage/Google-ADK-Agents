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
and /private/tmp/node-v24.22.1-darwin-arm64. Local .venv and web/node_modules are ignored symlinks into temporary storage
to avoid syncing generated dependencies through iCloud Documents. These are temporary; a normal clean
checkout uses installed runtimes. Python .venv can be recreated with `uv sync`.

GCloud and Gemini CLI installation are deferred to their phases. Shopify and a
billing-enabled AlloyDB project are required for E; no chargeable resources have
been created. The course deadline timezone still needs confirmation in Canvas.

## Vertex AI backend setup

The repository defaults to `GOOGLE_GENAI_USE_VERTEXAI=TRUE`. Vertex AI bills the
Cloud project, so Google Cloud Free Trial credits apply to it; Gemini Developer API
usage from an AI Studio key bills a separate pipeline those credits do not cover.
See `technical-decisions.md` for the evidence behind that choice.

Vertex AI authenticates with application default credentials, so no key material is
stored in this repository.

```sh
brew install --cask google-cloud-sdk
# The Homebrew cask does not put gcloud on PATH by default:
export PATH=/opt/homebrew/share/google-cloud-sdk/bin:"$PATH"   # add to ~/.zshrc

gcloud auth login                                  # interactive, opens a browser
gcloud projects list                               # choose the project on the
                                                   # Free Trial billing account
gcloud config set project <PROJECT_ID>
gcloud services enable aiplatform.googleapis.com
gcloud auth application-default login              # interactive; what libraries read
```

Then set `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` in the local root `.env`
and run `make probe-lead`. The probe makes two real calls and prints the backend,
project, location, plain-generation result and grounding result. A populated `.env`
is never treated as a passing gate.

Cost control: keep the project on the **Free Trial** billing account and do not
accept any prompt to activate a full paid account. Google stops the trial account
when the credit or the 90 days run out, which bounds spend; a budget alert only
notifies and does not cap. Model availability on Vertex AI is per-region, so rerun
`make probe-lead` after changing `GOOGLE_CLOUD_LOCATION`.
