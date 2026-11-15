-- For a database created from an older schema.sql (fresh volumes get this from schema.sql).
-- Additive and idempotent. Needed before the API with the C-06 broken-import fix starts:
--   docker compose exec -T db psql -U repolens -d repolens < backend/migrations/2026-11-15-unread-paths.sql
-- Jobs from before this keep NULL, which means "not recorded": re-running the detect stage on
-- them (python -m app.ingest.redetect) skips the broken-import rule and writes a quality note.
BEGIN;

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS unread_paths TEXT[];

COMMIT;
