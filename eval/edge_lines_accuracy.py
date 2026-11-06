"""Check the line of every import/call site against the source text. Parse only; reads files as data.

v2 step 6a (source lines on edges). Needs the dev DB (itsdangerous = snapshot 1, express = 3) and a
checkout of sindresorhus/ky @ 3541888 (path as argument):
    cd backend; uv run --env-file ../.env python -I ../eval/edge_lines_accuracy.py <ky checkout>
Import check: the statement starting at the reported line contains the specifier. Call check: the
callee name appears on the reported line (cannot catch a same-name call on another line)."""
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, ".")
from app import db  # noqa: E402
from app.ingest.parse import parse_python  # noqa: E402
from app.ingest.parse_js import parse_js  # noqa: E402
from app.ingest.resolve import JsModules, PythonModules, resolve_js, resolve_python  # noqa: E402

CHECKED = {
    "itsdangerous": ["src/itsdangerous/__init__.py", "src/itsdangerous/url_safe.py",
                     "tests/test_itsdangerous/test_timed.py"],
    "express": ["index.js"] + [f"lib/{n}.js" for n in
                               ("application", "request", "response", "utils", "view", "express")],
    "ky": ["source/index.ts", "source/core/Ky.ts", "source/utils/merge.ts",
           "source/utils/options.ts", "source/errors/HTTPError.ts"],
}
SUFFIX = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
NEW_STMT = re.compile(r"^\s*(import|export|const|let|var|function|class|def|from)\b")


def load(name):
    if name == "ky":
        root = Path(sys.argv[1])
        return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8", errors="replace")
                for p in root.rglob("*") if p.suffix in SUFFIX and "node_modules" not in p.parts
                and ".git" not in p.parts}
    snap = {"itsdangerous": 1, "express": 3}[name]
    db.open_pool()
    with db.pool().connection() as conn:
        rows = conn.execute("SELECT path, content FROM files WHERE snapshot_id = %s AND language IN"
                            " ('python','javascript','typescript')", (snap,)).fetchall()
        tsc = conn.execute("SELECT content FROM files WHERE snapshot_id = %s AND path = 'tsconfig.json'",
                           (snap,)).fetchone()
    return {r["path"]: r["content"] for r in rows}, (tsc["content"] if tsc else None)


def import_ok(lines, path, imp):
    """The statement starting at imp.line contains the specifier literal."""
    i = imp.line - 1
    if i >= len(lines):
        return False
    window = lines[i:i + 40]
    spec = imp.specifier
    if path.endswith(".py"):
        text, depth = "", 0
        for ln in window:
            text += ln + "\n"
            depth += ln.count("(") - ln.count(")")
            if depth <= 0 and not ln.rstrip().endswith("\\"):
                break
        first = window[0].lstrip()
        return first.startswith(("import ", "from ")) and spec in text
    for k, ln in enumerate(window):
        if k and NEW_STMT.match(ln):
            return False
        if any(q + spec + q in ln for q in ("'", '"', "`")):
            return True
    return False


def main():
    summary = []
    for name, targets in CHECKED.items():
        loaded = load(name)
        files, tsconfig = loaded if isinstance(loaded, tuple) else (loaded, None)
        if name == "ky":
            tsconfig = files.get("tsconfig.json") if "tsconfig.json" in files else None
        parsed = {p: (parse_python(p, s) if p.endswith(".py") else parse_js(p, s))
                  for p, s in files.items()}
        py = PythonModules([p for p in files if p.endswith(".py")])
        js = JsModules([p for p in files if not p.endswith(".py")], tsconfig)
        edges = defaultdict(set)  # (path, target) -> lines
        ok = bad = 0
        misses = []
        for path in targets:
            if path not in parsed:
                print("MISSING FILE", name, path)
                continue
            lines = files[path].split("\n")
            for imp in parsed[path].imports:
                ts = resolve_python(path, imp, py) if path.endswith(".py") else resolve_js(path, imp, js)
                if imp.specifier and ts is not None:
                    for t in ts:
                        if t.kind == "internal" and t.key == path:
                            continue
                        edges[(path, t)].add(imp.line)
                good = import_ok(lines, path, imp)
                ok += good
                bad += not good
                if not good:
                    misses.append((path, imp.line, imp.specifier, lines[imp.line - 1][:80] if imp.line <= len(lines) else ""))
        # edges counted as (file, target) with their lines; every line of an edge must be ok
        per_edge_ok = 0
        for (path, t), lns in edges.items():
            lines = files[path].split("\n")
            imps = [i for i in parsed[path].imports if i.line in lns]
            per_edge_ok += all(import_ok(lines, path, i) for i in imps)
        # all call sites in the repo: does the callee name appear on the reported line?
        calls = cok = 0
        cmiss = []
        for path, pf in parsed.items():
            lines = files[path].split("\n")
            for c in pf.calls:
                calls += 1
                ln = lines[c.line - 1] if c.line <= len(lines) else ""
                if c.name in ln:
                    cok += 1
                else:
                    cmiss.append((path, c.line, c.name, ln.strip()[:80]))
        print(f"{name}: import statements checked {ok + bad} -> {ok} correct, {bad} not;"
              f" edges (file,target) in the checked files {len(edges)}, all lines correct: {per_edge_ok};"
              f" call sites in repo {calls}, name on reported line {cok}")
        for m in misses[:10]:
            print("  import miss", m)
        for m in cmiss[:10]:
            print("  call miss", m)
        summary.append((name, len(edges), per_edge_ok, calls, cok))
    print(summary)


main()
