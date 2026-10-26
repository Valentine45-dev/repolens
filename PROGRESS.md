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
  - CI: `.github/workflows/ci.yml` (ruff + `pytest -q -rs`, pgvector service, schema loaded with
    psql). Green on `feat/ingest`. `DATABASE_URL` is set at job level; the CI log shows
    "40 passed, 2 skipped" (only the `RUN_NETWORK_TESTS` skips), so the DB tests run in CI.
  - psycopg_pool deprecation warning fixed by passing `open=True` to `ConnectionPool` (`a5e2979`).
  - Tests: 36 local (redaction, discover, parser, URL validation); 2 network tests pass with
    `RUN_NETWORK_TESTS=1`; 4 DB end-to-end tests run only where `DATABASE_URL` is set (CI).

  - **Local end-to-end run (27 Oct):** `.env` from `.env.example` (`DATABASE_URL` -> `localhost:5433`),
    `docker compose up -d db`, full suite locally with DB + network tests: **42 passed, 0 skipped**.
    API via `uv run --env-file ../.env uvicorn app.main:app` (config reads `os.environ`, so the
    `--env-file` flag is needed). Ingested `pallets/itsdangerous` @ `672971d`: status `done`, 100%,
    no error. Rows: **41 files** (15 Python), **159 symbols** (98 method, 29 class, 17 function,
    15 module), **7 findings** (all `hardcoded-secret` on placeholder `secret_key=` in `tests/`,
    values masked). Clone workspace deleted afterwards.
  - **Fixed: Tree-sitter segfault.** First ingest killed the API process (exit 139, access violation in
    `node.named_children` during parse). Identical code crashed 6/6 runs on `tree-sitter` 0.26.0 and
    0/6 on 0.25.2, so it is a native regression in py-tree-sitter 0.26.0 (seen on Windows; Linux CI
    never hit it). Pinned `tree-sitter>=0.25.2,<0.26` in `pyproject.toml`.

## Next
- Merge `feat/ingest` into `main` (waiting for the go-ahead).
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
- Local dev on this 8 GB RAM laptop: only the `db` service runs in Docker; the API runs natively
  with `uv run uvicorn`. The full compose stack (`db`, `api`, later `web`) is kept for the demo.

## Known issues
- DB tests `TRUNCATE repos RESTART IDENTITY CASCADE` on whatever `DATABASE_URL` points at, so running
  pytest locally wipes ingested dev data. Re-ingest after tests, or later point tests at a separate DB.
- `hardcoded-secret` is noisy on test code (placeholder keys in `tests/`). Consider lower severity
  for test paths when the Day 3 detectors land.
- Fixture tests do not reproduce the 0.26.0 crash (only bigger files did); the pin is the guard.
  Re-check before ever lifting it.
- `httpx` with Starlette TestClient emits a deprecation warning (suggests `httpx2`); harmless for now.
- Git for Windows `autocrlf` converts working copies to CRLF; repo stores LF. `.sh` files forced LF.
