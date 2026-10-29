"""User-scoped Shopify cart service. Model text never authorizes a mutation."""

import hashlib
import json
import uuid
from typing import Any
from urllib.parse import urlsplit

import httpx
from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from .config import CommerceSettings
from .shopify import ShopifyCatalog, ShopifyUnavailable

CART_FIELDS = """
 id checkoutUrl totalQuantity cost { totalAmount { amount currencyCode } }
 lines(first: 100) { pageInfo { hasNextPage } nodes {
   id quantity merchandise { ... on ProductVariant { id title availableForSale
     price { amount currencyCode } product { title } } }
 } }
"""


class CommerceError(RuntimeError):
    def __init__(self, code: str, status: int = 409):
        self.code, self.status = code, status
        super().__init__(code)


class Commerce:
    def __init__(self, settings: CommerceSettings):
        self.settings = settings
        self.source = ShopifyCatalog(settings)

    async def request(
        self, query: str, variables: dict[str, Any], *, mutation: bool = False
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False) as client:
            return await self.source.query(client, query, variables, mutation=mutation)

    async def availability(self, variant_id: str) -> dict[str, Any]:
        result = await self.request(
            """query Variant($id: ID!) { node(id: $id) {
          ... on ProductVariant { id title availableForSale
            price { amount currencyCode } product { id title } }
        } }""",
            {"id": variant_id},
        )
        if not result.get("node") or "availableForSale" not in result["node"]:
            raise CommerceError("VARIANT_NOT_FOUND", 404)
        return dict(result["node"])

    async def raw_cart(self, cart_id: str) -> dict[str, Any]:
        result = await self.request(
            "query Cart($id: ID!) { cart(id: $id) {" + CART_FIELDS + "} }", {"id": cart_id}
        )
        cart = result.get("cart")
        if not cart:
            raise CommerceError("CART_EXPIRED", 410)
        if cart["lines"]["pageInfo"]["hasNextPage"]:
            raise CommerceError("CART_TOO_LARGE")
        return dict(cart)

    @staticmethod
    def public_cart(cart: dict[str, Any], local_id: str) -> dict[str, Any]:
        # Shopify cart IDs include a secret key; keep those on the server.
        return {
            "id": local_id,
            "quantity": cart["totalQuantity"],
            "cost": cart["cost"],
            "lines": cart["lines"]["nodes"],
            "inventory": "Refresh required before checkout",
        }

    async def owned(self, db: AsyncConnection, subject: str, local_id: str) -> str:
        row = await (
            await db.execute(
                "SELECT shopify_cart_id FROM commerce.cart_mappings WHERE id=%s AND "
                "subject=%s AND merchant=%s",
                (uuid.UUID(local_id), subject, self.settings.shopify_store_domain),
            )
        ).fetchone()
        if not row:
            raise CommerceError("CART_NOT_FOUND", 404)
        return str(row[0])

    async def view(self, subject: str, local_id: str | None = None) -> dict[str, Any]:
        async with await AsyncConnection.connect(
            self.settings.database_url.get_secret_value()
        ) as db:
            if local_id is None:
                row = await (
                    await db.execute(
                        "SELECT id FROM commerce.cart_mappings WHERE subject=%s AND merchant=%s",
                        (subject, self.settings.shopify_store_domain),
                    )
                ).fetchone()
                if not row:
                    return {"cart": None}
                local_id = str(row[0])
            source_id = await self.owned(db, subject, local_id)
        return self.public_cart(await self.raw_cart(source_id), local_id)

    async def action(
        self, subject: str, request_id: uuid.UUID, action: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        fingerprint = hashlib.sha256(
            json.dumps({"action": action, **payload}, sort_keys=True).encode()
        ).hexdigest()
        # Autocommit persists the intent BEFORE Shopify. Unknown outcomes must not retry blindly.
        async with await AsyncConnection.connect(
            self.settings.database_url.get_secret_value(), autocommit=True
        ) as db:
            await db.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (subject,))
            try:
                previous = await (
                    await db.execute(
                        "SELECT fingerprint,status,result FROM commerce.operations WHERE "
                        "subject=%s AND request_id=%s",
                        (subject, request_id),
                    )
                ).fetchone()
                if previous:
                    if previous[0] != fingerprint:
                        raise CommerceError("IDEMPOTENCY_KEY_REUSED")
                    if previous[1] == "completed":
                        return dict(previous[2])
                    raise CommerceError("OPERATION_REQUIRES_RECONCILIATION")
                await db.execute(
                    "INSERT INTO "
                    "commerce.operations(subject,request_id,action,fingerprint,status) "
                    "VALUES (%s,%s,%s,%s,'pending')",
                    (subject, request_id, action, fingerprint),
                )
                try:
                    result = await self._perform(db, subject, action, payload)
                except Exception:
                    await db.execute(
                        "UPDATE commerce.operations SET status='unknown' WHERE subject=%s AND "
                        "request_id=%s",
                        (subject, request_id),
                    )
                    raise
                await db.execute(
                    "UPDATE commerce.operations SET status='completed', result=%s WHERE "
                    "subject=%s AND request_id=%s",
                    (Jsonb(result), subject, request_id),
                )
                await db.execute(
                    "INSERT INTO commerce.audit(subject,action,outcome) VALUES (%s,%s,'completed')",
                    (subject, action),
                )
                return result
            finally:
                await db.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (subject,))

    async def _perform(
        self, db: AsyncConnection, subject: str, action: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        if action == "create":
            existing = await (
                await db.execute(
                    "SELECT id,shopify_cart_id FROM commerce.cart_mappings WHERE "
                    "subject=%s AND merchant=%s",
                    (subject, self.settings.shopify_store_domain),
                )
            ).fetchone()
            if existing:
                return self.public_cart(await self.raw_cart(existing[1]), str(existing[0]))
            result = await self.request(
                "mutation { cartCreate(input: {}) { cart {"
                + CART_FIELDS
                + "} userErrors { code } } }",
                {},
                mutation=True,
            )
            cart = self.cart_result(result, "cartCreate")
            local_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO "
                "commerce.cart_mappings(id,subject,merchant,shopify_cart_id) VALUES (%s,%s,%s,%s)",
                (local_id, subject, self.settings.shopify_store_domain, cart["id"]),
            )
            return self.public_cart(cart, local_id)
        local_id = payload["cart_id"]
        source_id = await self.owned(db, subject, local_id)
        cart = await self.raw_cart(source_id)
        if action == "add":
            variant = await self.availability(payload["variant_id"])
            already = sum(
                line["quantity"]
                for line in cart["lines"]["nodes"]
                if line["merchandise"]["id"] == variant["id"]
            )
            quantity = already + payload["quantity"]
            if not variant["availableForSale"] or (
                variant.get("quantityAvailable") is not None
                and quantity > variant["quantityAvailable"]
            ):
                raise CommerceError("INSUFFICIENT_INVENTORY")
            if len(cart["lines"]["nodes"]) >= 100:
                raise CommerceError("CART_TOO_LARGE")
            result = await self.request(
                "mutation Add($id: ID!, $lines: [CartLineInput!]!) { "
                "cartLinesAdd(cartId:$id,lines:$lines) { cart {"
                + CART_FIELDS
                + "} userErrors { code } } }",
                {
                    "id": source_id,
                    "lines": [{"merchandiseId": variant["id"], "quantity": payload["quantity"]}],
                },
                mutation=True,
            )
            return self.public_cart(self.cart_result(result, "cartLinesAdd"), local_id)
        if action == "remove":
            if payload["line_id"] not in {line["id"] for line in cart["lines"]["nodes"]}:
                raise CommerceError("LINE_NOT_FOUND", 404)
            result = await self.request(
                "mutation Remove($id: ID!, $lines: [ID!]!) { "
                "cartLinesRemove(cartId:$id,lineIds:$lines) { cart {"
                + CART_FIELDS
                + "} userErrors { code } } }",
                {"id": source_id, "lines": [payload["line_id"]]},
                mutation=True,
            )
            return self.public_cart(self.cart_result(result, "cartLinesRemove"), local_id)
        if action == "checkout":
            if not cart["lines"]["nodes"]:
                raise CommerceError("EMPTY_CART")
            for line in cart["lines"]["nodes"]:
                variant = await self.availability(line["merchandise"]["id"])
                if not variant["availableForSale"] or (
                    variant.get("quantityAvailable") is not None
                    and line["quantity"] > variant["quantityAvailable"]
                ):
                    raise CommerceError("INVENTORY_CHANGED")
            url = cart["checkoutUrl"]
            if urlsplit(url).scheme != "https" or not urlsplit(url).hostname:
                raise CommerceError("INVALID_CHECKOUT_URL", 502)
            return {
                "checkout_url": url,
                "payment_status": "NOT_VERIFIED",
                "notice": "Shopify confirms final inventory, shipping, taxes and payment.",
            }
        raise CommerceError("UNSUPPORTED_ACTION", 400)

    @staticmethod
    def cart_result(result: dict[str, Any], field: str) -> dict[str, Any]:
        value = result[field]
        if value.get("userErrors") or not value.get("cart"):
            raise ShopifyUnavailable("Shopify rejected the cart operation")
        if value["cart"]["lines"]["pageInfo"]["hasNextPage"]:
            raise CommerceError("CART_TOO_LARGE")
        return dict(value["cart"])
