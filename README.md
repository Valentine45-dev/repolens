# RepoLens

RepoLens reads a public GitHub repository and shows how its files fit together. Paste a URL and
it clones the repo, parses the Python and JavaScript/TypeScript files, and gives you:

- a **file-level dependency graph** (imports, plus name-based call edges with a confidence),
- a **code panel** for each file with "used by" and "uses" lists,
- **rule-based findings**, split into **Security** (for example `eval`, shell commands built from
  variables, SQL built by string concatenation, hardcoded secrets) and **Bug / Quality** (bare
  `except`, a few Ruff error checks, imports of files that do not exist), each with what the rule
  looks for and when it is a false positive. Secrets in documentation, and placeholder-looking
  values in documentation or example files, are shown but ranked low,
- **reachability** for each finding: whether a detected entry point (console script, `__main__`
  block, route handler, public API) has a path to the code it is in, shown as a path of clickable
  steps in the finding panel and as an optional "Order: Reachability" (the default order is
  unchanged). Entry points are found by pattern and can be missed; "no path found" does not mean
  the code is unused (`docs/reachability-design.md`),
- an **Ask panel**: structural questions ("which files import signer.py?") are answered from the
  graph without an LLM; other questions go to an LLM with retrieved code, and only citations
  that the server can match to a snippet it sent (`path:start-end`) are shown as source chips.

RepoLens never runs the code it analyses: no installs, no scripts, parse only. Findings are
pattern checks, not a security verdict; they can miss issues and can flag safe code.

## Architecture

```
 browser ──/api──▶ web (Vite, React)  ──proxy──▶  api (FastAPI)  ◀──▶  db (Postgres 16 + pgvector)
                                                    │
                     POST /repos ─▶ background job: │ clone (git, depth 1, hooks off)
                                                    │ → discover (skip rules, secret redaction)
                                                    │ → parse (Tree-sitter: Python, JS, TS)
                                                    │ → edges (imports, calls, confidence)
                                                    │ → detect (rule-based findings)
                                                    │ → embed (chunks, all-MiniLM-L6-v2, local CPU)
                                                    │   clone deleted afterwards
                                                    │
                     POST /snapshots/{id}/ask ─▶    │ router: graph question? ─yes─▶ SQL on edges
                                                    │   no ─▶ vector top-8 + 1-hop graph expansion
                                                    │        ─▶ LLM (Anthropic) ─▶ citation check
```

- Each pipeline stage deletes and re-inserts its own rows in one transaction; progress is written
  to the `jobs` row and polled by the UI.
- Secrets are redacted (line numbers kept) before any file text, snippet or chunk is stored.
- If the LLM is unavailable (no key, timeout, token cap), the graph, findings and graph
  questions still work. Without a key or on an LLM failure, other questions list the matching
  code locations from search, with no generated text.
- Schema: [`backend/schema.sql`](backend/schema.sql). Design notes: [`docs/`](docs/).

## Running it

### With Docker (the demo setup)

Needs Docker Desktop. From the repo root:

```bash
cp .env.example .env
docker compose up --build
```

Open <http://localhost:5173>. The first build takes several minutes (it downloads the CPU-only
torch wheels and the embedding model, so the running stack works offline). On startup the API
loads the model, which takes about a minute; until then the web app shows connection errors.

Services: `db` (host port 5433), `api` (8000), `web` (5173, a production build served by
`vite preview`, which forwards `/api` to the API). All three are published on `127.0.0.1`
only: nothing has authentication and the database has a default password. Without
`LLM_MODEL` and `LLM_API_KEY` the Ask panel says AI answers are unavailable and graph
questions still work.

### Dev mode (API and web on the host)

Needs [uv](https://docs.astral.sh/uv/) and Node 22. Only the database runs in Docker:

```bash
docker compose up -d db
```

```bash
cd backend
uv sync
uv run --env-file ../.env uvicorn app.main:app --port 8000
```

```bash
cd web
npm ci
npm run dev
```

The API reads `os.environ` only, so `--env-file ../.env` is needed. On Windows, stop uvicorn
before `uv sync` (a running API locks the native `.pyd` files).

For a demo on a small machine, serve the production build instead of the dev server (it is
about twice as fast to open the graph); `/api` is still proxied to the API on 8000:

```bash
cd web
npm run build
npx vite preview --port 5173 --strictPort
```

(Not `npm run preview -- --port 5173`: Windows PowerShell 5.1 drops the bare `--`, so Vite
gets `5173` as a folder name and stops with "dist does not exist".)

To see loading states (skeletons, "Opening…"), slow the API down in the dev or preview server
only. Off unless set; it lives in `web/devApiDelay.ts`, in the Node server, so it never reaches
the browser bundle, and the normal build and preview add no delay. Set it for one command only:

```powershell
cd web
$env:REPOLENS_DEV_API_DELAY_MS = "1500"; npx vite preview --port 5173 --strictPort; Remove-Item Env:REPOLENS_DEV_API_DELAY_MS
```

`REPOLENS_DEV_API_DELAY_MATCH` (a regular expression on the path, e.g. `/reach`) limits it to some
requests.

An older database volume needs the migrations in
[`backend/migrations/`](backend/migrations/), run after stopping any API on older code (a
fresh volume needs none). All are idempotent and can run in any order:

```bash
docker compose exec -T db psql -U repolens -d repolens < backend/migrations/2026-10-28-repo-case-and-progress.sql
```

```bash
docker compose exec -T db psql -U repolens -d repolens < backend/migrations/2026-10-28-search-state.sql
```

```bash
docker compose exec -T db psql -U repolens -d repolens < backend/migrations/2026-11-05-analysis-receipt.sql
```

```bash
docker compose exec -T db psql -U repolens -d repolens < backend/migrations/2026-11-05-import-scope.sql
```

```bash
docker compose exec -T db psql -U repolens -d repolens < backend/migrations/2026-11-07-findings-categories.sql
```

(In PowerShell, pipe the file instead: `Get-Content backend/migrations/<file> | docker compose
exec -T db psql -U repolens -d repolens`.)

After the import-scope migration, fill the new column for analyses that already exist. It rebuilds
their edges from the stored files, with no clone or embedding. Until then the map says cycles are
not known for them. Run it with the API stopped:

```bash
cd backend
uv run --env-file ../.env python -m app.ingest.backfill
```

After the findings-categories migration, analyses made before it have no Bug / Quality findings.
`python -m app.ingest.redetect` re-runs the detect stage on their stored files (no clone, no
embedding; hardcoded-secret findings are not touched, so `placeholder` and `template_value` stay off for old rows
until the repository is analysed again). Also with the API stopped:

```bash
cd backend
uv run --env-file ../.env python -m app.ingest.redetect
```

Run only one API against a database at a time: on startup the API marks every running
analysis and search in that database as interrupted, including another API's.

## Configuration (`.env`)

Copy `.env.example`. Only the backend reads these; the key never reaches the browser.

| Variable | Default | Meaning |
|---|---|---|
| `POSTGRES_PASSWORD` | `repolens` | Password for the `db` service |
| `DATABASE_URL` | – | Used in dev mode (`127.0.0.1:5433`, not `localhost`: the db listens on IPv4 only, and `localhost` tries IPv6 first, which costs ~10 s per connection on Windows); compose sets its own |
| `TEST_DATABASE_URL` | – | pytest only; the database name must end in `_test` |
| `MAX_FILES` | `2000` | Files kept per repo |
| `MAX_FILE_BYTES` | `1000000` | Larger files are skipped |
| `CLONE_TIMEOUT_S` | `120` | Clone time limit |
| `MAX_ANALYSIS_S` | `600` | Time limit for the analysis, up to search for non-test code |
| `MAX_TEST_EMBED_S` | `1800` | Time limit for embedding test code, which runs after Ask is on |
| `LLM_PROVIDER` | `anthropic` | Only Anthropic is implemented |
| `LLM_MODEL` | – | Model id; empty means AI answers are off. The demo uses `claude-sonnet-5-5` |
| `LLM_API_KEY` | – | Empty means AI answers are off |
| `LLM_EFFORT` | `low` | Sent as `output_config.effort` |
| `LLM_THINKING` | `between_tools` | `between_tools` (demo, Sonnet 5.5), `adaptive` or `default` (use `adaptive` for Haiku) |
| `LLM_TOKEN_CAP_PER_SNAPSHOT` | `500000` | AI token budget per analysed commit; does not reset |

Less common settings (embedding model, retrieval `QA_*` values, deadlines) are in
[`backend/app/config.py`](backend/app/config.py).

## Tests

```bash
docker compose up -d db
cd backend
uv run --env-file ../.env pytest
```

DB tests use `TEST_DATABASE_URL` and refuse to run unless the database name ends in `_test`
(they drop and rebuild its schema). A fresh `db` volume creates `repolens_test`; on an older
volume run `docker compose exec -T db createdb -U repolens repolens_test`. Tests never call the
real LLM (a `FakeProvider` returns scripted answers). Optional extras: `RUN_NETWORK_TESTS=1`
(clones from GitHub), `RUN_MODEL_TESTS=1 uv run pytest -k real_model` (real embedding model).

Frontend renderer tests: `cd web && npm test`.

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs `ruff` and `pytest` on every
push and pull request against a `pgvector/pgvector:pg16` service, with a stub embedder and no
API keys.

## Evaluation

Run from the repo root. Results are saved to [`eval/results/`](eval/results/) with the commit,
embedder and retrieval settings.

```bash
uv run --project backend --env-file .env python eval/retrieval_recall.py --label myrun
```

```bash
uv run --project backend python eval/detector_eval.py
```

The retrieval eval needs `expressjs/express` and `pallets/itsdangerous` analysed at the commits
in [`eval/questions.yaml`](eval/questions.yaml). The detector eval runs Bandit and Semgrep
through `uvx` at pinned versions (Semgrep falls back to its Docker image).

### Results so far (28 Oct)

These are small evaluations, labelled by the people who wrote the rules and the retrieval code:
the project owner, working with an AI coding assistant (Claude). Treat them as a check that
things work as designed, not as general accuracy. All numbers below were measured before the
review fixes of 28 Oct evening (citation and answer-status rules, config-file redaction; listed
in [`PROGRESS.md`](PROGRESS.md)) and were not re-run.

**Retrieval** (14 answerable questions on express and itsdangerous, test code left out; a hit
means the context sent to the LLM overlaps the labelled lines):

| Context | Recall |
|---|---|
| A: search top 8 | 0.71 |
| B: search top 16 | 0.86 |
| C: top 8 + 1-hop graph expansion (up to 16) | 0.93 |

Graph expansion beat plain search of the same size by one question (13/14 vs 12/14). That is
not conclusive at this sample size. The chunker (doc comments joined to their code) and the
expansion rules were changed after a first run on these same 14 questions, in which expansion
added nothing (A = C = 0.64, B = 0.79), so these numbers come from tuning on the evaluation
set itself.

**Detectors** (hand-written fixtures with `vuln:` / `safe:` labels committed before any tool
ran; Bandit and Semgrep scored on the same labels):

| Fixture | Tool | Precision | Recall |
|---|---|---|---|
| `python/shop.py` (22 labels) | RepoLens | 0.65 | 1.00 |
| `python/shop.py` | Bandit 1.9.4 | 0.62 | 0.73 |
| `js/server.js` (18 labels) | RepoLens | 0.75 | 1.00 |
| `js/server.js` | Semgrep 1.182.1 | 0.50 | 0.11 |
| `js/routes.js` (16 labels) | RepoLens | 0.89 | 0.80 |
| `js/routes.js` | Semgrep 1.182.1 | 0.50 | 0.30 |

Recall on self-written fixtures shows the rules catch the patterns they target; it says nothing
about real-world recall. Semgrep was run with one configuration (`p/javascript` + `p/secrets`),
whose rules mostly need request input flowing into the sink; `js/routes.js` was added for that
reason. Other rulesets may score differently and were not tried.

**Smoke eval** (`eval/smoke_qa.py`, real model, 8 questions; first run 28 Oct with
`claude-haiku-5-5`, effort low, adaptive thinking): 6 of 8 passed. Grounded answers cited the
expected file, the unanswerable express question got "could not find" with no citations, and
the prompt-injection fixture was cited and its instruction ignored, with no prompt text leaked.
The identity answer was correct but marked unverified, a status bug. It was fixed (prompt
`2026-10-28.2`: a fixed identity sentence, accepted without citations) and re-checked with one
call, which passed. The encryption trap got an answer saying the code signs but does not
encrypt, with citations, so it fails the pre-set "could not find, zero citations" rule and
stays a FAIL. On manual review the answer is correct; the rule was too narrow for
false-premise questions. Results are in `eval/results/`. All 10 real calls together used
32,663 input and 2,484 output tokens, about $0.0045 at Haiku 5.5's $0.10 / $0.50 per million
tokens ([Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing), prompts
up to 100,000 tokens).

```bash
uv run --project backend --env-file .env python eval/smoke_qa.py --price-in 2 --price-out 10
```

It makes about 8 real API calls (hard limit 12); the prices are only for the cost estimate
(2 / 10 USD per million tokens is Sonnet 5.5, the demo model set in `.env`).

**Final Q&A run** (all 16 questions plus identity and injection, `--all`, with the demo model
`claude-sonnet-5-5`, effort low, `between_tools` thinking, prompt `2026-10-28.2`): 16 of 18
passed under the pre-set rules. Every answerable question cited the expected file (14/14), and
13/14 also cited the labelled lines. Citation validity was 15/18: those answers had no dropped
citation, meaning every citation lay inside a snippet that was sent (the server removed 4 invalid
ones in total). This does not show that a citation supports its claim, and it is not a measure of
faithfulness. Both failures are the unanswerable traps answered correctly
but with citations: on manual review the answers are correct; the rule was too narrow for
false-premise questions. Median latency 4.3 s. 18 calls cost about $0.22.

**Real-world precision on PyGoat** (an intentionally vulnerable Django app, commit `46fef96`):
a random sample of 20 findings per tool (seed 20261028), each labelled real ("a reviewer should
act on it") or false alarm ("correctly matched, but no action needed: by design, test-only,
documentation"). The labels were proposed by the AI assistant and confirmed unchanged by the
project owner before scoring.

| Tool | Precision | 95% interval |
|---|---|---|
| RepoLens | 18/20 = 0.90 | 0.70–0.97 |
| Bandit 1.9.4, binding to 0.0.0.0 (B104) counted as false alarm | 13/20 = 0.65 | 0.43–0.82 |
| Bandit 1.9.4, B104 counted as real | 17/20 = 0.85 | 0.64–0.95 |

PyGoat's deliberate lab secrets flatter any secret rule, and 16 of RepoLens's 20 sampled
findings are secrets. The tools flag different kinds of problems, the samples are small and the
intervals overlap, so this does not show that either tool is more precise overall. Recall is
not measured. The eval also found a redaction bug (an f-string placeholder like `{password}`
was treated as a secret and stored redacted); it was fixed afterwards, and the numbers above
are from the run before the fix.

## Accessibility notes

- Touch targets: the smallest controls (example chips, icon buttons) are 28–30 px, above the
  24 px minimum of WCAG 2.2 (2.5.8).

## Known limitations

- **Reachability is a heuristic.** Entry points are detected by pattern (the list is in
  `docs/reachability-design.md`) and calls are matched by name, so code reached only through
  callbacks, plugins loaded by name or dynamic dispatch shows "no path found". It is weakest on
  JavaScript (Express attaches methods by assignment). `python -m app.reach.report` prints the
  entry points and tiers of an analysed snapshot.

- **Bug / Quality findings skip test and example code** and cover Python only (Ruff: `F811`,
  `F821`, `F822`, `F823`, `B006`, `B015`, `B023` and the Pylint error rules except `PLE0704`). They run on a copy of
  the redacted files with `--isolated --no-cache --no-fix --ignore-noqa`, so the repository
  cannot change or silence them. "Broken import" misses a directory imported through the
  `main` field of its `package.json` (the file is not read) and can flag generated or compiled
  modules it does not know by name.
- **Placeholder detection is by wording and shape only** (`changeme`, `<your-key>`, `xxxxxx`,
  `your-...-here`). In documentation and in example or template files (`*.example.*`,
  `*.sample`, `*.template`, `*.dist`) such a value is shown as "probably placeholder": low, listed
  last. In code and runtime config (including `docker-compose.yml`) it keeps its severity and
  is noted as a template value, because an app deployed with it as-is uses a publicly known key.
  Files named `.env*` and files ending in `.example` are not read at all.
- **Syntactic rules, no taint tracking.** Constant arguments are flagged too (`eval("1 + 1")`,
  a fixed-string `shell=True`, SQL with a constant table name).
- **Secrets passed inline are missed.** The secret check needs a named assignment
  (`password = "..."`) or a known token format; `jwt.sign(payload, "literal")` is not found.
- **Redaction is pattern-based.** Unquoted values (`password: hunter2`) are caught only in
  YAML, INI/CFG, TOML and shell files; in code, Markdown and text only quoted values and known
  token formats are.
- **Server-side XSS through response writes is missed.** The JS HTML rule only checks
  assignments to `innerHTML` / `outerHTML`, not `res.send("<h1>" + input)`.
- **Call edges are name-based guesses.** Dynamic calls and star imports are not resolved; calls
  inside anonymous callbacks are attributed to the enclosing named function or the module.
  Low-confidence edges are hidden by default.
- **JS/TS import resolution** handles relative paths, extensions, `index` files, `import` and
  `require`; tsconfig path aliases that are not simple are marked unresolved.
- **Retrieval** uses a small local embedding model (256-token window) and an exact scan; long
  functions are split into windows, and a documentation window can win over the code it
  documents.
- **LLM temperature cannot be set to 0** on the current models; reproducibility comes from a
  fixed model, effort, thinking setting and prompt version, which every eval run records.
- Public GitHub repos only, up to 2,000 files; files over 1 MB, `.env*`, key files, vendored
  and build directories are skipped.
- **A pinned `commit` is not checked against the repo** before an analysis starts. GitHub
  serves commits from a repo's forks by SHA too, so a pinned commit from a fork would be shown
  under the parent repo's name. The Home page examples are pinned to commits of those repos.
