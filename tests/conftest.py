import pytest

# pydantic-settings reads os.environ even when _env_file is None, so a provider
# variable exported in the developer's shell would silently satisfy a Settings object
# that a test meant to leave unconfigured. Readiness and fail-closed assertions would
# then pass or fail depending on the shell rather than the code. Tests that need real
# credentials read them from the local .env file, which this does not touch.
AMBIENT = (
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_GENAI_USE_ENTERPRISE",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "LOCAL_ACCESS_TOKEN",
    "AUTH_MODE",
    "SESSION_DATABASE_URL",
)


@pytest.fixture(autouse=True)
def hermetic_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in AMBIENT:
        monkeypatch.delenv(name, raising=False)
