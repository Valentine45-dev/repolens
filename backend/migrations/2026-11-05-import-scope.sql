-- For a database created from an older schema.sql (fresh volumes get this from schema.sql).
-- Additive and idempotent:
--   docker compose exec -T db psql -U repolens -d repolens < backend/migrations/2026-11-05-import-scope.sql
-- Existing import edges keep NULL until they are rebuilt, and the graph API then reports
-- cycles_available = false. Rebuild them from the stored files (no clone, no embedding), with the
-- API stopped:
--   cd backend; uv run --env-file ../.env python -m app.ingest.backfill
BEGIN;

ALTER TABLE edges ADD COLUMN IF NOT EXISTS import_scope TEXT
  CHECK (import_scope IN ('top_level', 'nested', 'type_checking'));

COMMIT;
