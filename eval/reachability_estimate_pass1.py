"""Estimate RepoLens finding counts from GitHub code search + the git tree. No cloning.
Counts are FILES that match (the search API's total_count), outside test/docs/example paths.
"""
import json
import re
import subprocess
import sys
import time

OUT = sys.argv[1]
EXCL = "-path:test -path:tests -path:spec -path:docs -path:doc -path:example -path:examples -path:fixtures -path:vendor"

CALIBRATION = [  # RepoLens real security counts are known for these
    ("adeyosemanputra/pygoat", "py"), ("pallets/flask", "py"), ("psf/black", "py"), ("expressjs/express", "js"),
]
CANDIDATES = [
    ("ipython/ipython", "py"), ("sqlmapproject/sqlmap", "py"), ("sphinx-doc/sphinx", "py"),
    ("pytest-dev/pytest", "py"), ("OctoPrint/OctoPrint", "py"), ("mitmproxy/mitmproxy", "py"),
    ("celery/celery", "py"), ("getredash/redash", "py"), ("yt-dlp/yt-dlp", "py"), ("ranger/ranger", "py"),
    ("juice-shop/juice-shop", "js"), ("jquery/jquery", "js"), ("handlebars-lang/handlebars.js", "js"),
    ("serverless/serverless", "js"), ("NodeBB/NodeBB", "js"), ("sequelize/sequelize", "js"),
    ("shelljs/shelljs", "js"), ("knex/knex", "js"),
]
CODE = {
    "py": {"eval": "eval(", "exec": "exec(", "shell_true": "shell=True", "sql_execute": ".execute("},
    "js": {"eval": "eval(", "new_function": "new Function", "exec": "exec(", "innerHTML": "innerHTML",
           "sql_select": "SELECT"},
}
SECRET = {"password": '"password ="', "secret": '"secret ="', "api_key": '"api_key ="', "token": '"token ="'}
EXT = {"py": "extension:py", "js": "-extension:md -extension:json -extension:html -extension:txt"}


def gh(*args):
    for attempt in range(3):
        p = subprocess.run(["gh", "api", *args], capture_output=True, text=True, encoding="utf-8")
        if p.returncode == 0:
            return json.loads(p.stdout)
        msg = (p.stderr or p.stdout)[:200]
        if "rate limit" in msg.lower() or "403" in msg:
            time.sleep(65)
            continue
        return {"error": msg}
    return {"error": "gave up"}


def count(repo, term, lang):
    time.sleep(7)
    q = f"{term} repo:{repo} {EXT[lang]} {EXCL}"
    r = gh("-X", "GET", "search/code", "-f", f"q={q}", "-f", "per_page=1")
    return r.get("total_count") if "error" not in r else f"error: {r['error']}"


def tree(repo):
    meta = gh(f"repos/{repo}")
    if "error" in meta:
        return {"error": meta["error"]}
    branch = meta["default_branch"]
    head = gh(f"repos/{repo}/commits/{branch}")
    sha = head.get("sha")
    t = gh(f"repos/{repo}/git/trees/{sha}?recursive=1")
    files = [e["path"] for e in t.get("tree", []) if e["type"] == "blob"]
    is_test = re.compile(r"(^|/)(tests?|spec|__tests__|testing|fixtures?)(/|$)|(^|/)(test_[^/]*|[^/]*_test)\.py$|\.(test|spec)\.[jt]sx?$")
    py = [f for f in files if f.endswith(".py")]
    js = [f for f in files if re.search(r"\.(js|jsx|mjs|cjs|ts|tsx)$", f) and not f.endswith((".min.js", ".d.ts"))]
    return {
        "sha": sha, "license": (meta.get("license") or {}).get("spdx_id"), "archived": meta["archived"],
        "size_kb": meta["size"], "stars": meta["stargazers_count"], "truncated": t.get("truncated"),
        "files_total": len(files), "py_files": len(py), "js_ts_files": len(js),
        "py_non_test": len([f for f in py if not is_test.search(f)]),
        "js_non_test": len([f for f in js if not is_test.search(f)]),
    }


result = {}
for repo, lang in CALIBRATION + CANDIDATES:
    entry = {"lang": lang, "tree": tree(repo), "code": {}, "secrets": {}}
    for name, term in CODE[lang].items():
        entry["code"][name] = count(repo, term, lang)
    for name, term in SECRET.items():
        entry["secrets"][name] = count(repo, term, lang)
    result[repo] = entry
    json.dump(result, open(OUT, "w"), indent=1)
    print(repo, entry["tree"].get("files_total"), entry["code"], entry["secrets"], flush=True)
print("done", flush=True)
