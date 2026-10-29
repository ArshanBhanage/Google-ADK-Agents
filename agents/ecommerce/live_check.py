"""Real API, PostgreSQL, MCP, Vertex and Shopify tests; never places an order."""

import asyncio
import json
import uuid
from datetime import UTC, datetime

import httpx
from psycopg import AsyncConnection

from .config import COMPONENT, CommerceSettings


async def check() -> dict[str, object]:
    settings = CommerceSettings()
    async with await AsyncConnection.connect(settings.database_url.get_secret_value()) as db:
        row = await (
            await db.execute(
                "SELECT p.title,v.source_id FROM commerce.products p JOIN commerce.variants v "
                "ON p.merchant=v.merchant AND p.source_id=v.product_id WHERE p.active AND v.active "
                "AND v.available AND p.merchant=%s ORDER BY p.source_id,v.source_id LIMIT 1",
                (settings.shopify_store_domain,),
            )
        ).fetchone()
        assert row, "No available authorized merchant variant"
        counts = await (
            await db.execute(
                "SELECT (SELECT count(*) FROM commerce.products), "
                "(SELECT count(*) FROM commerce.variants)"
            )
        ).fetchone()
    assert counts
    owner = (COMPONENT / ".local/owner.token").read_text().strip()
    other = (COMPONENT / ".local/isolation-test.token").read_text().strip()
    evidence: dict[str, object] = {
        "checked_at": datetime.now(UTC).isoformat(),
        "mode": "local_postgres",
        "catalog_provenance": (
            "Authorized Shopify API records; demo-style catalog, production provenance unverified"
        ),
        "products": counts[0],
        "variants": counts[1],
    }
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8085", timeout=110, trust_env=False
    ) as client:
        assert (await client.get("/api/me")).status_code == 401
        client.headers["Authorization"] = "Bearer " + owner
        assert (await client.get("/api/me")).status_code == 200
        result = await client.get("/api/catalog", params={"query": row[0]})
        assert result.status_code == 200, f"MCP catalog HTTP {result.status_code}"
        assert result.json()["products"], "Real MCP search must return imported rows"
        evidence["mcp_catalog_rows"] = len(result.json()["products"])
        denied = await client.post(
            "/api/cart/actions",
            json={"action": "create", "request_id": str(uuid.uuid4()), "confirmed": False},
        )
        assert denied.status_code == 422
        body = {"action": "create", "request_id": str(uuid.uuid4()), "confirmed": True}
        result = await client.post("/api/cart/actions", json=body)
        assert result.status_code == 200, f"Create HTTP {result.status_code}: {result.text[:200]}"
        cart = result.json()
        repeated = await client.post("/api/cart/actions", json=body)
        assert repeated.json() == cart
        evidence["create_idempotent"] = True
        evidence["confirmation_enforced"] = True
        other_headers = {"Authorization": "Bearer " + other}
        assert (
            await client.get("/api/cart", params={"cart_id": cart["id"]}, headers=other_headers)
        ).status_code == 404
        assert (
            await client.post(
                "/api/cart/actions",
                headers=other_headers,
                json={
                    "action": "add",
                    "request_id": str(uuid.uuid4()),
                    "confirmed": True,
                    "cart_id": cart["id"],
                    "variant_id": row[1],
                },
            )
        ).status_code == 404
        evidence["cross_user_read_and_write_denied"] = True
        body = {
            "action": "add",
            "request_id": str(uuid.uuid4()),
            "confirmed": True,
            "cart_id": cart["id"],
            "variant_id": row[1],
            "quantity": 1,
        }
        result = await client.post("/api/cart/actions", json=body)
        assert result.status_code == 200, f"Add HTTP {result.status_code}: {result.text[:200]}"
        added = result.json()
        assert (await client.post("/api/cart/actions", json=body)).json() == added
        evidence["add_idempotent"] = True
        try:
            result = await client.post(
                "/api/cart/actions",
                json={
                    "action": "checkout",
                    "request_id": str(uuid.uuid4()),
                    "confirmed": True,
                    "cart_id": cart["id"],
                },
            )
            assert result.status_code == 200, f"Checkout HTTP {result.status_code}"
            assert result.json()["checkout_url"].startswith("https://")
            assert result.json()["payment_status"] == "NOT_VERIFIED"
            evidence["real_checkout_url_received"] = True
            evidence["payment_attempted"] = False
        finally:
            for line in added["lines"]:
                if line["merchandise"]["id"] == row[1]:
                    result = await client.post(
                        "/api/cart/actions",
                        json={
                            "action": "remove",
                            "request_id": str(uuid.uuid4()),
                            "confirmed": True,
                            "cart_id": cart["id"],
                            "line_id": line["id"],
                        },
                    )
                    assert result.status_code == 200
                    evidence["test_item_removed"] = True
        orders = await client.get("/api/orders")
        assert orders.json()["status"] == "BLOCKED"
        evidence["unauthorized_order_access_blocked"] = True
        result = await client.post(
            "/api/chat",
            json={
                "message": "Find "
                + row[0]
                + ". Use catalog tools to verify its price and variants. Do not change any carts."
            },
        )
        assert result.status_code == 200, f"Vertex chat HTTP {result.status_code}"
        answer = result.json()
        assert answer["answer"] and "search_catalog" in answer["tools"]
        evidence["vertex_adk_tools"] = answer["tools"]
        evidence["vertex_answer_received"] = True
    return evidence


if __name__ == "__main__":
    result = asyncio.run(check())
    (COMPONENT / "evidence/postgres-e2e.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
