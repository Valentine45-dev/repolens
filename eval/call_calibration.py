"""Call-confidence calibration: draw the sample and build the blind sheets (v2 step 6a, Part 2).

    uv run --project backend --env-file .env python eval/call_calibration.py counts
    uv run --project backend --env-file .env python eval/call_calibration.py build

Rule, quotas, caps, seed and scoring are fixed in eval/call_calibration_rule.md, committed before
`build` is run. No LLM; reads the dev database (stored, redacted text only, nothing is cloned).
`counts` prints the populations and writes nothing. `build` draws, writes the blank sheets and the
key to ASSETS (outside git) and saves the counts and the files' SHA-256 to eval/results.
"""

import csv
import hashlib
import json
import random
import secrets
import string
import sys
from collections import Counter
from pathlib import Path

from runinfo import header, run_info, save_results  # also puts backend/ on sys.path

from app import db  # noqa: E402
from app.paths import is_test_path  # noqa: E402
from blind_sheet import mask  # noqa: E402

SEED = 20261107
CAP_PER_EDGE = 1
CAP_PER_CALLEE = 2
BANDS = (1.0, 0.9, 0.5)
BAND_QUOTA = 30
EXPRESS_PER_BAND = 8
JUDGE2_PER_BAND = 10
CONTEXT = 3
CALLEE_LINES = 15
BLACK_MIN_SITES, BLACK_MIN_CALLEES = 15, 8
ASSETS = Path(r"C:\projects\repolens-eval-assets\call-calibration")

URLS = {
    "pygoat": "https://github.com/adeyosemanputra/pygoat",
    "flask": "https://github.com/pallets/flask",
    "black": "https://github.com/psf/black",
    "express": "https://github.com/expressjs/express",
}
HEADER = ["id", "repo", "call site", "caller", "call site code", "callee", "callee location",
          "callee definition (first 15 lines)", "label (correct / incorrect / unsure)", "note"]


def snapshot_of(conn, url: str) -> tuple[int, str]:
    row = conn.execute(
        "SELECT s.id, s.commit_sha FROM snapshots s JOIN repos r ON r.id = s.repo_id"
        " JOIN snapshot_status st ON st.snapshot_id = s.id"
        " WHERE lower(r.url) = lower(%s) AND st.status = 'done' ORDER BY s.id DESC",
        (url,)).fetchone()
    return row["id"], row["commit_sha"]


def load_sites(conn, snapshot_id: int, python_only: bool, include_tests: bool) -> list[dict]:
    rows = conn.execute(
        "SELECT es.line, round(es.confidence::numeric, 1) AS conf, e.id AS eid, d.id AS did,"
        " s.qualified_name AS caller, sf.path AS caller_path, d.qualified_name AS callee,"
        " df.path AS callee_path, d.start_line, d.end_line FROM edge_sites es"
        " JOIN edges e ON e.id = es.edge_id JOIN symbols s ON s.id = e.src_id"
        " JOIN files sf ON sf.id = s.file_id JOIN symbols d ON d.id = e.dst_id"
        " JOIN files df ON df.id = d.file_id WHERE e.snapshot_id = %s AND e.type = 'calls'"
        " AND es.confidence IS NOT NULL", (snapshot_id,)).fetchall()
    out = []
    for r in rows:
        in_test = is_test_path(r["caller_path"]) or is_test_path(r["callee_path"])
        if in_test and not include_tests:
            continue
        if python_only and not (r["caller_path"].endswith(".py") and r["callee_path"].endswith(".py")):
            continue
        out.append({**r, "conf": float(r["conf"]), "in_test": in_test})
    return sorted(out, key=lambda r: (r["caller_path"], r["line"], r["callee"]))


def capped_order(sites: list[dict], rng: random.Random) -> list[dict]:
    """The eligible sites in a seeded random order with the caps applied; any prefix is a valid draw."""
    order = list(sites)
    rng.shuffle(order)
    edges, callees, kept = set(), Counter(), []
    for s in order:
        if s["eid"] in edges or callees[s["did"]] >= CAP_PER_CALLEE:
            continue
        edges.add(s["eid"])
        callees[s["did"]] += 1
        kept.append(s)
    return kept


def band_pool(sites: list[dict], band: float) -> list[dict]:
    return [s for s in sites if s["conf"] == band]


def quotas(band: float, lists: dict[str, list[dict]], raw: dict[str, list[dict]]) -> dict[str, int]:
    """Fixed rule (eval/call_calibration_rule.md)."""
    if band == 1.0:
        want = {"pygoat": 15, "flask": 15}
    else:
        pygoat = min(len(lists["pygoat"]), BAND_QUOTA // 2)
        rest = BAND_QUOTA - pygoat
        black_ok = (len(raw["black"]) >= BLACK_MIN_SITES
                    and len({s["did"] for s in raw["black"]}) >= BLACK_MIN_CALLEES)
        if black_ok:
            want = {"pygoat": pygoat, "flask": rest - rest // 2, "black": rest // 2}
        else:
            want = {"pygoat": pygoat, "flask": rest}
    # a repo that cannot fill its quota after the caps passes the shortfall to the others
    got = {r: min(n, len(lists[r])) for r, n in want.items()}
    short = sum(want.values()) - sum(got.values())
    for r in [r for r in ("flask", "black", "pygoat") if r in got]:
        room = len(lists[r]) - got[r]
        add = min(room, short)
        got[r] += add
        short -= add
    return got


def snippet(content: str, line: int) -> str:
    lines = content.splitlines()
    i = line - 1
    lo, hi = max(0, i - CONTEXT), min(len(lines), i + CONTEXT + 1)
    return mask("\n".join(f"{'>' if n == i else ' '} {n + 1:>4}  {lines[n]}" for n in range(lo, hi)))


def definition(content: str, start: int | None, end: int | None) -> str:
    lines = content.splitlines()
    if not start:
        return ""
    stop = min(end or start, start + CALLEE_LINES - 1, len(lines))
    text = "\n".join(f"  {n:>4}  {lines[n - 1]}" for n in range(start, stop + 1))
    if (end or start) > stop:
        text += f"\n  ...  ({(end or start) - stop} more lines)"
    return mask(text)


def stats(sites: list[dict]) -> dict:
    return {"sites": len(sites), "distinct_callees": len({s["did"] for s in sites}),
            "distinct_caller_files": len({s["caller_path"] for s in sites}),
            "distinct_callee_files": len({s["callee_path"] for s in sites})}


def populations(conn) -> dict:
    snaps = {name: snapshot_of(conn, url) for name, url in URLS.items()}
    py = {n: load_sites(conn, snaps[n][0], python_only=True, include_tests=False)
          for n in ("pygoat", "flask", "black")}
    express = load_sites(conn, snaps["express"][0], python_only=False, include_tests=True)
    return {"snaps": snaps, "py": py, "express": express}


def main(mode: str) -> None:
    db.open_pool()
    with db.pool().connection() as conn:
        pop = populations(conn)
        print("snapshots:", {n: (i, sha[:7]) for n, (i, sha) in pop["snaps"].items()})
        for band in BANDS:
            for repo, sites in pop["py"].items():
                raw = band_pool(sites, band)
                capped = capped_order(raw, random.Random(f"{SEED}-{band}-{repo}"))
                print(f"{repo:8} band {band}: raw {stats(raw)} | drawable after caps {len(capped)}")
            raw = band_pool(pop["express"], band)
            print(f"express  band {band}: raw {stats(raw)} (in test/example: "
                  f"{sum(s['in_test'] for s in raw)})")
        if mode == "counts":
            return

        drawn: dict[tuple[str, float], list[dict]] = {}
        for band in BANDS:
            raw = {r: band_pool(pop["py"][r], band) for r in pop["py"]}
            lists = {r: capped_order(raw[r], random.Random(f"{SEED}-{band}-{r}")) for r in raw}
            for repo, n in quotas(band, lists, raw).items():
                drawn[(repo, band)] = lists[repo][:n]
            rawx = band_pool(pop["express"], band)
            drawn[("express", band)] = capped_order(
                rawx, random.Random(f"{SEED}-{band}-express"))[:EXPRESS_PER_BAND]

        contents: dict[tuple[str, str], str] = {}

        def text(repo: str, path: str) -> str:
            if (repo, path) not in contents:
                row = conn.execute("SELECT content FROM files WHERE snapshot_id = %s AND path = %s",
                                   (pop["snaps"][repo][0], path)).fetchone()
                contents[(repo, path)] = row["content"] if row else ""
            return contents[(repo, path)]

        sysrand = random.SystemRandom()
        used: set[str] = set()

        def new_id() -> str:
            while True:
                rid = "r-" + "".join(sysrand.choice(string.ascii_lowercase) for _ in range(5))
                if rid not in used:
                    used.add(rid)
                    return rid

        main_rows, express_rows = [], []
        for (repo, band), sites in drawn.items():
            for s in sites:
                row = {"id": new_id(), "repo": repo, "band": band, "edge_id": s["eid"],
                       "callee_symbol_id": s["did"], "in_test": s["in_test"],
                       "call site": f"{s['caller_path']}:{s['line']}", "caller": s["caller"],
                       "code": snippet(text(repo, s["caller_path"]), s["line"]),
                       "callee": s["callee"],
                       "callee location": f"{s['callee_path']}:{s['start_line']}-{s['end_line']}",
                       "definition": definition(text(repo, s["callee_path"]), s["start_line"],
                                                s["end_line"])}
                (express_rows if repo == "express" else main_rows).append(row)
        sysrand.shuffle(main_rows)
        sysrand.shuffle(express_rows)
        judge2 = []
        for band in BANDS:
            pool = [r for r in main_rows if r["band"] == band]
            judge2 += random.Random(f"{SEED}-judge2-{band}").sample(
                sorted(pool, key=lambda r: r["id"]), JUDGE2_PER_BAND)
        sysrand.shuffle(judge2)

    def write(name: str, rows: list[dict]) -> Path:
        path = ASSETS / name
        with path.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(HEADER)
            for r in rows:
                w.writerow([r["id"], r["repo"], r["call site"], r["caller"], r["code"], r["callee"],
                            r["callee location"], r["definition"], "", ""])
        return path

    ASSETS.mkdir(parents=True, exist_ok=True)
    files = {"sheet-blank.csv": write("sheet-blank.csv", main_rows),
             "sheet-blank-express.csv": write("sheet-blank-express.csv", express_rows),
             "sheet-blank-judge2.csv": write("sheet-blank-judge2.csv", judge2)}
    key = ASSETS / "key.json"
    key.write_text(json.dumps({"seed": SEED, "main": main_rows, "express": express_rows,
                               "judge2_ids": [r["id"] for r in judge2]}, indent=2) + "\n",
                   encoding="utf-8")
    files["key.json"] = key
    sha = {n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in files.items()}

    counts = {}
    for (repo, band), sites in sorted(drawn.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        counts[f"{repo} {band}"] = {**stats(sites),
                                    **({"in_test_or_example": sum(s["in_test"] for s in sites)}
                                       if repo == "express" else {})}
    totals = {str(b): stats([s for (r, bb), v in drawn.items() if bb == b and r != "express"
                             for s in v]) for b in BANDS}
    info = run_info(llm_used=False)
    print(header(info))
    for k, v in counts.items():
        print(k, v)
    print("per band, main sheet:", totals)
    print("rows: main", len(main_rows), "express", len(express_rows), "judge2", len(judge2))
    for n, h in sha.items():
        print(f"sha256 {n} {h}")
    results = {
        "repos": {n: {"snapshot_id": i, "commit": c} for n, (i, c) in pop["snaps"].items()},
        "rule": "eval/call_calibration_rule.md",
        "seed": SEED, "caps": {"per_edge": CAP_PER_EDGE, "per_callee": CAP_PER_CALLEE},
        "populations_non_test_python": {
            f"{r} {b}": stats(band_pool(pop["py"][r], b)) for b in BANDS for r in pop["py"]},
        "populations_express_all_code": {
            str(b): {**stats(band_pool(pop["express"], b)),
                     "in_test_or_example": sum(s["in_test"] for s in band_pool(pop["express"], b))}
            for b in BANDS},
        "drawn": counts, "drawn_per_band_main": totals,
        "rows": {"main": len(main_rows), "express": len(express_rows), "judge2": len(judge2)},
        "sha256": sha, "files_location": str(ASSETS),
        "note": "key.json is not opened until labelling is done; the labelled sheet's hash is "
                "committed before it is opened.",
    }
    print("saved", save_results("call_calibration_setup", info, results))


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("counts", "build"):
        sys.exit(__doc__)
    main(sys.argv[1])
