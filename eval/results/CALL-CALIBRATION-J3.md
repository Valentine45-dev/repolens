# Call calibration: second judge (J3) vs J1

The plan was fixed before J3's sheet was opened: `CALL-CALIBRATION-J3-PLAN.md` (`6c42b41`, Amendment 1
`4846f88`). J3's sheet hash and structure check were committed before any agreement was computed
(`6a169f1`). The scorer `eval/call_calibration_j3_agreement.py` was committed before it ran (`d33c614`)
and was run once. Numbers: `call_calibration_j3_agreement-20261113T115645Z-d33c614.json`. No LLM was used.
`CALL-CALIBRATION.md` and J1's labels are unchanged.

## Judge and sheet
- **J3**, a third person (not J1, the owner, and not J2 of the reachability study), labelled
  `sheet-blank-judge2.csv`: 30 rows, 10 per confidence band, from the main (Python) sheet. J3 is
  identified by code only. **AI use: none (self-reported).**
- J3's sheet SHA-256 `4de0cc5513720b789123de4499a443a68376be280d2e83cc04186819e69e6072` matches the
  hash the owner gave. Same 30 ids in the same order, the same header, and every non-label cell
  identical to the blank sheet.
- **Normalisations needed: none.** Both files have a UTF-8 BOM. Line endings are the same in both
  (31 CRLF, 510 LF inside cells). Quoting style is the same in both (minimal), there are no trailing
  empty rows, 0 cells needed line-ending or whitespace normalisation, and 0 labels needed trimming or
  lower-casing. No label was invalid.
- Rows were matched to J1's labels (`sheet-labelled.csv`, SHA-256 `672a3559...c34`) by id.

## Agreement
| comparison | rows | agree | percent agreement | chance agreement | Cohen's kappa | kappa < 0.4 |
|---|---|---|---|---|---|---|
| 1. correct / incorrect / unsure | 30 | 30 | 100% | 0.82 | 1.00 | no |
| 2. correct vs incorrect (either unsure excluded) | 30 | 30 | 100% | 0.82 | 1.00 | no |

- **Excluded from comparison 2: 0 rows.** Neither judge used unsure, so comparisons 1 and 2 are the
  same 30 rows.
- Both judges: 27 correct, 3 incorrect, 0 unsure. Table (J1 rows x J3 columns): correct-correct 27,
  incorrect-incorrect 3, every other cell 0.
- **Read the kappa with care.** "Correct" dominates (27 of 30), so chance agreement is already 0.82,
  and kappa rests on the 3 incorrect rows. For scale (simple arithmetic, not part of the
  result): if one row had differed, agreement would have been 29 of 30 and kappa about 0.78 (J3
  calls a J1-incorrect row correct) or about 0.84 (J3 calls a J1-correct row incorrect).

## Disagreements and unsure rows
**None.** No row has different labels, and no row is unsure for either judge. So there are no notes
from J3 to list here.

## J3 per confidence band (descriptive only)
| band | rows | J3 correct | J3 incorrect | J3 unsure |
|---|---|---|---|---|
| 1.0 | 10 | 10 | 0 | 0 |
| 0.9 | 10 | 10 | 0 | 0 |
| 0.5 | 10 | 7 | 3 | 0 |

There are no intervals and no test here: 10 rows per band is too few to say anything about J3's
precision apart from J1's.

## Limits
- 30 rows, only 3 of them incorrect for either judge. Perfect agreement on this sheet does not show
  that the judges would agree on harder or more mixed rows.
- These are the Python main-sheet rows only. The express add-on had no second judge.
- What J3 was given besides the sheet (instructions, the label rule, time spent) is not recorded
  here. The check shows only that J3 returned the blank sheet with only labels and notes filled in.
