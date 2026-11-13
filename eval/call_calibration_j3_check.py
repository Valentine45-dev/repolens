"""Check J3's labelled call-calibration sheet against the blank judge-2 sheet, before any agreement is
computed (eval/results/CALL-CALIBRATION-J3-PLAN.md, Step 2 items 1-3, with Amendment 1).

    uv run --project backend python eval/call_calibration_j3_check.py <stated sha256>

Non-label cells are compared after normalising only line endings, a UTF-8 BOM, the CSV quoting style
and leading/trailing whitespace; every normalisation used is counted. Any other difference, an
invalid label, or a hash that is not the stated one stops the check. Prints no labels. Writes
eval/results/call_calibration_labels_received_j3-<date>.json.
"""

import csv
import hashlib
import io
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = Path(r"C:\projects\repolens-eval-assets\call-calibration")
BLANK = ASSETS / "sheet-blank-judge2.csv"
J3 = ASSETS / "sheet-labelled-judge3.csv"
BLANK_SHA256 = "1c7b891e18b278dcb2b5c2eb2ed77af1fceb29307a75c86b44ca7df11d25d3ee"
BOM = b"\xef\xbb\xbf"
LABEL_COL, NOTE_COL = 8, 9
LABELS = {"correct", "incorrect", "unsure"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def line_endings(text: str) -> dict:
    crlf = text.count("\r\n")
    return {"crlf": crlf, "lone_lf": text.count("\n") - crlf, "lone_cr": text.count("\r") - crlf}


def unify(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def quoting_style(text: str, rows: list[list[str]]) -> str:
    """Which csv.writer quoting reproduces this file's text (line endings unified, BOM removed)."""
    target = unify(text)
    for name, q in (("minimal", csv.QUOTE_MINIMAL), ("all", csv.QUOTE_ALL)):
        buf = io.StringIO(newline="")
        csv.writer(buf, quoting=q, lineterminator="\n").writerows(rows)
        if buf.getvalue() in (target, target + "\n") or buf.getvalue().rstrip("\n") == target.rstrip("\n"):
            return name
    return "other"


def load(path: Path) -> dict:
    raw = path.read_bytes()
    has_bom = raw.startswith(BOM)
    text = raw[len(BOM):].decode("utf-8") if has_bom else raw.decode("utf-8")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    trailing_empty = 0
    while rows and all(c == "" for c in rows[-1]):
        rows.pop()
        trailing_empty += 1
    return {"bom": has_bom, "line_endings": line_endings(text), "rows": rows,
            "trailing_empty_rows": trailing_empty, "quoting": quoting_style(text, rows)}


def main() -> None:
    stated = sys.argv[1].strip().lower()
    problems: list[str] = []
    j3_sha = sha256(J3)
    if j3_sha != stated:
        problems.append(f"J3 sheet SHA-256 {j3_sha} is not the stated {stated}")
    if sha256(BLANK) != BLANK_SHA256:
        problems.append("blank judge-2 sheet hash differs from the setup record")

    b, j = load(BLANK), load(J3)
    brows, jrows = b["rows"], j["rows"]
    counts = {"line_endings_only": 0, "whitespace_only": 0, "line_endings_and_whitespace": 0}
    where: dict[str, list[str]] = {k: [] for k in counts}
    if len(brows) != len(jrows):
        problems.append(f"row count {len(jrows) - 1} (blank {len(brows) - 1})")
    for r, (br, jr) in enumerate(zip(brows, jrows)):
        if len(br) != len(jr):
            problems.append(f"row {r}: {len(jr)} columns (blank {len(br)})")
            continue
        if any(c == "" for c in jr) and all(c == "" for c in jr):
            problems.append(f"row {r}: empty row inside the file")
        for c, (bc, jc) in enumerate(zip(br, jr)):
            if r > 0 and c in (LABEL_COL, NOTE_COL):
                continue
            if bc == jc:
                continue
            le, ws = unify(bc) == unify(jc), bc.strip() == jc.strip()
            if le:
                kind = "line_endings_only"
            elif ws:
                kind = "whitespace_only"
            elif unify(bc).strip() == unify(jc).strip():
                kind = "line_endings_and_whitespace"
            else:
                problems.append(f"row {r} ({br[0]}), column '{brows[0][c]}': text differs")
                continue
            counts[kind] += 1
            where[kind].append(f"{br[0]}/{brows[0][c]}")

    ids_b = [r[0].strip() for r in brows[1:]]
    ids_j = [r[0].strip() for r in jrows[1:]]
    invalid, unsure_without_note = [], 0
    for row in jrows[1:]:
        if len(row) <= NOTE_COL:
            continue
        lab = row[LABEL_COL].strip().lower()
        if lab not in LABELS:
            invalid.append({"id": row[0], "raw_label": row[LABEL_COL]})
        elif lab == "unsure" and not row[NOTE_COL].strip():
            unsure_without_note += 1
    if invalid:
        problems.append(f"{len(invalid)} label(s) not correct / incorrect / unsure after trim + lower-case")
    label_needed_trim_or_case = sum(1 for row in jrows[1:] if len(row) > LABEL_COL
                                    and row[LABEL_COL] != row[LABEL_COL].strip().lower()
                                    and row[LABEL_COL].strip().lower() in LABELS)

    normalisations = {
        "bom": f"blank has BOM: {b['bom']}, J3 has BOM: {j['bom']}"
               + (" (differs; removed before comparing)" if b["bom"] != j["bom"] else " (same)"),
        "line_endings_in_file": {"blank": b["line_endings"], "j3": j["line_endings"]},
        "trailing_empty_rows_ignored": {"blank": b["trailing_empty_rows"], "j3": j["trailing_empty_rows"]},
        "quoting_style": {"blank": b["quoting"], "j3": j["quoting"],
                          "differs": b["quoting"] != j["quoting"]},
        "non_label_cells_needing_normalisation": counts,
        "non_label_cells_needing_normalisation_where": where,
        "labels_needing_trim_or_lower_case": label_needed_trim_or_case,
    }
    record = {
        "received": date.today().isoformat(),
        "file": "sheet-labelled-judge3.csv (outside git, repolens-eval-assets/call-calibration/)",
        "sha256": j3_sha,
        "stated_sha256": stated,
        "stated_sha256_matches": j3_sha == stated,
        "judge": "J3 (third person; labelled the sheet built for a second judge; identified by code only)",
        "ai_use": "none (self-reported)",
        "plan": "eval/results/CALL-CALIBRATION-J3-PLAN.md (with Amendment 1)",
        "checks": {
            "passed": not problems,
            "problems": problems,
            "header_equal_after_normalisation": not any(p.startswith("row 0") for p in problems),
            "rows": len(jrows) - 1,
            "ids_identical_and_same_order": ids_b == ids_j,
            "ids_unique": len(set(ids_j)) == len(ids_j),
            "invalid_labels": invalid,
            "unsure_rows_without_note": unsure_without_note,
        },
        "normalisations": normalisations,
        "notes_committed": False,
        "agreement_computed": False,
    }
    if ids_b != ids_j:
        problems.append("ids differ from the blank sheet or are in another order")
        record["checks"]["passed"] = False
    out = ROOT / "eval" / "results" / f"call_calibration_labels_received_j3-{record['received']}.json"
    out.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print("written", out.relative_to(ROOT))
    print(json.dumps({"passed": record["checks"]["passed"], "problems": problems,
                      "normalisations": {k: v for k, v in normalisations.items()
                                         if k != "non_label_cells_needing_normalisation_where"}}, indent=1))
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
