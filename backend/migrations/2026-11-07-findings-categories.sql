-- For a database created from an older schema.sql (fresh volumes get this from schema.sql).
-- Additive and idempotent; run with the API stopped:
--   docker compose exec -T db psql -U repolens -d repolens < backend/migrations/2026-11-07-findings-categories.sql
-- (PowerShell: Get-Content backend/migrations/2026-11-07-findings-categories.sql | docker compose exec -T db psql -U repolens -d repolens)
--
-- findings.in_docs / findings.placeholder: see schema.sql. Existing hardcoded-secret findings in
-- documentation files (.md/.rst/.txt) are marked and lowered to low here, from the stored path.
-- `placeholder` cannot be filled for old rows (the value is not stored); re-run an analysis to
-- get it. Quality findings (Ruff, broken imports) appear when an analysis is re-run.
BEGIN;

ALTER TABLE findings ADD COLUMN IF NOT EXISTS in_docs BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE findings ADD COLUMN IF NOT EXISTS placeholder BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS quality_note TEXT;

UPDATE findings f
SET in_docs = true,
    severity = 'low',
    message = CASE WHEN f.in_test
                   THEN regexp_replace(f.message, '[.]$', ' and in documentation.')
                   ELSE regexp_replace(f.message, '[.]$', ' in documentation.') END
FROM files fi
WHERE fi.id = f.file_id
  AND f.rule_id = 'hardcoded-secret'
  AND NOT f.in_docs
  AND lower(fi.path) ~ '[.](md|rst|txt)$';

COMMIT;
