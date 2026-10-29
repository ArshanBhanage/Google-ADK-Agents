import asyncio
from typing import Any

import httpx

from .config import CommerceSettings
from .models import Product, Variant

VARIANT_FIELDS = """
  id title sku availableForSale
  price { amount currencyCode }
  image { url }
"""
PRODUCT_FIELDS = """
  id title description vendor productType handle onlineStoreUrl updatedAt
"""
CATALOG = (
    """query Catalog($after: String) {
  products(first: 50, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes { """
    + PRODUCT_FIELDS
    + """
      variants(first: 100) {
        pageInfo { hasNextPage endCursor }
        nodes { """
    + VARIANT_FIELDS
    + """ }
      }
    }
  }
}"""
)
VARIANTS = (
    """query Variants($id: ID!, $after: String) {
  product(id: $id) { variants(first: 100, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes { """
    + VARIANT_FIELDS
    + """ }
  } }
}"""
)


class ShopifyUnavailable(RuntimeError):
    pass


class ShopifyCatalog:
    def __init__(self, settings: CommerceSettings) -> None:
        if (
            not settings.shopify_store_domain
            or not settings.shopify_storefront_token.get_secret_value()
        ):
            raise ShopifyUnavailable("BLOCKED_SHOPIFY: set merchant domain and Storefront token")
        self.settings = settings
        self.url = f"https://{settings.shopify_store_domain}/api/{settings.shopify_api_version}/graphql.json"

    async def query(
        self,
        client: httpx.AsyncClient,
        query: str,
        variables: dict[str, Any],
        *,
        mutation: bool = False,
    ) -> dict[str, Any]:
        header = (
            "Shopify-Storefront-Private-Token"
            if self.settings.shopify_token_type == "private"
            else "X-Shopify-Storefront-Access-Token"
        )
        attempts = 1 if mutation else 3
        for attempt in range(attempts):
            try:
                async with client.stream(
                    "POST",
                    self.url,
                    json={"query": query, "variables": variables},
                    headers={header: self.settings.shopify_storefront_token.get_secret_value()},
                ) as response:
                    if response.status_code in {429, 502, 503, 504} and attempt < attempts - 1:
                        try:
                            wait = min(float(response.headers.get("Retry-After", "2")), 15)
                        except ValueError:
                            wait = 2
                    else:
                        if response.status_code != 200:
                            raise ShopifyUnavailable(
                                f"Shopify HTTP {response.status_code}; verify scopes/store"
                            )
                        data = bytearray()
                        async for chunk in response.aiter_bytes():
                            data.extend(chunk)
                            if len(data) > 4_000_000:
                                raise ShopifyUnavailable("Shopify response exceeds 4 MB limit")
                        import json

                        result = json.loads(data)
                        if result.get("errors"):
                            if (
                                all(
                                    error.get("extensions", {}).get("code") == "THROTTLED"
                                    for error in result["errors"]
                                )
                                and attempt < attempts - 1
                            ):
                                wait = 2**attempt
                            else:
                                raise ShopifyUnavailable(
                                    "Shopify GraphQL rejected the request; check API/scopes"
                                )
                        elif isinstance(result.get("data"), dict):
                            return dict(result["data"])
                        else:
                            raise ShopifyUnavailable("Shopify response has no data")
            except httpx.TransportError as exc:
                if attempt == attempts - 1:
                    raise ShopifyUnavailable("Shopify network request failed") from exc
                wait = 2**attempt
            await asyncio.sleep(max(1, wait))
        raise ShopifyUnavailable("Shopify retry budget exhausted")

    async def fetch_all(self) -> list[Product]:
        products = []
        cursor = None
        seen_cursors: set[str] = set()
        async with (
            asyncio.timeout(300),
            httpx.AsyncClient(
                timeout=30,
                follow_redirects=False,
                trust_env=False,
            ) as client,
        ):
            while True:
                result = await self.query(client, CATALOG, {"after": cursor})
                connection = result["products"]
                for source in connection["nodes"]:
                    variants = list(source["variants"]["nodes"])
                    page = source["variants"]["pageInfo"]
                    variant_cursors: set[str] = set()
                    while page["hasNextPage"]:
                        next_cursor = page["endCursor"]
                        if (
                            not next_cursor
                            or next_cursor in variant_cursors
                            or len(variants) > 10000
                        ):
                            raise ShopifyUnavailable("Invalid or excessive variant pagination")
                        variant_cursors.add(next_cursor)
                        more = await self.query(
                            client, VARIANTS, {"id": source["id"], "after": next_cursor}
                        )
                        if not more.get("product"):
                            raise ShopifyUnavailable(
                                "Catalog changed during synchronization; retry"
                            )
                        page = more["product"]["variants"]["pageInfo"]
                        variants.extend(more["product"]["variants"]["nodes"])
                    products.append(parse_product(source, variants))
                    if len(products) > self.settings.max_catalog_products:
                        raise ShopifyUnavailable(
                            "Catalog limit exceeded; no partial snapshot will be saved"
                        )
                if not connection["pageInfo"]["hasNextPage"]:
                    break
                cursor = connection["pageInfo"]["endCursor"]
                if not cursor or cursor in seen_cursors:
                    raise ShopifyUnavailable("Invalid catalog pagination cursor")
                seen_cursors.add(cursor)
        return products


def parse_product(source: dict[str, Any], variants: list[dict[str, Any]]) -> Product:
    return Product(
        id=source["id"],
        title=source["title"],
        description=source["description"],
        vendor=source["vendor"],
        product_type=source["productType"],
        handle=source["handle"],
        url=source.get("onlineStoreUrl"),
        updated_at=source["updatedAt"],
        variants=[
            Variant(
                id=v["id"],
                title=v["title"],
                sku=v.get("sku"),
                amount=v["price"]["amount"],
                currency=v["price"]["currencyCode"],
                available=v["availableForSale"],
                image_url=v["image"]["url"] if v.get("image") else None,
            )
            for v in variants
        ],
    )
