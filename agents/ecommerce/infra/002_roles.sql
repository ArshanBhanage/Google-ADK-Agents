DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='commerce_catalog_reader') THEN
    CREATE ROLE commerce_catalog_reader NOLOGIN;
  END IF;
END $$;
GRANT USAGE ON SCHEMA commerce TO commerce_catalog_reader;
GRANT SELECT ON commerce.products, commerce.variants TO commerce_catalog_reader;
