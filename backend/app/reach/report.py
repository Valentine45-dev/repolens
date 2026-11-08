"""Print what reachability found in analysed snapshots: entry points per kind with examples, the
tier of every finding, and a few traced paths to check by hand.

    cd backend; uv run --env-file ../.env python -m app.reach.report [snapshot_id ...]
"""

import sys
from collections import Counter

from app.db import close_pool, open_pool, pool
from app.paths import is_test_path
from app.reach.graph import GUESS, NONE, NOT_CHECKED, SOLID
from app.reach.load import build


def describe(reach, symbol_id: int, paths: dict[int, str]) -> str:
    s = reach.symbols[symbol_id]
    where = paths.get(s.file_id, "?")
    return f"{s.name if s.kind != 'module' else where}@{where}:{s.start}"


def trace(reach, finding, paths) -> str:
    sym = reach.symbol_at(finding["file_id"], finding["line"])
    steps = reach.path_to(sym) if sym is not None else []
    if not steps:
        return "(no path)"
    seed = reach.seed_for(sym)
    chain = " -> ".join(
        describe(reach, st.symbol_id, paths) + ("?" if st.guess else "") for st in steps
    )
    return f"[{seed.label}] {chain}"


def report(snapshot_id: int, examples: int = 3) -> None:
    with pool().connection() as conn:
        repo = conn.execute(
            "SELECT r.url, s.commit_sha FROM snapshots s JOIN repos r ON r.id = s.repo_id"
            " WHERE s.id = %s", (snapshot_id,)
        ).fetchone()
        paths = {r["id"]: r["path"] for r in conn.execute(
            "SELECT id, path FROM files WHERE snapshot_id = %s", (snapshot_id,))}
        findings = conn.execute(
            "SELECT f.id, f.file_id, f.line, f.rule_id, f.severity, f.in_test, f.in_docs,"
            " f.placeholder FROM findings f WHERE f.snapshot_id = %s ORDER BY f.id", (snapshot_id,)
        ).fetchall()
    reach = build(snapshot_id)
    print(f"\n=== snapshot {snapshot_id} {repo['url']} @ {repo['commit_sha'][:7]}")
    kinds = Counter(s.kind for s in reach.seeds)
    print(f"entry points: {len({s.symbol_id for s in reach.seeds})} symbols, by kind {dict(kinds)}")
    for kind in sorted(kinds):
        for seed in [s for s in reach.seeds if s.kind == kind][:examples]:
            print(f"   {kind}: {seed.label}   [{seed.detail}]")
    code = [s for s in reach.symbols.values()
            if s.kind != "module" and not is_test_path(paths[s.file_id])]
    reached = Counter(reach.tier_of_symbol(s.id) for s in code)
    print(f"non-test functions/methods/classes: {len(code)}; solid {reached[SOLID]}, "
          f"guess {reached[GUESS]}, no path {reached[NONE]}")
    tiers = [(f, reach.tier(f["file_id"], f["line"])) for f in findings]
    for title, subset in (
        ("all findings", tiers),
        ("non-test, non-docs, non-placeholder",
         [(f, t) for f, t in tiers if not (f["in_test"] or f["in_docs"] or f["placeholder"])]),
    ):
        count = Counter(t for _, t in subset)
        n = len(subset)
        shares = ", ".join(f"{t} {count[t]} ({count[t] / n:.0%})" if n else f"{t} 0"
                           for t in (SOLID, GUESS, NOT_CHECKED, NONE))
        print(f"tiers, {title}: n={n}: {shares}")
    shown = Counter()
    print("traced paths (a '?' marks a guessed step):")
    for f, t in tiers:
        if t in (SOLID, GUESS) and shown[t] < examples and not f["in_test"]:
            shown[t] += 1
            print(f"   finding {f['id']} {f['rule_id']} {paths[f['file_id']]}:{f['line']} -> {t}: "
                  f"{trace(reach, f, paths)}")
    for f, t in tiers:
        if t == NONE and shown[NONE] < examples and not f["in_test"]:
            shown[NONE] += 1
            print(f"   finding {f['id']} {f['rule_id']} {paths[f['file_id']]}:{f['line']} -> none")


def main(argv: list[str]) -> int:
    open_pool()
    try:
        with pool().connection() as conn:
            done = [r["snapshot_id"] for r in conn.execute(
                "SELECT snapshot_id FROM snapshot_status WHERE status = 'done' ORDER BY 1")]
        wanted = [int(a) for a in argv] or done
        for snapshot_id in wanted:
            report(snapshot_id)
        return 0
    finally:
        close_pool()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
