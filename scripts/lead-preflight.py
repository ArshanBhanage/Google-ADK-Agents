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

PROBE = "Reply with the single word ok."
REQUIRED = ("GOOGLE_API_KEY", "GEMINI_MODEL")
TRANSIENT = (500, 502, 503, 504)


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
    values = {
        "GOOGLE_API_KEY": settings.google_api_key.get_secret_value(),
        "GEMINI_MODEL": settings.gemini_model,
    }
    missing = [name for name in REQUIRED if not values[name]]
    if missing:
        print(f"BLOCKED: set {', '.join(missing)} in root .env; never paste secrets in chat.")
        return 2
    if not live:
        print("CONFIGURED_NOT_VERIFIED: run `make probe-lead` to test the provider itself.")
        return 0

    model = values["GEMINI_MODEL"]
    client = genai.Client(api_key=values["GOOGLE_API_KEY"])
    generation = capability(client, model, grounded=False)
    grounding = capability(client, model, grounded=True)
    print(f"model={model} generation={generation} google_search_grounding={grounding}")
    if generation != "OK":
        print(f"BLOCKED: {model} rejected a minimal request ({generation}).")
        return 2
    if grounding != "OK":
        print(
            f"BLOCKED_SEARCH_GROUNDING: google_search returned {grounding} while plain "
            "generation succeeded, so this key has no usable Google Search grounding quota.\n"
            "Lead discovery requires live search and will not be faked. To unblock, either\n"
            "  1. enable paid-tier billing for this API key's project, then check usage at\n"
            "     https://ai.dev/rate-limit and rerun this command, or\n"
            "  2. supply credentials for another authorized real search API.\n"
            "Nothing downstream of discovery can be verified until one of these is done."
        )
        return 2
    print("VERIFIED: generation and Google Search grounding both answered this key.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(live="--live" in sys.argv[1:]))
