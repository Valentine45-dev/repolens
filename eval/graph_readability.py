"""The folder-first map on real snapshots: every folder's node and edge counts, cycles, spot checks
of aggregated edges against SQL, and timing. No LLM, no embedding; reads the database only.

    uv run --project backend --env-file .env python eval/graph_readability.py --label part-a

Two settings per repo: "default" (tests hidden, guesses hidden: what a visitor first sees) and
"everything" (tests and guesses shown: the largest views the toggles can produce).
"""

import argparse
import statistics
import time
from collections import Counter

from runinfo import header, run_info, save_results

from app.api.graph import file_graph, load_repo_map, map_view
from app.db import close_pool, open_pool, pool
from app.graph_map import RepoMap, find_cycles
from app.paths import is_test_path

SETTINGS = {
    "default": {"exclude_tests": True, "min_confidence": 0.9},
    "everything": {"exclude_tests": False, "min_confidence": 0.5},
}
BUCKETS = [(1, 5), (6, 15), (16, 30), (31, 60), (61, 61)]
SPOT_CHECKS = 5
TIMING_REPEATS = 7


def latest_snapshots(names: list[str]) -> dict[str, tuple[int, str]]:
    """Repo name -> (newest finished snapshot, commit)."""
    out = {}
    with pool().connection() as conn:
        for name in names:
            row = conn.execute(
                "SELECT s.id, s.commit_sha FROM snapshots s JOIN repos r ON r.id = s.repo_id"
                " JOIN snapshot_status st ON st.snapshot_id = s.id"
                " WHERE st.status = 'done' AND lower(r.url) LIKE %s ORDER BY s.id DESC LIMIT 1",
                (f"%/{name.lower()}",),
            ).fetchone()
            if row:
                out[name] = (row["id"], row["commit_sha"])
            else:
                print(f"{name}: no finished snapshot, skipped")
    return out


def walk_folders(repo: RepoMap) -> list[dict]:
    """The folder view of every folder a visitor can reach by clicking, from the repo root."""
    views = []
    queue = [""]
    seen = set()
    while queue:
        view = repo.folder_view(queue.pop())
        if view["root"] in seen:
            continue
        seen.add(view["root"])
        views.append(view)
        queue += [n["path"] for n in view["nodes"] if n["kind"] == "folder"]
    return sorted(views, key=lambda v: v["root"])


def check_conservation(repo: RepoMap, view: dict) -> bool:
    """Every link touching the root is on an edge, inside a node, or across the boundary, once."""
    root = view["root"]

    def under(path):
        return not root or path.startswith(root + "/")

    touching = sum(li.count for li in repo.links if under(li.source) or under(li.target))
    return touching == (sum(e["count"] for e in view["edges"])
                        + sum(n["internal_count"] + n["outside_in"] + n["outside_out"]
                              for n in view["nodes"]))


def spot_check_edges(snapshot_id: int, views: list[dict], setting: dict) -> list[dict]:
    """The largest aggregated edges, recounted from the raw edge rows with their own SQL."""
    candidates = []
    for view in views:
        nodes = {n["id"]: n for n in view["nodes"]}
        if view["hidden_count"]:
            continue
        for e in view["edges"]:
            candidates.append((e["count"], view["root"], nodes[e["source"]], nodes[e["target"]], e))
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]["id"], c[3]["id"]))

    checks = []
    with pool().connection() as conn:
        for count, root, a, b, edge in candidates[:SPOT_CHECKS]:
            rows = conn.execute(
                "SELECT sf.path AS source, df.path AS target, e.type FROM edges e"
                " JOIN symbols s ON s.id = e.src_id JOIN symbols d ON d.id = e.dst_id"
                " JOIN files sf ON sf.id = s.file_id JOIN files df ON df.id = d.file_id"
                " WHERE e.snapshot_id = %s AND e.type IN ('imports', 'calls')"
                " AND s.file_id <> d.file_id AND round(e.confidence::numeric, 2) >= %s"
                " AND (sf.path = %s OR sf.path LIKE %s) AND (df.path = %s OR df.path LIKE %s)",
                (snapshot_id, setting["min_confidence"], a["path"], a["path"] + "/%",
                 b["path"], b["path"] + "/%"),
            ).fetchall()
            if setting["exclude_tests"]:
                rows = [r for r in rows
                        if not is_test_path(r["source"]) and not is_test_path(r["target"])]
            found = Counter(r["type"] for r in rows)
            checks.append({
                "view": root, "source": a["path"], "target": b["path"],
                "api": [count, edge["imports"], edge["calls"]],
                "sql": [len(rows), found["imports"], found["calls"]],
                "match": [count, edge["imports"], edge["calls"]]
                == [len(rows), found["imports"], found["calls"]],
            })
    return checks


def median_ms(fn, repeats=TIMING_REPEATS) -> float:
    runs = []
    for _ in range(repeats):
        started = time.perf_counter()
        fn()
        runs.append((time.perf_counter() - started) * 1000)
    return round(statistics.median(runs), 1)


def measure_timing(snapshot_id: int, setting: dict) -> dict:
    with pool().connection() as conn:
        repo = load_repo_map(conn, snapshot_id, setting["min_confidence"],
                             setting["exclude_tests"])

        def read():
            load_repo_map(conn, snapshot_id, setting["min_confidence"], setting["exclude_tests"])

        load = median_ms(read)
    return {
        "flat_graph_ms": median_ms(lambda: file_graph(snapshot_id, setting["min_confidence"],
                                                      setting["exclude_tests"])),
        "load_and_cycles_ms": load,
        "cycles_only_ms": median_ms(lambda: find_cycles(
            repo.by_path, ((li.source, li.target) for li in repo.links if li.top_level_import))),
        "root_view_only_ms": median_ms(lambda: repo.folder_view("")),
        "full_root_request_ms": median_ms(lambda: map_view(
            snapshot_id, "folder", "", setting["min_confidence"], setting["exclude_tests"])),
        "files": len(repo.files),
        "links": len(repo.links),
    }


def symbol_views(snapshot_id: int, repo: RepoMap, setting: dict) -> dict:
    nodes, edges = [], []
    over = 0
    for f in repo.files:
        view = map_view(snapshot_id, "symbol", f.path, setting["min_confidence"],
                        setting["exclude_tests"])
        nodes.append(len(view["nodes"]))
        edges.append(len(view["edges"]))
        over += bool(view["hidden_count"])
    return {"views": len(nodes), "max_nodes": max(nodes, default=0),
            "median_nodes": statistics.median(nodes) if nodes else 0,
            "max_edges": max(edges, default=0), "with_overflow": over}


def import_scopes(snapshot_id: int) -> dict:
    with pool().connection() as conn:
        rows = conn.execute(
            "SELECT d.file_id IS NOT NULL AS internal, coalesce(e.import_scope, 'NULL') AS scope,"
            " count(*) AS n FROM edges e JOIN symbols d ON d.id = e.dst_id"
            " WHERE e.snapshot_id = %s AND e.type = 'imports' GROUP BY 1, 2",
            (snapshot_id,),
        ).fetchall()
    return {("internal " if r["internal"] else "external ") + r["scope"]: r["n"] for r in rows}


def false_cycles(repo: RepoMap) -> list[list[str]]:
    """What the cycle list would be with every import counted, as stored before scopes."""
    return find_cycles(repo.by_path, ((li.source, li.target) for li in repo.links if li.imports))


def measure(name: str, snapshot_id: int, commit: str) -> dict:
    result = {"snapshot_id": snapshot_id, "commit": commit,
              "import_scopes": import_scopes(snapshot_id)}
    for setting_name, setting in SETTINGS.items():
        with pool().connection() as conn:
            repo = load_repo_map(conn, snapshot_id, setting["min_confidence"],
                                 setting["exclude_tests"])
        views = walk_folders(repo)
        nodes = [len(v["nodes"]) for v in views]
        edges = [len(v["edges"]) for v in views]
        flat = file_graph(snapshot_id, setting["min_confidence"], setting["exclude_tests"])
        result[setting_name] = {
            "flat_nodes": len(flat["nodes"]),
            "flat_edges": len(flat["edges"]),
            "root": repo.folder_view("")["root"],
            "root_nodes": nodes[0] if views else 0,
            "root_edges": edges[0] if views else 0,
            "folder_views": len(views),
            "max_nodes": max(nodes, default=0),
            "median_nodes": statistics.median(nodes) if nodes else 0,
            "max_edges": max(edges, default=0),
            "median_edges": statistics.median(edges) if edges else 0,
            "views_by_nodes": {f"{a}-{b}": sum(1 for n in nodes if a <= n <= b)
                               for a, b in BUCKETS},
            "views_with_overflow": [{"root": v["root"], "nodes": len(v["nodes"]),
                                     "hidden": v["hidden_count"]}
                                    for v in views if v["hidden_count"]],
            "conservation_ok": all(check_conservation(repo, v) for v in views),
            "cycles_top_level": [c["files"] for c in repo.cycle_summary()["cycles"]],
            "cycles_if_every_import_counted": false_cycles(repo),
            "two_way_folder_pairs_without_cycle": two_way_pairs(views),
            "spot_checks": spot_check_edges(snapshot_id, views, setting),
            "symbol_views": symbol_views(snapshot_id, repo, setting),
            "timing": measure_timing(snapshot_id, setting),
            "per_folder": [{"root": v["root"] or "/", "nodes": len(v["nodes"]),
                            "edges": len(v["edges"]), "hidden": v["hidden_count"]}
                           for v in views],
        }
    return result


def two_way_pairs(views: list[dict]) -> list[str]:
    """Node pairs with edges both ways and no cycle edge: the case that must never be labelled
    circular."""
    pairs = []
    for v in views:
        edges = {(e["source"], e["target"]): e for e in v["edges"]}
        for (a, b), e in edges.items():
            back = edges.get((b, a))
            if a < b and back and not e["cycle_edges"] and not back["cycle_edges"]:
                pairs.append(f"{v['root'] or '/'}: {a} <-> {b} ({e['count']}, {back['count']})")
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="")
    parser.add_argument("--repos", nargs="*", default=["itsdangerous", "pygoat", "express",
                                                       "flask", "black"])
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    open_pool()
    try:
        info = run_info(llm_used=False)
        info["notes"] = args.notes
        print(header(info))
        results = {}
        for name, (snapshot_id, commit) in latest_snapshots(args.repos).items():
            results[name] = measure(name, snapshot_id, commit)
            for setting_name in SETTINGS:
                r = results[name][setting_name]
                timing = r["timing"]
                print(f"{name:13} {setting_name:10} flat {r['flat_nodes']:4}n {r['flat_edges']:4}e"
                      f" | root {r['root_nodes']:3}n {r['root_edges']:3}e"
                      f" | {r['folder_views']:3} views, max {r['max_nodes']:2}n {r['max_edges']:3}e"
                      f" | overflow {len(r['views_with_overflow'])}"
                      f" | cycles {len(r['cycles_top_level'])}"
                      f" (all imports: {len(r['cycles_if_every_import_counted'])})"
                      f" | spot {sum(c['match'] for c in r['spot_checks'])}"
                      f"/{len(r['spot_checks'])}"
                      f" | conservation {r['conservation_ok']}"
                      f" | root request {timing['full_root_request_ms']} ms")
        name = "graph_readability" + (f"-{args.label}" if args.label else "")
        print(save_results(name, info, {"repos": results}))
    finally:
        close_pool()


if __name__ == "__main__":
    main()
