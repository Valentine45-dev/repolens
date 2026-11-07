# Call-confidence calibration (v2 step 6a, Part 2)

**What this measures: the precision of the call edges RepoLens draws, per confidence band. It does
not measure missed calls (recall): a call RepoLens never links is invisible to this sheet.**

Pre-registered in `eval/call_calibration_rule.md` (committed `f0af11f`, before the draw). Scored by
`eval/score_call_calibration.py`; numbers in `call_calibration_scored-20261107T130746Z-6588b8a.json`.
How to read it: one labeller, small samples, three repos. Treat it as a first calibration of the
three bands, not a general rate.

## Method in short
- **Unit:** one call site (an `edge_sites` row) with its own confidence. In these repos no edge
  mixes confidences, so a site and its edge are in the same band.
- **Sample:** seeded (20261107), at most 1 site per edge and 2 per callee, non-test Python code,
  30 per band (90 rows): 1.0 = PyGoat 15 + flask 15; 0.9 = PyGoat 1 + flask 15 + black 14;
  0.5 = PyGoat 9 + flask 11 + black 10 (PyGoat has only 5 distinct callees at 0.5). Express is a
  separate add-on of 8 per band, tests and examples included.
- **Sheet:** the call site with 3 lines of context each side and the candidate callee's first 15
  lines; confidence, rule and band were not shown. The shape of a row can still hint at its band.
- **Labels:** by the project owner alone, with no AI and no RepoLens, from the sheet and the repo
  source on GitHub at the pinned commits (about 2 hours). correct / incorrect / unsure by the
  pre-registered rule (read statically, does this call execute this callee). The labelled sheets'
  SHA-256 were recorded and pushed (`3ccbd22`) before the key was opened.
- **Primary result:** precision with unsure excluded, correct / (correct + incorrect), Wilson 95%.
  The two alternatives (unsure as incorrect, unsure as correct) are shown alongside. **No row was
  labelled unsure**, so all three are identical.

## Main sheet (90 rows, Python, non-test)
| band | rows | correct | incorrect | unsure | precision (unsure excluded) | Wilson 95% | distinct callees | caller / callee files |
|---|---|---|---|---|---|---|---|---|
| 1.0 | 30 | 30 | 0 | 0 | 1.00 | 0.89 to 1.00 | 28 | 14 / 14 |
| 0.9 | 30 | 30 | 0 | 0 | 1.00 | 0.89 to 1.00 | 26 | 15 / 15 |
| 0.5 | 30 | 21 | 9 | 0 | 0.70 | 0.52 to 0.83 | 24 | 18 / 17 |

By repo (correct / rows): 1.0: PyGoat 15/15, flask 15/15. 0.9: PyGoat 1/1, flask 15/15, black 14/14.
0.5: PyGoat 6/9, flask 8/11, black 7/10. All 9 incorrect rows are in the 0.5 band, three in each
repo. The repos are too small per band to compare with each other.

## Express add-on (24 rows, JS, reported separately)
| band | rows | correct | incorrect | unsure | precision | Wilson 95% | in test/example code |
|---|---|---|---|---|---|---|---|
| 1.0 | 8 | 8 | 0 | 0 | 1.00 | 0.68 to 1.00 | 8 of 8 |
| 0.9 | 8 | 8 | 0 | 0 | 1.00 | 0.68 to 1.00 | 0 of 8 |
| 0.5 | 8 | 8 | 0 | 0 | 1.00 | 0.68 to 1.00 | 8 of 8 |

Express has very few non-test sites at 0.5 (4 in the whole repo), so its 1.0 and 0.5 rows are all
test or example code, where calls are often simple. This sheet says nothing against the main
result and is not comparable with it.

## What the 9 incorrect 0.5 rows look like
Only one of them has a note from the labeller: flask `templating.py:158` links to
`ProxyMixin._get_current_object`, a type-checking stub in `globals.py`; at runtime the call reaches
werkzeug's `LocalProxy`. For the others, from the sheet alone (not the labeller's reasons): three
PyGoat rows link a `get` or `delete` call to `challenge.views.DoItFast.get/delete`, the callee
that took 140 of PyGoat's 150 non-test 0.5 sites; two black rows link to `Parser.pop` in
`blib2to3`; the rest are `get_source`, `Cache.write` and `AppContext.from_environ`. The 0.5 rule links a call to the only
candidate of that name in the snapshot, so a wrong link is what that rule can produce; I did not
check each row's cause.

## Reading
- **1.0 and 0.9:** 30 of 30 correct in each. With 30 rows this fits a true precision of roughly 0.89
  to 1.0 at the lower end; it does not show that the bands are perfect. The 0.9 band is mostly
  flask and black (29 of 30 rows).
- **0.5:** 21 of 30 (0.70, 0.52 to 0.83). The interval does not overlap the 1.0 and 0.9 lower
  bounds (0.89), which supports drawing 0.5 edges dashed and labelled as guesses, as the UI does.
  Roughly a fifth to a half of 0.5 edges may be wrong (from the interval); the UI should keep calling them guesses.
- Rows from the same file or callee are correlated, so the intervals are optimistic. Distinct
  callees and files per band are in the tables.

## Limits
- One labeller, who is the project's author; no second judge has labelled yet (`sheet-blank-judge2.csv`
  is built, 30 rows, not labelled), so there is no agreement figure.
- The band was hidden but the shape of a row can hint at it.
- Only edges RepoLens drew were judged: this is precision, not recall.
- Python only on the main sheet (PyGoat, flask, black); JS is the 24-row express add-on.
- PyGoat's 0.5 band rests on 5 callees; its 0.9 band on one site.
- Small samples: differences of a few rows are not conclusive.
