# Re-baseline after graph correctness fixes, batch 2 (C-01 to C-06)

- **Branch / commit:** `fix/graph-batch2` at `88ee0c4` (base `main` `7917f12`). Date: 15 Nov 2026.
- **Machine:** the fixed eval PC (Intel Pentium Silver N5030, 7.8 GB RAM, Python 3.12.16).
- **Source:** findings C-01 to C-06 of the backend review of 14 Nov 2026.
- **Spend:** $0 API. No Ask question was asked and no paid eval was run. No new dependencies.

## What changed

| | Fix | Commit |
|---|---|---|
| C-01 | Python: an absolute import that no source root has is looked up in the importer's own folder and the folders above it, while none is a package (a script folder, a namespace package, pytest's rootdir insertion). Standard-library names are never taken from a folder. | `5e91682` |
| C-02 | Python: the source roots that contain the importer are tried first, deepest first. Two other roots with the same module give an `unresolved` edge instead of whichever root was found first. | `cf60e78` |
| C-03 | The parsers record how an enclosing function binds a called name (`app/ingest/scopes.py`). A call through a parameter or local variable is capped at 0.5. A nested function is a target only for calls it is visible from, and the nearest definition wins. A function nested elsewhere is never a 1.0 target or a guess. `Cls.f()` on an imported class goes to the class, not to a same-named module function. | `068266a` |
| C-04 | The 0.5 unique-name guess skips Python builtins, JS global functions, receivers whose first name is an external import (`os.path.join`), and builtin types as receivers (`str.join`). | `05e8c0a` |
| C-05 | Test paths: `spec/ e2e/ cypress/ example/ samples/ benchmarks/` added (any case). The stems `test`/`tests`/`spec`, `test_*`, `*_test`, `*-test` and `*_spec` now count for every code language. `testing/` is deliberately **not** a test folder, because packages ship it as product code (`IPython/testing`). | `a938c5f`, `88ee0c4` |
| C-06 | Discover lists the files it walked but did not keep, in the new column `jobs.unread_paths` (migration `2026-11-15-unread-paths.sql`). The broken-import rule counts those files as existing. NULL means "not recorded": the rule is skipped and the findings list carries a quality note. Graph edges are unchanged. | `e43f547` |

Every fix has regression tests. Each new test fails with that commit's code reverted; the exceptions are the guard tests, which must pass on both versions. Backend suite: 693 passed, 3 skipped (the opt-in model and network tests). ruff is clean, and CI is green on `88ee0c4`.

## Prediction, made before any fix code

- **File:** `graph_batch2_prediction-20261115-7917f12.json` (first commit on the branch), SHA-256 `81b1350a74cbccd369637a8d99c66712b31317623f5a4d24e94d94c9d12c871a`.
- **How it was computed:** a prototype of the fixes, run over the stored (redacted) file text of the 10 dev snapshots. The harness that rebuilds edges from stored text reproduced main's stored edges exactly.
- **Correction:** the file's method note says "63,666" stored edges. The correct total is **55,666** (sum over the 10 snapshots); the check covered all of them. The file is left as committed.

**Result: 592 of 592 changed edges match the prediction value for value (confidence, scope, site count, sites), and no edge changed that was not predicted.**
- **Files:** identical in every snapshot (path, language, content hash).
- **Code symbols:** identical in every snapshot.
- **Placeholder symbols:** the only symbol differences are 5 `external` placeholders (`hello` in flask; `consumers`, `routing`, `views` in gunicorn; `pip_install` in certbot). They disappear because C-01 resolves exactly those imports to repo files.
- **Findings:** 434 before and after, identical row for row (path, line, rule, severity, flags, message, snippet).
- **Chunks:** identical counts per snapshot.

### Edges by type and band (before -> after)

| snapshot | imports internal | imports external | imports unresolved | defines | calls 1.0 | calls 0.9 | calls 0.5 |
|---|---|---|---|---|---|---|---|
| 1 itsdangerous | 36 | 39 | 0 | 91 | 52 | 22 | 8 |
| 2 PyGoat | 38 | 216 | 0 | 103 | 145 | 32 | 110 -> 67 |
| 3 express | 154 | 244 | 0 | 0 | 63 -> 62 | 34 | 243 -> 244 |
| 4 fixture | 12 | 7 | 3 | 8 | 14 | 1 | 1 |
| 6 flask | 190 -> 191 | 250 -> 249 | 0 | 376 | 504 -> 512 | 91 | 563 -> 557 |
| 7 black | 167 | 410 | 15 | 746 | 1385 -> 1376 | 176 | 320 -> 338 |
| 11 gunicorn | 569 -> 572 | 1004 -> 1001 | 8 | 4011 | 4631 -> 4698 | 1243 | 1470 -> 1404 |
| 12 certbot | 1103 -> 1104 | 1205 -> 1204 | 0 | 3619 | 3058 -> 3061 | 1432 | 1461 -> 1430 |
| 13 redash | 1554 | 2232 | 1101 | 2623 | 4301 -> 4300 | 569 | 2266 -> 2215 |
| 14 ipython | 701 | 1463 | 0 | 1777 | 3314 -> 3217 | 628 | 1454 -> 1574 |

### Changes by finding

- **C-01:** 5 imports change from external to internal (flask 1, gunicorn 3, certbot 1), plus 1 new 1.0 call in certbot (`tools/pipstrap.py` -> `tools/pip_install.py`). Without the standard-library rule, black's test data `import collections` would have gone to a sibling `collections.py`.
- **C-02:** gunicorn only. 2 imports move from `tests/conftest.py` to `tests/docker/stress/conftest.py`, the one pytest would load. 6 calls go from 0.5 to 1.0 (now through an explicit import). No ambiguous case occurs in the 10 snapshots.
- **C-03:**
  - 179 calls go from 1.0 to 0.5, all through a parameter or local variable (ipython 144, black 20, gunicorn 11, redash 3, express 1).
  - 144 new 1.0 edges: a call to the nested function its enclosing function defines, where the old rule gave up because the file had several same-named nested functions.
  - 93 guesses at 0.5 removed; all pointed into functions nested elsewhere.
  - 2 wrong 1.0 edges removed. flask's call to the builtin `set()` pointed at a `set` nested in another test. ipython's `BadPretty()` pointed at the module-level class; it now goes to the class defined inside the calling test.
  - The imported-class case changes no edge in these snapshots.
- **C-04:** 138 guesses at 0.5 removed (gunicorn 61, PyGoat 43, ipython 15, certbot 11, redash 6, black 2). On 15 other guess edges only the site list shrinks.
- **C-05:** no edge change. New test files:
  - gunicorn: 11 (`benchmarks/`);
  - redash: 11 (`client/e2e/`, `client/cypress/`);
  - none elsewhere.

  No finding was on these files, and those snapshots have no chunks.
- **C-06:** no change. No snapshot hit the file limit, and the only broken-import findings are the fixture's 3 deliberate ones. `unread_paths` is now recorded on every new job (0 to 775 paths).

**Hand check of the 144 new nested-function 1.0 edges:** 20 drawn at random (`random.Random(20261115)`), each checked against the source. All 20 are correct: the call sits in the function that defines (or encloses) the nested def, and no other binding of the name exists in that scope. This is a sanity check, not a labelled sample.

## Reachability (4 study snapshots)

- **Shared helpers:** `app/reach/load.py` imports `resolve_python`, `PythonModules` and `is_test_path`. So C-01, C-02 and C-05 change reachability output through those helpers even though no file under `app/reach` was edited.
- **The guard doesn't see this:** `eval/reachability_guard.py` only diffs `backend/app/reach`, `backend/app/api/reach.py` and the design doc, so it does not cover this path. The input graph changed as well (C-03, C-04).
- **Measured on the live data after re-analysis:**
  - Every stored finding's tier is unchanged in gunicorn, certbot, redash and ipython.
  - All 25 paths to reached findings are unchanged.
  - Entry points: gunicorn loses 7 (main blocks and shebangs of `benchmarks/*.py`, now test code). certbot, redash and ipython are unchanged.

  All of this matches the prediction.

## Free evals

| Eval | Result | vs BASELINE-v1 / batch 1 |
|---|---|---|
| Retrieval A/B/C | A 0.71, B 0.86, C 0.93 (`retrieval_context-graph-batch2-20261115T163947Z-88ee0c4.json`) | Every question's record identical to batch 1, which was identical to BASELINE-v1. itsdangerous has no edge change; express's one change is in `test/Router.js`, test code that retrieval leaves out. |
| Detectors | `detectors-20261115T164104Z-88ee0c4.json` | Identical in every field (labels, scores, per-fixture, out of scope, tool versions). |
| PyGoat findings | 81, row for row as before | Unchanged. The labelled precision sample was not redrawn. |
| edge_lines_accuracy | itsdangerous 22/22, express 52/52, ky 50/50 edges; call sites 378/378, 11,649/11,649, 14,349/14,349 (`edge_lines_accuracy-20261115-88ee0c4.txt`) | Identical to `edge_lines_accuracy-20261107-cce0465.txt`. |
| ui_drawn_counts | 457 views (`ui_drawn_counts-after-graph-batch2-20261115T164529Z-88ee0c4.json`) | 13 views change counts, all explained by predicted edges (below). 102 symbol views differ only in `drawn_sha1`, which keys symbols by database id; ids are new after any re-analysis, and those views' counts are identical. |

**ui_drawn_counts changes:**
- **PyGoat:** 4 "everything" views lose guess edges (C-04).
- **flask:** gains the `tests/test_apps/helloworld` import (C-01, 3 views); 3 views lose guesses from `src/` into a function nested in a test (C-03).
- **black:** `linegen.py` symbol view draws 39 edges (was 38; new nested `append_to_line` edges). `trans.py` has 170 edges at the default setting (was 186; `is_valid_index` callers now at 0.5). The file view loses 2 test -> src guesses (C-04).

## Re-analysis

**Backup before the migration and re-analysis:**
- `C:\projects\repolens-db-backups\db-backup-2026-11-15-pre-graph-batch2.sql`: 48,348,086 bytes, `pg_dump --no-owner`, SHA-256 `cf40783d91fa4ae5acfa16f7fea804ae7da19a96bde49b7e67850075f06eb243`.
- Restored into a throwaway database: row counts of all 9 tables equal. That copy was the "before" side of the comparison and was then dropped.

**Migration:** applied twice to the dev database; the second run was a no-op.

**Procedure:** the API was restarted on `88ee0c4`. The snapshots were re-analysed one at a time with the PC otherwise idle, except for the first: my backup dump ran alongside it, a status request timed out, and the driver was resumed, so itsdangerous has no timing. The fixture snapshot was rebuilt with `smoke_qa.fixture_snapshot()`.

| snapshot | job | time | chunks before (non-test / test) | after | search |
|---|---|---|---|---|---|
| 1 itsdangerous | 25 | not measured | 113 / 68 | 113 / 68 | ready |
| 3 express | 26 | 484 s | 129 / 1,048 | 129 / 1,048 | ready |
| 6 flask | 27 | 512 s | 713 / 690 | 713 / 690 | ready |
| 2 PyGoat | 28 | 284 s | 753 / 79 | 753 / 79 | ready |
| 14 ipython | 29 | 628 s | 0 / 0 | 0 / 0 | failed, 600 s cap |
| 7 black | 30 | 627 s | 0 / 0 | 0 / 0 | failed, 600 s cap |
| 11 gunicorn | 31 | 637 s | 0 / 0 | 0 / 0 | failed, 600 s cap |
| 12 certbot | 32 | 687 s | 0 / 0 | 0 / 0 | failed, 600 s cap |
| 13 redash | 33 | 625 s | 0 / 0 | 0 / 0 | failed, 600 s cap |
| 4 fixture | 34 | 67 s | 51 / 4 | 51 / 4 | ready |

The search state is the same as before this batch for every snapshot. **black's search was lost in batch 1**, not here: it had 4,803 non-test chunks before batch 1's re-analysis (from that batch's backup) and has had none since.

## Earlier results are not re-run (note, 15 Nov 2026)

`CALL-CALIBRATION.md`, `CALL-CALIBRATION-J3.md`, `REACHABILITY.md` and `BASELINE-v1.md` describe the graph at their own commits and stay exactly as they are; none was re-run. Re-running one would be a new, exploratory study, only if the owner decides so.

The call-calibration repos are affected by this batch:
- PyGoat: C-04, 43 guesses removed.
- flask: C-01 and C-03.
- black: C-03 and C-04.

Whether any sampled edge is among the changed ones was not checked: that would need the sample, which this branch did not open.

## Not in scope, seen in passing

redash has 1,101 unresolved import edges, mostly aliases defined outside the root `tsconfig.json`. They are not covered by C-01 to C-06 and are left for later.
