# Handoff: independent design and comparison with v1 (5 Nov 2026)

**For:** the main RepoLens session, which has not seen the conversation behind this file.
**From:** a separate session that wrote an independent system design, then compared it with the code.
**Repo state reviewed:** `main` at `b8f03d6` (includes the tag `v1-submitted` = `75be6fb` plus eval-only commits). Line references are for that commit.

The owner read both the design and the comparison and said they like them. They want the main session to carry this out.

## How to use this
1. Read `CLAUDE.md`, `PROGRESS.md` and `eval/results/BASELINE-v1.md` as usual. Nothing here overrides `CLAUDE.md`.
2. Re-check each finding against the current code before acting on it. They came from reading code. No tests, exploits or app runs were done.
3. Start with the recommended order in section 3, and confirm scope with the owner where section 6 says so.

**Status:** no product code changed. Nothing was prototyped. This file is the only change from that session and it is uncommitted. Every target number is a proposal, not a result.

## 1. Context from the owner
- Solo developer, building this as a **master's project**. This is newer than the design doc's "team of two".
- The owner first asked for an unconstrained design, then gave the solo master's context. **Work from the scoped version in section 2.2.** The hosted version in 2.1 is reference only.
- An LLM API key is needed only for generated answers and AI explanations. Graph, findings, structural questions, local embeddings, tests and CI all run without one. Develop with `FakeProvider` and call the real API only for evals and the demo.
- Check the university's rules on third-party APIs and AI assistance, since both affect what the write-up must disclose.

## 2. The independent design

**Core idea:** compute facts deterministically and record how each was derived. The LLM explains facts and proposes hypotheses, but never establishes a fact itself. Every edge, finding and answer carries its evidence.

### 2.1 Full hosted version (reference only)
- **Pipeline:** Temporal workflows run a Firecracker microVM per job (fetch, discover and redact, parse, resolve, scan, chunk). The VM has no network after fetch and no credentials.
- **Trust boundary:** analyzers output only NDJSON. A trusted validator checks schema, paths and line numbers before storing.
- **Storage:** Postgres with pgvector, Zoekt for code search, S3 for blobs. Snapshot key is `(repo, commit SHA, analyzer version)`.
- **Graph:** Tree-sitter plus compiler-grade resolvers (TypeScript compiler API, Pyright). Dependencies may be fetched with scripts disabled, never run. Each edge records a resolution tier.
- **Graph view:** the server enforces about 60 nodes and 150 edges per view. Default is the folder hierarchy with merged single-child folders and aggregated edges, ELK layered layout, cycles collapsed and highlighted, utility hubs hidden behind a badge. Symbols appear only as a 1-2 hop neighbourhood. Leiden clustering is a fallback for flat repos, and a dependency matrix is a secondary view.
- **Findings:** Ruff, Opengrep with our own rules, Gitleaks and OSV-Scanner on lockfiles, ranked by reachability from entrypoints. Repo tool configs are never loaded and suppression comments are ignored. LLM findings are separate "AI hypotheses" that survive an independent refutation pass.
- **Q&A:** structural questions go to the graph with no LLM. Others go to a bounded agent with read-only tools, using lexical and dense search, summaries and a reranker.
- **Verification:** claims must carry `{chunk_id, start_line, end_line, quote}`. A claim survives only if the chunk was retrieved, the lines are in range, the quote matches those lines, and named identifiers exist in the cited code or symbol table. Otherwise it is removed. This proves the evidence exists, not that it supports the claim, so support rate is measured separately by humans.
- **Never:** execute submitted repos, even in a VM. Dynamic analysis is only for evaluation on a curated corpus.

Extra feature ideas: blind-spot report, route-to-sink tracing, generated onboarding tour, blast radius, snapshot diff, churn hotspots, MCP server and SARIF export.

Biggest failure risks: confident but wrong structure; no measurable advantage over a general coding agent, hidden by flattering self-written evals; a trust or safety incident.

### 2.2 Scoped version for the solo master's project (use this)
**Keep:**
- evidence tiers on edges, with Tree-sitter plus import-aware resolution
- a view limit on the graph (about 60 nodes), using the folder hierarchy
- scanners plus own rules, ranked by reachability
- server-side claim validation with the exact-quote check
- a fallback to ranked code locations when the LLM is down
- the blind-spot report

**Simplify:**
| Hosted design | Scoped version |
|---|---|
| Firecracker microVMs | Hardened Docker: no network, read-only, non-root, all capabilities dropped, resource limits |
| Temporal | A jobs table with stage and progress |
| Zoekt, reranker, pgvector tuning | Postgres full-text search plus exact vector scan |
| Bounded agent | One-shot retrieval with 1-hop graph expansion |
| 24-person study, paid labellers | Pilot with 6-8 people, plus a second human labeller on a sample |

**Drop:** hosting and sign-in, LLM review for logic bugs, Joern, MCP server, snapshot diff, churn hotspots. If time remains, add compiler-grade TypeScript resolution first.

**Research questions the project can test:**
1. Does graph expansion improve retrieval over plain hybrid search?
2. Does reachability ranking improve precision@20 compared with Bandit and Opengrep defaults?
3. Does claim validation raise the share of claims their citations support, compared with plain RAG?

## 3. Recommended order for v2
| # | Change | Why | Size |
|---|---|---|---|
| 1 | Allowlist git's environment, add `TrustedHostMiddleware`, harden compose | Removes obvious risks | Small |
| 2 | Run fetch and parsing in a separate no-network process or container | Contains crashes and hostile input | Medium |
| 3 | **New frozen holdout questions before any retrieval change, with a human judge** | Makes everything after it measurable | Medium |
| 4 | Hybrid search, compared against current retrieval | Likely the cheapest retrieval gain, unproven | Small |
| 5 | Claim-level status and exact-quote checks, then measure support rate | Meets "verify every answer" | Medium |
| 6 | Store source lines on edges | Makes graph answers verifiable | Small |
| 7 | Folder hierarchy with aggregated edges and cycle detection | Meets "readable on large repos" | Large |
| 8 | Reachability ranking, plus Ruff with `--isolated` for code quality | Better ranking and coverage | Medium |
| 9 | Coverage report, and code locations as the LLM fallback | Honest reporting, better degraded mode | Small |

Item 3 must come before items 4 and 5, or those results repeat the current tuning-on-the-eval-set problem.

Also fix the three bugs listed in `BASELINE-v1.md` section 9: `tests.py` is not treated as test code, the misleading timeout message, and the 600 s limit also covering test-code embedding.

## 4. Findings behind that order

**Graph**
- `RENDER_CAP = 300` in `web/src/graphModel.ts:8`, flat file nodes, while the limit allows about 2,000 files. Beyond 300, only the most connected are drawn; List view still shows all.
- `backend/app/api/graph.py:27` has no `level` or `root` parameter, although design section 10 specifies them.
- A search of `backend/app` found no cycle detection.

**Answer verification**
- `backend/app/qa/answer.py:150`: an answer is `answered` if any citation survives. Baseline: 102 of 154 sentences (0.66) carry a valid citation. The uncited ones have not been categorised, so some may be harmless.
- `backend/app/qa/citations.py:58`: checks only that a range falls inside a sent snippet, so a citation can pass while pointing at lines that do not support the claim.
- `backend/app/ingest/pipeline.py:242`: edges store no source line, so "From the graph" results cannot point at the exact import or call.

**Isolation and security**
- Parsing runs inside the API process, which holds database credentials and the LLM key. `PROGRESS.md` records a Tree-sitter segfault that killed the API.
- `backend/app/ingest/clone.py:69`: `dict(os.environ)` passes the whole environment, including `LLM_API_KEY` where set, to git subprocesses.
- `docker-compose.yml` sets memory and CPU limits on `api` but no capability drop or read-only filesystem. The primary demo runs natively with no container.
- Deadlines are checked only between steps (for example `pipeline.py:164`), so a stuck parse cannot be interrupted.
- `backend/app/main.py:41` has no host validation, so DNS rebinding may be possible. **Not tested.**

**Retrieval**
- `search_tsv` is written and indexed but `backend/app/qa/retrieve.py` never reads it. Search top 8 finds 10 of 14 (0.71).
- Do not change the embedding model first. This machine manages about 12-17 chunks per second, and a larger model would likely be slower.

**Findings**
- Order is severity then path, with no reachability. Own rules: 4 Python, 5 JS/TS, plus secrets. Code-quality coverage is thin.

**Degraded mode and coverage**
- `answer.py:99` returns "unavailable" before retrieval runs when there is no provider, so no code locations are offered.
- `hit_file_limit` and skipped-file counts only reach the logs (`pipeline.py:556`). A repo cut off at the file limit does not tell the user.

**Evaluation**
- Graph expansion wins by one question of 14, on the questions used for tuning. The baseline correctly calls this not conclusive.
- Citation support has never been measured. `citation_validity` only checks that ranges were sent to the LLM.
- No scored graph evaluation: 125 hand-checked import edges, informal spot checks on call edges. PyCG's 112-program micro-benchmark is a candidate for Python.
- 16 of RepoLens's 20 PyGoat samples are secrets, on a repo that is vulnerable by design.
- No independent human judge yet. No usability-test results were found in `eval/results`.

## 5. Keep from v1
These are as good as or better than the design:
- test code excluded from retrieval (86% of Express's chunks were test code)
- doc comments attached to their functions
- the markdown renderer that cannot produce links, images or HTML
- atomic token budgets and the prompt hash check in CI
- clear degraded states: ambiguous, refused, unavailable, cap reached
- staged search, where Ask unlocks before test code finishes embedding
- evaluation records: pre-set rules, kept failures, documented deviations
- confidence values 1.0 / 0.9 / 0.5 with dashed guesses. Renaming them to tiers is not worth doing.
- `git fetch` rather than the tarball idea from the design

## 6. Check with the owner first
- `CLAUDE.md` describes the 4-day build and its deadline has passed. Items here may conflict with its "not in the core build" list, which says to ask first, and folder graph levels are stretch-only there. Confirm that v2 scope replaces those limits before building.
- New dependencies need a stated reason, per `CLAUDE.md` (for example Ruff at runtime, or a container runner for item 2).
- No v2 plan was found. `BASELINE-v1.md` mentions "v2" and "v2 phase 3", but `README.md` and `PROGRESS.md` contain no such plan. Ask the owner whether one exists elsewhere.
- `PROGRESS.md` predates the re-baseline and its numbers are older than `BASELINE-v1.md`. Use the baseline.
- Follow `CLAUDE.md` for git: feature branches only, ask before merging to `main`, and no AI attribution lines in commits or PRs.

## 7. Tool facts: how far they were checked
- **Secondary sources only:** Semgrep's maintained rules are reported to exclude SaaS and competing use, and Opengrep remains an active LGPL fork. Have the licence text checked before relying on it.
- **Unconfirmed:** whether `scip-python` and `scip-typescript` are actively maintained. Treat them as a time-boxed spike.
- **Checked:** PyCG's micro-benchmark has 112 programs with JSON call graphs; its paper reports about 99.2% precision and 69.9% recall.
- **Weak evidence:** no good head-to-head for embedding models. If a change is ever tested, run a bake-off on this project's own questions.
- **From memory, not checked:** Firecracker, Temporal, Zoekt, Joern, CVEfixes, CrossVul, BenchmarkPython, CVE-2024-32002.
