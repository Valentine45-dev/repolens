"""What the folder-map UI draws, before and after: nodes and edges per view, with the web app's
edge-density rule applied (web/src/mapModel.ts selectEdges, run by Node through
graph_ui_readability.mjs). No LLM, no embedding; reads the database only.

    uv run --project backend --env-file .env python eval/graph_ui_readability.py --label part-b

Before = the flat file graph the Explorer drew by default (render cap 300, most connected files).
After = the view a visitor now opens (start rule: files at 30 or fewer visible files, else
folders at the root), and every folder view reachable by clicking, at the same two settings as
graph_readability.py: "default" (tests hidden, guesses hidden) and "everything" (both shown).
Symbol views are measured for every non-test file at the default setting only.
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

RENDER_CAP = 300  # web/src/graphModel.ts
START_FILE_LIMIT = 30  # web/src/mapModel.ts
MJS = Path(__file__).with_name("graph_ui_readability.mjs")


def flat_before(flat: dict) -> dict:
    """The old default picture: the 300 most connected files and the edges among them."""
    nodes = flat["nodes"]
    degree = {n["id"]: 0 for n in nodes}
    for e in flat["edges"]:
        degree[e["source"]] += 1
        degree[e["target"]] += 1
    kept = sorted(nodes, key=lambda n: (-degree[n["id"]], n["path"]))[:RENDER_CAP]
    ids = {n["id"] for n in kept}
    return {
        "flat_nodes": len(nodes),
        "flat_edges": len(flat["edges"]),
        "nodes_drawn": len(kept),
        "edges_drawn": sum(1 for e in flat["edges"] if e["source"] in ids and e["target"] in ids),
        "capped": len(nodes) > RENDER_CAP,
    }


def slim(view: dict) -> list[dict]:
    return [{"source": e["source"], "target": e["target"], "count": e["count"],
             "guess": e.get("guess", False), "type": e.get("type"),
             "cycle_edges": e.get("cycle_edges")} for e in view["edges"]]


def collect(name: str, snapshot_id: int, setting_name: str, setting: dict,
            with_symbols: bool, views: list[dict]) -> dict:
    """Adds this repo's views to `views` (for Node) and returns what Python already knows."""
    min_conf, hide = setting["min_confidence"], setting["exclude_tests"]
    flat = file_graph(snapshot_id, min_conf, hide)
    path_of = {n["id"]: n["path"] for n in flat["nodes"]}
    flat_paths = [n["path"] for n in flat["nodes"]]
    flat_pairs = [(path_of[e["source"]], path_of[e["target"]]) for e in flat["edges"]]
    visible = len(flat["nodes"])
    level = "file" if visible <= START_FILE_LIMIT else "folder"
    key = f"{name}|{setting_name}"

    default = map_view(snapshot_id, level, "", min_conf, hide)
    views.append({"id": f"{key}|default", "edges": slim(default)})
    info = {"before": flat_before(flat), "default": {
        "level": level, "root": default["root"], "visible_files": visible,
        "nodes": len(default["nodes"]), "edges_total": len(default["edges"])}}

    with pool().connection() as conn:
        repo = load_repo_map(conn, snapshot_id, min_conf, hide)
    folders = []
    for v in walk_folders(repo):
        root = v["root"]
        under = [p for p in flat_paths if not root or p.startswith(root + "/")]
        among = sum(1 for a, b in flat_pairs
                    if (not root or a.startswith(root + "/")) and (not root or b.startswith(root + "/")))
        views.append({"id": f"{key}|folder|{root}", "edges": slim(v)})
        folders.append({"root": root or "/", "files_under": len(under), "flat_edges_among": among,
                        "nodes": len(v["nodes"]), "edges_total": len(v["edges"]),
                        "overflow": v["hidden_count"]})
    info["folders"] = folders

    symbols = []
    if with_symbols:
        for f in repo.files:
            v = map_view(snapshot_id, "symbol", f.path, min_conf, hide)
            views.append({"id": f"{key}|symbol|{f.path}", "edges": slim(v)})
            symbols.append({"path": f.path, "nodes": len(v["nodes"]),
                            "edges_total": len(v["edges"]), "overflow": v["hidden_count"]})
    info["symbols"] = symbols
    return info


def run_rule(views: list[dict]) -> dict[str, dict]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "views.json"
        path.write_text(json.dumps(views), encoding="utf-8")
        out = subprocess.run(
            ["node", "--experimental-strip-types", "--no-warnings", str(MJS), str(path)],
            check=True, capture_output=True, text=True).stdout
    return {v["id"]: v for v in json.loads(out)["views"]}


def finish(result: dict, drawn: dict[str, dict], key: str) -> None:
    """Fills in the drawn-edge numbers the rule produced."""
    d = drawn[f"{key}|default"]
    result["default"].update(edges_drawn=d["drawn_edges"], mode=d["mode"], min_count=d["min_count"])
    for f in result["folders"]:
        root = "" if f["root"] == "/" else f["root"]
        v = drawn[f"{key}|folder|{root}"]
        f.update(edges_drawn=v["drawn_edges"], mode=v["mode"], min_count=v["min_count"])
    for s in result["symbols"]:
        v = drawn[f"{key}|symbol|{s['path']}"]
        s.update(edges_drawn=v["drawn_edges"], mode=v["mode"])


def summarise(result: dict) -> dict:
    folders, symbols = result["folders"], result["symbols"]
    out = {
        "folder_views": len(folders),
        "max_nodes": max((f["nodes"] for f in folders), default=0),
        "max_edges_total": max((f["edges_total"] for f in folders), default=0),
        "max_edges_drawn": max((f["edges_drawn"] for f in folders), default=0),
        "views_with_hidden_edges": sum(1 for f in folders if f["edges_drawn"] < f["edges_total"]),
        "median_edges_total": statistics.median([f["edges_total"] for f in folders] or [0]),
    }
    if symbols:
        out.update(
            symbol_views=len(symbols),
            symbol_max_nodes=max(s["nodes"] for s in symbols),
            symbol_max_edges_total=max(s["edges_total"] for s in symbols),
            symbol_max_edges_drawn=max(s["edges_drawn"] for s in symbols),
            symbol_views_with_hidden_edges=sum(1 for s in symbols if s["edges_drawn"] < s["edges_total"]),
        )
    return out


def markdown(info: dict, results: dict) -> str:
    lines = ["# Folder-map UI readability (before vs after)", "",
             f"Commit `{info.get('commit_sha', '?')[:7]}`. Rule: web/src/mapModel.ts `selectEdges`, budget 40, "
             "whole tiers of equal count, circular-import edges always drawn.", "",
             "Before = the old default (flat file graph, 300 most connected files). After = the view a "
             "visitor now opens, with edges drawn at rest. Hovering or selecting a node adds all of "
             "its edges; \"Show all edges\" draws every one.", ""]
    for setting in SETTINGS:
        lines += [f"## Setting: {setting}", "",
                  "| Repo | Before (nodes / edges) | After: opens as | nodes | edges total | edges drawn | "
                  "Worst folder view: nodes / edges total / drawn |",
                  "|---|---|---|---|---|---|---|"]
        for name, r in results.items():
            s = r[setting]
            b, d, sm = s["before"], s["default"], s["summary"]
            worst = max(s["folders"], key=lambda f: (f["edges_total"], f["nodes"]), default=None)
            w = (f"{worst['root']}: {worst['nodes']} / {worst['edges_total']} / {worst['edges_drawn']}"
                 if worst else "-")
            lines.append(f"| {name} | {b['nodes_drawn']} / {b['edges_drawn']}"
                         f"{' (capped from ' + str(b['flat_nodes']) + ')' if b['capped'] else ''}"
                         f" | {d['level']} at root | {d['nodes']} | {d['edges_total']} | "
                         f"{d['edges_drawn']} | {w} |")
        lines += [""]
    lines += ["## Symbol views (default setting, every non-test file)", "",
              "| Repo | Views | Most nodes | Most edges | Most drawn | Views with hidden edges |",
              "|---|---|---|---|---|---|"]
    for name, r in results.items():
        sm = r["default"]["summary"]
        if "symbol_views" in sm:
            lines.append(f"| {name} | {sm['symbol_views']} | {sm['symbol_max_nodes']} | "
                         f"{sm['symbol_max_edges_total']} | {sm['symbol_max_edges_drawn']} | "
                         f"{sm['symbol_views_with_hidden_edges']} |")
    lines += ["", "## Every folder view (default setting)", ""]
    for name, r in results.items():
        lines += [f"### {name}", "",
                  "| Folder | Files under it | Flat edges among them (before) | Nodes | Edges total | Edges drawn |",
                  "|---|---|---|---|---|---|"]
        for f in r["default"]["folders"]:
            lines.append(f"| `{f['root']}` | {f['files_under']} | {f['flat_edges_among']} | "
                         f"{f['nodes']}{' (+overflow)' if f['overflow'] else ''} | "
                         f"{f['edges_total']} | {f['edges_drawn']} |")
        lines.append("")
    return "\n".join(lines)


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
        views: list[dict] = []
        results: dict = {}
        for name, (snapshot_id, commit) in latest_snapshots(args.repos).items():
            results[name] = {"snapshot_id": snapshot_id, "commit": commit}
            for setting_name, setting in SETTINGS.items():
                results[name][setting_name] = collect(
                    name, snapshot_id, setting_name, setting,
                    with_symbols=setting_name == "default", views=views)
            print(f"{name}: collected {len(views)} views so far")
        drawn = run_rule(views)
        for name, r in results.items():
            for setting_name in SETTINGS:
                finish(r[setting_name], drawn, f"{name}|{setting_name}")
                r[setting_name]["summary"] = summarise(r[setting_name])
                s = r[setting_name]
                b, d, sm = s["before"], s["default"], s["summary"]
                print(f"{name:13} {setting_name:10} before {b['nodes_drawn']:3}n {b['edges_drawn']:4}e"
                      f" | after {d['level']:6} {d['nodes']:3}n {d['edges_total']:3}e"
                      f" drawn {d['edges_drawn']:3}"
                      f" | worst folder view {sm['max_nodes']}n {sm['max_edges_total']}e"
                      f" drawn {sm['max_edges_drawn']}"
                      + (f" | worst symbol view {sm['symbol_max_nodes']}n"
                         f" {sm['symbol_max_edges_total']}e drawn {sm['symbol_max_edges_drawn']}"
                         if "symbol_views" in sm else ""))
        name = "graph_ui_readability" + (f"-{args.label}" if args.label else "")
        saved = save_results(name, info, {"repos": results})
        md = Path(str(saved)).with_suffix(".md")
        md.write_text(markdown(info, results), encoding="utf-8")
        print(saved)
        print(md)
    finally:
        close_pool()


if __name__ == "__main__":
    main()
