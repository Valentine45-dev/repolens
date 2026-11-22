# Locked-run scorer and freeze checks (branch `eval/locked-scorer`, 21 Nov 2026)

What this branch freezes before the locked questions are on this PC: the scoring rules, the
runner, the run-day procedure and the analysis time limit. Rules: `docs/V2-EVAL-DESIGN-metrics.md`
(§5, §6 and the decisions taken with the owner). No locked question, label or answer key was seen;
p-limit, tenacity, cachetools, httpx and axios were not fetched, cloned or analysed (tree metadata
only, Part B step 1).

## 1. What was built
| File | What it is |
|---|---|
| `eval/locked_metrics.py` | Pure scoring rules (schema check, code_hit/doc_hit, McNemar, graph sets, answered_correct_file, citation_validity, cited_sentence_rate via `score_claims.py`, unanswerable_ok with the revised false-premise rule, summary, agreement). Frozen by hash. |
| `eval/locked_eval.py` | Runner: `validate`, `estimate`, `run`, `summary`, `sheet`, `judge`, `analyse [--in-process]`. Guards for locked runs (question-file hash, scorer hash, clean tree, two passes, real provider, $1 cap per pass). |
| `eval/test_locked_metrics.py`, `eval/test_locked_eval.py` | 79 unit tests, no database or LLM; run in CI (`eval-unit` job). |
| `eval/tuning_locked_format.yaml` | 11 tuning questions (every type) on itsdangerous, express and flask, written before any run. |
| `eval/locked/` | `pins.yaml` (5 repos + commits), `README.md` (agents never open the question file or locked results), `.gitattributes` (question and hash files stored byte for byte), `scorer.sha256` (the freeze). |
| `eval/locked_tree_check.py`, `eval/timing_pins.yaml` | Part B steps 1 and 2. |

**How a question runs.** The runner calls `app.api.ask.ask()` in its own process, so the live
routing, retrieval (configuration C: top 8 + graph expansion up to 8, 6,000-token budget, test
code left out), prompt and citation validation are the product's own. The provider is wrapped to
count calls, tokens and cost and to stop a pass before a call whose worst case would pass the cap.
The chunks sent are read from the prompt. Configurations A, B, C are run separately (no LLM) for
code_how, locate and purpose. Each record has: route, status, answer, citations, dropped, chunks
sent, graph result paths, retrieval per configuration, latency, calls, tokens, cost.

**Output.** One JSON per run (run info, repo facts, every per-question record per pass, summary).
The console prints the summary only: overall, per repo, per writer, per type; paired code_hit
comparisons with exact McNemar p-values; agreement of pass 1 and 2. No question id or text appears
in the summary (a unit test checks this).

## 2. Tuning runs (the first result counts)
| Run | File | Spend |
|---|---|---|
| FakeProvider dry run, 2 passes (plumbing only; every answer is "could not find") | `locked_run-fake-dryrun-20261121T164612Z-106bcdc.json` | $0 |
| Paid check, 2 passes, Sonnet 5.5, effort low, thinking between_tools, prompt 2026-10-28.2 | `locked_run-tuning-paid-20261121T165413Z-190c1e9.json` | **$0.191** (estimate $0.218; cap $0.25 per pass) |

Prices for the paid check: $2 / $10 per MTok input / output, read from the provider's pricing page
(platform.claude.com, "Claude Sonnet 5.5" row) on 21 Nov 2026.

Paid check, 11 questions, per pass (pass 1 / pass 2):
- code_hit@k (code_how + locate, n = 4): A 3/4, B 4/4, C 4/4 in both passes (retrieval identical).
- doc_hit@k (n = 1): 0/1 in every configuration, by construction: v2.0 chunks code only.
- answered_correct_file: 5/5 and 5/5.
- graph: routing 3/3, exact 3/3, precision and recall 1.0 (both passes; no LLM involved).
- citation_validity (answers with no dropped citation): 6/8 and 7/8.
- unanswerable_ok: pass 1: 1 automatic pass, 2 awaiting human; pass 2: 3 awaiting human. Every
  unanswerable and false-premise answer begins with the "could not find" sentence and then
  explains with citations, which is the case the revised rule sends to the judge.
- Agreement pass 1 vs 2: route 11/11, answered_correct_file 5/5, graph exact 3/3, citation_valid
  7/8; unanswerable_ok 0/0 with 3 pending left out.
- These are 11 tuning questions written by the agent: they test the scorer, not the system.

**Rule changed before the freeze (owner, 21 Nov).** In pass 1 the express gzip question
(unanswerable) came back `unverified`: the "could not find" sentence, an explanation, and one
citation the server dropped (it pointed outside the snippets sent). Its validated citations were
empty, so the first rule passed it automatically. The automatic pass now needs zero citations in
the model's raw output (validated + dropped); any attempted citation sends the answer to the
judge (unit test `test_dropped_citation_goes_to_the_sheet`). `scorer.sha256` was regenerated
after the change. Re-scored offline under the new rule (information only; the recorded result
above stays as it is): unanswerable_ok in pass 1 becomes 0 automatic passes, 3 awaiting human.

**Tuning API spend to date (from result files):** final_qa 28 Oct $0.223, rebaseline Q&A 31 Oct
$0.218, smoke runs 28 Oct $0.0039 + $0.0002 + $0.085, today's check $0.191: **$0.721 recorded**
(PROGRESS also records one unsaved Haiku call, about $0.0004). The owner's own Ask testing in the
UI is not in any file. Within the $3 tuning cap.

## 3. Part B step 1: locked repos at their pins (tree metadata only)
`locked_tree_check-20261121T170645Z-81a41f0.json`. Trees not truncated, no submodules.

| repo @ commit | files | size | kept (upper bound) | code files (non-test) | non-test code | est. non-test chunks | est. embed time |
|---|---|---|---|---|---|---|---|
| sindresorhus/p-limit @ a8a6fbe | 16 | 0.05 MB | 11 | 6 (5) | 23.7 kB | 47–66 | 16–43 s |
| jd/tenacity @ aac059c | 97 | 0.26 MB | 92 | 20 (13) | 83.5 kB | 167–234 | 58–152 s |
| tkem/cachetools @ 07bb960 | 44 | 0.26 MB | 40 | 24 (10) | 66.2 kB | 132–185 | 46–120 s |
| encode/httpx @ 3ba5fe0 | 117 | 3.00 MB | 92 | 63 (26) | 313.4 kB | 627–878 | 219–571 s |
| axios/axios @ 84a9f3b | 466 | 3.62 MB | 427 | 239 (84) | 298.9 kB | 598–837 | 209–544 s |

All five are far under 2,000 files and 20 MB. Ratios: 2.0–2.8 non-test chunks per kB (itsdangerous
2.59, PyGoat 2.79, express 2.07, flask 2.02) and 0.35–0.65 s per chunk (BASELINE-v1 timings).

## 4. Part B step 2: analysis time and MAX_ANALYSIS_S
`analysis_timing-part-b-timing-inprocess-20261121T171500Z-14d439b.json`. In this process
(`analyse --in-process`), MAX_ANALYSIS_S=3600 so search could not be lost, one repo at a time, the
agent otherwise idle. Not idle: the owner's Chrome and Firefox, the Claude desktop app, and the
other session's API (idle, holding its own copy of the model); free RAM was about 0.8 GB.

| repo @ commit | role | files kept / skipped | non-test chunks | analysis (what the cap covers) | of which non-test embed | with test code |
|---|---|---|---|---|---|---|
| pallets/flask @ 49943b5 | tuning (snapshot 6, re-analysed in place) | 194 / 42 | 713 (690 test) | **509 s** | 436 s | 767 s |
| mochajs/mocha @ 5b5afa7 | timing only (snapshot 39, no questions) | 557 / 142 | 1,006 (1,849 test) | **426 s** | 350 s | 1,165 s |

- Times run from submit to `done` (includes about 24 s of model loading in this process for
  flask). Fetch to embed start took 50–75 s; embedding is the rest.
- Per chunk: flask 0.61 s, mocha 0.35 s. Both inside the 0.35–0.65 s range used for the estimate.
- Locked repos, worst case from section 3: httpx 878 chunks x 0.65 s = 571 s embed + about 75 s
  = **about 650 s**; axios about 620 s. Both are above the old 600 s cap: with 600 s, search could
  be lost on httpx or axios.
- flask on this PC, earlier measurements: 512 s (15 Nov), 730 s (14 Nov, under other load).

**MAX_ANALYSIS_S = 2100 (recorded and frozen for the locked runs).** Rule: at least 2.5x the slowest
measured, rounded up to a multiple of 300 s. The slowest full analysis of a repo this size on this
PC is flask's 730 s (14 Nov), so 2.5 x 730 = 1,825 s, which rounds up to 2,100 s. Using only
today's runs (509 s) would give 1,500 s. 2,100 s is about 3.2x the httpx worst-case estimate. A
higher cap costs nothing when analyses finish; it only delays the failure of a stuck one. The
limit is set for the run-day process only (`$env:MAX_ANALYSIS_S`); `.env` and the product default
(600) are unchanged on this branch.

Database state after the timing: flask's job 35 (search lost in the incident, section 6) and job 27
are marked `Re-run: ...`; job 36 re-analysed flask with search ready, 713 / 690 chunks as before,
1,976 edges as in the batch-2 re-baseline. mocha is snapshot 39 (job 37), a timing-only snapshot:
no questions are written for it.

## 5. Run-day checklist (owner)
Commands in PowerShell from `C:\projects\repolens`. `<X>` and `<Y>` are today's input and output
prices per MTok from the provider's pricing page. Keep every output; never re-run only failures.

**Before run day (freeze, §6.1):**
1. Build the question file off this PC. Compute its hash there (`Get-FileHash v2.0.yaml -Algorithm SHA256`).
2. On a branch from `main`, commit the hash only, then merge into `main` (CI green):
   ```powershell
   Set-Content -Encoding ascii eval\locked\v2.0.sha256 "<the 64-hex hash>"
   ```

**Run day:**
1. Close other apps, and **close every other Claude Code session, the FE2 session included**:
   a session that saw its background API exit restarts it on its own. Then make sure **no
   RepoLens API process is running**: the run-day analysis is in process, so none is needed (if an
   API is used for anything, exactly one, never two: a second API start marks running jobs
   "Interrupted by server restart"). This must list nothing:
   ```powershell
   Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'uvicorn' } | Select-Object ProcessId, CommandLine
   ```
2. Start the database and check `main` is clean and has the freeze:
   ```powershell
   docker compose up -d db
   ```
   ```powershell
   git switch main; git pull; git status --short; git log -1 --format=%H -- eval/locked/scorer.sha256
   ```
3. Branch for the run:
   ```powershell
   git switch -c eval/locked-run-v2.0
   ```
4. Analyse the five repos at their pins, in this process, with the frozen time limit (no API
   needed). It stops if search is not ready on any of them:
   ```powershell
   $env:MAX_ANALYSIS_S = "2100"; uv run --project backend --env-file .env python eval/locked_eval.py analyse eval/locked/pins.yaml --in-process --label locked-v2.0 --notes "run day; apps closed"
   ```
5. Copy the question file in and compare its hash with the committed one (the run checks again):
   ```powershell
   Copy-Item <usb>\v2.0.yaml eval\locked\v2.0.yaml; (Get-FileHash eval\locked\v2.0.yaml -Algorithm SHA256).Hash; Get-Content eval\locked\v2.0.sha256
   ```
6. Validate (schema, and every expected path exists in the analysed snapshots; prints counts only):
   ```powershell
   uv run --project backend --env-file .env python eval/locked_eval.py validate eval/locked/v2.0.yaml
   ```
   **Pre-registered (22 Nov, at the hash freeze):** validate is expected to report exactly **1**
   expected path not in the analysed snapshots (a file type v2.0 does not store; kept in the key
   deliberately). The command then exits with an error code; that is expected for a count of 1.
   **Any other count: stop and report**, do not run.
7. Estimate one pass (refuses above $1):
   ```powershell
   uv run --project backend --env-file .env python eval/locked_eval.py estimate eval/locked/v2.0.yaml --price-in <X> --price-out <Y>
   ```
8. The run: two full passes, summary only on screen:
   ```powershell
   uv run --project backend --env-file .env python eval/locked_eval.py run eval/locked/v2.0.yaml --passes 2 --price-in <X> --price-out <Y> --label v2.0 --notes "run day; prices from the pricing page <date>"
   ```
   If a pass is VOID (spend cap), the run stops; report it, do not resume or re-run part of it.
9. Blind sheet, written outside the repository (the runner refuses a folder inside it):
   ```powershell
   uv run --project backend --env-file .env python eval/locked_eval.py sheet eval/results/locked/<results>.json --out C:\projects\repolens-eval-assets\judging-v2.0
   ```
10. Commit the question file with the results and the analysis record, push, ask before merging:
    ```powershell
    git add eval/locked/v2.0.yaml eval/results/locked eval/results/analysis_timing-locked-v2.0-*.json; git commit -m "eval: locked run v2.0 (two passes)"; git push -u origin eval/locked-run-v2.0
    ```
11. After the judge has filled the sheet (faithful: yes/partly/no; rejects_premise and
    false_claim_cited: yes/no on rows with a premise_truth):
    ```powershell
    uv run --project backend --env-file .env python eval/locked_eval.py judge eval/results/locked/<results>.json --sheet <filled csv> --key <key json> --judge J1
    ```

**v2.1** (after Step 5): the same file, the same steps with `--label v2.1`. If the runner gained
new retrieval configurations, add `--runner-changed`; the diff against the freeze is saved in the
results. The scoring files must be byte-identical (after line endings), or the run refuses.

v2.1 additions (Step 5 Part A, 22 Nov), between steps 4 and 6. **Part A ships switched off**
(`QA_DOC_POOL` 0 by its adoption rule: doc-leak above 30% at every cutoff, PROGRESS.md), so `/ask`
and every answer are code only. The doc backfill is needed only if a configuration sends docs. The
v2.1 runner has one: **E**, retrieval only (never sent to the LLM; answers unaffected), DG plus up
to 2 doc chunks at the 8th code vector hit's cutoff, reported for doc_hit (its code_hit must equal
DG's). So step 4a stays for v2.1:
- 4a. Step 4 reuses the v2.0 analyses (same pins), which have no documentation chunks. `analyse`
  now prints each repo's snapshot id and, at the end, the backfill command for them. The owner runs
  it (agents never run it on these snapshots). It chunks and embeds the stored doc files with the
  same function a fresh analysis uses, and replaces only the doc rows (code chunks untouched):
  ```powershell
  cd backend; uv run --env-file ../.env python -m app.ingest.docchunks <the printed snapshot ids>; cd ..
  ```
- 6. Validate as before. **Pre-registered for v2.1: 2 expected paths not in the analysed snapshots,
  the same count as v2.0's run-day result** (doc chunks do not change which files are stored).
  Any other count: stop and report.
- The run (step 8, with `--runner-changed`) refuses when a configuration sends docs (E is in
  `CONFIGS`, or `QA_DOC_POOL` > 0) and a snapshot has doc files but 0 doc chunks (the backfill was
  not run). Run info records the real doc settings (`/ask` off; E's pool and cutoff) and the doc
  chunk count per repo.

## 6. Incidents and limits
- **A second API start interrupted a timing run (my mistake).** I stopped the native API (free
  RAM 0.74 GB) for the in-process runs; the idle FE2 session restarted its API on port 8000 about
  a minute later (it saw its background task exit; confirmed by the owner). My own API for the timing (MAX_ANALYSIS_S=3600) then
  failed to bind, but its startup hook still marked the running flask job 35 "Interrupted by
  server restart". The other API kept running the job, which finished with search failed at its
  600 s cap. The first timing file is kept as invalid (`analysis_timing-part-b-timing-
  20261121T170128Z-81a41f0.json`). The timing was redone in process (`analyse --in-process`, no
  API started). Database backup before any of this:
  `C:\projects\repolens-db-backups\db-backup-2026-11-21-pre-locked-timing.sql` (48,554,232
  bytes, SHA-256 `F46065BCF194FB7A8130068B13E3A32FAC3C157E21383F808C875D203843C40C`), restored
  into a throwaway database with identical row counts in all 8 tables, then dropped.
- The other session's API is still running on 8000 (not stopped by this branch).
- `snapshots.llm_tokens_used` keeps a reserved estimate when a pass is stopped by the spend cap
  in the middle of a call (the product's reserve is not returned); recorded before and after.
- The blind sheet shows `premise_truth` on unanswerable and false-premise rows, so those rows
  reveal their type; configuration and pass are hidden.
