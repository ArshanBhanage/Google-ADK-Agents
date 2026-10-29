import google.auth
from google import genai
from google.adk.models.google_llm import Gemini
from google.genai import types

from .config import CommerceSettings


def vertex_client(settings: CommerceSettings) -> genai.Client:
    if not settings.google_cloud_project or not settings.google_cloud_location:
        raise ValueError("BLOCKED_VERTEX: configure project and location")
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return genai.Client(
        vertexai=True,
        project=settings.google_cloud_project,
        location=settings.google_cloud_location,
        credentials=credentials,
        http_options=types.HttpOptions(timeout=30000),
    )


def vertex_model(settings: CommerceSettings) -> Gemini:
    return Gemini(model=settings.gemini_model, client=vertex_client(settings))
