"""Blind judging across versions: mix the blind sheets of two locked runs into one sheet, and
split the filled sheet back into each run's own sheet format.

    uv run --project backend python eval/judging_mix.py mix --input LABEL DIR [--input LABEL DIR]
        --out DIR [--seed N] [--per-version 50]
    uv run --project backend python eval/judging_mix.py unmix MIXED_SHEET MIXED_KEY --out DIR

`mix`: each --input is a version label and either a folder holding exactly one `*-sheet.csv` and
one `*-KEY-do-not-open.json` (as `locked_eval.py sheet` writes them), or the two files given as
`--input LABEL SHEET KEY`. Only pass-1 rows are kept; each version must have exactly
--per-version of them, every question id once, and the same question ids as the other versions.
The rows are shuffled with a fixed, printed seed and renumbered 1..N. Writes `mixed-sheet.csv`
(same columns as the original sheets; no version, pass or configuration in it or in its name) and
`mixed-KEY-do-not-open.json` (new row -> version + original row, plus each source's path and
SHA-256).

`unmix`: reads the filled mixed sheet and the combined key and writes, per version,
`<label>-filled-sheet.csv`: the original sheet, rows in their original order, with the judged
columns of its pass-1 rows filled and pass-2 rows left blank. `locked_eval.py judge` reads it
unchanged with that version's original key (a blank row counts as awaiting).

Both refuse to write inside the repository. Both print counts only, never question, answer or
cited text.
"""

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path

from locked_eval import ROOT, SHEET_COLUMNS

JUDGED = ("faithful", "rejects_premise", "false_claim_cited", "note")
ALLOWED = {"faithful": ("", "yes", "partly", "no"), "rejects_premise": ("", "yes", "no"),
           "false_claim_cited": ("", "yes", "no")}
DEFAULT_SEED = 20261123
PER_VERSION = 50
MIXED_SHEET = "mixed-sheet.csv"
MIXED_KEY = "mixed-KEY-do-not-open.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def refuse_inside_repo(out: Path, root: Path = ROOT) -> Path:
    out = out.resolve()
    if out.is_relative_to(root.resolve()):
        raise SystemExit("refused: write the mixed sheet, key and filled sheets outside the"
                         " repository")
    return out


def read_sheet(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != SHEET_COLUMNS:
            raise SystemExit(f"{path.name}: columns are not the blind sheet's")
        return list(reader)


def write_sheet(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SHEET_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def find_inputs(values: list[str]) -> tuple[str, Path, Path]:
    """--input LABEL DIR or --input LABEL SHEET KEY -> (label, sheet, key)."""
    if len(values) == 3:
        return values[0], Path(values[1]), Path(values[2])
    if len(values) != 2:
        raise SystemExit("--input takes LABEL DIR or LABEL SHEET KEY")
    label, folder = values[0], Path(values[1])
    sheets = sorted(folder.glob("*-sheet.csv"))
    keys = sorted(folder.glob("*-KEY-do-not-open.json"))
    if len(sheets) != 1 or len(keys) != 1:
        raise SystemExit(f"{label}: expected one *-sheet.csv and one *-KEY-do-not-open.json in"
                         f" {folder} (found {len(sheets)} and {len(keys)})")
    return label, sheets[0], keys[0]


def pass1_rows(label: str, rows: list[dict], key: dict, per_version: int) -> list[dict]:
    """The pass-1 rows of one version's sheet, after checking the sheet against its key."""
    ids = [r["row"] for r in rows]
    problems = []
    if len(set(ids)) != len(ids):
        problems.append(f"{len(ids) - len(set(ids))} duplicate row ids in the sheet")
    if missing := sum(1 for i in ids if i not in key):
        problems.append(f"{missing} sheet rows not in the key")
    if extra := len(set(key) - set(ids)):
        problems.append(f"{extra} key rows not in the sheet")
    if filled := sum(1 for r in rows if any(r[c].strip() for c in JUDGED)):
        problems.append(f"{filled} rows already have a judged column filled")
    if problems:
        raise SystemExit(f"{label}: " + "; ".join(problems))
    keep = [r for r in rows if str(key[r["row"]]["pass"]) == "1"]
    qids = [key[r["row"]]["id"] for r in keep]
    print(f"{label}: {len(rows)} rows in the sheet, {len(keep)} pass 1,"
          f" {len(set(qids))} distinct question ids in pass 1")
    if len(keep) != per_version or len(set(qids)) != len(qids):
        raise SystemExit(f"{label}: need exactly {per_version} pass-1 rows, each question id"
                         f" once (got {len(keep)} rows, {len(qids) - len(set(qids))} repeats)")
    return keep


def mix(inputs: list[tuple[str, Path, Path]], out: Path, seed: int = DEFAULT_SEED,
        per_version: int = PER_VERSION, root: Path = ROOT) -> tuple[Path, Path]:
    out = refuse_inside_repo(out, root)
    labels = [label for label, _, _ in inputs]
    if len(labels) < 2 or len(set(labels)) != len(labels):
        raise SystemExit("mix needs at least two inputs with different labels")
    sheet_path, key_path = out / MIXED_SHEET, out / MIXED_KEY
    if sheet_path.exists() or key_path.exists():
        raise SystemExit(f"refused: {out} already holds a mixed sheet or key (never overwritten)")
    pool, sources, id_sets = [], {}, {}
    for label, sheet, keyfile in inputs:
        sheet, keyfile = sheet.resolve(), keyfile.resolve()
        key = json.loads(keyfile.read_text(encoding="utf-8"))["rows"]
        keep = pass1_rows(label, read_sheet(sheet), key, per_version)
        id_sets[label] = {key[r["row"]]["id"] for r in keep}
        pool += [(label, r) for r in keep]
        sources[label] = {"sheet": str(sheet), "sheet_sha256": sha256(sheet),
                          "key": str(keyfile), "key_sha256": sha256(keyfile)}
    first = id_sets[labels[0]]
    for label in labels[1:]:
        if id_sets[label] != first:
            raise SystemExit(f"question ids differ: {len(first - id_sets[label])} only in"
                             f" {labels[0]}, {len(id_sets[label] - first)} only in {label}")
    random.Random(seed).shuffle(pool)
    rows, combined = [], {}
    for n, (label, r) in enumerate(pool, start=1):
        rows.append({**{c: r[c] for c in SHEET_COLUMNS}, "row": str(n),
                     **dict.fromkeys(JUDGED, "")})
        combined[str(n)] = {"version": label, "row": r["row"]}
    out.mkdir(parents=True, exist_ok=True)
    write_sheet(sheet_path, rows)
    key_path.write_text(json.dumps({"seed": seed, "per_version": per_version,
                                    "sources": sources, "rows": combined}, indent=1) + "\n",
                        encoding="utf-8")
    print(f"seed {seed}; {len(rows)} rows ({per_version} per version x {len(labels)})"
          f" -> {sheet_path}\nkey -> {key_path} (do not open until judging is done)")
    return sheet_path, key_path


def _norm(text: str) -> str:
    return " ".join(text.split())


def unmix(mixed_sheet: Path, mixed_key: Path, out: Path, root: Path = ROOT) -> dict[str, Path]:
    out = refuse_inside_repo(out, root)
    combined = json.loads(mixed_key.read_text(encoding="utf-8"))
    rows = read_sheet(mixed_sheet)
    ids = [r["row"] for r in rows]
    if len(set(ids)) != len(ids) or set(ids) != set(combined["rows"]):
        raise SystemExit(f"mixed sheet and key do not match: {len(ids)} rows in the sheet"
                         f" ({len(ids) - len(set(ids))} repeated), {len(combined['rows'])} in the"
                         f" key, {len(set(ids) ^ set(combined['rows']))} in only one of them")
    originals, keys = {}, {}
    for label, src in combined["sources"].items():
        sheet, keyfile = Path(src["sheet"]), Path(src["key"])
        if sha256(sheet) != src["sheet_sha256"] or sha256(keyfile) != src["key_sha256"]:
            raise SystemExit(f"{label}: the original sheet or key changed since mix")
        originals[label] = read_sheet(sheet)
        keys[label] = json.loads(keyfile.read_text(encoding="utf-8"))["rows"]
    by_row = {label: {r["row"]: r for r in rs} for label, rs in originals.items()}
    problems, seen = [], set()
    for r in rows:
        where = combined["rows"][r["row"]]
        target = by_row[where["version"]].get(where["row"])
        if target is None or (where["version"], where["row"]) in seen:
            problems.append(f"row {r['row']}: no original row, or one used twice")
            continue
        seen.add((where["version"], where["row"]))
        if str(keys[where["version"]][where["row"]]["pass"]) != "1":
            problems.append(f"row {r['row']}: its original row is not a pass-1 row")
        if _norm(r["question"]) != _norm(target["question"]):
            problems.append(f"row {r['row']}: question differs from its original row")
        for col, allowed in ALLOWED.items():
            if r[col].strip().lower() not in allowed:
                problems.append(f"row {r['row']}: {col} must be one of"
                                f" {'/'.join(a for a in allowed if a)} or blank")
        for col in JUDGED:
            target[col] = r[col].strip()
    for label, key in keys.items():
        p1 = {i for i, k in key.items() if str(k["pass"]) == "1"}
        if left := len(p1 - {row for v, row in seen if v == label}):
            problems.append(f"{label}: {left} pass-1 rows have no row in the mixed sheet")
    if problems:
        raise SystemExit("mixed sheet rejected:\n  " + "\n  ".join(problems))
    out.mkdir(parents=True, exist_ok=True)
    written = {}
    for label, rs in originals.items():
        key = keys[label]
        path = out / f"{label}-filled-sheet.csv"
        write_sheet(path, rs)
        written[label] = path
        p1 = [r for r in rs if str(key[r["row"]]["pass"]) == "1"]
        faithful = sum(1 for r in p1 if r["faithful"])
        print(f"{label}: {len(rs)} rows -> {path}; pass 1: {len(p1)} rows, {faithful} with"
              f" faithful, {len(p1) - faithful} without; other passes: {len(rs) - len(p1)} rows"
              f" left blank (awaiting)\n  judge with --key {combined['sources'][label]['key']}")
    return written


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mix")
    m.add_argument("--input", action="append", nargs="+", required=True,
                   metavar="LABEL DIR | LABEL SHEET KEY")
    m.add_argument("--out", type=Path, required=True)
    m.add_argument("--seed", type=int, default=DEFAULT_SEED)
    m.add_argument("--per-version", type=int, default=PER_VERSION)
    u = sub.add_parser("unmix")
    u.add_argument("sheet", type=Path)
    u.add_argument("key", type=Path)
    u.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    refuse_inside_repo(args.out)  # before reading anything
    if args.cmd == "mix":
        mix([find_inputs(v) for v in args.input], args.out, args.seed, args.per_version)
    else:
        unmix(args.sheet, args.key, args.out)


if __name__ == "__main__":
    main()
