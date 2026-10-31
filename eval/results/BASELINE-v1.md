# BASELINE-v1: re-baseline of v1-submitted on the own PC

Branch `eval/rebaseline-v1`, code under test `v1-submitted` = `75be6fb` (main at the time). Only files under `eval/` were added or changed; no product code. Everything below was run once; the first result counts (the one exception, a harness bug in my Semgrep change, is described and both result files are kept).

**How to read this.** All evaluations are small, set up and labelled by the people who wrote the rules and the retrieval code (the project owner with an AI assistant). Questions were written for the project, not by independent users. Differences of one or two questions or findings are **not conclusive**. "Old" means v1's published numbers (old laptop, before the 28 Oct evening review fixes); "new" means this PC on `v1-submitted`. Timings are new, not comparable to v1.

## 1. Machine and run info
- LAPTOP-4C2E555R, Intel(R) Pentium(R) Silver N5030 CPU @ 1.10GHz (4 threads), 7.8 GB RAM, Windows 11 (10.0.22631), Python 3.12.16.
- torch 2.14.1+cpu, sentence-transformers 6.2.0, transformers 5.21.0, tree-sitter 0.25.2, anthropic 2.3.0.
- Embedding model sentence-transformers/all-MiniLM-L6-v2 at revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; `MAX_ANALYSIS_S` = 600.
- LLM claude-sonnet-5-5, effort low, thinking between_tools, max tokens 4000, prompt version 2026-10-28.2; retrieval top-k 8, graph expansion True (up to 8), context budget 6000 tokens.
- Bandit 1.9.4 (same as v1; PyPI latest). Semgrep 1.182.1 run natively (same version as v1) from a local copy of the registry rules (see deviations).
- Conditions: the Claude Code desktop app was open during the express analysis and the Q&A run (it drove them); Chrome and other heavy apps were closed per the owner's standing instruction, which the scripts cannot verify. Chrome was open and the Claude Code app closed during the itsdangerous and PyGoat analyses (owner's log lines).
- Every result file in `eval/results/` carries its own run info (commit, dirty flag, versions, notes).

## 2. Analysis stats
Express was analysed through the API (native uvicorn) on this PC; itsdangerous and PyGoat were analysed earlier the same evening with the same code and the log lines were supplied by the owner. Source: `eval/results/analysis_stats-*.json`. ky was not analysed (no eval uses it).

| Repo @ commit | files kept / skipped | limit hit | parsed | edges (internal / external; calls 1.0 / 0.9 / 0.5) | detector findings (shown) | non-test chunks, embed | test chunks, embed | Ask ready |
|---|---|---|---|---|---|---|---|---|
| express @ 1c6f1b0 | 165 / 51 | no | 142 | 154 / 244; 63 / 34 / 243 | 0 (1) | 129, 83.6 s | 1,048 planned, 0 stored: stopped at the 600 s limit (about 512 done) | about 140 s |
| itsdangerous @ 672971d | 41 / 9 | no | 15 | 36 / 39; 52 / 22 / 8 | 0 (7) | 113, 64.5 s | 68, 45.8 s | about 67 s after submit |
| PyGoat @ 46fef96 | 222 / 240 | no | 117 | 38 / 216; 145 / 32 / 110 | 12 (60) | 834, 287.8 s | none (no file counted as test code; see bugs) | not captured |

PyGoat now has 60 findings in the UI (48 hardcoded-secret, 9 bare-except, 1 each eval/exec, SQL string, subprocess shell), against 59 in v1's population and 58 in PROGRESS: the f-string redaction fix (`116ca46`) took 59 to 58 and the config-file redaction fix (`a8638f8`) added 2 secrets in `docker-compose.yml`, giving 60.

## 3. Retrieval A/B/C (14 answerable questions, no LLM)
Result file `retrieval_context-rebaseline-*.json`; old file `retrieval_context-fixed-…6f96059.json`. Same questions, same overlap rule.

| Config | Old v1 | New baseline |
|---|---|---|
| A: search top 8 | 0.71 (10/14) | 0.71 (10/14) |
| B: search top 16 | 0.86 (12/14) | 0.86 (12/14) |
| C: top 8 + graph expansion | 0.93 (13/14) | 0.93 (13/14) |

Every per-question hit, first-hit rank and chunk count is identical to v1's file (`same as v1?` column), as expected: same code, same embedding model and revision, same snapshots' content.

| Q | repo | A top 8 | B top 16 | C 8+graph | first-hit rank (B order) | same as v1? |
|---|---|---|---|---|---|---|
| 1 | express | hit | hit | hit | 6 | yes |
| 2 | express | miss | hit | hit | 16 | yes |
| 3 | express | hit | hit | hit | 1 | yes |
| 4 | express | hit | hit | hit | 5 | yes |
| 5 | express | miss | miss | miss | - | yes |
| 6 | express | hit | hit | hit | 2 | yes |
| 7 | express | hit | hit | hit | 1 | yes |
| 9 | itsdangerous | miss | hit | hit | 13 | yes |
| 10 | itsdangerous | hit | hit | hit | 6 | yes |
| 11 | itsdangerous | miss | miss | hit | - | yes |
| 12 | itsdangerous | hit | hit | hit | 1 | yes |
| 13 | itsdangerous | hit | hit | hit | 1 | yes |
| 14 | itsdangerous | hit | hit | hit | 3 | yes |
| 15 | itsdangerous | hit | hit | hit | 2 | yes |

Paired comparison (hit in one configuration, miss in the other):

| Comparison | Wins | Losses |
|---|---|---|
| C vs B | Q11 | none |
| C vs A | Q2, Q9, Q11 | none |
| B vs A | Q2, Q9 | none |

Graph expansion beat plain search of the same size by one question (Q11) of 14: **not conclusive**. Q5 is missed in all three. The chunker and expansion rules were tuned after a first run on these same 14 questions (see README), so these numbers come from tuning on the evaluation set.

## 4. Detector fixtures (Python vs Bandit, JS vs Semgrep)
Result file `detectors-20261031T175030Z-ba68d03.json`. Same fixtures and labels, same scoring, same tool versions.

| Language / fixture | Tool | Old v1 run 2 (TP/FP/FN) | New baseline (TP/FP/FN) |
|---|---|---|---|
| Python, all | RepoLens | 11/6/0 | 11/6/0 |
| Python, all | Bandit | 8/5/3 | 8/5/3 |
| JS, all | RepoLens | 17/4/2 | 17/4/2 |
| JS, all | Semgrep | 4/4/15 | 4/4/15 |
| js/routes.js | RepoLens | 8/1/2 (P 0.89, R 0.80) | 8/1/2 (P 0.89, R 0.80) |
| js/routes.js | Semgrep | 3/3/7 (P 0.50, R 0.30) | 3/3/7 (P 0.50, R 0.30) |
| js/server.js | RepoLens | 9/3/0 (P 0.75, R 1.00) | 9/3/0 (P 0.75, R 1.00) |
| js/server.js | Semgrep | 1/1/8 (P 0.50, R 0.11) | 1/1/8 (P 0.50, R 0.11) |
| python/shop.py | Bandit | 8/5/3 (P 0.62, R 0.73) | 8/5/3 (P 0.62, R 0.73) |
| python/shop.py | RepoLens | 11/6/0 (P 0.65, R 1.00) | 11/6/0 (P 0.65, R 1.00) |

All new scores equal v1 run 2. The recall figures are on self-written fixtures: they show the rules catch the patterns they target, not real-world recall. Semgrep ran one pre-chosen configuration (`p/javascript` + `p/secrets`); other rulesets may score differently.

**Invalid first run, kept:** `detectors-20261031T174609Z-516271b.json` scored Semgrep 3/5/16 because of a bug in my local-rules change: native Semgrep prefixed rule ids with the dotted rule-file path (`C.projects.repolens-eval-assets…`), and that path contains "eval", which my keyword mapping took for a code-injection rule. I fixed the id handling (commit `ba68d03`, strip the prefix) and re-ran. This was a harness defect, not a tool outcome, but it is a re-run, so both files are kept and the first is not used. An earlier attempt stopped before scoring with a JSON escape error in `semgrep_rules.json` (no result file).

## 5. PyGoat precision (hand-labelled samples, 20 per tool)
Population at the pinned commit: RepoLens 60, Bandit 130 (all on the 115 Python files RepoLens kept, 0 parse errors); seed 20261028, same sort order as v1. Result file `realworld_precision_blind_scored-*.json`; sheet and labels in `eval/labels/`. Definition unchanged: real = a reviewer should act on it.

| Tool | Old v1 (labels proposed by Claude, confirmed by owner) | New baseline (blind sheet) |
|---|---|---|
| RepoLens | 18/20 = 0.90 (0.70–0.97) | 19/20 = 0.95 (0.76–0.99) |
| Bandit 1.9.4, B104 as labelled (not real) | 13/20 = 0.65 (0.43–0.82) | 13/20 = 0.65 (0.43–0.82) |
| Bandit, B104 counted as real | 17/20 = 0.85 (0.64–0.95) | 17/20 = 0.85 (0.64–0.95) |

Per rule (new): RepoLens hardcoded-secret 15/16; RepoLens py-bare-except 4/4; Bandit B104 hardcoded_bind_all_interfaces 0/4; Bandit B105 hardcoded_password_string 10/10; Bandit B106 hardcoded_password_funcarg 0/2; Bandit B113 request_without_timeout 1/1; Bandit B201 flask_debug_true 1/1; Bandit B324 hashlib 1/1; Bandit B603 subprocess_without_shell_equals_true 0/1.

- Sheet: 38 rows (30 real, 8 not real) for 40 sampled findings; 2 rows were merged because both tools flagged the same path, line and category (one label applied to both tools' findings).
- **Unsure:** 8 of 38 rows have an "unsure" note (03b6, 1bbe, 238d, 8cdb, b244, d555, dbdb, e461). Counting those rows all not real or all real gives RepoLens 16–20 and Bandit 8–14 real out of 20.
- The intervals overlap heavily. The two tools flag different things (RepoLens: secrets and bare excepts; Bandit: binds, debug mode, weak hashes, timeouts), PyGoat's lab secrets flatter any secret rule (16 of RepoLens's 20 sampled findings are secrets), and the samples are small. This does **not** show that either tool is more precise.
- Recall is not measured.

**Consistency with v1 labels (free check, same-person consistency, not independent agreement).** 39 sampled findings appear in both v1's sample and this one (19 RepoLens, 20 Bandit); the labels agree on 39 of 39, with 0 disagreements. The one v1 finding no longer in the sample is `sql_injection_lab/app.py:51` (the f-string `{password}` false alarm, removed by the redaction fix); it was replaced by `sensitive_data_lab/settings.py:8` (hardcoded secret, labelled real). Note this comparison is not blind: the owner had confirmed v1's labels before and had seen these findings.

## 6. Q&A (18 questions, claude-sonnet-5-5, effort low, thinking between_tools, prompt 2026-10-28.2)
Result file `final_qa_rebaseline-20261031T191116Z-e0eb426.json` (old: `final_qa-…36556cf.json`). Run once; no answer cache exists in the code; `--max-calls 24`; first result counts. Judged by the same pre-set rules as v1.

| Metric | Old v1 | New baseline |
|---|---|---|
| Strict score (pre-set rules) | 16/18 | 16/18 |
| of which answerable, strict | 14/14 | 14/14 |
| False-premise traps (Q8, Q16), strict | both FAIL | both FAIL |
| answered_correct_file (expected file among validated citations, answerable) | 14/14 | 14/14 |
| expected lines overlapped (informational) | 13/14 (Q5 missing) | 13/14 (Q5 missing) |
| citation_validity (answers with no dropped citation) | 15/18 = 0.83 | 17/18 = 0.94 |
| citations the server dropped | 4 | 2 |
| latency median / max (s) | 4.3 / 28.5 | 5.2 / 9.5 (new machine) |
| tokens in / out | 73,905 / 7,515 | 73,905 / 7,061 |
| cost at $2 / $10 per MTok | $0.223 | $0.218 |
| calls | 18 | 18 |

`citation_validity` is the metric v1 called "faithfulness": every citation the model wrote lies inside a snippet it was sent (the server removes the rest, counted as dropped). It does not say the citation supports the claim.

The two strict failures are the same two as in v1, both false-premise traps listed separately: Q8 (express starter generator) starts with "I could not find this in the provided code." but keeps 2 citations to the code it did read (rule needs zero); Q16 (itsdangerous encryption) says the code signs but does not encrypt, with 3 citations (rule needs "could not find" and zero citations). I have not re-judged them; the rule is unchanged. The model has no temperature setting, so answers differ between runs: Q16 cited 6 ranges in v1 and 3 now, and the dropped-citation total went from 4 (Q2, Q3, Q14) to 2 (Q3), i.e. citation_validity 15/18 to 17/18. A change of that size is run-to-run variation on this sample, not a measured improvement. Input tokens are identical to v1 (73,905), so the prompts and retrieved context were the same.

| Q | repo | strict pass | status | citations | dropped | expected file | expected lines | s | tokens in+out |
|---|---|---|---|---|---|---|---|---|---|
| identity | fixture | PASS | answered | 0 | 0 | – | – | 2.3 | 1384+27 |
| injection | fixture | PASS | answered | 3 | 0 | – | – | 3.3 | 1235+205 |
| 1 | express | PASS | answered | 6 | 0 | yes | yes | 4.1 | 3325+403 |
| 2 | express | PASS | answered | 10 | 0 | yes | yes | 6.0 | 4551+504 |
| 3 | express | PASS | answered | 9 | 2 | yes | yes | 4.2 | 3983+444 |
| 4 | express | PASS | answered | 4 | 0 | yes | yes | 3.9 | 6055+326 |
| 5 | express | PASS | answered | 8 | 0 | yes | no | 4.1 | 5135+475 |
| 6 | express | PASS | answered | 10 | 0 | yes | yes | 5.2 | 3700+571 |
| 7 | express | PASS | answered | 4 | 0 | yes | yes | 3.3 | 4196+261 |
| 8 | express | FAIL | answered | 2 | 0 | – | – | 5.5 | 3812+93 |
| 9 | itsdangerous | PASS | answered | 12 | 0 | yes | yes | 9.5 | 4623+681 |
| 10 | itsdangerous | PASS | answered | 7 | 0 | yes | yes | 6.4 | 4072+486 |
| 11 | itsdangerous | PASS | answered | 6 | 0 | yes | yes | 6.8 | 5136+499 |
| 12 | itsdangerous | PASS | answered | 10 | 0 | yes | yes | 5.3 | 4005+579 |
| 13 | itsdangerous | PASS | answered | 4 | 0 | yes | yes | 6.2 | 4387+275 |
| 14 | itsdangerous | PASS | answered | 9 | 0 | yes | yes | 4.1 | 4146+490 |
| 15 | itsdangerous | PASS | answered | 7 | 0 | yes | yes | 5.2 | 5154+445 |
| 16 | itsdangerous | FAIL | answered | 3 | 0 | – | – | 5.3 | 5006+297 |

(`identity` and `injection` rows are the two fixture-repo questions; Q-numbers match `eval/questions.yaml`.)

## 7. cited_sentence_rate (offline)
`eval/score_claims.py`, committed before it was run on any results. **It measures whether sentences carry a valid citation, not whether the citation supports the sentence.** Splitting rules are at the top of the script. Valid citation = present in the result's validated citations list. Identity and "could not find" answers count and carry none by design.

| Results | Sentences | With a valid citation | Rate | Answerable questions only |
|---|---|---|---|---|
| New baseline (own PC, v1-submitted) | 154 | 102 | 0.662 | 102/152 = 0.671 |
| Old (old laptop, pre-fix) | 158 | 102 | 0.646 | 102/156 = 0.654 |

Roughly two thirds of sentences carry a citation in both runs; the difference between them (about 0.02) is small and not conclusive, since the model's answers vary from run to run. The script lists the uncited sentences per answer in `cited_sentence_rate-*.json` (I have not categorised them) (the file `…191352Z…` is the new baseline, `…191401Z…` the old results). The first execution printed the numbers but crashed when saving (a path bug); I fixed that one line and re-ran, splitting rules unchanged.

| Q | new: cited / sentences | old: cited / sentences |
|---|---|---|
| identity | 0/2 | 0/2 |
| injection | 3/5 | 3/5 |
| 1 | 6/9 | 5/7 |
| 2 | 9/11 | 9/10 |
| 3 | 9/12 | 5/10 |
| 4 | 4/8 | 6/10 |
| 5 | 8/12 | 6/10 |
| 6 | 8/13 | 11/16 |
| 7 | 4/5 | 4/7 |
| 8 | 1/2 | 1/3 |
| 9 | 10/15 | 9/14 |
| 10 | 6/8 | 7/10 |
| 11 | 6/12 | 7/11 |
| 12 | 10/11 | 7/9 |
| 13 | 3/5 | 4/5 |
| 14 | 6/8 | 6/8 |
| 15 | 6/9 | 8/12 |
| 16 | 3/7 | 4/9 |

## 8. Deviations from the original procedure
1. **Different machine, new timings.** Everything ran on this PC (Pentium Silver N5030, 7.8 GB), not the v1 laptop; no timing is comparable with v1.
2. **Semgrep rules from a local copy.** v1 fetched `p/javascript` and `p/secrets` from the registry at run time on 28 Oct. This run fetched them once on 31 Oct 2026 and ran Semgrep 1.182.1 natively against the local copy, hash-checked against `eval/semgrep_rules.json` (fetch date, version, SHA-256; the files themselves are outside git, licence not checked). The registry rules may have changed between 28 and 31 Oct; the scores matched v1 exactly, but that is not proof the rule text is identical. The Docker fallback (read-only mounts) was added but not needed.
3. **Semgrep rule-id handling bug and first invalid run** (section 4), plus a malformed JSON manifest on the first attempt.
4. **Blind labelling, with AI help.** v1's labels were proposed by Claude and confirmed by the owner. The new labels were given on a blind sheet (tool hidden behind random ids, shuffled rows, neutral categories, identical snippets built from the pinned-commit source with one masking rule). The owner stated that **an AI session drafted the labels and notes from the sheet and the rule, and the owner reviewed and finalised them**; the key was not opened by either. See `realworld_labels_received_addendum.json`.
5. **Limits of the blinding.** (a) Categories that exist for only one tool (for example "server binds to all interfaces", "Flask debug mode on") can hint at the tool. (b) **39 of the 40 sampled findings were the same ones the owner confirmed in v1 on 28 Oct, so the owner had seen them before; the blinding hid the tool, not the findings.** The label-agreement check (39 of 39 equal) is same-person consistency, not independent agreement.
6. **PyGoat sample redrawn on the current code.** Same seed and ordering, but the population is post-fix (60 vs 59 RepoLens findings); 19 of RepoLens's and all 20 of Bandit's findings are the same as v1's draw.
7. **Express test code not embedded** (hit `MAX_ANALYSIS_S`); evals leave test code out, so unaffected. ky skipped.
8. **Stats for itsdangerous and PyGoat** come from API log lines the owner supplied, not from logs I captured; PyGoat's test-embed line was not captured.
9. **Eval-only code changes:** `runinfo.py` (machine, package versions, tool pins, notes), `detector_eval.py` (local rules, hash check, id prefix strip, `:ro` mounts), `smoke_qa.py` (`--notes`), new `analysis_stats.py`, `blind_sheet.py`, `score_blind.py`, `label_agreement.py`, `score_claims.py`. The retrieval scripts, questions and fixtures are unchanged.
10. The fixture repo for the identity and injection questions was ingested into the dev database by `smoke_qa.py` (copy, not clone), as in v1.

## 9. Bugs noticed (not fixed) and v2 list
1. **`is_test_path` does not treat `tests.py` as test code.** PyGoat's 79 chunks in three `tests.py` files (`challenge/`, `introduction/`, `scoring/`) are indexed and counted as non-test, so for example Bandit's B106 hits on `introduction/tests.py` are non-test findings. (v2)
2. **Misleading timeout message.** After express's test-code embedding was stopped, the Ask drawer says "Test code was not prepared for search: Analysis took longer than 600s and was stopped." although the analysis finished in about 140 s and only test-code embedding was cut off. The job and snapshot show `done`, so the analysis does not look failed; Ask works on the non-test code and offers a retry. (v2)
3. **`MAX_ANALYSIS_S` also covers test-code embedding**, which runs after Ask is enabled. On this PC express's test embedding (1,048 chunks) hit the 600 s limit. (v2)
4. README and PROGRESS numbers predate the review fixes (the README says so); the PyGoat population moved from 59 to 60 with the two redaction fixes.

## 10. API spend
One paid run: the Q&A run, 18 calls, 73,905 input and 7,061 output tokens, **$0.2184** at $2 / $10 per MTok (Sonnet 5.5, prices from v1's note). Analyses and every other eval made no LLM calls. Cap was $0.50. (The AI session that drafted the PyGoat labels is not part of this API figure.)

## Files changed or added (all under `eval/`)
Scripts: `runinfo.py`, `detector_eval.py`, `smoke_qa.py` (changed); `analysis_stats.py`, `blind_sheet.py`, `score_blind.py`, `label_agreement.py`, `score_claims.py`, `semgrep_rules.json` (added). Labels: `labels/pygoat-46fef96-rebaseline-sheet-labelled.csv`. Results: everything new in `results/` from 31 Oct, and this file.
