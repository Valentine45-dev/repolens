# Reachability as a re-ranker of Bandit's output: pre-registration (v2, approved by the owner with six decisions on 8 Nov 2026)

Branches: `feat/reachability` (the tiers) and `eval/precision-at-20` (this evaluation). v2 step 6b, Part 2.
This file is committed and pushed **before any Bandit counting, any reachability run on an evaluation repo, any sample draw and any label.**
After that, the only edits allowed are typo fixes and a dated "Deviations" section at the bottom.

Why the design changed (v1 of this draft, 8 Nov): RepoLens's own security rules fire too rarely on real projects for an ordering test
(outside tests and docs: flask 2, black 1, express 0, itsdangerous 0; only a deliberately vulnerable app like PyGoat has dozens, and 45 of its 48 are secrets).
Bandit's default output on a Python project is long enough to be ordered, so reachability is tested as a **re-ranker of Bandit's findings**.
RepoLens's own findings are a secondary, honestly reported comparison.

## 1. Question
Do Bandit's findings, put in reachability order (is the flagged code reachable from an entry point?) before Bandit's severity,
put more findings a reviewer should act on near the top than Bandit's own severity-and-confidence order puts there?

**H1:** average precision (AP) of the reachability order is higher than AP of Bandit's order, on the same findings with the same labels.
One-sided, because the claim is "better", not "different".

The study is small and set up by the people who built the tool. A result is a result for these repos, not a general rate.
The report says "reachability helps / does not help on these repos", never "reachability works".

## 2. The two orderings (paired: same findings, same labels)
Bandit (pinned version, with B101 and B404 skipped, section 6) is run once per repo. Each finding is one Bandit result: `(path, line_number, test_id, severity, confidence)`.
- **Bandit order (control):** `(severity rank, confidence rank, path, line, test_id, occurrence)`, with HIGH = 0, MEDIUM = 1, LOW = 2 for both ranks.
  (Bandit's own text output is grouped by file; this is the order a user gets by sorting its severity and confidence columns.)
- **Reachability order (treatment):** `(tier rank, severity rank, confidence rank, path, line, test_id, occurrence)`.
- **Mapping to a tier:** each finding is mapped to the innermost RepoLens symbol (function, method, class body) whose line range contains `line_number`, or to its module when
  the line is outside every symbol. The tier is a property of that unit, so findings in one function share a tier.
- Nothing else differs between the two orderings. "Severity first, then tier" is exploratory only: computed and shown, never tested, never the headline.

## 3. Tiers
A module is reached when it is imported along a path from an entry point (importing runs module-level code).

| Tier | Meaning | Edges allowed on the path | Rank |
|---|---|---|---|
| **solid path** | An entry point reaches the unit. | internal import edges and call edges at confidence 1.0 or 0.9 | 0 |
| **guess path** | Reached only if 0.5-confidence call edges are used. | plus call edges at 0.5 | 1 |
| **not checked** | The finding is in a file that is not analysed code (config such as `.yml .yaml .json .toml .ini .cfg`, `Dockerfile`, `docker-compose.yml`, templates, documentation), or in a Python file RepoLens could not parse. UI text: "Not in analysed code, so reachability was not checked". | none | **1** (same position as guess path, a separate label, never counted as guess path) |
| **no path found** | Analysed code, but no path from any entry point, even with guesses. | | 2 |

- Why two path tiers: call calibration (`CALL-CALIBRATION.md`, 7 Nov) found 30/30 correct at 1.0, 30/30 at 0.9 and 21/30 = 0.70 at 0.5.
- Bandit findings are all in `.py` files, so "not checked" can only occur here for an unparsable file. It matters for the secondary comparison (secrets in config files).
- "No path found" is not "dead code": call edges are name-based, and dynamic dispatch, decorators and plugins are invisible. The UI never says "unused".
- **Entry points** (frozen in the design note committed with `feat/reachability`, before any evaluation repo is analysed with it):
  `if __name__ == "__main__"` modules, `__main__.py`, `console_scripts` / `[project.scripts]` targets, route and CLI-command decorated functions of the common frameworks,
  and for libraries the public API (names exported by a package's `__init__`). Test files are never entry points.
- **Known risk to the contrast:** in a library most code is public API, so most findings may land in one tier and the two orderings then barely differ.
  The report shows the share of each pool in each tier next to every result. A repo where all findings share one tier counts as a difference of 0; it is not dropped.
- The tiers are built and tuned on the development set only (section 5). The reachability code is not changed after the first evaluation repo has been analysed with it;
  its commit SHA is recorded in the setup file.

## 4. Metrics
Computed per repo on the labelled pool (section 7) in each ordering, with **unsure rows removed first** (primary), so ranks are positions among the remaining rows.
- **Precision@20 (P@20)** = real findings among the first 20 / 20. Reported for a repo only if at least 40 rows remain after removing unsure (P@k needs a list of at least 2k).
- **Average precision (AP)** = (1 / R) * sum over real findings of the precision at that finding's rank, R = real findings in the pool. A pool with R = 0 has no AP; the repo is reported ("no real findings") and left out of the means.
- **Per repo and pooled.** Pooled AP = mean of the per-repo values (each repo counts once). Pooled P@20 = real findings in the first 20 of every repo / (20 x repos).
- **Intervals.** Wilson 95% interval on every P@20 (per repo: n = 20; pooled: n = 20 x repos, which treats findings as independent and is therefore optimistic: findings in one file are correlated)
  and on every set precision (real / (real + not real) over the pool). For the difference in AP, a bootstrap 95% interval over files (clustered), 10,000 resamples, `random.Random(20261108)`.
- **Primary endpoint:** pooled mean of AP(reachability) - AP(Bandit). P@20 is reported next to it with its own p-value, **not corrected for the second test**.
- **Sensitivity (same intervals):** unsure counted as real; unsure counted as not real. The unsure rows are listed by id with their notes.
- Also shown: share of each pool in each tier; real share per tier (a descriptive table; not tested).
- A tie in rank cannot occur (the key ends in `occurrence`).

## 5. Test (paired)
Randomisation test of "the tier carries no information about relevance beyond Bandit's order":
- Statistic: mean over repos (with R > 0) of AP(reachability) - AP(Bandit). The same procedure gives the P@20 statistic.
- Null: within each repo, shuffle the tier values **among the units that contain at least one pool finding**, so every finding keeps its unit's (shuffled) tier and findings of one function stay together;
  severity, confidence, path, line and test_id stay in place. Re-sort, recompute both APs. 10,000 shuffles, `random.Random(20261108)`.
  p = share of shuffles whose statistic is at least the observed one (one-sided, alpha 0.05); the two-sided value is shown too.
- Why not flip signs across repos: with n repos the smallest possible two-sided p is 2 / 2^n (0.0625 at five repos), so no result could pass.
- The p-value describes this set of findings, not repos in general.
- Reported whichever way it falls; a null or negative result is written up the same way.

## 6. Repos: the rule is fixed here, before anything is run
**Eligible:** public Python repositories on GitHub that satisfy all of:
1. **Not used in development:** not PyGoat, flask, black, express, itsdangerous (the development set), not markupsafe, ky or `repolens-smoke/sample_repo` (analysed during development),
   and not a repo of the locked Q&A set. The locked set's repo URLs (names only; its questions are never opened, CLAUDE.md rule 10) are in `eval/results/reachability_exclusions.txt`:
   `https://github.com/sindresorhus/p-limit` and `https://github.com/jd/tenacity`. A pool repo on that list is skipped and named in the report.
   **More locked repos may be added later. If one turns out to be in the accepted set, that is recorded in the report; the repo is not swapped out.**
2. **Within the size limits:** the discover stage, with the pipeline's limits (2,000 kept files, 1 MB per file, the same skip lists), must not hit its file limit (`hit_file_limit` false). A repo over the limit is skipped, not truncated.
3. **At least 40 non-test Bandit findings** (below, with B101 and B404 skipped). Fewer than 40 is skipped; the count is reported.

**Counting run (the only thing run before the next step):** shallow clone as in CLAUDE.md (depth 1, hooks off, no submodules, no LFS smudge, symlinks off, `GIT_TERMINAL_PROMPT=0`, time limit; clone deleted afterwards).
The discover stage lists the kept Python files; test and example files (`app.paths.is_test_path`) and files under `docs/` or `doc/` are removed;
**the remaining files, as the discover stage stores them (secrets redacted, line numbers unchanged), are written to a temporary directory and Bandit runs there**, so no `.bandit`, `pyproject.toml`, `setup.cfg` or `tox.ini` of the repo can be found or read.
Command: Bandit **1.9.4** (as in the v1 baseline), `bandit -r <copy> -f json -q --ignore-nosec --exit-zero --skip B101,B404`, otherwise default plugins, default severity and confidence thresholds, no baseline file.
**B101 and B404 are skipped, in the 40-count and in every labelled list (decided by the owner before any count):** `B101` flags `assert` statements and `B404` flags `import subprocess`;
neither is actionable by itself (an assert is not a vulnerability, and importing the module is not a call). `B603`, `B607` and `B311` stay in: they flag a call that executes a process, a partial executable path and a weak random source.
`--ignore-nosec` is used because `# nosec` comments in the repo would otherwise silence findings (same reason as Ruff's `--ignore-noqa`).
Bandit parses files and never runs them (CLAUDE.md rule 1). Output kept: counts per repo, per `test_id`, per severity and per confidence. No snippets and no file text are stored.
A test (committed with the counting script, run first) puts a `.bandit` file, a `pyproject.toml` with `[tool.bandit]` and a `# nosec` line in a seeded repo directory and checks that all three are ignored, and that B101 and B404 are skipped while B603 is still reported.

**The pool of candidates is fixed here, in this order (alphabetical by owner/name), and none is looked at in any other order:**
`benoitc/gunicorn`, `celery/celery`, `certbot/certbot`, `getredash/redash`, `ipython/ipython`, `mitmproxy/mitmproxy`, `OctoPrint/OctoPrint`, `paramiko/paramiko`,
`psf/requests`, `pytest-dev/pytest`, `ranger/ranger`, `scrapy/scrapy`, `sphinx-doc/sphinx`, `sqlmapproject/sqlmap`, `tornadoweb/tornado`, `urllib3/urllib3`, `yt-dlp/yt-dlp`.
Repos are counted in that order. **The first four that satisfy the rule are accepted** (target 4); counting then stops, so the repos after the fourth are not counted.
If the whole pool is exhausted with fewer than four, the report lists what was counted and the study **stops there**: no repo is added to the pool afterwards.
The pinned full commit SHA (default branch HEAD at the counting run) and the licence of each counted repo are recorded.
**Minimum to make a comparison claim:** at least 3 accepted repos. With 3 the report says "small"; with fewer it stops.

## 7. Pool and sampling (the labelled set)
- The pool of a repo is its whole non-test Bandit list if it has **60 findings or fewer**; otherwise a seeded random sample of **60** drawn from the list sorted by `(path, line, test_id, occurrence)`:
  `random.Random(f"{SEED}-{repo}")`, `SEED = 20261108`. Both orderings are applied to the same pool, so the comparison is paired.
- Consequence to state in the report: for a repo with more than 60 findings, P@20 and AP are computed on a **random 60 of its list**, so "first 20" means the first third of that sample,
  not the first 20 of the repo's whole list. They measure how well each order separates real from not real; they are not the P@20 a user of the full list would see.
- Order of events: the reachability tiers are computed for the accepted repos' whole lists first; the sample is drawn from the sorted list without looking at tiers or labels.
- **Secondary pool (RepoLens's own findings):** on the same accepted repos, the Security category of the Part 1 analysis, excluding rows with `in_test`, `in_docs` or `placeholder`
  (what a reader sees after "Hide test and example code" and "Hide probable placeholders"); all rows are labelled if 60 or fewer, else the same seeded sample rule.

## 8. Sheets and labels
- **One pooled blind sheet** for Bandit and RepoLens findings from all accepted repos: random row ids (`r-` plus five letters), shuffled rows, the tool, the rule id, the severity, the tier and the rank hidden;
  one row where both tools flag the same path, line and category (both findings get that label); code from the stored redacted text with 3 lines of context, masked once by `blind_sheet.mask()`.
  Limit of the blinding: a rule's wording can hint at the tool.
- The key (id -> repo, tool, finding ids) is `key.json` outside git. It is not opened until the labelled sheet's SHA-256 is committed and pushed.
- **Label rule (given by humans; an AI never proposes a label).** Judge 1 (J1) is the project owner; Judge 2 (J2) is the second judge (not yet confirmed; labelling by J1 can start without J2, and if J2 never labels, the report says the second-judge check was not done). Committed files carry the codes `J1` and `J2` only.
  - **real:** the flagged line is a genuine instance of the weakness the rule names, in this code's context, so a reviewer should act on it. Deliberate vulnerabilities in a lab app would count as real.
  - **not real:** it is not (constant input, a value that cannot be attacker-controlled, an import of a module, a test-only or example value, an unrelated meaning of the name).
  - **unsure:** plausibly either; a note is required.
  - A rule that flags a category rather than a defect (for example Bandit's `B104` bind-to-all-interfaces) is labelled by the same rule. The report **always** shows the primary result a second time with every `B104` row counted as real (the v1 baseline's Bandit precision was 0.65 as labelled and 0.85 with B104 counted as real).
- **One label per row.** There is no second column.
- **J2 subset: 20% of each repo's pool**, rounded up, drawn with `random.Random(f"{SEED}-judge2-{repo}")`, shown in the same blind sheet format (the J2 sheet holds only these rows, shuffled).
  Reported: percent agreement and Cohen's kappa on `label`, unsure as its own category, the disagreeing row ids with each judge's note.
  If kappa is below 0.4 the headline is called **judge-dependent**, and the primary table is repeated for the J2 subset with both judges' labels. J1's labels are the primary labels; J2 does not replace them.

## 9. Secondary comparison: RepoLens's own security findings with and without reachability
Same two orderings idea on RepoLens's list: current order `(placeholder, severity rank, path, line, id)` (`app/api/findings.py`, frozen at `main` `803a24f`) against
`(placeholder, tier rank, severity rank, path, line, id)`, on the secondary pool of section 7. Lists will be short; therefore:
- P@k only where a list has at least 2k findings (k = 10 or 20); AP and set precision with Wilson intervals otherwise; the per-repo table is the result.
- The same tier-shuffle test is computed on the pooled set and labelled **exploratory** with its p-value; no claim rests on it.
- Config-file secrets are "not checked" (rank 1, same position as guess path).
- It is reported even if every list is tiny or tied. Nothing about RepoLens's own rules is concluded from the Bandit result.

## 10. Order of work and what is fixed
1. This file is shown to the owner as a diff, then committed and pushed with `eval/results/REACHABILITY-SHORTLIST.md`. **Nothing is counted before this commit.**
2. The counting script (`eval/reachability_bandit_count.py`) and its config-isolation test are written and committed. The counting run is made once, in the order of section 6.
   The report lists every counted repo with its pinned SHA, licence, kept-file count, non-test Bandit total, and the counts per severity, confidence and `test_id`, and which repos qualify. **Then the work stops** for the owner. No tier code is run on these repos.
3. `feat/reachability` is built and tuned on the development set. Its commit SHA is recorded. It does not touch `eval/`.
4. Tiers computed on the accepted repos; samples drawn; blind sheet, J2 sheet and `key.json` built; hashes recorded in `eval/results/reachability_setup-*.json`.
5. J1 (and J2) label. The labelled sheet's SHA-256 is committed and pushed. Only then is the key opened.
6. The scoring script runs once. The first result counts; a failed run is fixed and re-run in full, never on the failures only, and both result files are kept.
7. `eval/results/REACHABILITY.md` reports every number above, including those that do not favour reachability, and the limitations below.
- Eval branches change only `eval/`. Product branches do not edit saved eval results. No LLM call is made anywhere in this study ($0). Run info records the machine, and the versions of Python, Bandit and Ruff.
- No repo is added or dropped after the counting run. No label exists before the key is opened for scoring.

## 11. Limitations (written now, repeated in the report)
- **Python only.** Bandit is a Python tool; no JavaScript or TypeScript result is produced. Nothing here says reachability helps JS/TS findings.
- **Semgrep arm dropped.** The Semgrep Rules License v1.0 (page dated 13 Dec 2024) permits use for the licensee's own internal business purposes and forbids distributing the rules;
  it does not mention academic use or publishing results. Rule files stay out of git and no Semgrep result is reported.
- Bandit is the object being re-ranked; the result says how well reachability re-ranks Bandit's output, not how good Bandit is or how good RepoLens's rules are.
- AP and P@20 are computed on a pool of at most 60 findings per repo (a random sample when the list is longer).
- Labels are by the project owner (the people who built the tool), with a 20% second-judge check; this is not an independent evaluation.
- RepoLens's call graph is name-based (calibration: 0.70 precision at confidence 0.5), entry points are heuristic, and "no path found" is not "unused".
- Small sample: 3 to 4 repos, at most about 240 labelled Bandit rows. Intervals are wide and findings within a file are correlated.
- One machine (this PC); run info is recorded; a different machine means re-running.

## 12. Decisions recorded (owner, 8 Nov 2026)
1. Pool of 60 findings per repo (a random sample when the list is longer), as in section 7.
2. The candidate pool of 17 and its alphabetical order, as in section 6.
3. Locked repos excluded: `p-limit` and `tenacity` (names only). Later additions are recorded, not swapped.
4. B101 and B404 excluded from the count and the labelled lists; B603, B607 and B311 kept (section 6).
5. No second label column; one label per row.
6. J2 is the second judge, code `J2` only, not yet confirmed; J1 labelling does not wait for J2.

## 13. Amendment 1 (8 Nov 2026), committed before any evaluation repo is analysed with the reachability code

Nothing in sections 1 to 12 is rewritten; this section adds to them. It is committed and pushed before the four accepted repos (gunicorn, certbot, redash, ipython) are ingested or their tiers computed.
The counting run (section 6) is the only thing done with them so far, and it used no tier code.

### 13.1 Frozen tier code
- **Frozen tier code: merge commit `cfd4835dc50b5497a189ca34ca410df19767bc52`** (`feat/reachability` merged into `main`, CI green on the branch `8d65fe8` and on `main`).
- The tier rules are `docs/reachability-design.md` and the code is `backend/app/reach/` at that commit. Section 3 of this file is the summary; where they differ in detail, that document at that commit decides.
- No change to the tier code after this commit may be used for this study. A change would be written into a dated deviation below and the tiers would be recomputed, from scratch, for all repos.
- Built and checked on the development set only (PyGoat, flask, black, express, itsdangerous). The four evaluation repos were not opened, ingested or inspected before this commit (the counting run only counted Bandit findings).

### 13.2 Decision 1: one solid tier, entry class recorded (owner, 8 Nov)
- The ranking has **one** solid tier. There is no split of solid into "app entry" and "public API only" in any sort key, primary or exploratory.
- Each finding's **entry class** is recorded at compute time (`reach_entry_class`): `app` if the same tier is reached without the public-API entry points, `public-api` if it needs them; none when there is no path (no path found, not checked).
  App entry kinds: `main-block`, `main-module`, `console-script`, `plugin-entry`, `route-or-command`, `url-handler`, `framework-module`, `shebang`, `package-main`. The public-API kind is `public-api` (the exports of an `__init__.py`).
- **Section 4's descriptive table** ("real share per tier") becomes: **real share per tier, and per entry class, with a tier x entry-class cross-table**, unsure excluded, counts shown next to every share, Wilson intervals, no test. It is descriptive.
- Dev-set facts behind the decision (8 Nov, non-test findings, RepoLens's own findings): 59 solid via an app entry, 2 solid via the public API only, 2 guess, 5 no path found, 3 not checked.
  Too few public-API-only findings to say the split would help, and the app-entry detectors are the heuristic with lower recall, so a split would make the order depend on them.

### 13.3 Decision 2: structural guesses and the tie-break (owner, 8 Nov)
- A class reaches its constructor (`__init__`, JS `constructor`) as a solid step. It reaches its other **special (dunder) methods** (`__enter__`, `__call__`, `__deepcopy__` ...) as a **guess**, because Python calls them implicitly.
  **An ordinary method gets no structural edge**: only a call (by a name the resolver can match) reaches it, so a method nothing calls is "no path found" even when its class is reached.
- A function defined inside a function remains a guess (it runs if the enclosing function hands it out, as a decorator's wrapper does). It changed no dev-set finding either way.
- **Tie-break among paths** to a symbol: fewest guessed steps, then fewest structural guesses, then fewest steps. The tier depends only on the first key; the other two decide which path is shown.
- Section 3's "guess path" is therefore: reached only if at least one step is a guess, where a guess is a call matched by name at confidence 0.5, a special method Python calls implicitly, or a function defined inside code that is reached.
- Effect on the dev set: no dev-set finding changed tier. Symbols moved from guess to no path found (itsdangerous 8, PyGoat 14, flask 185, black 128); solid is unchanged.
- Wording in the UI (fixed in the same commit): "Reachable only through guessed steps (a call matched by name, a special method Python calls implicitly, or a function defined inside code that is reached)".

### 13.4 Also fixed before the freeze (found by tests)
- A file that is a single function mapped its lines to the module because the two have the same line range. A tie now prefers the non-module symbol.
- Decorator and `__main__` detection read real code with `ast`; examples inside docstrings no longer count as entry points (flask: 18 route/command entry points, 14 of them docstrings, now 4).

### 13.5 What is reported next, before any label exists
For each of the four repos: the pinned SHA, the size of the Bandit list, the pool size, the tier shares and the entry-class shares (whole list and pool), and the hashes of the blank sheets and the key.
No finding contents and no labels are reported. Sheets and the key are built outside git (section 8); only their SHA-256 is committed.
