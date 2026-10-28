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
- **Day 2 task 8 done (27 Oct): web shell** (`web/`, Vite 8 + React 19 + TypeScript 7,
  TanStack Query, React Router; fonts self-hosted via `@fontsource`, so no Google Fonts call).
  - Home (`/`): URL field with live validation (check when valid, specific message after blur,
    server message kept under the field), limits caption, example chips for the three tested repos
    (itsdangerous, express, ky), "Recent analyses (this browser)" from localStorage with live
    status. Copy claims only what exists (the graph); no findings/Q&A/About/theme toggle yet.
  - Progress (`/a/:id`): `owner/repo @ sha`, a status line (aria-live, changes per stage, not per
    percent tick), a ledger of the four real pipeline stages. Only parse shows a number
    (stage-relative). Slow note after 60s in one stage; failure callout with the server's message,
    Retry (resets the cached status so polling restarts on the same id) and a link home; 404 page
    for unknown ids. 4xx responses are not retried.
  - Spec §8.2 tokens as CSS variables in `web/src/styles.css`, light only. Authored line icons
    (5 glyphs), no icon library.
  - Vite proxies `/api` to FastAPI (`API_URL`, default `http://127.0.0.1:8000`). `web` service in
    compose (dev server, non-root; `/app` owned by `node` so Vite can write its temp config).
    Checked: image builds (69 s), container proxies `/api/health` and serves `/a/9`.
  - Design process (impeccable skill, as asked): `PRODUCT.md` from the docs (confirmed), surface
    brief with direction contract in `.impeccable/surfaces/`, detector clean, finish review found
    5 material issues (fake per-stage percent, dead Retry on the same snapshot id, wrong retry
    caption, redundant "done", missing slow state), all fixed and re-scored.
  - Checked live in the in-app browser: invalid URL, server rejection, a new repo
    (`pallets/markupsafe`, `pallets/click`) running to done, recent list, 404, a forced failed job
    retried to done, 375 px width (recent rows stack).
  - `exclude_tests` also hides Python `test_*.py` / `*_test.py`.
  - Day to day: `npm run dev` in `web/` with the API on :8000; `npm run build` type-checks.
- **Day 2 task 9 done (27-28 Oct): Explorer (graph view + node panel)**, `/a/:id/explore`
  (lazy-loaded; React Flow 12 + dagre 3).
  - Toolbar: Graph/List, "Show test files" (`exclude_tests`), "Show guessed calls"
    (`min_confidence=0.5`), Fit, and a note ("N files · M test files hidden", or "Showing 300 of
    415 files, the most connected. List view shows all."). State in the URL (`tests`, `guesses`,
    `view`, `node`).
  - Graph: file nodes (name over folder, `py`/`js`/`ts` mark), edges point at the file used;
    guesses (confidence < 0.9) dashed, legend with the spec microcopy. Render cap 300, keeping the
    most connected files. dagre layers taller than 24 wrap into columns. First view fits the
    whole graph only when names stay readable (zoom >= 0.8), else frames the hub and its
    neighbours; Fit shows everything. Selecting a file centres it beside the panel; focus mode
    dims the rest.
  - List view: every file (never capped) with uses / used by / external / unresolved; phones
    (< 768px) get the list only with "The graph view needs a larger screen."
  - Node panel: path, language, lines; Used by / Uses / External / Unresolved counts; tabs Code
    (line numbers), Used by, Uses (grouped by file, external/unresolved tagged, guesses marked).
    Esc or x closes; focus moves in on open and back to the opener on close. Queries keyed per
    node and cancelled on switch, so a slow answer never lands in another node's panel.
  - Progress: a watched run shows "Analysis complete." + "Open graph" and opens the graph after
    1.2s (replacing the Progress entry, so Back leaves the analysis); opening a finished `/a/:id`
    goes straight to the graph.
  - Network: connection errors (fetch failure, proxy 502/503/504) retry with backoff 1-10s,
    forever, and show "Connection lost, reconnecting…" while keeping the last data; React
    Query pauses offline and resumes on reconnect. "Analysis failed" only from the server.
  - Error boundary around all routes (resets on navigation). 4xx are never retried.
  - Backend: a fetch that fails with a network error or timeout is retried once on a clean
    workspace if a full attempt still fits before the deadline (`CloneError.transient`).
  - `--node-external` #a1a1aa -> #71717a (4.8:1); new `--edge` #8a8a93 (3.4:1). DESIGN.md has
    the graph tokens, Explorer components and the 900/767/560 breakpoints.
  - Live checks (Playwright at 1440x900, 820, 390): express default and with both toggles,
    itsdangerous with panel and Uses tab, list view, psf/black (503 files kept, 415 parsed:
    55 shown by default, cap 300 of 415 with tests), API stopped mid-session (reconnecting, then
    recovered without reload, backoff 1/2/4/8/10s), Back after auto-open, focus in/out.
    Production build renders black's capped graph in ~2.0s.
  - Design review (impeccable finish reviewer): first pass asked for mobile/tablet/complete
    captures and found spec §10 phone list-only missing and page overflow on phones (fixed);
    second pass found unreadable default zoom, selection hidden behind the panel, Back bouncing,
    panel focus (all fixed).
  - Tests: 108 passed, 2 skipped (fetch retry: transient classification, retried once, not for
    other errors, not without time left).
- **Day 3 task 1 done (28 Oct, `feat/detectors`): detect stage + Python rules.**
  - `app/detect/rules.py`: rule catalogue (id, language, severity, label, what it looks for, why
    it is risky, possible-false-positive hint), including `hardcoded-secret`. `app/detect/python.py`:
    one Tree-sitter walk for `py-eval-exec` (builtins only, not `obj.eval()`), `py-subprocess-shell`
    (`subprocess.*`, aliases and `from subprocess import …`, with `shell=True`), `py-sql-string`
    (f-string, `+`, `%`, `.format()` with a non-constant part), `py-bare-except`.
  - SQL shape: the string must start with the statement (any case) or use upper-case keywords, so
    prose like "select an item from the list" is not SQL (the negative fixture caught this).
  - New pipeline stage `detect` (after `edges`, 90%): re-parses each code file, stores line,
    innermost enclosing symbol, rule severity and label, and the redacted line as snippet;
    delete-then-insert only for detector rule ids. Progress page lists "Running detectors".
  - `hardcoded-secret` in a test path (shared `app/paths.is_test_path`, same as `exclude_tests`) is
    severity low with "… in a test file."
  - Fixtures `tests/fixtures/detectors/py_positive.py` / `py_negative.py` with `# expect: <rule>`
    marks; tests compare exact (line, rule) sets. DB test ingests the fixtures as a repo.
    Fixture tsconfig now uses `./web/src/lib/*` (no baseUrl); resolver tests cover `./` targets.
  - Tests: 125 passed, 2 skipped.
  - Real repos (re-ingested): itsdangerous, requests, flask-sqlalchemy: 0 detector findings.
    psf/black: 17, all hand-checked as genuine matches of their rule: 9 bare `except:` and 7
    `eval`/`exec` in test data (deliberately odd code that black formats), plus
    `src/blib2to3/pgen2/pgen.py:100` `value = eval(label)` in source. No real-repo SQL hits yet;
    the SQL rule is covered by the fixtures.
- **Day 3 task 2 done (28 Oct): JS/TS rules** (`app/detect/javascript.py`, grammar by suffix).
  - `js-eval` (global `eval(...)`), `js-new-function` (`new Function(...)` and `Function(...)`),
    `js-child-process-exec` (`exec`/`execSync` bound to `child_process` / `node:child_process`
    via require, destructuring, aliases, namespace/default/named imports or inline
    `require("child_process").exec`, with a non-constant command), `js-inner-html` (`=` or `+=`
    to `.innerHTML`/`.outerHTML` with a non-constant value), `js-sql-string` (template with `${}`
    or `+` with a SQL-shaped literal). Unrelated `exec` (regex, DB driver) is not flagged.
  - "Constant" means a string, a template without `${}`, or a `+` chain of only those (jQuery's
    test files caught `"<style>" + "..."` being flagged; fixed and added to the negative fixture).
  - Fixtures `js_positive.js` (CommonJS), `ts_positive.ts` (ESM, TS syntax), `js_negative.js`.
    Tests: 130 passed, 2 skipped.
  - Real repos: express and ky have 0 findings. A grep of their source for every rule pattern
    finds only strings (an XSS payload in `test/res.redirect.js`, `waitForFunction` in ky), so
    no misses. jquery/jquery @ HEAD (222 code files): 8 findings, all genuine: `innerHTML` in
    `src/manipulation.js:276` and `src/manipulation/buildFragment.js:47` (by design: `.html()`),
    the same in the vendored `test/data/jquery-3.7.1.js` (3), and 3 `eval` calls in tests.
- **Day 3 task 3 done (28 Oct): findings API** (`app/api/findings.py`).
  - `GET /snapshots/{id}/findings` with filters `severity`, `rule`, `language`, `path_prefix`,
    `in_test`, and `limit` (default 50, 1..200, else 422) / `offset`. Response:
    `{snapshot_id, total, limit, offset, items, counts}`. Items: id, rule_id, severity, message,
    file_id, path, language, line, `symbol` (name, null at module level), masked snippet,
    `in_test`, `node_id` (finding's symbol, else the file's module symbol, for "Open in Explorer").
  - Order: severity rank via CASE (high, medium, low), then path (`COLLATE "C"`), line, id.
  - `counts` (total, by_severity, by_rule) are over the whole snapshot, not the filter.
  - 404 unknown snapshot; 422 bad severity / unknown rule / language / limit / offset; 409 with
    the reason while detection has not finished ("…not finished yet (current stage: parse)") or
    if the analysis failed ("Detection did not run: the analysis failed during fetch."), never
    an empty list that reads as "no findings".
  - `GET /rules`: the catalogue from `app/detect/rules.py` (id, language, severity, title, checks,
    why, false_positive).
  - Schema: `findings.in_test` (set when stored, same rule as `exclude_tests`); dev DB got one
    `ALTER TABLE`. Index `findings_snapshot (snapshot_id, severity)` was already there.
    Test-file findings are included by default and marked.
  - Tests (detector fixtures as a repo): order, pages of 7 neither overlap nor skip, each filter,
    counts ignore filters, node_id fallback, 422/404/409, raw fixture secret never in any
    response. 151 passed, 2 skipped.
  - Real snapshots (re-ingested): itsdangerous 7 findings, all `hardcoded-secret` in `tests/`
    (low, `in_test`; were high on Day 1); express 1 (placeholder password in
    `examples/auth/index.js`, low, `in_test`).
  - Follow-up fixes: the message says "... in test or example code." (examples/ counts as test
    code, so "in a test file" was wrong). All dev snapshots were re-run in place (same ids) so
    none has stale `in_test` values; the bogus `example/broken` snapshot was deleted.
- **Day 3 task 4 done (28 Oct): chunks + embeddings** (`app/qa/chunks.py`, `app/qa/embed.py`,
  `embed` stage in the pipeline, 92–99%).
  - Model `sentence-transformers/all-MiniLM-L6-v2`, revision pinned in `app/config.py`
    (`EMBED_MODEL_REVISION=1110a243fdf4706b3f48f1d95db1a4f5529b4d41`), 384 dims, CPU only.
    **`max_seq_length` is 256 word pieces, checked in code** (`model.max_seq_length`; the embedder
    refuses to start if the dimension is not 384). Every job logs `model@revision` with its stats
    so eval runs can report them.
  - Chunks: one per function, method and class (class = header up to its first method; nested
    functions stay inside their enclosing function), plus module-level chunks: one per contiguous
    run of top-level code (lines outside every function/class), so a file can have several.
    Text only from the redacted `files.content`. Blank edge lines trimmed.
  - Embedded text = `"{path} {qualified_name}\n" + code`. Tokens counted with the model's own
    tokenizer (special tokens included). A unit over 256 tokens is split into line windows with
    3 lines of overlap, each with its own start/end lines; each window's exact count is re-checked
    and shrunk if needed; a single line too long on its own is cut.
  - Vectors normalized; cosine `<=>`; exact scan scoped to `snapshot_id`, no HNSW. Model loads
    once per process; encode in batches of 64; delete-then-insert in one transaction.
    `chunks` gained `start_line`, `end_line`, `token_count`; `search_tsv` holds identifier parts
    (`getUserById` -> get user by id) for the stretch hybrid retrieval.
  - Dependencies: first an optional extra `embed`; replaced the same day (see "Task 4
    follow-ups" below) by a default dependency group. torch comes from the explicit
    `pytorch-cpu` uv index (CPU wheels, no CUDA). Tests and CI use `EMBEDDER=stub` (hashing
    embedder, design §19.4). Real-model test: `RUN_MODEL_TESTS=1 uv run pytest -k real_model`.
  - Tests: unit ranges, windows within budget with overlap and no gaps, JS units, DB rows valid
    (ranges match file lines, ≤256 tokens, 384-dim unit vectors, no raw secret), cosine search
    scoped to the snapshot, rerun replaces rows. 159 passed, 3 skipped.
  - Real runs (both jobs ran at the same time, so times include CPU contention):

    | repo | chunks | windows | units split | of which functions/methods/classes | max tokens | embed time |
    |---|---|---|---|---|---|---|
    | expressjs/express | 1219 | 852 | 148 | 30 (18 in tests) | 256 | 83.1 s |
    | pallets/itsdangerous | 181 | 38 | 13 | 12 (3 in tests) | 251 | 19.4 s |

    No chunk over 256 tokens, no bad line ranges. Express: 1053 of 1219 chunks are in `test/`
    (mocha `describe`/`it` callbacks are top-level code), and 118 of its 148 split units are
    module-level runs in test files.
- **Task 4 follow-ups (28 Oct).**
  - Token limit re-checked with the tokenizer itself (`len(tokenizer(text)["input_ids"])`,
    [CLS]/[SEP] included) on every stored chunk of express and itsdangerous: max 256 and 251,
    none at 257–258, every stored `token_count` equal to the recount. No window change needed.
    The real-model test now asserts the same per chunk.
  - `chunks.in_test` (same rule as `findings.in_test`, `app/paths.is_test_path`), stored at write
    time, so retrieval can leave test code out in SQL (`AND NOT in_test`). Dev DB got one
    `ALTER TABLE`; the express/itsdangerous chunks predate it (all `false`) until re-run.
  - Embedding packages are a **default dependency group** `embed` (`[tool.uv] default-groups =
    ["dev", "embed"]`, uv 0.11.14). Plain `uv sync` / `uv run` installs them, so the
    `--extra embed` trap is gone: run the API with
    `uv run --env-file ../.env uvicorn app.main:app --port 8000`. CI sets `UV_NO_GROUP=embed`
    (applies to `uv run` too) and `EMBEDDER=stub`, so torch and the model are not even installed
    there. Checked locally both ways (without the group: neither installed, suite green; plain
    sync: torch 2.14.1+cpu back).
  - api `Dockerfile`: `uv sync --locked --no-dev` (keeps the embed group; the lock resolves Linux
    torch to `2.14.1+cpu`, no `nvidia-*` packages); downloads the pinned model revision at build
    time into `HF_HOME=/opt/hf`, then sets `HF_HUB_OFFLINE=1`; runs as uid 1000 `repolens`.

## Next
- Scope change (27 Oct, `7233e27`): Python and JS/TS both get full analysis; CLAUDE.md updated.
- **`feat/graph-api` merged into `main` (28 Oct, `0c514d2`)** after CI was green on `5111572` and
  on `main` (108 passed, 2 skipped). Includes the user's logo mark and favicons.
- Day 3 on `feat/detectors`: merge into `main` when approved, then task 5 (`/ask`). Full
  `docker compose up` check is Day 4.
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

## Day 3 plan
Approved 28 Oct with these changes (they override the task text below where they differ):
- `react-markdown` yes; never add `rehype-raw` (no raw HTML, ever).
- Token cap 200k tokens per snapshot.
- `hardcoded-secret` in a test path (same rule as `exclude_tests`) is severity low, and its message
  says it is in a test file.
- No similarity threshold to skip the LLM unless it is calibrated: skip the LLM only when the
  snapshot has no chunks; otherwise the grounding prompt handles "could not find".
- Chunk windows stay within the embedding model's input limit (check `max_seq_length` of
  all-MiniLM-L6-v2 and record it here).
- 1-hop graph expansion is a config switch (for the Day 4 with/without comparison).
- Task 5 adds the prompt-injection fixture file for the smoke eval.
- Fixture tsconfig: `paths` targets use a leading `./` without `baseUrl` (`"./web/src/lib/*"`); the
  resolver must handle it.

Original draft (28 Oct): Order from CLAUDE.md: detectors + findings API, then Q&A
(chunks, embeddings, /ask), then the UI panels. Each task ends with: run it, show the result,
commit, push, check CI, update this file, stop.

1. **Detect stage + Python rules** (`app/detect/`, new pipeline stage after `edges`).
   - Re-parse each code file's redacted content with Tree-sitter (the parse stage keeps no trees;
     re-parsing is cheap). Each rule: id, language, severity, label, what it looks for, why it is
     risky, "possible false positive if…". Finding = file, line, enclosing symbol, masked snippet.
   - Delete-then-insert only its own rule ids; `hardcoded-secret` (discover stage) is untouched.
   - Python rules:
     - `py-eval-exec` (high): calls to the builtins `eval(...)` / `exec(...)`; `obj.eval()` is not
       flagged.
     - `py-subprocess-shell` (high): `subprocess.*(..., shell=True)`, including `from subprocess
       import run` and aliases.
     - `py-sql-string` (high): a SQL-shaped literal (`SELECT … FROM`, `INSERT INTO`, `UPDATE … SET`,
       `DELETE FROM`) built with an f-string, `+`, `%` or `.format(...)` with a non-literal part.
     - `py-bare-except` (low): `except:` with no exception type.
   - Fixtures: `tests/fixtures/detectors/` with positive and negative samples per rule (committed,
     never executed); one test per rule that checks the exact lines it reports.
2. **JS/TS rules** (same stage).
   - `js-eval` (high): `eval(...)`; `js-new-function` (high): `new Function(...)`.
   - `js-child-process-exec` (high): `exec` / `execSync` bound to `child_process` (require or
     import, incl. `cp.exec`, destructured and aliased) with a non-literal first argument.
   - `js-inner-html` (medium): assignment to `.innerHTML` / `.outerHTML` with a non-literal value.
   - `js-sql-string` (high): SQL-shaped template literal with `${}`, or `+` concatenation with a
     SQL-shaped literal.
   - Same fixture/test pattern. Run on express, ky and black and hand-check the findings
     (a quick precision check now; the measured eval with Bandit/Semgrep is Day 4).
3. **Findings API.** `GET /snapshots/{id}/findings?severity=&rule=&language=&path=&limit=&offset=`
   - Paginated (Day 3 note): `{ total, limit, offset, items, counts: {by_severity, by_rule} }`,
     sorted by severity, then path, then line.
   - Rule catalogue served from the backend (`GET /rules` or inside the response), so UI labels
     always match real rule ids.
   - Graph and file endpoints already carry finding counts; no change needed there.
4. **Chunks + embeddings** (new stages `chunk` and `embed`).
   - One chunk per function, method and class (class chunk = header and body up to its first
     method) + one module chunk per file (top-level code outside any symbol). Each chunk text starts
     with `path:start-end` and the qualified name. Very long symbols are split by line windows.
   - Text comes from the redacted file content; `search_tsv` fills identifiers split into words
     (`getUserById` -> get user by id), ready for the hybrid stretch item.
   - Embeddings: `sentence-transformers` with `all-MiniLM-L6-v2` (384 dims, matches the schema).
     torch must come from the CPU wheel index (uv index config), otherwise the Linux Docker image
     pulls multi-GB CUDA wheels. The model (~90 MB) is downloaded once and cached (a Docker volume
     for the api service; pre-fetch in the Dockerfile).
   - Behind an `Embedder` interface; tests and CI use a deterministic stub (no model download).
5. **Q&A: `POST /snapshots/{id}/ask`** (`app/qa/`).
   - Route: structural questions ("which files import X", "who/what calls Y", "what does X
     import/call") are answered from the graph, labelled `graph`, with no LLM.
   - Retrieve: embed the question, exact top-k (k=8) cosine scan for this snapshot, then 1-hop
     expansion through import/call edges (up to 8 more chunks, highest confidence first), within a
     context budget; every snippet tagged `path:start-end`.
   - If the snapshot has no chunks, answer "I could not find this in the provided code." with no
     LLM call; otherwise the grounding prompt handles it (no uncalibrated threshold).
   - `LLMProvider` with `AnthropicProvider` (official `anthropic` SDK; check the installed Messages
     API first; model from `LLM_MODEL`; temperature 0) and `FakeProvider` for tests.
   - Day 3 notes: timeout (30 s), at most one retry, per-snapshot token cap
     (`LLM_TOKEN_CAP_PER_SNAPSHOT`, counted in a new `snapshots.llm_tokens_used` column). If any of
     these trips, or no key is set: "AI answers are unavailable right now. Graph questions still
     work." The key never reaches logs, errors or the frontend.
   - `app/qa/prompts/system.md` with `PROMPT_VERSION` (identity, grounding, citations, trust
     boundary as CLAUDE.md states them), returned in every `/ask` response.
   - Citation validation: only `path:start-end` tags whose path was in the context and whose range
     lies inside a provided snippet are kept; the rest are stripped from the text and counted
     (`dropped`). Response: `{ route, answer, citations[], dropped, prompt_version }`.
   - Tests: router, citation validator, retrieval with the stub embedder, `/ask` with FakeProvider
     (incl. LLM down, cap reached, no relevant code). No API key in CI.
6. **Findings UI** (`/a/:id/findings`).
   - Analysis tabs under the repo header: Explorer | Findings (n) (spec §3.4; no other tabs).
   - Filters for severity, rule, language and path in the URL. The spec's notice: "These are
     rule-based checks. They can miss issues and can flag safe code. Review each one."
   - Rows with severity shown as icon + text + colour. A detail panel shows what the rule looks for,
     why it is risky, the false-positive hint, the masked snippet, "Open in Explorer" (file selected,
     line highlighted) and "Copy location". Secrets are always "value hidden".
   - Empty: "No findings from our current rules. This does not guarantee the code is safe."
   - Node panel gets a Findings tab; Progress lists the new stages (detectors, search).
7. **Ask drawer.**
   - "Ask" button in the analysis header opens a right drawer, kept open across tabs. The
     conversation is per snapshot, in sessionStorage, with a one-click clear.
   - Answers are labelled "AI answer" or "From the graph"; validated citations are chips that open
     the Explorer on that file with the lines highlighted; "1 source could not be verified and was
     removed" when `dropped > 0`.
   - Suggested questions are built from real data (top hub files, files with findings).
   - Markdown rendered without raw HTML. Unavailable, no-answer and cap states use the spec's copy.
   - "Ask about this" from the node panel pre-fills the file.

Decisions to confirm:
- New dependencies:
  - `anthropic` (required);
  - `sentence-transformers` with CPU-only torch (required by CLAUDE.md);
  - `react-markdown` for safe rendering (escapes HTML by default). The alternative is a small
    hand-written formatter for paragraphs, lists and code.
- Token cap default: 200k tokens per snapshot, in a new `snapshots.llm_tokens_used` column (a
  one-line schema change plus an `ALTER TABLE` on the dev DB).
- Severities as listed (secrets stay high).
- If time runs short: task 7's suggested questions and "Ask about this" shrink first, then the node
  panel Findings tab.

## Day 3 notes
Agreed 27 Oct, to apply when building Day 3:
- `GET /snapshots/{id}/findings` is paginated (limit/offset with a total), not one unbounded list.
- The LLM call gets a timeout, at most one retry, and a per-snapshot token cap; when any of these
  trips, the answer says AI is unavailable and graph questions still work.
- No CORS middleware at all: the browser only talks to `/api` through the Vite proxy (same
  origin). Never a wildcard origin.

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
- A dagre layout of 300 nodes takes ~0.4s on the main thread (dev); fine at the cap, would need
  a worker if the cap grows.
- React Flow logs a `nodeTypes` warning in dev StrictMode (double mount); not in production.
- The in-app browser pane sometimes times out on screenshots when the window is behind others;
  `get_page_text` still works.
- Progress percent for parse updates every 50 files (pipeline), so small repos jump straight past it.
- `--node-external` (#a1a1aa) is about 2.6:1 on white, below the 3:1 floor for UI graphics: pick
  a darker grey for external nodes when the graph view (task 9) uses it. `DESIGN.md` (written by
  the impeccable documenter from the built shell) leaves the graph colours out until then.
- Calls made inside anonymous callbacks (`it(...)`, `forEach(function () {...})`) get the
  enclosing named symbol, often the module, as caller. Fine for the file-level graph.
- Call edges never use star imports (`from x import *`, `export * from`).
- PyPI fetches sometimes time out on this network (`uv add` failed once); `UV_HTTP_TIMEOUT=180` worked.
- Docker Desktop can stop on its own; if DB tests error on connect, start it and `docker compose up -d db`.
- JS member assignments and object-literal methods become symbols only at top level, not inside
  functions (e.g. `function setup(app) { app.get = ... }` is not a symbol).
- The api image is built and loads the model offline, but the full `docker compose up` stack
  with the model is not checked yet (Day 4).
- Test code dominates retrieval on test-heavy repos (express: 86% of chunks in `test/`). Task 5
  leaves `in_test` chunks out by default; decide the default with the Q&A eval.
- On Windows, `uv sync` fails with "Access is denied" on a `.pyd` while the API is running from
  the same venv: stop uvicorn first.
- First real-model load takes ~1–2 min (download + torch import); later loads are faster.
- Fixture tests do not reproduce the 0.26.0 crash (only bigger files did); the pin is the guard.
  Re-check before ever lifting it.
- `httpx` with Starlette TestClient emits a deprecation warning (suggests `httpx2`); harmless for now.
- Git for Windows `autocrlf` converts working copies to CRLF; repo stores LF. `.sh` files forced LF.
