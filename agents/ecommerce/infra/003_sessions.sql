CREATE TABLE IF NOT EXISTS commerce.access_tokens (
  token_hash text PRIMARY KEY, subject text NOT NULL REFERENCES commerce.users(subject),
  created_at timestamptz NOT NULL DEFAULT now(), revoked boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS commerce.operations (
  subject text NOT NULL REFERENCES commerce.users(subject), request_id uuid NOT NULL,
  action text NOT NULL, fingerprint text NOT NULL,
  status text NOT NULL CHECK(status IN ('pending','completed','failed','unknown')),
  result jsonb, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(subject, request_id)
);
INSERT INTO commerce.schema_version(version) VALUES (3) ON CONFLICT DO NOTHING;
