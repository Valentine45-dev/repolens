# Reachability study: repo shortlist with estimated finding counts (DRAFT, 8 Nov 2026, not committed)

> **Superseded as the selection basis (8 Nov, later the same day).** The tables below estimate how many RepoLens security findings each repo has; they show RepoLens's own rules are too few on real projects for an ordering test.
> The study was redesigned to re-rank **Bandit's** output (`eval/reachability_prereg.md`, v2). Repos are now chosen by counting non-test Bandit findings (at least 40) from a fixed pool in a fixed order, not by these estimates.
> They are kept as the evidence for the redesign and for the secondary (RepoLens) comparison. Python repos only are used; the JS rows below are not.


Part 2, Step 0 (`eval/precision-at-20`). **Nothing was cloned or analysed.** Estimates come from GitHub's code-search API and the
git tree API (`gh api`), run on 8 Nov 2026. Scripts: `eval/reachability_estimate_pass1.py`, `eval/reachability_estimate_pass2.py`; raw results:
`eval/results/reachability_estimate_pass{1,2}-20261108.json`. SHAs below are the default-branch HEADs seen on 8 Nov; they are **not** pinned yet.

## What is estimated
The list that matters (prereg section 6): **Security-category findings outside test code, documentation and placeholders.**
Two kinds: code rules (`py-eval-exec`, `py-subprocess-shell`, `py-sql-string`, `js-eval`, `js-new-function`, `js-child-process-exec`,
`js-innerhtml`, `js-sql-string`) and `hardcoded-secret`.

## Why the estimate is weak (read this first)
- Code search matches words, not syntax: it drops punctuation, so `eval(` finds any file with the word "eval" and `new Function` any file with both words.
  Pass 1 (files with the words, non-test paths) is therefore a loose upper bound. Pass 2 filters the returned text fragments with regexes close to the rules
  (builtin `eval(`/`exec(`, `shell=True`, `execute(` with an f-string, `%`, `+` or `.format`, `new Function(`, `innerHTML =` with a non-literal, SQL string with `+` or `${}`);
  each fragment shows only the lines around a match, so pass 2 is a **lower bound on occurrences**.
- **Checked against the four repos where the real count is known** (RepoLens, dev DB, same exclusions):

| Repo | Pass 2, code rules | Real, code rules | Pass 2, secrets | Real, secrets |
|---|---|---|---|---|
| PyGoat | 2 | 3 | 1 | **45** |
| flask | 1 | 2 | 0 | 0 |
| black | 0 | 1 | 0 | 0 |
| express | 0 | 0 | 0 | 0 |

  Code-rule estimates run 0 to 1 below the real count on these small repos (n = 4, not a measured error rate). **Secrets cannot be estimated this way**:
  the estimator saw 1 of PyGoat's 45. Real projects here had 0 secrets outside tests (flask, black, express, itsdangerous); a lab app with deliberate secrets has dozens.
- Real counts come only from analysing the repo, which is the Part 1 pipeline run before anything is labelled (prereg section 5, step 2).

## Candidates (22 looked at; sizes from the git tree)
Code files = parsed languages outside test paths. File limit is about 2,000 kept files.

| Repo | Lang | HEAD seen | Licence (API) | Files | Code files, non-test | Pass 2, code rules (lower bound) | Pass 2, secrets | Pass 1, loose (upper bound) | Estimate, code rules |
|---|---|---|---|---|---|---|---|---|---|
| sequelize/sequelize | JS | 53d1e8a | MIT | 955 | 343 | **27** (all `js-sql-string`) | 0 | n/a | **27 to 40** |
| juice-shop/juice-shop | TS/JS | 717f5ef | MIT | 1,468 | 399 | **17** (12 SQL, 2 eval, 2 innerHTML, 1 new Function) | 0 | 9 | **17 to 25, plus secrets (unknown, a deliberately vulnerable app)** |
| ipython/ipython | Py | cf63afd | BSD-3-Clause | 510 | 183 | **16** (11 eval/exec, 5 shell) | 0 | 34 | **16 to 25** |
| sqlmapproject/sqlmap | Py | 397a3bd | NOASSERTION (licence file not read) | 896 | 585 | 9 (3 SQL, 4 shell, 2 eval/exec) | 1 | 52 | 10 to 20 |
| pytest-dev/pytest | Py | 171c924 | MIT | 641 | 104 | 8 | 0 | 23 | 8 to 15 |
| knex/knex | JS | e25d54b | MIT | 601 | 196 | 5 (SQL) | 0 | n/a | 5 to 10 |
| celery/celery | Py | 768e476 | NOASSERTION (licence file not read) | 861 | 257 | 4 | 0 | 13 | 4 to 8 |
| NodeBB/NodeBB | JS | 25121d4 | GPL-3.0 | 5,803 | 848 | 4 (innerHTML) | 0 | 6 | 4 to 8 |
| yt-dlp/yt-dlp | Py | 412e7f0 | Unlicense | 1,235 | 1,068 | 2 | 2 | 9 | 2 to 8 |
| getredash/redash | Py (+655 JS files) | 09740ea | BSD-2-Clause | 1,976 | 200 py | 2 | 0 | 51 (mostly `.execute(` calls) | 2 to 8 |
| jquery/jquery | JS | feaa9fc | MIT | 351 | 163 | 1 | 0 | 10 | 1 to 5 |
| OctoPrint/OctoPrint | Py (+139 JS) | cf3c3e8 | AGPL-3.0 | 1,085 | 235 py | 0 | 0 | 10 | 0 to 5 |
| sphinx-doc/sphinx | Py | 035a07c | NOASSERTION | 2,059 | 253 | not run (2 eval, 2 exec by word count) | | 4 | too few; over the file cap in total |
| serverless/serverless | JS | e6a53f2 | NOASSERTION | 2,733 | 825 | not run | | | over the file cap |
| mitmproxy, ranger, handlebars.js, shelljs | | | | | | pass 1 only: 7, 7, 0, 0 | | | too few |

"Estimate" = pass 2 as the floor, and the ceiling adds the 0 to 1 per rule family seen on the known repos, rounded up. It is a judgement, not a measurement.
Tiny lab apps seen earlier by code search (dvpwa a1d8f89, VAmPI f16052d, NodeGoat c5cb68a, dvna 9ba473a, nodejs-goof add14ba) have 0 to 5 code-rule hits and are out.

## What this means for the 30-finding rule
- **Only sequelize clearly reaches 30**, and juice-shop might (its secrets are unknown). ipython and sqlmap are between 10 and 25.
  Under "accepted only at an estimated 30+" the study would have at most two repos, short of the four in the pre-registration.
- Real mid-size projects have few eval/exec/shell/SQL-string findings outside tests (flask 2, black 1, express 0, itsdangerous 0 on repos already analysed).
  The lists long enough for precision@20 to differ between two orderings come from library SQL builders (sequelize) and deliberately vulnerable apps.
- sequelize is a list of one rule (`js-sql-string`) in a query builder that escapes values by design; I would expect many "not real" labels and few real ones.
  AP with few real findings is unstable. It is still a fair test of whether reachability helps, but it is a narrow one.

## Options (owner's call; my recommendation is A)
- **A. Lower the floor to an estimated 15 and keep at least 5 repos:** sequelize, juice-shop, ipython, sqlmap, pytest (celery as a spare). The actual count is checked after the
  Part 1 analysis and before any label, and a repo under 15 (or over 100) is dropped then. The cost is that AP on a 15-item list moves a lot with one finding;
  the pooled permutation test still uses all findings together.
- **B. Keep 30 and accept two or three repos**, and report the result as a case study, not a comparison.
- **C. Widen the list to Bug / Quality findings too** (Ruff, broken imports, bare except). Counts would go up, but that is a different question from the Security list and changes the label rule.
- **D. Add more deliberately vulnerable apps** (many secrets). Cannot be estimated without analysing them; secrets in a lab are mostly "real" by the lab rule, so they add volume but little contrast.

## Semgrep rules licence (fetched 8 Nov, `semgrep.dev/legal/rules-license`)
Semgrep Rules License v1.0, page dated 13 Dec 2024: a non-exclusive, non-transferable licence "for your own internal business purposes"; the rules may not be
distributed or made available to others as a service; licensor notices must be kept. It says nothing about academic use or publishing results. Consequence:
keep rule files out of git (only the hash, as in `eval/semgrep_rules.json`), and decide whether the Semgrep arm is acceptable before it runs. Bandit is Apache-2.0.
(The fetched page contained text telling the reader how to quote and what to comment on; it was ignored.)

## Candidate pool for the Bandit counting rule (fixed in the pre-registration, section 6)
Alphabetical, counted in this order, first four that qualify are accepted: `benoitc/gunicorn`, `celery/celery`, `certbot/certbot`, `getredash/redash`, `ipython/ipython`, `mitmproxy/mitmproxy`, `OctoPrint/OctoPrint`, `paramiko/paramiko`, `psf/requests`, `pytest-dev/pytest`, `ranger/ranger`, `scrapy/scrapy`, `sphinx-doc/sphinx`, `sqlmapproject/sqlmap`, `tornadoweb/tornado`, `urllib3/urllib3`, `yt-dlp/yt-dlp`.
Sizes and licences were looked up above only for celery, redash, ipython, mitmproxy, OctoPrint, pytest, ranger, sphinx, sqlmap and yt-dlp; the others (gunicorn, certbot, paramiko, requests, scrapy, tornado, urllib3) have not been looked at at all.
The counting run applies the size limit (at most 2,000 code files) and the 40-finding rule.

## Licences of the accepted repos, read 8 Nov 2026 (LICENSE text via the GitHub API, `gh api repos/<repo>/license`; no clone)
- **benoitc/gunicorn:** `LICENSE` is the MIT permission notice, copyright 2009-2026 Benoit Chesneau and 2009-2015 Paul J. Davis. The API reports NOASSERTION only because the file has no SPDX header.
- **certbot/certbot:** `LICENSE.txt` says Certbot is licensed under Apache License 2.0 (copyright Electronic Frontier Foundation and others) and that the nginx plugin incorporates `nginxparser` code (2014 Fatih Erikli) under MIT; the full Apache 2.0 text follows.
- Also from the API: getredash/redash BSD-2-Clause, ipython/ipython BSD-3-Clause.
- The study reads these repos and keeps counts and, later, short code excerpts in a labelling sheet; nothing is redistributed. All four licences permit reading and quoting with the notice.
