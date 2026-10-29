import uuid
from datetime import UTC, datetime

from psycopg import AsyncConnection

from .config import COMPONENT, CommerceSettings
from .models import Product, SyncResult
from .shopify import ShopifyCatalog


async def migrate(settings: CommerceSettings) -> None:
    dsn = (
        settings.migration_database_url.get_secret_value()
        or settings.database_url.get_secret_value()
    )
    if not dsn:
        raise ValueError("BLOCKED_DATABASE: configure DATABASE_URL")
    async with await AsyncConnection.connect(dsn, connect_timeout=10) as connection:
        await connection.execute((COMPONENT / "infra/001_catalog.sql").read_text())
        await connection.execute((COMPONENT / "infra/003_sessions.sql").read_text())


async def sync_catalog(settings: CommerceSettings) -> SyncResult:
    dsn = settings.database_url.get_secret_value()
    if not dsn:
        raise ValueError("BLOCKED_DATABASE: configure DATABASE_URL")
    source = ShopifyCatalog(settings)
    async with await AsyncConnection.connect(dsn, connect_timeout=10) as connection:
        async with connection.transaction():
            # Hold a per-merchant transaction lock across retrieval to serialize full snapshots.
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (settings.shopify_store_domain,),
            )
            products = await source.fetch_all()
            sync_id = uuid.uuid4()
            await connection.execute(
                "INSERT INTO commerce.sync_runs(id, merchant) VALUES (%s, %s)",
                (sync_id, settings.shopify_store_domain),
            )
            for product in products:
                await upsert_product(connection, settings.shopify_store_domain, product, sync_id)
            for table in ("products", "variants"):
                from psycopg import sql

                await connection.execute(
                    sql.SQL(
                        "UPDATE commerce.{} SET active=false, updated_at=now() "
                        "WHERE merchant=%s AND sync_id<>%s"
                    ).format(sql.Identifier(table)),
                    (settings.shopify_store_domain, sync_id),
                )
            count = sum(len(product.variants) for product in products)
            await connection.execute(
                "UPDATE commerce.sync_runs SET completed_at=now(), product_count=%s, "
                "variant_count=%s WHERE id=%s",
                (len(products), count, sync_id),
            )
    return SyncResult(
        status="SYNCED",
        products=len(products),
        variants=count,
        completed_at=datetime.now(UTC),
        database_mode=settings.database_mode,
    )


async def upsert_product(
    connection: AsyncConnection, merchant: str, product: Product, sync_id: uuid.UUID
) -> None:
    await connection.execute(
        """
      INSERT INTO commerce.products(merchant,source_id,title,description,vendor,product_type,
        handle,url,source_updated_at,sync_id)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
      ON CONFLICT(merchant,source_id) DO UPDATE SET title=excluded.title,
        description=excluded.description,vendor=excluded.vendor,product_type=excluded.product_type,
        handle=excluded.handle,url=excluded.url,source_updated_at=excluded.source_updated_at,
        sync_id=excluded.sync_id,active=true,updated_at=now()
    """,
        (
            merchant,
            product.id,
            product.title,
            product.description,
            product.vendor,
            product.product_type,
            product.handle,
            product.url,
            product.updated_at,
            sync_id,
        ),
    )
    for variant in product.variants:
        await connection.execute(
            """
          INSERT INTO commerce.variants(merchant,source_id,product_id,title,sku,amount,currency,
            available,image_url,sync_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
          ON CONFLICT(merchant,source_id) DO UPDATE SET product_id=excluded.product_id,
            title=excluded.title,sku=excluded.sku,amount=excluded.amount,currency=excluded.currency,
            available=excluded.available,image_url=excluded.image_url,sync_id=excluded.sync_id,
            active=true,updated_at=now()
        """,
            (
                merchant,
                variant.id,
                product.id,
                variant.title,
                variant.sku,
                variant.amount,
                variant.currency,
                variant.available,
                variant.image_url,
                sync_id,
            ),
        )
