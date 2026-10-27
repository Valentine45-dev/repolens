# PROGRESS

## Done
- **`feat/ingest` merged into `main` (27 Oct, `9b4ffe6`)** after CI run #8 was green on `17f883b`
  (40 passed, 2 network skips). Day 2 work continues on `feat/graph-api`.
- Git repo, `.gitignore`, `.gitattributes`; `main` pushed.
- Day 1 on `feat/ingest` (pushed):
  - uv project in `backend/` (Python 3.12), `docker-compose.yml` (db on host 5433, api on 8000),
    `backend/Dockerfile` (non-root, git installed), `.env.example`.
  - `backend/schema.sql`: design section 6 tables + `snapshot_status` view (with `job_id`).
  - `app/ingest/redact.py`: line-preserving redaction; returns `SecretMatch(line, kind)`, never the value.
  - `app/ingest/discover.py`: skip rules (secret files, venvs, vendor/build dirs, binaries, >1 MB),
    `MAX_FILES` cap, CRLF normalised, content redacted.
  - `app/ingest/parse.py`: Tree-sitter 0.25.2 Python parser -> module/class/function/method symbols.
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

- **Day 2 task 1 done (27 Oct, `feat/graph-api`): separate test database.**
  - `tests/conftest.py`: DB tests read `TEST_DATABASE_URL` only; `DATABASE_URL` is removed from the
    environment at pytest start. A name not ending in `_test` is a hard error (`UsageError`); unset
    means DB tests skip locally but is an error when `CI` is set. Session fixture `test_db` drops and rebuilds `public` from `schema.sql`.
  - `db-init/02-test-db.sql` creates `repolens_test` on fresh volumes (checked with a throwaway
    container); existing volume: `docker compose exec -T db createdb -U repolens repolens_test`.
  - CI service DB is `repolens_test` via `TEST_DATABASE_URL`; the psql schema step is gone.
  - `tests/test_db_guard.py` (7 cases). Local: **47 passed, 2 skipped** (network); with
    `TEST_DATABASE_URL` pointing at `repolens` pytest stops with the guard error; dev DB kept its
    41 files after a run with `DATABASE_URL` set to it.
- **Day 2 task 2 done (27 Oct): discover JS/TS + `unresolved` symbol kind.**
  - `discover.py` keeps `.js .jsx .mjs .cjs` (`javascript`) and `.ts .tsx` (`typescript`); the
    parser will pick the tsx grammar by suffix. Skips `*.min|.bundle|.chunk` + JS suffix,
    `bower_components/`, `.next/`, `coverage/`, and JS/TS files with a line > 5000 chars or an
    average line > 300 chars (Python is never skipped for long lines).
  - The parse stage still only parses `language = 'python'`; JS/TS files are stored, not parsed yet.
  - `schema.sql`: symbol kind `unresolved` (`file_id` NULL, `qualified_name` = specifier) with a
    unique index per snapshot + name. Dev DB got the index with one `CREATE UNIQUE INDEX`; data kept.
  - Tests: 3 new discover tests. Local: **50 passed, 2 skipped** (network).
- **Process (27 Oct):** CI errors if `TEST_DATABASE_URL` is missing; local `.env` has it. CLAUDE.md:
  no local PostgreSQL (db stays on host 5433); feature branches are pushed after each commit, ask
  only before merging into `main`.

## Next
- Scope change (27 Oct, `7233e27`): Python and JS/TS both get full analysis; CLAUDE.md updated.
- Day 2: task 3 of the Day 2 plan below (parsers return symbols, imports and calls; `parse_js`).
- Running tests locally: `uv run --env-file ../.env pytest` (`.env` has `TEST_DATABASE_URL`).

## Day 2 plan
Approved 27 Oct. Each task ends with: run it, show the result, commit, update this file, stop.

1. **Separate test database.**
   - `tests/conftest.py` reads `TEST_DATABASE_URL` only, never `DATABASE_URL`.
   - Hard error (not skip) unless the database name ends in `_test`.
   - At session start it rebuilds the schema from `schema.sql`, so tests always see the current schema.
   - `db-init/02-test-db.sql` creates `repolens_test` on fresh volumes; on the existing volume,
     create it once with `createdb`.
   - CI uses `repolens_test` via `TEST_DATABASE_URL`; the separate psql schema step goes away.
   - `.env.example` gets `TEST_DATABASE_URL`. Test for the name guard.
2. **Discover JS/TS + schema for unresolved imports.**
   - Keep `.js .jsx .mjs .cjs .ts .tsx` (tsx parsed with the tsx grammar).
   - Skip `*.min.js`, `*.bundle.js`, `*.chunk.js`, and minified files detected by very long lines
     (`dist/` and `node_modules` are already skipped).
   - New symbol kind `unresolved`: one per import specifier per snapshot, `file_id` NULL, so an
     unresolved import is still an edge (edges must point at a symbol). Dev DB needs only one
     `CREATE INDEX`; no data loss.
3. **Parsers return symbols, imports and calls.**
   - `parse_python` returns `ParsedFile(symbols, imports, calls)`.
   - New `parse_js` with the same output. Symbols: module, class, function (including top-level
     `const f = () =>`), method.
   - JS imports from `import` / `export ... from`, `require('x')`, and `import('x')` with a literal.
   - Add JS/TS files to the fixture repo: `require`, `index`, `.js` -> `.ts`, a tsconfig alias.
4. **Python import resolution + new `edges` stage.**
   - Module map from file paths, including `src/` layouts; relative imports; `from pkg import name`
     tries module `pkg.name` first.
   - Not found internally -> `external`; relative import with no matching file -> `unresolved`.
   - Stage does delete-then-insert for edges plus external/unresolved symbols.
   - Show edge counts on itsdangerous.
5. **JS/TS import resolution, then the JS checkpoint.**
   - Extension and `index` probing; TS-style `./x.js` maps to `x.ts`; `node:fs` and bare package
     names -> `external`.
   - tsconfig `paths` from the root `tsconfig.json` only, and only when each pattern has one `*` and
     one target; anything else -> `unresolved`.
   - Checkpoint done right after this task, not at end of day: ingest one small real JS repo and one
     small TS repo. Candidates: `expressjs/express` (CommonJS) and `sindresorhus/ky` (TS); check
     sizes first.
   - **Hand-check ~20 edges from source files (`lib/`, `src/`), not tests.**
   - If it fails: JS/TS drops to symbols-only, recorded here.
6. **Call edges, both languages.** Name-based, with confidence:
   - **1.0** callee defined in the same file or explicitly imported.
   - **0.9** `self.m()` / `this.m()` calling a method in the same class.
   - **0.5** unique name match elsewhere in the snapshot.
   - Ambiguous names: no edge.
7. **Graph and file APIs.**
   - `GET /snapshots/{id}/graph`: file nodes, import and call edges with weights.
     **Unresolved and external nodes are hidden by default; each file shows only per-file counts of
     its external and unresolved imports.**
   - `GET /snapshots/{id}/files/{file_id}`: content, symbols, findings.
   - `/symbols/{id}/dependents` and `/symbols/{id}/dependencies` (design doc paths); for a module
     symbol they cover the whole file.
   - DB tests on the fixture repo.
8. **Web shell (`web/`).**
   - Vite React TS, TanStack Query, React Router.
   - Home (URL input); snapshot page polls status and shows stage, percent, error.
   - Light-theme CSS variables. Vite proxies `/api` to the API (no CORS).
   - `web` service in compose for the demo; day to day `npm run dev` natively.
9. **Graph view + node panel.**
   - React Flow (`@xyflow/react`) with dagre for layout (React Flow does not position nodes).
   - Node panel: code (plain `<pre>` with line numbers) and "Used by" / "Uses".
   - End of Day 2: end-to-end run, push, green CI, then ask before merging.

Plan decisions:
- New dependencies: `tree-sitter-javascript` 0.25.0 and `tree-sitter-typescript` 0.23.2 (both load
  and parse on the pinned tree-sitter 0.25.2); frontend `@xyflow/react`, `@tanstack/react-query`,
  `react-router-dom`, `@dagrejs/dagre`. No highlighter or UI kit.
- `unresolved` as a symbol kind is the smallest schema change that lets an unresolved import be an edge.
- If time runs short, task 6 (call edges) shrinks first: same-file and explicitly imported calls only.

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
- `hardcoded-secret` is noisy on test code (placeholder keys in `tests/`). Consider lower severity
  for test paths when the Day 3 detectors land.
- Fixture tests do not reproduce the 0.26.0 crash (only bigger files did); the pin is the guard.
  Re-check before ever lifting it.
- `httpx` with Starlette TestClient emits a deprecation warning (suggests `httpx2`); harmless for now.
- Git for Windows `autocrlf` converts working copies to CRLF; repo stores LF. `.sh` files forced LF.
