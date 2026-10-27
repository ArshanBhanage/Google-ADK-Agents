"""Check lead-research provider dependencies.

Default mode validates configuration only. `--live` additionally probes the two
capabilities the pipeline actually needs, so a gate is never recorded as passing
on the strength of a populated .env file.
"""

import sys
import time

from google import genai
from google.genai import errors, types

from packages.agent_core.config import Settings
from packages.agent_core.provider import Backend, ProviderUnavailable, resolve_backend

PROBE = "Reply with the single word ok."
TRANSIENT = (500, 502, 503, 504)


def build_client(backend: Backend) -> genai.Client:
    if backend.uses_vertex:
        # Authenticates with application default credentials, so usage bills the
        # Cloud project where Free Trial credits apply.
        return genai.Client(vertexai=True, project=backend.project, location=backend.location)
    return genai.Client(api_key=Settings().google_api_key.get_secret_value())


def capability(client: genai.Client, model: str, *, grounded: bool) -> str:
    tools = [types.Tool(google_search=types.GoogleSearch())] if grounded else None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=PROBE,
                config=types.GenerateContentConfig(tools=tools, max_output_tokens=64),
            )
        except errors.APIError as exc:
            if exc.code in TRANSIENT and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            return f"{exc.code}_{getattr(exc, 'status', 'ERROR')}"
        return "OK" if response.candidates else "EMPTY_RESPONSE"
    return "UNREACHABLE"


def main(live: bool) -> int:
    settings = Settings()
    missing = settings.provider_missing()
    if missing:
        print(f"BLOCKED: set {', '.join(missing)} in root .env; never paste secrets in chat.")
        return 2
    try:
        backend = resolve_backend(settings)
    except ProviderUnavailable as exc:
        print(str(exc))
        return 2
    if not live:
        print(f"CONFIGURED_NOT_VERIFIED: {backend.describe()}; run `make probe-lead` to test it.")
        return 0

    client = build_client(backend)
    generation = capability(client, backend.model, grounded=False)
    grounding = capability(client, backend.model, grounded=True)
    print(f"{backend.describe()} generation={generation} google_search_grounding={grounding}")
    if generation != "OK":
        print(f"BLOCKED: {backend.model} rejected a minimal request ({generation}).")
        return 2
    if grounding != "OK":
        print(
            f"BLOCKED_SEARCH_GROUNDING: google_search returned {grounding} while plain "
            "generation succeeded, so this backend has no usable Google Search grounding.\n"
            "Lead discovery requires live search and will not be faked. To unblock:\n"
            "  - On gemini_api: the Developer API free tier does not offer grounding at all,\n"
            "    and Cloud Free Trial credits do not cover AI Studio usage. Prefer Vertex AI.\n"
            "  - On vertex_ai: confirm aiplatform.googleapis.com is enabled, that the project\n"
            "    is linked to a billing account, and that the model exists in this location.\n"
            "  - Or supply credentials for another authorized real search API."
        )
        return 2
    print("VERIFIED: generation and Google Search grounding both answered this backend.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(live="--live" in sys.argv[1:]))
