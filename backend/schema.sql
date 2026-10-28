-- RepoLens schema (this build). Based on docs/repolens-system-design.md section 6, minus
-- llm_traces, answer_cache and the job-queue columns (no heartbeat/requeue in this build).
-- Loaded once by the Postgres image from /docker-entrypoint-initdb.d/.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE repos (
  id          BIGSERIAL PRIMARY KEY,
  url         TEXT NOT NULL,                    -- https://github.com/Owner/Repo, case as given
  created_at  TIMESTAMPTZ DEFAULT now()
);
-- GitHub names are case-insensitive: one row per repo whatever the capitalisation.
CREATE UNIQUE INDEX repos_url_ci ON repos (lower(url));

-- A snapshot is one repo at one exact commit (SHA resolved with `git ls-remote`).
CREATE TABLE snapshots (
  id          BIGSERIAL PRIMARY KEY,
  repo_id     BIGINT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  commit_sha  TEXT NOT NULL,
  llm_tokens_used BIGINT NOT NULL DEFAULT 0,    -- AI question budget (LLM_TOKEN_CAP_PER_SNAPSHOT)
  created_at  TIMESTAMPTZ DEFAULT now(),
  UNIQUE (repo_id, commit_sha)
);

-- jobs.status is the single source of truth for processing state.
CREATE TABLE jobs (
  id            BIGSERIAL PRIMARY KEY,
  snapshot_id   BIGINT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
  stage         TEXT NOT NULL DEFAULT 'queued',
  status        TEXT NOT NULL DEFAULT 'queued',   -- queued|running|done|failed
  percent       INT NOT NULL DEFAULT 0,
  error         TEXT,
  search_error  TEXT,                             -- embed stage failed; the job still finishes
  -- Counts within the current stage (parse: files, embed: chunks); NULL in other stages.
  progress_done  INT,
  progress_total INT,
  created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX jobs_snapshot ON jobs (snapshot_id);

-- A snapshot is "ready" when its latest job is done.
CREATE VIEW snapshot_status AS
SELECT DISTINCT ON (snapshot_id) snapshot_id, id AS job_id, status, stage, percent, error,
  search_error, progress_done, progress_total
FROM jobs
ORDER BY snapshot_id, id DESC;

CREATE TABLE files (
  id           BIGSERIAL PRIMARY KEY,
  snapshot_id  BIGINT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
  path         TEXT NOT NULL,
  language     TEXT,
  loc          INT,
  content      TEXT,                              -- redacted source text
  UNIQUE (snapshot_id, path)
);

-- Every graph node is a symbol: a file is a 'module' symbol, a third-party package an
-- 'external' symbol with no file, and an import we cannot resolve an 'unresolved' symbol with
-- no file (qualified_name = the import specifier). Edges point only at symbols.id.
CREATE TABLE symbols (
  id              BIGSERIAL PRIMARY KEY,
  snapshot_id     BIGINT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
  file_id         BIGINT REFERENCES files(id) ON DELETE CASCADE,   -- NULL for external/unresolved
  kind            TEXT NOT NULL,             -- module|class|function|method|external|unresolved
  name            TEXT NOT NULL,
  qualified_name  TEXT NOT NULL,
  start_line      INT,
  end_line        INT,
  signature       TEXT
);
CREATE INDEX symbols_file ON symbols (file_id);
CREATE INDEX symbols_snapshot_qname ON symbols (snapshot_id, qualified_name);
CREATE UNIQUE INDEX symbols_one_module_per_file ON symbols (file_id) WHERE kind = 'module';
CREATE UNIQUE INDEX symbols_one_external_per_name ON symbols (snapshot_id, qualified_name)
  WHERE kind = 'external';
CREATE UNIQUE INDEX symbols_one_unresolved_per_name ON symbols (snapshot_id, qualified_name)
  WHERE kind = 'unresolved';

CREATE TABLE edges (
  id           BIGSERIAL PRIMARY KEY,
  snapshot_id  BIGINT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
  src_id       BIGINT NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
  dst_id       BIGINT NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
  type         TEXT NOT NULL,                     -- imports|calls|inherits|defines
  confidence   REAL NOT NULL DEFAULT 1.0
);
CREATE INDEX edges_src ON edges (snapshot_id, src_id);
CREATE INDEX edges_dst ON edges (snapshot_id, dst_id);

CREATE TABLE findings (
  id           BIGSERIAL PRIMARY KEY,
  snapshot_id  BIGINT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
  file_id      BIGINT REFERENCES files(id) ON DELETE CASCADE,
  symbol_id    BIGINT REFERENCES symbols(id) ON DELETE SET NULL,
  line         INT,
  rule_id      TEXT NOT NULL,
  severity     TEXT NOT NULL,                     -- low|medium|high
  message      TEXT NOT NULL,
  snippet      TEXT,                              -- masked
  in_test      BOOLEAN NOT NULL DEFAULT false     -- file is a test/example (app/paths.py)
);
CREATE INDEX findings_snapshot ON findings (snapshot_id, severity);

CREATE TABLE chunks (
  id           BIGSERIAL PRIMARY KEY,
  snapshot_id  BIGINT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
  symbol_id    BIGINT NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
  start_line   INT NOT NULL,                      -- the chunk's own range (a window of a long
  end_line     INT NOT NULL,                      -- symbol has its own), cited as path:start-end
  token_count  INT NOT NULL,                      -- model tokens of the embedded text
  in_test      BOOLEAN NOT NULL DEFAULT false,    -- test or example code (app/paths.py)
  text         TEXT NOT NULL,                     -- redacted
  search_tsv   TSVECTOR,
  embedding    vector(384)                        -- all-MiniLM-L6-v2 / bge-small class models
);
CREATE INDEX chunks_snapshot ON chunks (snapshot_id);
CREATE INDEX chunks_tsv ON chunks USING gin (search_tsv);
-- No vector index: exact scan per snapshot (see design section 6).
