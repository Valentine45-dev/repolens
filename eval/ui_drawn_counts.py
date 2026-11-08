"""Nodes and edges the Explorer draws at rest, for every map view of a repo: the before/after check
for UI-only branches (feat/ui-polish). No LLM, no embedding; reads the database only.

    uv run --project backend --env-file .env python eval/ui_drawn_counts.py --label before
    uv run --project backend --env-file .env python eval/ui_drawn_counts.py --label after \
        --compare eval/results/ui_drawn_counts-before-....json

Views: the view a visitor opens (start rule), every folder view at level "folder" and at level
"file", and every non-test file's symbol view; at two settings, "default" (tests and guesses
hidden) and "everything" (both shown; symbol views at default only). Node counts come from the API's
own map_view; drawn edges come from the web app's code (ui_drawn_counts.mjs runs the real
selectEdges with the real edgeBudgetFor, as Explore.tsx does). The SHA-1 of the drawn edge keys
shows that the same edges are drawn, not only the same number.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from graph_readability import SETTINGS, latest_snapshots, walk_folders
from runinfo import header, run_info, save_results

from app.api.graph import file_graph, load_repo_map, map_view
from app.db import close_pool, open_pool, pool

START_FILE_LIMIT = 30  # web/src/mapModel.ts
MJS = Path(__file__).with_name("ui_drawn_counts.mjs")


def slim(view: dict) -> dict:
    return {"node_count": len(view["nodes"]),
            "edges": [{k: e.get(k) for k in ("source", "target", "count", "guess", "guess_calls",
                                             "type", "cycle_edges")} for e in view["edges"]]}


def collect(name: str, snapshot_id: int, setting_name: str, setting: dict,
            views: list[dict]) -> None:
    min_conf, hide = setting["min_confidence"], setting["exclude_tests"]
    key = f"{name}|{setting_name}"
    visible = len(file_graph(snapshot_id, min_conf, hide)["nodes"])
    start = "file" if visible <= START_FILE_LIMIT else "folder"
    first = map_view(snapshot_id, start, "", min_conf, hide)
    views.append({"id": f"{key}|start|{start}|", **slim(first)})
    with pool().connection() as conn:
        repo = load_repo_map(conn, snapshot_id, min_conf, hide)
    for v in walk_folders(repo):
        root = v["root"]
        views.append({"id": f"{key}|folder|{root}", **slim(v)})
        views.append({"id": f"{key}|file|{root}",
                      **slim(map_view(snapshot_id, "file", root, min_conf, hide))})
    if setting_name == "default":
        for f in repo.files:
            views.append({"id": f"{key}|symbol|{f.path}",
                          **slim(map_view(snapshot_id, "symbol", f.path, min_conf, hide))})


def run_rule(views: list[dict]) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "views.json"
        path.write_text(json.dumps(views), encoding="utf-8")
        out = subprocess.run(
            ["node", "--experimental-strip-types", "--no-warnings", str(MJS), str(path)],
            check=True, capture_output=True, text=True).stdout
    return json.loads(out)["views"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="")
    parser.add_argument("--repos", nargs="*", default=["pygoat", "express", "flask", "black"])
    parser.add_argument("--compare", help="an earlier result file: exit 1 if any view differs")
    args = parser.parse_args()

    open_pool()
    try:
        info = run_info(llm_used=False)
        print(header(info))
        snaps = latest_snapshots(args.repos)
        views: list[dict] = []
        for name, (snapshot_id, _sha) in snaps.items():
            for setting_name, setting in SETTINGS.items():
                collect(name, snapshot_id, setting_name, setting, views)
            print(f"{name}: snapshot {snapshot_id}, {len(views)} views so far")
        drawn = run_rule(views)
    finally:
        close_pool()

    totals = {}
    for v in drawn:
        repo = v["id"].split("|")[0]
        t = totals.setdefault(repo, {"views": 0, "nodes": 0, "edges_total": 0, "edges_drawn": 0})
        t["views"] += 1
        t["nodes"] += v["nodes"]
        t["edges_total"] += v["edges_total"]
        t["edges_drawn"] += v["edges_drawn"]
    for repo, t in totals.items():
        print(f"{repo:8} views {t['views']:4}  nodes {t['nodes']:6}  edges {t['edges_total']:6}  "
              f"drawn at rest {t['edges_drawn']:6}")
    results = {"snapshots": {k: v[0] for k, v in snaps.items()}, "totals": totals, "views": drawn}
    path = save_results(f"ui_drawn_counts{'-' + args.label if args.label else ''}", info, results)
    print(path)

    if args.compare:
        saved = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        old = {v["id"]: v for v in saved["views"]}
        new = {v["id"]: v for v in drawn}
        diff = sorted(k for k in old.keys() | new.keys() if old.get(k) != new.get(k))
        print(f"compared with {args.compare}: {len(new)} views, {len(diff)} differ")
        for k in diff[:20]:
            print("  ", k, old.get(k), "->", new.get(k))
        sys.exit(1 if diff else 0)


if __name__ == "__main__":
    main()
