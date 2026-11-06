"""Edge crossings of the folder map, before and after a layout or edge-budget change. No LLM, no
embedding; reads the database only, then Node lays the views out with two checkouts' code.

    uv run --project backend --env-file .env python eval/graph_crossings.py --old C:/path/to/old/web/src --label part-b-round2

Views: the three named ones (flask `src/flask`, PyGoat's root, black `src/black`), the default
view of flask, and every folder view of the five repos at the default setting (tests and guesses
hidden). Yardstick: edgeMetrics in web/src/mapLayout.ts (straight lines between node centres).
"""

import argparse
import json
import statistics
import subprocess
import tempfile
from pathlib import Path

from graph_readability import SETTINGS, latest_snapshots, walk_folders
from runinfo import header, run_info, save_results

from app.api.graph import file_graph, load_repo_map, map_view
from app.db import close_pool, open_pool, pool

ROOT = Path(__file__).resolve().parent.parent
MJS = Path(__file__).with_name("graph_crossings.mjs")
NAMED = [("flask", "folder", "src/flask"), ("pygoat", "folder", ""), ("black", "folder", "src/black"),
         ("flask", "file", "")]
START_FILE_LIMIT = 30


def slim(sid: int, label: str, view: dict) -> dict:
    return {"id": f"{sid}|{view['level']}|{view['root']}", "label": label, "level": view["level"],
            "nodes": [{"id": n["id"], "kind": n["kind"]} for n in view["nodes"]],
            "edges": [{"source": e["source"], "target": e["target"], "count": e["count"],
                       "guess": e.get("guess", False), "type": e.get("type"),
                       "cycle_edges": e.get("cycle_edges")} for e in view["edges"]]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", required=True, help="web/src of the checkout before the change")
    parser.add_argument("--new", default=str(ROOT / "web" / "src"))
    parser.add_argument("--label", default="")
    parser.add_argument("--budget", default=None, help="one edge budget for every view (sweeps)")
    parser.add_argument("--repos", nargs="*", default=["itsdangerous", "pygoat", "express", "flask", "black"])
    args = parser.parse_args()
    setting = SETTINGS["default"]

    open_pool()
    try:
        info = run_info(llm_used=False)
        print(header(info))
        snaps = latest_snapshots(args.repos)
        views, named = [], []
        for name, level, root in NAMED:
            sid = snaps[name][0]
            v = map_view(sid, level, root, setting["min_confidence"], setting["exclude_tests"])
            label = f"{name} {root or '(root)'} ({level} level)"
            named.append(slim(sid, label, v)["id"])
            views.append(slim(sid, label, v))
        for name, (sid, _commit) in snaps.items():
            with pool().connection() as conn:
                repo = load_repo_map(conn, sid, setting["min_confidence"], setting["exclude_tests"])
            for v in walk_folders(repo):
                item = slim(sid, f"{name} {v['root'] or '(root)'}", v)
                if all(item["id"] != x["id"] for x in views):
                    views.append(item)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "views.json"
            path.write_text(json.dumps(views), encoding="utf-8")
            out = subprocess.run(
                ["node", "--experimental-strip-types", "--no-warnings", str(MJS), str(path),
                 "--old", args.old, "--new", args.new] + (["--budget", args.budget] if args.budget else []),
                check=True, capture_output=True, text=True).stdout
        results = json.loads(out)
        by_id = {r["id"]: r for r in results}

        def row(r):
            b, a = r["before"], r["after"]
            return (f"| {r['label']} | {r['nodes']} | {r['edgesTotal']} | {b['edges']} | {b['crossings']} | "
                    f"{b['throughNodes']} | {b['backward']}+{b['sameColumn']} | {a['edges']} | {a['crossings']} | "
                    f"{a['throughNodes']} | {a['backward']}+{a['sameColumn']} |")

        lines = ["# Edge crossings, before and after", "",
                 f"Commit `{info['commit_sha'][:7]}`. Yardstick: straight lines between node centres "
                 "(`edgeMetrics` in `web/src/mapLayout.ts`). 'Back+same' = edges pointing back + edges inside one column.", "",
                 "| View | Nodes | Edges | Drawn before | Crossings before | Through nodes before | Back+same before | "
                 "Drawn after | Crossings after | Through nodes after | Back+same after |",
                 "|---|---|---|---|---|---|---|---|---|---|---|"]
        lines += [row(by_id[i]) for i in named]
        crowded = [r for r in results if r["before"]["crossings"] > 0 or r["after"]["crossings"] > 0]
        lines += ["", f"All {len(results)} folder views (default setting): {len(crowded)} have any crossing.", "",
                  "| Measure | Before | After |", "|---|---|---|"]
        for key, title in (("crossings", "crossings, total"), ("throughNodes", "edges through nodes, total")):
            lines.append(f"| {title} | {sum(r['before'][key] for r in results)} | {sum(r['after'][key] for r in results)} |")
        for key, title in (("crossings", "crossings, most in one view"), ("edges", "edges drawn, most in one view")):
            lines.append(f"| {title} | {max(r['before'][key] for r in results)} | {max(r['after'][key] for r in results)} |")
        lines.append(f"| median crossings (views with any) | "
                     f"{statistics.median([r['before']['crossings'] for r in crowded] or [0])} | "
                     f"{statistics.median([r['after']['crossings'] for r in crowded] or [0])} |")
        name = "graph_crossings" + (f"-{args.label}" if args.label else "")
        saved = save_results(name, info, {"named": named, "views": results})
        Path(str(saved)).with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        print(saved)
    finally:
        close_pool()


if __name__ == "__main__":
    main()
