-- For a database created from an older schema.sql (fresh volumes get this from schema.sql).
-- Additive and idempotent. Needed before the API that reports the analysis receipt starts:
--   docker compose exec -T db psql -U repolens -d repolens < backend/migrations/2026-11-05-analysis-receipt.sql
-- Jobs from before this keep NULLs: their counts were only logged, so the status API returns no
-- receipt for them and the UI shows no notice.
BEGIN;

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS files_kept INT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS files_skipped INT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS files_beyond_limit INT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS hit_file_limit BOOLEAN;

COMMIT;
