"""Part B step 1 of the locked-run freeze: size checks of the five locked repos at their pinned
commits from GitHub tree metadata only (paths, modes and blob sizes; no file contents, no clone).

    uv run --project backend python eval/locked_tree_check.py

Uses `gh api repos/<repo>/git/trees/<sha>?recursive=1`. "Kept" applies discover's path and size
rules (skipped folders, secret files, wanted suffixes, generated JS names, symlinks, 1 MB); the
binary and minified checks need file contents, so "kept" is an upper bound. Chunks are estimated
from non-test code bytes with the ratio measured on the analysed tuning snapshots (2.0 to 2.8
non-test chunks per kB) and embedding time with this PC's measured 0.35 to 0.65 s per chunk.
"""

import json
import subprocess
from pathlib import PurePosixPath

import yaml
from runinfo import ROOT, run_info, save_results  # also puts backend/ on sys.path

CHUNKS_PER_KB = (2.0, 2.8)  # itsdangerous 2.59, PyGoat 2.79, express 2.07, flask 2.02
EMBED_S_PER_CHUNK = (0.35, 0.65)  # PyGoat 0.35, itsdangerous 0.57, express 0.65 (BASELINE-v1)
DOCS = {".md", ".rst", ".txt"}
MAX_BYTES = 20_000_000


def wanted(p: PurePosixPath) -> bool:
    from app.ingest.discover import (
        GENERATED_JS_MARKERS,
        LANGUAGES,
        SECRET_NAMES,
        SECRET_SUFFIXES,
        TEXT_SUFFIXES,
    )

    if p.name.startswith(".env") or p.name in SECRET_NAMES or p.suffix.lower() in SECRET_SUFFIXES:
        return False
    if LANGUAGES.get(p.suffix) == "javascript" and p.stem.endswith(GENERATED_JS_MARKERS):
        return False
    return p.suffix in LANGUAGES or p.suffix.lower() in TEXT_SUFFIXES


def check(repo: str, sha: str) -> dict:
    from app import config
    from app.ingest.discover import LANGUAGES, SKIP_DIRS
    from app.paths import is_test_path

    tree = json.loads(subprocess.run(
        ["gh", "api", f"repos/{repo}/git/trees/{sha}?recursive=1"],
        capture_output=True, text=True, check=True).stdout)
    blobs = [e for e in tree["tree"] if e["type"] == "blob"]
    venvs = {str(PurePosixPath(e["path"]).parent) for e in blobs
             if PurePosixPath(e["path"]).name == "pyvenv.cfg"}
    kept = []
    for e in blobs:
        p = PurePosixPath(e["path"])
        parents = [str(a) for a in p.parents if str(a) != "."]
        if any(PurePosixPath(d).name in SKIP_DIRS or d.endswith(".egg-info") or d in venvs
               for d in parents):
            continue
        if e["mode"] == "120000" or not wanted(p) or e["size"] > config.MAX_FILE_BYTES:
            continue
        kept.append(e)
    code = [e for e in kept if PurePosixPath(e["path"]).suffix in LANGUAGES]
    code_nt = [e for e in code if not is_test_path(e["path"])]
    kb = sum(e["size"] for e in code_nt) / 1000
    chunks = [round(kb * r) for r in CHUNKS_PER_KB]
    total = sum(e["size"] for e in blobs)
    return {
        "repo": repo, "commit": sha, "truncated": tree["truncated"],
        "files": len(blobs), "bytes": total,
        "submodules": sum(1 for e in tree["tree"] if e["type"] == "commit"),
        "kept_upper_bound": len(kept), "kept_bytes": sum(e["size"] for e in kept),
        "code_files": len(code), "code_nontest_files": len(code_nt),
        "code_nontest_kb": round(kb, 1),
        "doc_files": sum(1 for e in kept if PurePosixPath(e["path"]).suffix.lower() in DOCS),
        "est_chunks_nontest": chunks,
        "est_embed_s": [round(chunks[0] * EMBED_S_PER_CHUNK[0]),
                        round(chunks[1] * EMBED_S_PER_CHUNK[1])],
        "under_limits": len(kept) <= config.MAX_FILES and total <= MAX_BYTES,
    }


def main() -> None:
    from app import config

    pins = yaml.safe_load((ROOT / "eval" / "locked" / "pins.yaml").read_text(encoding="utf-8"))
    rows = [check(p["repo"], p["commit"]) for p in pins["repos"]]
    for r in rows:
        print(f"{r['repo']:<22} files {r['files']:>4}  {r['bytes'] / 1e6:5.2f} MB  kept <="
              f" {r['kept_upper_bound']:>4}  code {r['code_files']:>3} ({r['code_nontest_files']}"
              f" non-test, {r['code_nontest_kb']} kB)  chunks ~{r['est_chunks_nontest']}"
              f"  embed ~{r['est_embed_s']} s  under limits: {r['under_limits']}")
    info = run_info(llm_used=False)
    info["notes"] = "GitHub tree metadata only (no contents, no clone)"
    print("saved", save_results("locked_tree_check", info, {
        "ratios": {"chunks_per_kb": CHUNKS_PER_KB, "embed_s_per_chunk": EMBED_S_PER_CHUNK},
        "limits": {"max_files": config.MAX_FILES, "max_bytes": MAX_BYTES,
                   "max_file_bytes": config.MAX_FILE_BYTES},
        "repos": rows}))


if __name__ == "__main__":
    main()
