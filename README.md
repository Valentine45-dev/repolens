# RepoLens

RepoLens reads a public GitHub repository and shows how its files fit together. Paste a URL and
it clones the repo, parses the Python and JavaScript/TypeScript files, and gives you:

- a **file-level dependency graph** (imports, plus name-based call edges with a confidence),
- a **code panel** for each file with "used by" and "uses" lists,
- **rule-based findings** (for example `eval`, shell commands built from variables, SQL built by
  string concatenation, hardcoded secrets), each with what the rule looks for and when it is a
  false positive,
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
  questions still work.
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
`vite preview`, which forwards `/api` to the API). Without `LLM_MODEL` and `LLM_API_KEY` the
Ask panel says AI answers are unavailable and graph questions still work.

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
npm run preview -- --port 5173
```

A database volume created before 28 Oct needs one migration, run after restarting the API on
the current code: `docker compose exec -T db psql -U repolens -d repolens <
backend/migrations/2026-10-28-repo-case-and-progress.sql`.

## Configuration (`.env`)

Copy `.env.example`. Only the backend reads these; the key never reaches the browser.

| Variable | Default | Meaning |
|---|---|---|
| `POSTGRES_PASSWORD` | `repolens` | Password for the `db` service |
| `DATABASE_URL` | – | Used in dev mode (`localhost:5433`); compose sets its own |
| `TEST_DATABASE_URL` | – | pytest only; the database name must end in `_test` |
| `MAX_FILES` | `2000` | Files kept per repo |
| `MAX_FILE_BYTES` | `1000000` | Larger files are skipped |
| `CLONE_TIMEOUT_S` | `120` | Clone time limit |
| `MAX_ANALYSIS_S` | `600` | Whole-pipeline time limit |
| `LLM_PROVIDER` | `anthropic` | Only Anthropic is implemented |
| `LLM_MODEL` | – | Model id; empty means AI answers are off |
| `LLM_API_KEY` | – | Empty means AI answers are off |
| `LLM_EFFORT` | `low` | Sent as `output_config.effort` |
| `LLM_THINKING` | `between_tools` | `between_tools`, `adaptive` or `default` (use `adaptive` for Haiku) |
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

These are small, hand-labelled evaluations by the same author who wrote the rules and the
retrieval code. Treat them as a check that things work as designed, not as general accuracy.

**Retrieval** (14 answerable questions on express and itsdangerous, test code left out; a hit
means the context sent to the LLM overlaps the labelled lines):

| Context | Recall |
|---|---|
| A: search top 8 | 0.71 |
| B: search top 16 | 0.86 |
| C: top 8 + 1-hop graph expansion (up to 16) | 0.93 |

Graph expansion beat plain search of the same size by one question (13/14 vs 12/14). That is
not conclusive at this sample size.

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
uv run --project backend --env-file .env python eval/smoke_qa.py --price-in X --price-out Y
```

It makes about 8 real API calls (hard limit 12); the prices are only for the cost estimate.

**Final Q&A run** (all 16 questions plus identity and injection, `--all`, with the demo model
`claude-sonnet-5-5`, effort low, `between_tools` thinking, prompt `2026-10-28.2`): 16 of 18
passed under the pre-set rules. Every answerable question cited the expected file (14/14), and
13/14 also cited the labelled lines. 15 of 18 answers had no dropped citation (the server
removed 4 invalid ones in total). Both failures are the unanswerable traps answered correctly
but with citations: on manual review the answers are correct; the rule was too narrow for
false-premise questions. Median latency 4.3 s. 18 calls cost about $0.22.

**Real-world precision on PyGoat** (an intentionally vulnerable Django app, commit `46fef96`):
a random sample of 20 findings per tool (seed 20261028), each labelled real ("a reviewer should
act on it") or false alarm ("correctly matched, but no action needed: by design, test-only,
documentation"), labels confirmed before scoring.

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

## Known limitations

- **Syntactic rules, no taint tracking.** Constant arguments are flagged too (`eval("1 + 1")`,
  a fixed-string `shell=True`, SQL with a constant table name).
- **Secrets passed inline are missed.** The secret check needs a named assignment
  (`password = "..."`) or a known token format; `jwt.sign(payload, "literal")` is not found.
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
