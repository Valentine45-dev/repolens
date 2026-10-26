# Product Requirements Document (PRD)

## RepoLens: Graph-Based Code Intelligence and Vulnerability Detection for Python and JavaScript Repositories

| | |
|---|---|
| **Course** | MSc Computer Science, Mini Project 1, MIT WPU |
| **Team** | 2 students |
| **Timeline** | 1 month |
| **Document status** | Draft v1 (planning) |
| **Companion document** | `repolens-system-design.md` (architecture, schema, API, pipeline) |

> Numbers in this document that describe performance or scale are **targets and estimates**, not measurements. They are replaced with measured values after the evaluation phase.

---

## 1. Summary

RepoLens is a web application that analyzes a public GitHub repository and helps a developer understand it quickly. It builds an interactive **dependency and call graph**, flags **potential bugs, security issues, and code smells** using rule-based static analysis, and answers **natural-language questions** about the codebase with **file and line citations**.

Python and JavaScript/TypeScript get deep analysis. Other languages supported by Tree-sitter get basic structural extraction and search.

The project's technical contribution is **graph-aware retrieval** (vector search combined with dependency-graph expansion) and a **measured evaluation** against existing tools and a plain vector-search baseline.

---

## 2. Problem statement

Developers regularly face unfamiliar codebases: joining a team, reviewing an open-source dependency, auditing a project, or inheriting old code. Typical pain points:

- It is hard to see how files, classes, and functions relate to each other.
- Finding "where does X happen?" means grepping and reading many files.
- Security and quality issues are scattered and easy to miss.
- Generic "chat with your repo" tools often answer without grounding, cannot show how they got the answer, and rarely use the structure of the code.

RepoLens addresses this by combining **deterministic code analysis** (parsing, graphs, rules) with an **LLM used only where it is strong** (explanation and natural-language answers), and by making every answer **checkable** through citations.

---

## 3. Goals and non-goals

### Goals
1. Ingest a public GitHub repo and produce a navigable dependency and call graph.
2. Detect common bugs, security issues, and code smells with explainable rules.
3. Answer questions about the codebase with validated file and line citations.
4. Answer purely structural questions ("who imports X?") deterministically, without the LLM.
5. Evaluate quality with real numbers: detector precision and recall, retrieval recall, citation validity, and performance.
6. Keep the system safe: never execute analyzed code, redact secrets, enforce limits.

### Non-goals (v1)
- Private repositories and user accounts.
- Incremental re-indexing when a repo changes.
- Automatic test generation.
- "Why might this endpoint fail?" style runtime reasoning.
- Deep analysis for languages other than Python and JavaScript/TypeScript.
- Fixing or modifying the analyzed code.
- Replacing full commercial static-analysis suites.

---

## 4. Target users and personas

| Persona | Needs | How RepoLens helps |
|---|---|---|
| **New team member / student** | Understand an unfamiliar project fast | Graph map, "where does auth happen?" Q&A |
| **Open-source evaluator** | Judge a dependency's structure and risk | Findings list, dependency view |
| **Code reviewer / security-minded dev** | Spot dangerous patterns quickly | Rule-based findings with line-level evidence |
| **Evaluator (course)** | See a working, measured system | Demo, evaluation numbers, report |

Primary persona for the demo: a developer opening a mid-sized repository for the first time.

---

## 5. User stories

**Ingestion**
- As a user, I can paste a GitHub URL and start an analysis.
- As a user, I can see progress and a clear error if something fails.
- As a user, I get a clear message if the repo is too large instead of a crash.

**Exploration**
- As a user, I can view the repo as a graph, starting at folder level and drilling down to files and symbols.
- As a user, I can click a node to see its code, what depends on it, and what it depends on.
- As a user, I can see which edges are uncertain (low confidence).

**Findings**
- As a user, I can see a list of findings with severity, file, line, rule, and a masked snippet.
- As a user, I can filter findings by severity and rule, and jump from a finding to its node.

**Q&A**
- As a user, I can ask a question in plain English and receive an answer with citations.
- As a user, I can click a citation to open the cited code and highlight its node.
- As a user, I get direct answers to structural questions ("which files import X?") instantly.
- As a user, I still get the graph and findings if the LLM is unavailable.

---

## 6. Scope and language tiers

| Tier | Languages | Capabilities |
|---|---|---|
| **Tier 2 (deep)** | Python, JavaScript/TypeScript | Resolved dependency graph, call edges, rule-based detectors, evaluation |
| **Tier 1 (basic)** | Any other Tree-sitter-supported language | File, class, function extraction, and search only |

**Fallback rule:** if JavaScript/TypeScript deep analysis is not producing a correct graph on test repos by the end of Week 3, it is demoted to Tier 1 and the report says so. Python deep analysis is the committed baseline.

---

## 7. Functional requirements

Priority: **P0** = must have, **P1** = should have, **P2** = nice to have.

### 7.1 Repository submission and ingestion

| ID | Requirement | Priority |
|---|---|---|
| FR-1 | Accept a public GitHub repo URL; only `https://github.com/<owner>/<repo>` is valid | P0 |
| FR-2 | Create a snapshot (repo + commit SHA) and a background job; return the snapshot id immediately | P0 |
| FR-3 | Clone shallowly with hooks disabled, no submodules, symlinks ignored, size and time caps | P0 |
| FR-4 | Skip dependency folders, build output, minified, binary, and secret-bearing files | P0 |
| FR-5 | Enforce configurable limits (repo size, file count, file size, analysis time) and reject oversize repos with a clear message | P0 |
| FR-6 | Each ingestion stage replaces its own output (delete-then-insert in a transaction) and records stage and percent progress; an interrupted job restarts from the beginning | P0 |
| FR-7 | Expose job status; show failures with a readable error | P0 |
| FR-8 | Reuse an existing `ready` snapshot when the same repo and commit SHA were already analyzed | P1 |
| FR-9 | Zip upload as an alternative to a URL (with zip-slip and zip-bomb protection) | P2 |
| FR-10 | Reset stale `running` jobs automatically if a worker dies | P1 |

### 7.2 Parsing and graph construction

| ID | Requirement | Priority |
|---|---|---|
| FR-11 | Extract files, classes, functions, methods, and imports with Tree-sitter | P0 |
| FR-12 | Tolerate syntax errors: log and skip broken files without failing the job | P0 |
| FR-13 | Resolve imports as internal, external, or unresolved for Python | P0 |
| FR-14 | Resolve imports for JS/TS (relative paths, index files, `tsconfig` aliases) | P1 |
| FR-15 | Build best-effort call edges with a `confidence` value | P0 |
| FR-16 | Store edges of types `imports`, `calls`, `inherits`, `defines` | P0 |
| FR-17 | Tier 1 languages: extract symbols only, no resolved graph | P1 |
| FR-18 | Never execute analyzed code or install its dependencies | P0 |

### 7.3 Detection (findings)

| ID | Requirement | Priority |
|---|---|---|
| FR-19 | Implement rule-based detectors as Tree-sitter queries plus checks, each with id, severity, and message | P0 |
| FR-20 | Python rules: dangerous calls (`eval`, `exec`, `pickle.loads`, `subprocess` with `shell=True`), string-built SQL, hardcoded secrets, bare `except`, long functions, high complexity, circular imports, unused functions | P0 |
| FR-21 | JS/TS rules: `eval`, `new Function`, `child_process.exec` with dynamic input, string-built SQL, `innerHTML` with dynamic data, hardcoded secrets, complexity, circular imports, unused functions | P1 |
| FR-22 | Each finding stores file, line, rule id, severity, and a snippet | P0 |
| FR-23 | Secrets are redacted before snippets and chunks are stored or sent anywhere | P0 |
| FR-24 | The LLM may explain a finding on request but never decides whether a finding exists | P0 |

### 7.4 Retrieval and Q&A

| ID | Requirement | Priority |
|---|---|---|
| FR-25 | Chunk by function or class, embed with a local embedding model, store in pgvector | P0 |
| FR-26 | Route structural questions to the graph without the LLM (simple keyword and pattern routing) | P0 |
| FR-27 | For other questions: embed, retrieve top-k chunks, expand through the graph (1 to 2 hops) | P0 |
| FR-28 | Build the prompt within a token budget; every snippet tagged `path:start-end` | P0 |
| FR-29 | Call the LLM through a provider-agnostic interface, temperature 0 | P0 |
| FR-30 | Validate citations: any cited path or line range not present in the provided context is flagged or the answer rejected | P0 |
| FR-31 | Return answer text plus structured citations | P0 |
| FR-32 | Degrade gracefully when the LLM is unavailable (clear error, rest of the app works) | P0 |
| FR-33 | Offer "explain this function" and "explain this finding" from a selected node | P1 |

### 7.5 Frontend

| ID | Requirement | Priority |
|---|---|---|
| FR-34 | Submit screen with URL input and validation errors | P0 |
| FR-35 | Progress screen showing stage and percent | P0 |
| FR-36 | Interactive graph with level of detail: folder, file, symbol (expand on click) | P0 |
| FR-37 | Node panel: code, findings, dependents, dependencies | P0 |
| FR-38 | Findings panel with severity and rule filters | P0 |
| FR-39 | Chat panel with clickable citations that highlight the node and open the code | P0 |
| FR-40 | Visual marker for low-confidence edges | P1 |
| FR-41 | Safe rendering of LLM output (sanitized, no raw HTML) | P0 |
| FR-42 | Search box over symbols | P1 |

### 7.6 API (summary)

`POST /repos`, `GET /snapshots/{id}/status`, `GET /snapshots/{id}/graph`, `GET /snapshots/{id}/files/{file_id}`, `GET /snapshots/{id}/findings`, `GET /symbols/{id}/dependents`, `GET /symbols/{id}/dependencies`, `POST /snapshots/{id}/ask`, `GET /health`. Full details are in the system design document.

---

## 8. Non-functional requirements

| ID | Category | Requirement (target) |
|---|---|---|
| NFR-1 | Performance | Ingest of a mid-sized repo (around 100k lines) completes in a few minutes |
| NFR-2 | Performance | Q&A p95 latency around 5 seconds, excluding provider outages |
| NFR-3 | Scale | Supports repos up to the configured limits (default about 2,000 source files and 20 MB) |
| NFR-4 | Reliability | A job whose worker dies is re-queued (heartbeat) and re-run from the start with capped attempts, replacing partial results; a snapshot is shown as ready only when its job is done |
| NFR-5 | Availability of core features | Graph, findings, and structural queries work without the LLM |
| NFR-6 | Security | No execution of analyzed code; URL validation; secrets redacted before storage; sanitized output; non-root worker with resource limits |
| NFR-7 | Cost control | Per-snapshot LLM token and request caps; rate limits on submit and ask |
| NFR-8 | Reproducibility | Evaluation runs fix model name, temperature, commit SHAs, and embedding model, and record them |
| NFR-9 | Portability | Entire system runs with one `docker compose up`; config via environment variables |
| NFR-10 | Maintainability | Language support behind a `LanguageAnalyzer` interface; LLM behind an `LLMProvider` interface |
| NFR-11 | Privacy | The cloned workspace is deleted after ingestion; only redacted file text and derived data are stored; no raw secrets in logs or the database |
| NFR-12 | Usability | Graph is navigable via level of detail, with no screen full of thousands of nodes |

---

## 9. Technical overview

(Details in `repolens-system-design.md`.)

| Layer | Choice | Reason |
|---|---|---|
| Backend | Python, FastAPI | Team knows it; strongest ecosystem for parsing, embeddings, LLMs |
| Parsing | Tree-sitter plus per-language grammars | Fast, error-tolerant, multi-language |
| Database | PostgreSQL with pgvector | One store for jobs, structured data, embeddings |
| Graph analysis | NetworkX (in memory), edges persisted in Postgres | Mature algorithms, no extra infrastructure |
| Embeddings | Local `sentence-transformers` model | Free, reproducible, code stays local |
| LLM | Hosted LLM API behind `LLMProvider` (model decided later) | Swappable; not named in the submission |
| Job queue | Postgres jobs table with `FOR UPDATE SKIP LOCKED` | No extra service |
| Frontend | React with a graph library (React Flow or Cytoscape.js) | Good graph visualization |
| Runtime | Docker Compose: `db`, `api`, `worker`, `web` | Reproducible for both teammates |
| Hosting | Local first; optional hosted copy (Neon or Supabase for the database) | Laptop demo is the primary demo |

---

## 10. Key product decisions

1. **Rules detect, the LLM explains.** Rule-based detection is deterministic and measurable. LLM detection is not.
2. **Graph-aware retrieval over plain RAG.** Relevant context for code is its callers and callees, which similarity search alone does not find.
3. **Every answer is checkable.** Citations are required and validated.
4. **Depth over breadth.** Two languages with measured accuracy beats many languages with none.
5. **Boring infrastructure.** One database, one queue, no microservices.
6. **Redact before storing.** Secrets never reach the database or the LLM.
7. **Local-first delivery.** The laptop demo does not depend on free-tier hosting.

---

## 11. Success metrics and evaluation plan

Targets are set after the first baseline run, so they reflect what is achievable instead of invented numbers.

| Area | Metric | Method |
|---|---|---|
| Detector quality | Precision, recall, false-positive rate | Score against labeled ground truth (seeded fixtures plus a hand-labeled sample); Bandit, Semgrep, and ESLint are baselines scored on the same labels, on the rule categories we both implement |
| Retrieval quality | recall@k | 20 to 30 hand-written questions with known answers over 2 to 3 repos; vector-only, hybrid, vector + graph expansion, hybrid + graph expansion |
| Answer faithfulness | Percentage of answers with fully valid citations | Automated citation validator over the question set |
| Structural queries | Correctness | Compare graph answers against known ground truth in small fixture repos |
| Performance | Ingest time and memory vs repo size | Time runs on repos of different sizes |
| Graph correctness | Import and call edge accuracy | Manually verified sample on fixture repos |

**Evaluation protocol:** fix the model, temperature, embedding model, commit SHAs, and k; run each configuration the same way; record results and failure cases; report negative results honestly.

**Definition of success for the project:** a working end-to-end demo on Python repos, a documented evaluation with real numbers, and a report that states limitations clearly.

---

## 12. Acceptance criteria (per phase)

**Phase 1 (end of Week 1):** a Python repo can be submitted, cloned, parsed, and stored as symbols and edges; the graph endpoint returns data; `docker compose up` starts all services for both teammates.

**Phase 2 (end of Week 2):** the graph UI shows folder, file, and symbol levels; at least 5 Python detectors produce findings with correct lines; JS/TS analyzer work has started.

**Phase 3 (end of Week 3):** embeddings and graph-aware Q&A work with validated citations; JS/TS either produces a correct graph on a test repo or is demoted to Tier 1.

**Phase 4 (end of Week 4):** evaluation completed with recorded numbers; demo repos pre-ingested; report drafted; security limits verified (oversize repo rejected, secrets redacted, LLM-down case handled).

---

## 13. Milestones and team roles

| Week | Milestone |
|---|---|
| 1 | Vertical slice: clone, parse Python, store, basic graph endpoint, Docker Compose |
| 2 | Graph UI, first Python detectors, start JS/TS analyzer |
| 3 | JS/TS resolution and detectors, embeddings, graph-aware Q&A with citations |
| 4 | Evaluation, bug fixes, demo preparation, report; optional hosted copy (about 2 days maximum) |

**Team split (one developer)**
- **Developer:** all code (ingestion, parsing, graph, detectors, API, UI, retrieval, Q&A).
- **Second team member (no coding):** choosing and checking demo and evaluation repositories, writing golden questions with expected answers, running the usability test, demo script, README and report, UI feedback.
- Both must be able to explain the whole system in the viva, so a plain-language walkthrough is scheduled.

**Cut order if behind schedule:** hosted deployment, extra Tier 1 languages, JS/TS deep analysis (demote to Tier 1), explanation extras (FR-33). **Never cut:** evaluation and security limits.

---

## 14. Assumptions and constraints

**Assumptions**
- Evaluated repos are public, on GitHub, and within the configured limits.
- A small set of repos (2 to 3) is enough to demonstrate and evaluate the system.
- An LLM API is available within the team's budget (to be decided by the start of Week 3).
- The developer can run Docker locally.

**Constraints**
- One month, one developer plus a non-coding teammate, learning Docker and backend concurrency while building.
- Department requirements for the report and demo format are not yet confirmed (check with the project guide).
- Free hosting tiers change frequently and often sleep when idle.

---

## 15. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Call graphs are approximate in dynamic languages | Wrong or missing edges | Store edge confidence, show low-confidence edges differently, state the limitation |
| JS/TS import resolution takes longer than planned | Schedule slip | Demote to Tier 1 at the end of Week 3 |
| LLM hallucination | Misleading answers | Required citations, citation validation, low temperature |
| Prompt injection from repo text | Manipulated answers | Treat repo text as data, no tools for the model, no secrets in context, output sanitization |
| Secrets in analyzed repos | Leakage through storage, UI, or LLM | Skip secret files, redact before storing, best-effort detection (limits stated) |
| Huge or pathological repos | Crashes, cost spikes | Hard limits, per-file timeouts, rate limits |
| LLM provider outage or cost | Q&A unavailable or expensive | Provider interface, caps, graceful degradation |
| Graph too large to read | Poor usability | Level-of-detail graph, expand on click |
| Scope creep | Evaluation squeezed out | Cut order defined above, Week 4 protected |
| Learning curve (Docker, concurrency) | Slow start | Week 1 vertical slice with Docker Compose from day one |
| Hosted demo instability | Failed demo | Laptop demo is primary; hosted copy time-boxed |

---

## 16. Out of scope and future work

- Private repositories and GitHub OAuth, user accounts, per-user history.
- Incremental re-indexing and change tracking between commits.
- More deep-analysis languages (Java, Go, and others).
- Type-aware call resolution for better accuracy.
- Automatic test generation and "why might this endpoint fail?" analysis.
- Suggested fixes and pull-request integration.
- A decision model (for example for routing or severity triage) as an optional comparison against the keyword router.

---

## 17. Open questions

1. LLM budget: free or paid, and which provider and model (decide by the start of Week 3).
2. Does the demo need a public hosted URL, or is a laptop demo acceptable?
3. Which 2 to 3 repositories form the evaluation set, including one with known security issues?
4. Does the department require a specific report or demo format?
5. ~~Store full file contents or re-fetch?~~ **Decided:** store redacted file text in the database (needed for the code viewer and citations); the privacy statements were updated to match.

---

## 18. Glossary

- **AST:** abstract syntax tree, the tree form of parsed source code.
- **Tree-sitter:** an incremental, error-tolerant parser generator with grammars for many languages.
- **Symbol:** a named code element such as a function, class, or method.
- **Snapshot:** one analysis of a repository at a specific commit SHA.
- **Dependency graph:** nodes (files, symbols) and edges (imports, calls, inherits, defines).
- **Embedding:** a numeric vector representing the meaning of a text chunk.
- **pgvector:** a PostgreSQL extension for storing and searching vectors.
- **RAG:** retrieval-augmented generation, where retrieved text is given to an LLM to ground its answer.
- **Graph-aware retrieval:** retrieval that expands vector-search hits through the code graph (callers, callees, importers).
- **Citation validation:** checking that every file and line range cited in an answer exists in the context given to the LLM.
- **Prompt injection:** hostile text inside input data that tries to act as instructions to an LLM.
- **SSRF:** server-side request forgery, tricking a server into fetching an unintended address.
- **Confidence (edge):** how certain the analyzer is that a call or import edge is correct.
