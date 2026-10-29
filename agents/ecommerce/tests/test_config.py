import pytest
from agents.ecommerce.config import CommerceSettings
from pydantic import ValidationError


@pytest.mark.parametrize("hostname", ["https://shop.myshopify.com", "evil.com", "x' OR 1=1--"])
def test_merchant_host_rejects_untrusted_destinations(hostname: str) -> None:
    with pytest.raises(ValidationError):
        CommerceSettings(_env_file=None, shopify_store_domain=hostname)


@pytest.mark.parametrize(
    "url",
    [
        "http://remote/mcp",
        "https://host/mcpevil",
        "https://user:password@host/mcp",  # pragma: allowlist secret -- rejection input
        "https:///mcp",
    ],
)
def test_mcp_endpoint_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        CommerceSettings(_env_file=None, toolbox_url=url)


def test_vertex_fallback_is_forbidden() -> None:
    with pytest.raises(ValidationError):
        CommerceSettings(_env_file=None, google_genai_use_vertexai=False)


def test_no_merchant_means_blocked() -> None:
    settings = CommerceSettings(
        _env_file=None, shopify_store_domain="", shopify_storefront_token=""
    )
    assert "SHOPIFY_STORE_DOMAIN" in settings.missing()
    assert "SHOPIFY_STOREFRONT_TOKEN" in settings.missing()
