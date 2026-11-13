# Call-calibration second judge (J3): comparison plan

Fixed 13 Nov 2026 on branch `eval/call-calibration-j3`, **before J3's labelled sheet was opened, read
or hashed**. This file is committed and pushed on its own; the comparison (Step 2) runs once, after it.

## Who labelled
- The 30-row sheet `sheet-blank-judge2.csv` was built for a second judge. It was labelled by **J3**, a
  third person (not J1, the owner, and not J2, the second judge of the reachability study).
- J3 is recorded only as "J3", never by name. If a note names J3 or another person, the name is
  replaced with `[name]` in every file written.
- **AI use: J3 reports no AI used (self-reported).**

## Inputs (all in `C:\projects\repolens-eval-assets\call-calibration\`, outside git)
| file | role | SHA-256 |
|---|---|---|
| `sheet-blank-judge2.csv` | the 30 rows (10 per band) | `1c7b891e18b278dcb2b5c2eb2ed77af1fceb29307a75c86b44ca7df11d25d3ee` (recorded in `call_calibration_setup-20261107T095252Z-f0af11f.json`) |
| `sheet-labelled.csv` | J1's labels (90 rows) | `672a3559991f218486d05eea9ffe12c2e4700120f44028f65851078c4bd19c34` (recorded in `call_calibration_labels_received-20261107.json`) |
| `key.json` | band of each row | `28424cfa3d2aacd815cf784e37104f2a4472530c0abf5844e9f477d3e2640dd0` (already opened for the 7 Nov scoring) |
| `sheet-labelled-judge3.csv` | J3's labels | not hashed yet; recorded in Step 2 |

Checked while writing this plan (the three files above only): the blank and J1 hashes match the
recorded values; the 30 blank ids equal `key.json`'s `judge2_ids`; all 30 are in J1's sheet; bands
are 10 / 10 / 10 (1.0 / 0.9 / 0.5); repos flask 15, black 8, PyGoat 7. J1's labels on these 30
rows: 27 correct, 3 incorrect, 0 unsure.

## Step 2, in this order
1. Hash `sheet-labelled-judge3.csv` (SHA-256). It must match the hash the owner gives in chat.
2. Check it against the blank sheet: same 30 ids, same columns, every non-label cell identical (only
   `label (correct / incorrect / unsure)` and `note` may differ). Labels are compared trimmed and
   lower-case and must be `correct`, `incorrect` or `unsure`. A blank or other label, a changed cell,
   or a missing or extra id stops the run; I report it and do not guess or fix a label.
3. Record the hash, the check result and the AI-use statement in
   `eval/results/call_calibration_labels_received_j3-<date>.json`, commit and push it **before any
   agreement is computed**.
4. Commit the scorer (`eval/call_calibration_j3_agreement.py`) before it runs. It refuses to run
   unless J3's sheet has the committed hash.
5. Run it **once**. Output: `eval/results/call_calibration_j3_agreement-<time>-<sha7>.json` and a
   write-up `eval/results/CALL-CALIBRATION-J3.md`.

Rows are matched to J1's labels by `id`.

## What is reported
1. **All three categories (correct / incorrect / unsure), 30 rows:** percent agreement and Cohen's
   kappa, with the 3x3 table (J1 label x J3 label). This is the comparison the rule file
   (`eval/call_calibration_rule.md`, "Second judge") fixed: unsure as its own category.
2. **Correct vs incorrect only:** rows where either judge said unsure are excluded, and the number
   excluded is stated. Percent agreement and Cohen's kappa on the rest, with the 2x2 table. This
   matches the pre-registered primary rule (unsure excluded).

- Cohen's kappa = (observed - chance) / (1 - chance), chance from each judge's own label shares over
  the categories either judge used. If chance agreement is 1 (both judges used the same single
  category), kappa is reported as undefined, not as a number.
- **Flag if kappa < 0.4** (for each of the two kappas). An undefined kappa is stated as such; the
  flag is then not applied.
- **Both percent and kappa are reported, and neither alone is the result.** Most rows are "correct"
  (27 of 30 for J1), and kappa is unstable when one category dominates: one or two rows can move it
  a lot, and a high percent agreement can sit next to a low kappa.
3. **Every disagreement and every unsure row** (unsure by either judge), each with: id, repo, band,
   J1's label, J3's label, J3's note.
4. **After the agreement figures, per confidence band** (from `key.json`, 10 rows per band): J3's
   correct count per band (incorrect and unsure shown with it). Descriptive only: no intervals, no
   test, no claim that J3's precision differs from J1's.

## Not done
- No relabelling, by anyone, after J3's sheet is opened. J1's labels are not changed.
- `CALL-CALIBRATION.md` and the saved 7 Nov results are not edited; the J3 result goes in the new
  files above.
- One scoring run. No re-run, no re-run of only some rows.
- No LLM is used.
