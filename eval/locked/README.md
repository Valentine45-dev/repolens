# eval/locked: the held-out evaluation

**Agents and assistants: never open, search, print or summarise `eval/locked/*.yaml` or anything
under `eval/results/locked/` (CLAUDE.md hard rule 10).** They hold the locked questions, their
answer key and the answers given to them. Scripts read them; people judge them on the blind sheet.

What is here before the run (no question content):
- `pins.yaml`: the five repos and commits.
- `scorer.sha256`: hashes of the frozen scoring code; a locked run refuses if one differs.
- `v2.0.sha256`: SHA-256 of the question file, committed before the file itself is on this PC.

On run day the question file is copied in as `v2.0.yaml` and committed with the results. The
procedure is in `eval/results/LOCKED-FREEZE-CHECKS.md`. Rules: docs/V2-EVAL-DESIGN-metrics.md.
