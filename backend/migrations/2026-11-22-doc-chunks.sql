-- Step 5 Part A: documentation chunks. Idempotent: run as often as you like, in one transaction.
-- Code chunks keep every value they had; file_id is filled from their symbol's file.
-- Run with every API stopped (it rewrites the chunks table's rows once).
BEGIN;

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS file_id BIGINT REFERENCES files(id) ON DELETE CASCADE;
UPDATE chunks c SET file_id = s.file_id FROM symbols s WHERE s.id = c.symbol_id AND c.file_id IS NULL;
ALTER TABLE chunks ALTER COLUMN file_id SET NOT NULL;

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'code';
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chunks_source_check') THEN
    ALTER TABLE chunks ADD CONSTRAINT chunks_source_check CHECK (source IN ('code', 'doc'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chunks_code_has_symbol') THEN
    ALTER TABLE chunks ADD CONSTRAINT chunks_code_has_symbol
      CHECK (source = 'doc' OR symbol_id IS NOT NULL);
  END IF;
END $$;

ALTER TABLE chunks ALTER COLUMN symbol_id DROP NOT NULL;
CREATE INDEX IF NOT EXISTS chunks_file ON chunks (file_id);

COMMIT;
