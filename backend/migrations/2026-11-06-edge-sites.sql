-- For a database created from an older schema.sql (fresh volumes get this from schema.sql).
-- Additive and idempotent:
--   docker compose exec -T db psql -U repolens -d repolens < backend/migrations/2026-11-06-edge-sites.sql
-- Existing edges have site_count NULL and no edge_sites rows until they are rebuilt from the
-- stored files (no clone, no embedding), with the API stopped:
--   cd backend; uv run --env-file ../.env python -m app.ingest.backfill
BEGIN;

ALTER TABLE edges ADD COLUMN IF NOT EXISTS site_count INT;

CREATE TABLE IF NOT EXISTS edge_sites (
  edge_id     BIGINT NOT NULL REFERENCES edges(id) ON DELETE CASCADE,
  line        INT NOT NULL,
  confidence  REAL,
  PRIMARY KEY (edge_id, line)
);

COMMIT;
