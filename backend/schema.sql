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
  -- Search for questions: embedding (non-test code) | tests (Ask on, test code in the
  -- background) | ready | failed (search_error says why; can be retried). NULL on old rows.
  search_state  TEXT,
  -- Counts within the current stage (parse: files, embed: chunks); NULL in other stages.
  progress_done  INT,
  progress_total INT,
  -- What the discover stage kept and left out. NULL when it did not run, and on old rows. Not in
  -- snapshot_status: the older migrations rebuild that view with its current columns.
  files_kept         INT,
  files_skipped      INT,
  files_beyond_limit INT,   -- past MAX_FILES; counted with discover's skip rules, not read
  hit_file_limit     BOOLEAN,
  -- Set when the code-quality checks (Ruff) did not complete; the findings list says so. NULL
  -- when they ran, and on old rows.
  quality_note       TEXT,
  created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX jobs_snapshot ON jobs (snapshot_id);

-- A snapshot is "ready" when its latest job is done.
CREATE VIEW snapshot_status AS
SELECT DISTINCT ON (snapshot_id) snapshot_id, id AS job_id, status, stage, percent, error,
  search_error, progress_done, progress_total, search_state
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
  confidence   REAL NOT NULL DEFAULT 1.0,
  -- imports only: when the import runs (app/ingest/parse.py). Cycle detection uses top_level.
  -- NULL on an import edge = analysed before this column existed: cycles are not known yet.
  import_scope TEXT CHECK (import_scope IN ('top_level', 'nested', 'type_checking')),
  -- imports and calls: how many distinct lines the pair occurs on (edge_sites keeps at most 20).
  -- NULL = analysed before sites existed.
  site_count   INT
);
CREATE INDEX edges_src ON edges (snapshot_id, src_id);
CREATE INDEX edges_dst ON edges (snapshot_id, dst_id);

-- Where an import or call happens. The file is the source symbol's file (the importing module, or
-- the caller). One row per (edge, line); `confidence` is that site's own, for calls (the edge keeps
-- the maximum); NULL for imports. Rebuilt with the edges (ids change), so nothing may store edge ids.
CREATE TABLE edge_sites (
  edge_id     BIGINT NOT NULL REFERENCES edges(id) ON DELETE CASCADE,
  line        INT NOT NULL,
  confidence  REAL,
  PRIMARY KEY (edge_id, line)
);

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
  in_test      BOOLEAN NOT NULL DEFAULT false,    -- file is a test/example (app/paths.py)
  in_docs      BOOLEAN NOT NULL DEFAULT false,    -- file is documentation (.md/.rst/.txt)
  -- hardcoded-secret only, when the value looks like a stand-in (changeme, <your-key>, xxxxxx);
  -- the value itself is never stored. `placeholder`: in a file that does not run (documentation,
  -- example or template file), so the finding is low and listed last. `template_value`: the
  -- same kind of value in code or runtime config, which keeps its severity because the app may
  -- run with it as it is. Rows analysed before these columns existed are false.
  placeholder  BOOLEAN NOT NULL DEFAULT false,
  template_value BOOLEAN NOT NULL DEFAULT false
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
