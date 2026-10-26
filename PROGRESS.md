# PROGRESS

## Done
- Git repo, `.gitignore`, `.gitattributes`; `main` pushed.
- Day 1 on `feat/ingest` (pushed):
  - uv project in `backend/` (Python 3.12), `docker-compose.yml` (db on host 5433, api on 8000),
    `backend/Dockerfile` (non-root, git installed), `.env.example`.
  - `backend/schema.sql`: design section 6 tables + `snapshot_status` view (with `job_id`).
  - `app/ingest/redact.py`: line-preserving redaction; returns `SecretMatch(line, kind)`, never the value.
  - `app/ingest/discover.py`: skip rules (secret files, venvs, vendor/build dirs, binaries, >1 MB),
    `MAX_FILES` cap, CRLF normalised, content redacted.
  - `app/ingest/parse.py`: Tree-sitter 0.26 Python parser -> module/class/function/method symbols.
  - `app/ingest/clone.py`: GitHub URL validation, `git ls-remote` SHA resolve, shallow fetch by SHA
    with hooks off, no submodules/LFS, `core.symlinks=false`, host git config ignored, timeouts.
  - `app/ingest/pipeline.py`: fetch -> discover -> parse, delete-then-insert per stage, progress on
    the job row, deadline check, workspace always deleted.
  - API: `POST /repos`, `GET /snapshots/{id}/status`, `GET /health`.
  - CI: `.github/workflows/ci.yml` (ruff + pytest, pgvector service, schema loaded with psql).
    Green on `feat/ingest` (confirmed 27 Oct). `DATABASE_URL` is set at job level, so the DB
    tests are not skipped there.
  - Tests: 36 local (redaction, discover, parser, URL validation); 2 network tests pass with
    `RUN_NETWORK_TESTS=1`; 4 DB end-to-end tests run only where `DATABASE_URL` is set (CI).

## Next
- When Docker works: `docker compose up --build`, ingest `https://github.com/pallets/itsdangerous`,
  check row counts. Then merge `feat/ingest` into `main` (ask first).
- Day 2: import resolution + call edges, graph/file/dependents endpoints, React shell.

## Decisions
- Python 3.12 everywhere (safer for torch / sentence-transformers on Day 3).
- Embedding column `vector(384)` (all-MiniLM-L6-v2 / bge-small-en-v1.5 class models).
- No worker container: ingestion runs in FastAPI `BackgroundTasks` inside `api`.
- On API startup, jobs still `queued`/`running` are marked failed ("Interrupted by server restart").
- Config read from `os.environ` in `app/config.py` (no pydantic-settings).
- Dropped `jobs.attempts`, `jobs.heartbeat_at`, `jobs_queue` index (no heartbeat/requeue).
- Discover stores Python plus common text/config files (md, rst, txt, toml, cfg, ini, yaml, json, sh)
  so secrets in config are reported; only Python is parsed.
- **Secrets:** redaction matches become `findings` rows (`rule_id='hardcoded-secret'`, severity high,
  masked snippet) in the discover stage. The Day 3 detect stage must delete/insert only its own
  rule ids and leave `hardcoded-secret` alone.
- Re-submitting a URL whose commit has a queued/running/done job returns that job; a failed one
  starts a new job. No GitHub API size check (would need a token); file/size/time caps instead.
- Unexpected pipeline errors show only "Internal error during <stage>." (log has the exception type).

## Known issues
- Docker Desktop still installing: nothing has run in Docker yet; DB tests not yet run locally
  (the local Postgres on 5432 is off-limits).
- `httpx` with Starlette TestClient emits a deprecation warning (suggests `httpx2`); harmless for now.
- Git for Windows `autocrlf` converts working copies to CRLF; repo stores LF. `.sh` files forced LF.
