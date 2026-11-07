"""Second pass: strict-ish occurrence estimates from code-search text-match fragments. No cloning.
For each query we page through the matching files (non-test paths) and apply a regex close to the
RepoLens rule to the returned fragment text. Each fragment is only the lines around a match, so a
file with many hits may show only some: the totals are lower bounds on occurrences, per rule family.
"""
import json
import re
import subprocess
import sys
import time

OUT = sys.argv[1]
REPOS = [r.split(":") for r in sys.argv[2:]]  # owner/name:lang
EXCL = "-path:test -path:tests -path:spec -path:docs -path:doc -path:example -path:examples -path:fixtures -path:vendor"
EXT = {"py": "extension:py", "js": "-extension:md -extension:json -extension:html -extension:txt"}

SECRET_RE = re.compile(
    r"""(?i)\b\w*(password|passwd|secret|api_?key|token|private_?key)\w*\s*[:=]\s*[uUbBrR]?["'`][^"'`\s]{6,}["'`]""")
RULES = {
    "py": {
        "py_eval_exec": ("eval exec", re.compile(r"(?<![\w.])(eval|exec)\s*\(")),
        "py_subprocess_shell": ("shell True subprocess", re.compile(r"shell\s*=\s*True")),
        "py_sql_string": ("execute SELECT", re.compile(
            r"""execute\w*\(\s*(f["']|["'][^"']*["']\s*(%|\+)|[^)]*\.format\()""")),
        "secret_assign": ("password secret token key", SECRET_RE),
    },
    "js": {
        "js_eval": ("eval", re.compile(r"(?<![\w.$])eval\s*\(")),
        "js_new_function": ("Function", re.compile(r"new\s+Function\s*\(")),
        "js_child_process": ("child_process exec", re.compile(r"(?<![\w.$])exec(Sync)?\s*\(\s*[^\s\"'`)]")),
        "js_innerhtml": ("innerHTML", re.compile(r"\.(inner|outer)HTML\s*=\s*[^\s\"'`;]")),
        "js_sql_string": ("SELECT", re.compile(
            r"""["'`](SELECT|INSERT|UPDATE|DELETE)\b[^"'`]*["'`]\s*\+|`(SELECT|INSERT|UPDATE|DELETE)\b[^`]*\$\{""")),
        "secret_assign": ("password secret token key", SECRET_RE),
    },
}


def search(repo, terms, lang, page):
    time.sleep(7)
    q = f"{terms} repo:{repo} {EXT[lang]} {EXCL}"
    for attempt in range(3):
        p = subprocess.run(
            ["gh", "api", "-X", "GET", "search/code", "-H", "Accept: application/vnd.github.text-match+json",
             "-f", f"q={q}", "-f", "per_page=100", "-f", f"page={page}"],
            capture_output=True, text=True, encoding="utf-8")
        if p.returncode == 0:
            return json.loads(p.stdout)
        if "rate limit" in (p.stderr + p.stdout).lower() or "403" in p.stderr:
            time.sleep(65)
            continue
        return {"error": (p.stderr or p.stdout)[:200]}
    return {"error": "gave up"}


result = {}
for repo, lang in REPOS:
    entry = {}
    for name, (terms, rx) in RULES[lang].items():
        files_total = None
        hits = 0
        files_hit = set()
        page = 1
        while page <= 3:  # at most 300 files per query
            r = search(repo, terms, lang, page)
            if "error" in r:
                entry[name] = {"error": r["error"]}
                break
            files_total = r["total_count"]
            for item in r["items"]:
                n = 0
                for tm in item.get("text_matches", []):
                    n += len(rx.findall(tm.get("fragment", "")))
                if n:
                    hits += n
                    files_hit.add(item["path"])
            if len(r["items"]) < 100 or page * 100 >= files_total:
                break
            page += 1
        else:
            pass
        if name not in entry:
            entry[name] = {"files_returned_by_search": files_total, "files_with_regex_hit": len(files_hit),
                           "occurrences_in_fragments": hits}
    result[repo] = entry
    json.dump(result, open(OUT, "w"), indent=1)
    print(repo, {k: (v.get("files_with_regex_hit"), v.get("occurrences_in_fragments")) for k, v in entry.items()},
          flush=True)
print("done", flush=True)
