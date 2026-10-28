-- For a database created from an older schema.sql (fresh volumes get this from schema.sql).
-- Additive: safe to run while an older API is running, and needed before the API that uses
-- jobs.search_state starts:
--   docker compose exec -T db psql -U repolens -d repolens < backend/migrations/2026-10-28-search-state.sql
BEGIN;

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS search_state TEXT;
CREATE OR REPLACE VIEW snapshot_status AS
SELECT DISTINCT ON (snapshot_id) snapshot_id, id AS job_id, status, stage, percent, error,
  search_error, progress_done, progress_total, search_state
FROM jobs
ORDER BY snapshot_id, id DESC;

COMMIT;
