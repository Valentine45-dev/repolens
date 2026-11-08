# Reachability as a re-ranker of Bandit's output: results (8 Nov 2026)

Scored once from `reachability_scored-20261108T143659Z-32d1988.json`. Pre-registration: `eval/reachability_prereg.md` with Amendment 1; frozen tier code `cfd4835`; the labelled sheet's SHA-256 `197fa366e35a618f...` was committed before the key was opened. Labels by J1 (the project owner, who built the tool); a second judge (J2) labelled a 54-row subset (section below). This is a small study set up and labelled by the people who built the tool: the result is for these repos, not a general rate.

## Headline

- **The primary comparison rests on one repository.** Only redash has any finding labelled real in its Bandit pool; gunicorn (48 rows), certbot (60) and ipython (60) have none, so by the pre-registration they have no AP and are left out of the mean (R = 0).
- **Pooled mean AP difference (reachability order minus Bandit order): -0.017** over 1 repo. One-sided p = 0.831 (two-sided 0.761); bootstrap 95% interval over files -0.095 to +0.076. No evidence that ordering by reachability puts more real findings earlier; the point estimate is slightly negative and the interval is wide.
- **P@20, pooled over the four repos (80 rows per ordering):** Bandit order 12/80 = 0.150 (Wilson 0.09 to 0.24); reachability order 10/80 = 0.125 (Wilson 0.07 to 0.21). Difference -2 real findings in the top 20s (one-sided p = 0.600, a second test, not corrected). All of it comes from redash.
- **Why the result says little about whether reachability helps in general:** 233 of 261 sheet rows were labelled not real; in the Bandit pools of gunicorn, certbot and ipython the owner judged nothing actionable. All 27 real findings in the Bandit pools are in redash, and all of them are one rule (B113, request without timeout); 24 of them have no path from the detected entry points. That is consistent with the entry-point recall gap the freeze recorded as a risk; whether it is the cause was not checked. It is what the frozen rules produce.
- **Descriptively, real findings are more common where no path was found than where one was:** no path found 24/126 real (0.191), solid 3/81 (0.037), guess 0/9. That is the opposite of the premise of the ordering; all of the 24 no-path real findings are redash's. It is a table, not a test.
- **Second judge:** on the 54 shared rows the two judges agree on 50 (92.6%), Cohen's kappa 0.566; not judge-dependent by the pre-registered threshold (kappa below 0.4). Disagreements: all 4 are getredash/redash rows that J1 labelled real and J2 not real (section below).

## What was scored

- Four repos accepted by the counting rule, at pinned SHAs: benoitc/gunicorn `d93a59d`, certbot/certbot `138defe`, getredash/redash `09740ea`, ipython/ipython `cf63afd`.
- Pools (Bandit 1.9.4, B101 and B404 skipped): benoitc/gunicorn 48, certbot/certbot 60, getredash/redash 48, ipython/ipython 60. certbot and ipython are seeded samples of 60 (of 73 and 143); AP and P@20 there are on that sample, not on the whole list.
- Labels over the 261 sheet rows: 28 real, 233 not real, 0 unsure (so both unsure sensitivities equal the primary).
- Orderings: Bandit order `(severity, confidence, path, line, test_id, occurrence)`; reachability order `(tier rank, then the same)`; solid 0, guess and not checked 1, no path found 2.

## Primary result by repo (Bandit pool)

| repo | rows | real | set precision (Wilson) | AP Bandit | AP reachability | difference | P@20 Bandit | P@20 reachability |
|---|---|---|---|---|---|---|---|---|
| benoitc/gunicorn | 48 | 0 | 0.000 (0.00 to 0.07) | n/a | n/a | n/a | 0/20 | 0/20 |
| certbot/certbot | 60 | 0 | 0.000 (0.00 to 0.06) | n/a | n/a | n/a | 0/20 | 0/20 |
| getredash/redash | 48 | 27 | 0.562 (0.42 to 0.69) | 0.564 | 0.547 | -0.017 | 12/20 | 10/20 |
| ipython/ipython | 60 | 0 | 0.000 (0.00 to 0.06) | n/a | n/a | n/a | 0/20 | 0/20 |

No AP where there is no real finding (R = 0). Pooled AP (mean over repos with R > 0): Bandit 0.564, reachability 0.547, from 1 repo.

## Bandit set precision (descriptive)

Real / labelled Bandit pool, with a Wilson 95% interval. Findings in one file are correlated, so the intervals are optimistic; certbot and ipython are 60-row samples of longer lists.

| repo | labelled Bandit pool | real | set precision | Wilson 95% |
|---|---|---|---|---|
| benoitc/gunicorn | 48 | 0 | 0.000 | 0.00 to 0.07 |
| certbot/certbot | 60 | 0 | 0.000 | 0.00 to 0.06 |
| getredash/redash | 48 | 27 | 0.562 | 0.42 to 0.69 |
| ipython/ipython | 60 | 0 | 0.000 | 0.00 to 0.06 |
| **all four repos** | 216 | 27 | 0.125 | 0.09 to 0.18 |

## Test and interval

- Tier-shuffle randomisation (units shuffled within each repo, 10000 shuffles, seed 20261108): AP statistic -0.017, 8314 of 10000 shuffles at least as large (one-sided p = 0.8314; two-sided 0.7615).
- P@20 statistic -0.025: one-sided p = 0.6004, two-sided 0.7261 (second test, not corrected).
- Bootstrap over files (clustered, 10000 usable resamples), AP difference: -0.095 to +0.076.
- Findings in one file are correlated and only one repo contributes, so the p-value describes this set of findings, not repos in general.

## Sensitivities

- **Unsure as real / as not real:** there are no unsure rows, so both equal the primary.
- **Every B104 row counted as real** (always shown, pre-registered): 3 repos now have a real finding. Mean AP difference +0.017 over 3 repos (one-sided p = 0.478); P@20 pooled Bandit 15/80 = 0.188, reachability 12/80 = 0.150. B104 is 3 rows in all (one in each of gunicorn, certbot and redash), so the AP values for gunicorn and certbot rest on a single real finding and move with one row.
- **Exploratory, not tested: severity first, then tier:** mean AP difference +0.017 over 1 repo; P@20 difference +0.

## Descriptive tables (the Bandit pools together, n = 216; not tested)

**Real share per tier**

|  | n | real | real share | Wilson 95% |
|---|---|---|---|---|
| guess | 9 | 0 | 0.000 | 0.00 to 0.30 |
| none | 126 | 24 | 0.191 | 0.13 to 0.27 |
| solid | 81 | 3 | 0.037 | 0.01 to 0.10 |

**Real share per entry class (None = no path found)**

|  | n | real | real share | Wilson 95% |
|---|---|---|---|---|
| None | 126 | 24 | 0.191 | 0.13 to 0.27 |
| app | 81 | 1 | 0.012 | 0.00 to 0.07 |
| public-api | 9 | 2 | 0.222 | 0.06 to 0.55 |

**Tier x entry class**

| tier / entry class | n | real |
|---|---|---|
| guess / app | 9 | 0 |
| none / None | 126 | 24 |
| solid / app | 72 | 1 |
| solid / public-api | 9 | 2 |

**Per repo, by tier** (n / real)

| repo | solid | guess | no path found |
|---|---|---|---|
| benoitc/gunicorn | 18 / 0 | 4 / 0 | 26 / 0 |
| certbot/certbot | 36 / 0 | 3 / 0 | 21 / 0 |
| getredash/redash | 8 / 3 | 0 / 0 | 40 / 24 |
| ipython/ipython | 19 / 0 | 2 / 0 | 39 / 0 |

**Real share per Bandit rule (descriptive; not pre-registered, added to explain the result)**

| rule | n | real | real share | Wilson 95% |
|---|---|---|---|---|
| B102 | 8 | 0 | 0.000 | 0.00 to 0.32 |
| B103 | 3 | 0 | 0.000 | 0.00 to 0.56 |
| B104 | 3 | 0 | 0.000 | 0.00 to 0.56 |
| B105 | 14 | 0 | 0.000 | 0.00 to 0.22 |
| B108 | 6 | 0 | 0.000 | 0.00 to 0.39 |
| B110 | 44 | 0 | 0.000 | 0.00 to 0.08 |
| B113 | 28 | 27 | 0.964 | 0.82 to 0.99 |
| B202 | 1 | 0 | 0.000 | 0.00 to 0.79 |
| B301 | 1 | 0 | 0.000 | 0.00 to 0.79 |
| B303 | 2 | 0 | 0.000 | 0.00 to 0.66 |
| B307 | 5 | 0 | 0.000 | 0.00 to 0.43 |
| B310 | 4 | 0 | 0.000 | 0.00 to 0.49 |
| B311 | 7 | 0 | 0.000 | 0.00 to 0.35 |
| B318 | 1 | 0 | 0.000 | 0.00 to 0.79 |
| B324 | 3 | 0 | 0.000 | 0.00 to 0.56 |
| B403 | 1 | 0 | 0.000 | 0.00 to 0.79 |
| B408 | 1 | 0 | 0.000 | 0.00 to 0.79 |
| B501 | 6 | 0 | 0.000 | 0.00 to 0.39 |
| B602 | 5 | 0 | 0.000 | 0.00 to 0.43 |
| B603 | 36 | 0 | 0.000 | 0.00 to 0.10 |
| B604 | 15 | 0 | 0.000 | 0.00 to 0.20 |
| B605 | 4 | 0 | 0.000 | 0.00 to 0.49 |
| B606 | 1 | 0 | 0.000 | 0.00 to 0.79 |
| B607 | 11 | 0 | 0.000 | 0.00 to 0.26 |
| B608 | 6 | 0 | 0.000 | 0.00 to 0.39 |

25 rules appear in all; B113 holds 27 of the 27 real findings. The Bandit pools of all four repos together, n = 216.

## Secondary: RepoLens's own security findings, current order vs tier order (exploratory)

| repo | rows | real | tiers | AP current | AP reachability | P@10 cur / reach | P@20 cur / reach |
|---|---|---|---|---|---|---|---|
| certbot/certbot | 7 | 0 | {'solid': 6, 'none': 1} | n/a | n/a | n/a / n/a | n/a / n/a |
| getredash/redash | 19 | 0 | {'not_checked': 8, 'solid': 2, 'none': 9} | n/a | n/a | n/a / n/a | n/a / n/a |
| ipython/ipython | 42 | 1 | {'none': 37, 'solid': 2, 'guess': 3} | 0.143 | 0.083 | 0.100 / 0.000 | 0.050 / 0.050 |

gunicorn has no RepoLens security finding in the secondary pool. Only ipython has a real one (1 of 42); mean AP difference -0.060 over 1 repo; exploratory p = 0.649. P@k only where a list has at least 2k rows (ipython). No claim rests on this.

## Second judge (J2): agreement on the judge-2 subset

54 rows, 20% of each repo's sheet rows (rounded up), labelled by J2 (identified by code only) on the same blind rows. AI use: none (self-reported). Instructions: J2 started with the earlier wording ("is it a real security issue"); the updated wording ("should a reviewer act on it?") was sent partway through, and which rows came before the change is not recorded, so J2's labels may follow two definitions. J2's sheet SHA-256 `520e34288ae4ee1e0a6f8ed0ae29ead8aa4bebfaf6b21de79e3047492635af32` was committed before agreement was computed. Unsure rows: 0, so three-way agreement equals binary agreement.

| repo | shared rows | agree | percent agreement | Cohen's kappa | real: J1 / J2 |
|---|---|---|---|---|---|
| benoitc/gunicorn | 10 | 10 | 100.0% | undefined | 0 / 0 |
| certbot/certbot | 13 | 13 | 100.0% | undefined | 0 / 0 |
| getredash/redash | 12 | 8 | 66.7% | 0.385 | 7 / 3 |
| ipython/ipython | 19 | 19 | 100.0% | undefined | 0 / 0 |
| **all four repos** | 54 | 50 | 92.6% | 0.566 | 7 / 3 |

Kappa is undefined where both judges used one category on every shared row (all not real): agreement is 100% there, but chance agreement is 1. Pooled contingency table (J1 | J2): J1 not real | J2 not real = 47; J1 real | J2 not real = 4; J1 real | J2 real = 3.

- Pre-registered flag (pooled kappa below 0.4): pooled kappa 0.566, so the headline is **not judge-dependent**. Only redash has a defined kappa on its own (0.385); the flag is defined on the pooled value.
- Every row J2 labelled real was also real for J1 (3 of 3). In the three repos with no real Bandit finding in J1's labels, J2 also found none on the shared rows. J2 was the stricter judge on redash; this check does not test whether a more lenient judge would find real findings in the other three.
- Not done: the pre-registration (section 10) asks for the primary table to be repeated on the J2 subset with both judges' labels only if kappa is below 0.4; it is not.

**Disagreeing rows** (J1 wrote no notes; J2's note as written, ids are sheet row ids)

| row | repo | flagged for | rule | J1 | J2 | J2's note |
|---|---|---|---|---|---|---|
| r-axndl | getredash/redash | request without timeout | B113 | real | not real | In _get_graphs_schema (get_schema), which runs as an RQ job bounded by SCHEMAS_REFRESH_TIMEOUT (300s). |
| r-gkcec | getredash/redash | request without timeout | B113 | real | not real | test_connection runs as an RQ job with a 30s timeout, so a hang is bounded. |
| r-rzvru | getredash/redash | request without timeout | B113 | real | not real | One-time fire-and-forget subscribe job in a background worker at setup; a hang affects nothing important. |
| r-uoisp | getredash/redash | request without timeout | B113 | real | not real | In get_schema, run as an RQ job bounded by SCHEMAS_REFRESH_TIMEOUT (300s). |

## Limits, in addition to those pre-registered (section 11)

- Three of four repos have no real Bandit finding in the pool, so they cannot show an ordering effect; the comparison is a one-repo case study (redash).
- In redash nearly all real findings are one rule (B113) and most have no path from the detected entry points; the tier result there reflects the detectors' recall as well as the idea of reachability. Any fix to the detectors would be a dated deviation, scored as exploratory on the same labels, never replacing this result.
- The primary labels are one labeller's, the owner's, with GitHub open at the pinned commits. The second judge covered 54 of 261 rows, started under different wording, and was stricter on redash (4 of the owner's 7 real rows on the shared redash rows were not real for J2), so the redash result, the only one that carries the comparison, is sensitive to label strictness.
- certbot and ipython are 60-row samples of lists of 73 and 143; the pool of 60 is not the whole list.
- Public-API-only findings are few (9 in the pools), so the entry-class table says little.
- Python only; Bandit is the object being re-ranked, so this says nothing about Bandit's quality or RepoLens's rules.

## Deviations from the pre-registration

None in the scoring. Two choices the pre-registration did not spell out, recorded in the setup file: the secondary pool includes Python and non-code files (JS/TS left out), and judge-2 rows are 20% of each repo's sheet rows (rounded up). Not pre-registered and added: the per-rule table above.

## Provenance

Counting `reachability_bandit_count-20261107T211310Z-1dcb851.json`; setup `reachability_setup-20261108T075920Z-26485f5.json`; labels received `reachability_labels_received-20261108.json` (SHA-256 `197fa366e35a618f386dd632bf6f7b00c9098f11729bfd28138852afff9c6e7d`); scored `reachability_scored-20261108T143659Z-32d1988.json`. The sheets and the key are outside git (`repolens-eval-assets/reachability/`). Scripts: `reachability_bandit_count.py`, `reachability_ingest.py`, `reachability_setup.py`, `reachability_score.py`, `reachability_report.py`. No LLM was used ($0).

J2: labels received `reachability_labels_received_judge2-2026-11-08.json`, agreement `reachability_agreement-20261108T152123Z-339c22d.json`, script `reachability_agreement.py`.
