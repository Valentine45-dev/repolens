# Call-confidence calibration: rule, sampling and reporting (fixed 7 Nov, before any draw)

Branch `eval/call-calibration`; v2 step 6a, Part 2. Nothing here is drawn or labelled yet. This file,
`eval/call_calibration.py` and the seed are committed and pushed before the sample is drawn.

## What is measured
**Precision of the call edges RepoLens draws, per confidence band (1.0 / 0.9 / 0.5). It does not
measure missed calls (recall):** a call RepoLens never links is invisible to this sheet.

## Unit and bands
- The unit is one **call site** (one `edge_sites` row of a `calls` edge) with **its own** confidence:
  1.0, 0.9 or 0.5 (stored as REAL, rounded to one decimal). In these repos no edge mixes
  confidences, so a site and its edge are in the same band.
- Eligible: the caller and the callee are both outside test/example code (`app.paths.is_test_path`).
  Main sheet: Python callers and callees only (`.py`). Express add-on: JS, tests and examples included.

## Repos and quotas (30 sites per band, 90 rows)
- **1.0:** PyGoat 15, flask 15.
- **0.9 and 0.5:** PyGoat keeps what it has (at most 15, after the caps below). The rest of the 30 is
  split evenly between flask and black (an odd remainder: the extra goes to flask). Fixed rule: this split is
  used only if black has at least 15 non-test sites from at least 8 distinct callees in that band;
  otherwise flask takes the rest. A repo that cannot fill its quota after the caps passes the
  shortfall to the other.
- **Express add-on, reported separately:** 8 per band (24 rows), from all express code including
  tests and examples; each row is flagged `in_test` in the key and the report states the share.
- Caps in every draw: **at most 1 site per edge and at most 2 sites per callee symbol.**

## Draw
`random.Random(f"{SEED}-{band}-{repo}")` over the eligible sites sorted by
(caller path, line, callee qualified name), shuffled; sites are taken in that order, skipping any
that break a cap, until the quota is filled. `SEED = 20261107`.

## Sheets (blank files never show the band)
- `sheet-blank.csv` (90 rows), `sheet-blank-express.csv` (24 rows), `sheet-blank-judge2.csv`:
  10 rows per band, seeded, drawn from the main sheet only (30 rows, same ids; no express rows).
- Row: id (`r-` plus five letters, never number-like), repo, call site `path:line`, caller name,
  the call site with 3 lines of context each side (`>` marks the line), the callee's name and
  `path:start-end`, and the callee's first 15 lines. Text is the stored, redacted file text, masked
  once more with `blind_sheet.mask()`.
- Not shown: confidence, rule, "only candidate", edge counts. Rows are shuffled. The key
  (id -> repo, band, edge, in_test) is `key.json`, outside git, not opened until labelling is done.
- Limit of the blinding: the shape of a row can hint at the band (callee in the same file looks like
  1.0, `self.` like 0.9, a lone name like 0.5).
- SHA-256 of each blank sheet and of the key is recorded in `eval/results/call_calibration_setup-*.json`
  when they are built; the labelled sheet's hash is committed before the key is opened.

## Label rule (given by a human; AI never proposes a label)
Column `label (correct / incorrect / unsure)`, plus `note`.
- **correct:** read statically, this call executes this callee.
- **incorrect:** it runs a different function, a builtin or external one, or cannot reach this callee.
- **unsure:** plausibly one of several, or decided only at run time. A note is required.

## Scoring (fixed)
- **Primary result: precision with unsure excluded** = correct / (correct + incorrect), per band,
  with a Wilson 95% interval. Shown alongside it, with the same interval: unsure counted as
  incorrect, and unsure counted as correct. The unsure rows are listed by id with their notes.
- Also reported: the number of distinct callees and files each band covers (rows from one file or
  callee are correlated, so intervals are optimistic), per-repo counts, and the express add-on
  separately with its test/example share.
- Second judge (`sheet-blank-judge2.csv`, 30 rows): percent agreement and Cohen's kappa on the
  rows both judges labelled, unsure shown as its own category.
- Wording stays cautious: at about 30 rows per band an interval is roughly +-0.15; this is
  calibration on PyGoat, flask and black (Python), not a general rate.
- `CALIBRATION.md` must say, near the top, that this measures precision of drawn call edges only,
  not missed calls (recall).
