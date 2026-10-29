from collections.abc import Callable
from typing import Any

from google.adk.agents import Agent
from google.adk.agents.context import Context
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.google_llm import Gemini
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.genai import types

from .config import CommerceSettings
from .mcp_client import CATALOG_TOOLS, toolbox_headers
from .prompts import CATALOG_INSTRUCTION


def build_agent(settings: CommerceSettings | None = None, subject: str | None = None) -> Agent:
    config = settings or CommerceSettings()
    tools: list[Callable[..., Any] | BaseTool | BaseToolset] = []
    if config.toolbox_url:

        async def headers(context: ReadonlyContext) -> dict[str, str]:
            return await toolbox_headers(config)

        tools.append(
            McpToolset(
                connection_params=StreamableHTTPConnectionParams(
                    url=config.toolbox_url,
                    timeout=15,
                    sse_read_timeout=30,
                ),
                tool_filter=sorted(CATALOG_TOOLS),
                header_provider=headers,
            )
        )
    if subject:
        from .commerce import Commerce

        commerce = Commerce(config)

        async def view_cart() -> dict[str, Any]:
            """Read only the authenticated user's cart. No changes or checkout authorization."""
            return await commerce.view(subject)

        async def get_live_availability(variant_id: str) -> dict[str, Any]:
            """Read live Shopify availability for a variant returned by catalog tools."""
            return await commerce.availability(variant_id)

        tools.extend([view_cart, get_live_availability])

    def require_config(callback_context: Context) -> None:
        if config.missing():
            raise ValueError("BLOCKED_COMMERCE: configure " + ", ".join(config.missing()))

    # Explicit Vertex/project/location prevents an AI Studio key in root .env selecting
    # the Developer API. No fallback to an API-key client is implemented.
    model = Gemini(
        model=config.gemini_model,
        client_kwargs={
            "vertexai": True,
            "project": config.google_cloud_project,
            "location": config.google_cloud_location,
        },
    )
    return Agent(
        name="ecommerce",
        model=model,
        instruction=CATALOG_INSTRUCTION,
        tools=tools,
        before_agent_callback=require_config,
        generate_content_config=types.GenerateContentConfig(
            temperature=0.1, max_output_tokens=2048
        ),
    )


root_agent = build_agent()
