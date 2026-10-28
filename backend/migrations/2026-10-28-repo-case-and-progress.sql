-- For a database created from an older schema.sql (fresh volumes get this from schema.sql).
-- Run once, AFTER the API is restarted on the code that needs it (an older API still uses
-- ON CONFLICT (url) and would fail without the old constraint):
--   docker compose exec -T db psql -U repolens -d repolens < backend/migrations/2026-10-28-repo-case-and-progress.sql
BEGIN;

-- Repo URLs keep their capitalisation; one row per repo whatever the case.
ALTER TABLE repos DROP CONSTRAINT IF EXISTS repos_url_key;
CREATE UNIQUE INDEX IF NOT EXISTS repos_url_ci ON repos (lower(url));

-- Counts within the slow stages (parse: files, embed: chunks) for the Progress page.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS progress_done INT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS progress_total INT;
-- Also in 2026-10-28-search-state.sql. Here too so the view below matches the current one and
-- the two files can run in either order (dropping a view column is an error).
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS search_state TEXT;
CREATE OR REPLACE VIEW snapshot_status AS
SELECT DISTINCT ON (snapshot_id) snapshot_id, id AS job_id, status, stage, percent, error,
  search_error, progress_done, progress_total, search_state
FROM jobs
ORDER BY snapshot_id, id DESC;

COMMIT;
