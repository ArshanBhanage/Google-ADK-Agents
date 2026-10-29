"""Run from repository root: agents/ecommerce/.venv/bin/python -m agents.ecommerce.cli."""

import argparse
import asyncio
import json

from .config import CommerceSettings
from .database import migrate, sync_catalog
from .mcp_client import probe_toolbox
from .shopify import ShopifyCatalog


async def run(command: str) -> dict[str, object]:
    settings = CommerceSettings()
    if command == "readiness":
        missing = settings.missing()
        return {
            "status": "BLOCKED" if missing else "CONFIGURED_NOT_VERIFIED",
            "missing": missing,
            "provider": "vertexai",
            "mode": settings.database_mode,
        }
    if command == "shopify-check":
        products = await ShopifyCatalog(settings).fetch_all()
        return {
            "status": "SHOPIFY_CATALOG_READ_VERIFIED",
            "products": len(products),
            "variants": sum(len(product.variants) for product in products),
            "source_ids_validated": True,
        }
    if command == "migrate":
        await migrate(settings)
        return {"status": "MIGRATED", "mode": settings.database_mode}
    if command == "sync":
        return (await sync_catalog(settings)).model_dump(mode="json")
    return await probe_toolbox(settings)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["readiness", "shopify-check", "migrate", "sync", "probe"]
    )
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args.command))
    except Exception as exc:
        # Provider exception bodies can contain tokens, DSNs or private catalog data.
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "action": "Check local credentials, connectivity and configuration.",
                }
            )
        )
        raise SystemExit(1) from None
    print(json.dumps(result, indent=2))
    if result.get("status") == "BLOCKED":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
