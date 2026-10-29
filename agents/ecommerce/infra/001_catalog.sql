CREATE SCHEMA IF NOT EXISTS commerce;
CREATE TABLE IF NOT EXISTS commerce.schema_version (
  version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS commerce.sync_runs (
  id uuid PRIMARY KEY, merchant text NOT NULL,
  started_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
  product_count integer NOT NULL DEFAULT 0, variant_count integer NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS commerce.products (
  merchant text NOT NULL, source_id text NOT NULL, title text NOT NULL,
  description text NOT NULL, vendor text NOT NULL, product_type text NOT NULL,
  handle text NOT NULL, url text, source_updated_at timestamptz NOT NULL,
  active boolean NOT NULL DEFAULT true, sync_id uuid NOT NULL REFERENCES commerce.sync_runs(id),
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  search_document tsvector GENERATED ALWAYS AS
    (to_tsvector('simple', title || ' ' || description || ' ' || vendor || ' ' || product_type)) STORED,
  PRIMARY KEY(merchant, source_id)
);
CREATE INDEX IF NOT EXISTS products_search ON commerce.products USING gin(search_document);
CREATE TABLE IF NOT EXISTS commerce.variants (
  merchant text NOT NULL, source_id text NOT NULL, product_id text NOT NULL,
  title text NOT NULL, sku text, amount numeric(20,4) NOT NULL CHECK(amount >= 0),
  currency char(3) NOT NULL, available boolean NOT NULL, image_url text,
  active boolean NOT NULL DEFAULT true, sync_id uuid NOT NULL REFERENCES commerce.sync_runs(id),
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(merchant, source_id),
  FOREIGN KEY(merchant, product_id) REFERENCES commerce.products(merchant, source_id)
);
CREATE INDEX IF NOT EXISTS variants_product ON commerce.variants(merchant, product_id);
CREATE TABLE IF NOT EXISTS commerce.users (
  subject text PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS commerce.cart_mappings (
  id uuid PRIMARY KEY, subject text NOT NULL REFERENCES commerce.users(subject),
  merchant text NOT NULL, shopify_cart_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(subject, merchant)
);
CREATE TABLE IF NOT EXISTS commerce.audit (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  subject text NOT NULL, action text NOT NULL, outcome text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO commerce.schema_version(version) VALUES (1) ON CONFLICT DO NOTHING;
