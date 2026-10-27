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
- **Day 2 task 3 done (27 Oct): parsers return symbols, imports and calls.**
  - `parse_python` returns `ParsedFile(symbols, imports, calls)`. `ParsedImport(specifier, names,
    line)`: specifier as written (`.models`, `os.path`, `./lib`); names are `(imported, local)`
    pairs, imported `*` = whole module bound to local, local `*` = star import. `ParsedCall(caller,
    name, receiver, line)`: caller = innermost enclosing symbol; receiver None for `f()`, the dotted
    text for `x.f()` / `self.f()` / `this.f()`, `''` when the receiver is not a plain name.
    Decorator calls are now visited.
  - New `app/ingest/parse_js.py` (`parse_js`): grammar by suffix (.ts typescript, .tsx tsx, else
    javascript). Symbols: module, class (incl. abstract), function (declarations, generators,
    top-level `const f = () =>` / function expressions), method. JS qualified names: module = path,
    members `path:Name`, `path:Class.method`. Imports: `import`, `export ... from`,
    `require('x')` (with `const x` / `{a, b: c}` bindings), `import('x')`, literal strings only.
    Calls include `new X()`; `require` / `import()` are not calls.
  - Parse stage stores symbols for Python and JS/TS; imports/calls are stored by the edges stage
    (task 4).
  - Fixture repo: root `tsconfig.json` (`@lib/*` alias) + `web/src/` (app.ts, view.tsx, util.js,
    legacy.cjs, lib/index.ts, lib/math.ts) covering require, index, `.js`->`.ts`, alias,
    export-from, dynamic import, an unresolved `./missing`; `sample_app/__init__.py` got two
    relative imports.
  - Deps: `tree-sitter-javascript` 0.25.0, `tree-sitter-typescript` 0.23.2 (on tree-sitter 0.25.2).
  - Tests: 61 passed, 2 skipped (network). Crash check: all 98 JS/TS files of
    `sindresorhus/ky` parsed 15 times, no crash (1003 symbols, 311 imports per pass).
  - `test_db` connects with `connect_timeout=5`, so a stopped database fails fast instead of hanging.
- **JS CommonJS symbols (27 Oct, before task 4).** Top-level only:
  - `x.y = function name() {}` / `x.y = () => {}` (incl. `exports.y`, `module.exports.y`,
    `app.listen`, `res.send`, `View.prototype.render`) -> function named `x.y`.
  - `module.exports = function name() {}` -> function `name` (anonymous: `module.exports`).
  - Object literals assigned at top level (`module.exports = { a() {}, b: function () {},
    c: () => 1 }`, `const api = {...}`) -> methods `module.exports.a`, `api.b`, ...; shorthand
    properties are references, not symbols.
  - Calls inside get the new symbol as caller. Fixture `web/src/server.js`; express `lib/` now gives
    70 function symbols (was 7). Tests: 65 passed, 2 skipped.
  - Fixture `tsconfig.json` no longer has `baseUrl` (covers the no-baseUrl alias case, task 5).
- **Day 2 task 4 done (27 Oct): Python import resolution + `edges` stage.**
  - `app/ingest/resolve.py`: `PythonModules` maps dotted names to paths for the repo root and every
    source root (parent of a top-level package: `src/`, `backend/`, `tests/` when it holds a
    package); `.py` wins over `.pyi`. `resolve_python` handles relative imports (incl. `__init__`
    packages and too many dots), `from pkg import name` tries `pkg.name` first, then `pkg`.
  - Missing -> `external` keyed by top-level package (`os.path` -> `os`). Missing relative import,
    or a missing submodule of one of our own packages (`sample_app.gone`) -> `unresolved` (the
    plan said external for the latter; that would label our own code third-party).
  - `edges` stage (after parse, 85%): one transaction deletes the snapshot's import edges and
    external/unresolved symbols, re-inserts them, one edge per (file, target), self-imports
    dropped. Parse stage now returns its results so files are not parsed twice. JS/TS imports are
    not resolved yet (task 5).
  - Fixture: `broken.py` gained two unresolvable imports. Tests: 72 passed, 2 skipped (7 resolver
    unit tests + exact edge list in the DB test).
  - **itsdangerous @ `672971d`** (dev DB re-ingested, snapshot 3): status done; import edges
    **36 internal, 39 external, 0 unresolved**; 18 external packages (base64 ... zlib, pytest,
    freezegun). Hand-checked 22 edges of `src/itsdangerous/__init__.py`, `url_safe.py` and
    `tests/test_itsdangerous/test_timed.py` against the source: all correct
    (`from __future__` is not an import edge).
- **Day 2 task 5 done (27 Oct): JS/TS import resolution + JS checkpoint PASSED.**
  - `resolve.py` `JsModules` / `resolve_js`: relative imports with extension probing
    (`.ts .tsx .js .jsx .mjs .cjs .d.ts`), `index.*`, TS-style `./x.js` -> `x.ts`/`x.tsx`; a path that
    normalises to the repo root (`require('../..')`) finds root `index.*`; outside the repo ->
    unresolved. Asset imports (`.css`, `.svg`, `.json`, ...) get no edge.
  - Root `tsconfig.json` `paths` (JSONC tolerated): one `*` and one target with one `*`, else
    unresolved; exact (no-`*`) patterns match only themselves; longest prefix wins. Targets resolve
    against `baseUrl` when set, else the tsconfig's directory. With `baseUrl`, bare names are tried
    under it first.
  - Bare specifiers -> external by package (`@scope/pkg/x` -> `@scope/pkg`, `lodash/fp` -> `lodash`,
    `node:fs` -> `fs`); not a valid npm name (`@/x`, `~/x`) -> unresolved.
  - Edges stage now resolves both languages. Tests: 80 passed, 2 skipped (8 JS resolver tests incl.
    a `baseUrl` case; DB test checks all 11 fixture JS/TS edges).
  - **Checkpoint (real repos, dev DB):**
    - `expressjs/express` @ `1c6f1b0` (CommonJS, 142 JS files): first run had 96 unresolved, all
      `require('../..')` to the root `index.js` (bug: `./index.js` vs `index.js`), fixed. Now
      **154 internal, 244 external, 0 unresolved**. Hand-checked every `require` in `index.js` and
      all 6 `lib/*.js` files: **53/53 edges correct**; 3 `require`s with no edge are inside JSDoc
      examples (correct).
    - `sindresorhus/ky` @ `3541888` (TS, ESM, `.js` specifiers): **182 internal, 121 external,
      0 unresolved**. Checked `source/index.ts`, `core/Ky.ts`, `utils/merge.ts`, `utils/options.ts`,
      `errors/HTTPError.ts` against their imports: **50/50 correct** (multi-line imports included;
      one `from 'ky'` with no edge is in a JSDoc `@example`).
    - Result: JS/TS keeps full analysis (no fallback to symbols-only).
- **Day 2 task 6 done (27 Oct): call edges, both languages** (`app/ingest/calls.py`, pure).
  - 1.0: `f()` defined in the same file (if several, the single top-level one) or explicitly
    imported (one re-export hop: package `__init__`, `export {x} from`); `X.f()` with `X.f` in the
    same file (`User.create()`, express `app.set`); `mod.f()` with `mod` an imported module of ours
    (`import * as m`, `require`, `import pkg.mod`; CommonJS `exports.f` counts).
  - 0.9: `self.f()` / `this.f()` / `cls.f()` hitting the caller's own class or JS object.
  - 0.5: exactly one candidate in the snapshot, same language. Plain calls match only
    functions/classes, `x.f()` only methods. For `x.f()`: no guess when `x` is not a plain name or
    is a JS global (`Object.create`), and a JS object member (`app.set`, `View.prototype.render`)
    needs the receiver to name the owner (`this.app.set()`). Class methods match any receiver.
  - Ambiguous, external, recursion: no edge. One edge per (caller, callee), highest confidence.
  - Stored by the edges stage (same transaction as imports, `type='calls'`).
  - Tests: 88 passed, 2 skipped (8 call tests incl. the exact 14 fixture call edges).
  - Real repos (dev DB re-ingested): express snapshot 7: calls 63 @1.0, 34 @0.9, 243 @0.5;
    itsdangerous snapshot 8: 52 / 22 / 8. Before the receiver/owner rule express had 335 @0.5
    with wrong links like `Object.create` -> `examples/.../exports.create`, `arr.map` ->
    `examples/route-map:app.map`. All express `lib/` edges read correctly; the 4 remaining
    `lib/` 0.5 edges match the source (`app.handle`, `app.init`, `req.accepts`,
    `this.app.enabled`), and a random 12 of the test/example 0.5 edges are real calls into
    express. ky (snapshot 5) was ingested before this change and has no call edges until
    re-ingested.
- **Day 2 task 7 done (27 Oct): graph and file APIs** (`app/api/graph.py`).
  - `GET /snapshots/{id}/graph?min_confidence=0.9&exclude_tests=true`: nodes = code files (id,
    module `symbol_id`, path, language, loc, `external_imports` / `unresolved_imports` counts,
    `findings` count); external/unresolved are never nodes. Edges = one per (file -> file) pair:
    `import` (bool), `calls` (count of call edges >= min_confidence), `weight` = import + calls,
    `confidence` = 1.0 with an import, else the best call confidence (so guess-only pairs can be
    drawn dashed). Same-file edges left out. `exclude_tests` hides `test/`, `tests/`,
    `__tests__/`, `examples/` (any depth), `*.test.*`, `*.spec.*`; `hidden_files` says how many.
    404 unknown snapshot, 409 not done, 422 min_confidence outside 0..1.
  - `GET /snapshots/{id}/files/{file_id}`: content (redacted), symbols, findings, names of
    external and unresolved imports.
  - `GET /symbols/{id}/dependents` / `dependencies` (`min_confidence`, default 0.9 like the graph;
    tests are not hidden here): items `{type, confidence, symbol{...path}}`, deduped, plus a
    `files` count. For a module symbol they cover the whole file and skip same-file edges.
  - Confidence is REAL (0.9 is stored as 0.8999...), so filters and output use it rounded to 2
    decimals.
  - Fixture: `tests/check_service.py` (not `test_*`, so pytest never collects it) and
    `web/src/lib/math.spec.ts` exercise `exclude_tests`. The `client` fixture and `query` moved
    to `conftest.py`. Tests: 98 passed, 2 skipped (10 API tests).
  - express (snapshot 7): default graph 7 nodes / 7 edges (`index.js` + `lib/`, 135 test and
    example files hidden) in 43 ms; `exclude_tests=false&min_confidence=0.5`: 142 nodes, 291 edges,
    137 of them guess-only (dashed).

## Next
- Scope change (27 Oct, `7233e27`): Python and JS/TS both get full analysis; CLAUDE.md updated.
- Day 2: task 8 of the Day 2 plan below (web shell).
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
     one target; anything else -> `unresolved`. Targets resolve against `baseUrl` when set,
     otherwise against the tsconfig.json's own directory (fixture has no `baseUrl`; a tmp_path
     unit test covers `baseUrl`).
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
- Discover stores Python, JS/TS and common text/config files (md, rst, txt, toml, cfg, ini, yaml,
  json, sh) so secrets in config are reported; Python and JS/TS are parsed, the rest is text only.
- **Secrets:** redaction matches become `findings` rows (`rule_id='hardcoded-secret'`, severity high,
  masked snippet) in the discover stage. The Day 3 detect stage must delete/insert only its own
  rule ids and leave `hardcoded-secret` alone.
- Re-submitting a URL whose commit has a queued/running/done job returns that job; a failed one
  starts a new job. No GitHub API size check (would need a token); file/size/time caps instead.
- Unexpected pipeline errors show only "Internal error during <stage>." (log has the exception type).
- Local dev on this 8 GB RAM laptop: only the `db` service runs in Docker; the API runs natively
  with `uv run uvicorn`. The full compose stack (`db`, `api`, later `web`) is kept for the demo.

## Known issues
- `exclude_tests` uses only the agreed patterns; Python `test_*.py` / `*_test.py` outside a
  `tests/` folder are not hidden.
- Calls made inside anonymous callbacks (`it(...)`, `forEach(function () {...})`) get the
  enclosing named symbol, often the module, as caller. Fine for the file-level graph.
- Call edges never use star imports (`from x import *`, `export * from`).
- PyPI fetches sometimes time out on this network (`uv add` failed once); `UV_HTTP_TIMEOUT=180` worked.
- Docker Desktop can stop on its own; if DB tests error on connect, start it and `docker compose up -d db`.
- JS member assignments and object-literal methods become symbols only at top level, not inside
  functions (e.g. `function setup(app) { app.get = ... }` is not a symbol).
- `hardcoded-secret` is noisy on test code (placeholder keys in `tests/`). Consider lower severity
  for test paths when the Day 3 detectors land.
- Fixture tests do not reproduce the 0.26.0 crash (only bigger files did); the pin is the guard.
  Re-check before ever lifting it.
- `httpx` with Starlette TestClient emits a deprecation warning (suggests `httpx2`); harmless for now.
- Git for Windows `autocrlf` converts working copies to CRLF; repo stores LF. `.sh` files forced LF.
