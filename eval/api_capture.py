"""Capture API responses from the dev DB with whatever `app` package is first on sys.path.
usage: LLM_API_KEY= python capture.py <out.json>   (cwd must contain the app package to test)

Refuses to run with an LLM key set: only graph questions are asked, but a question the router
does not take would go to the AI route and spend real money (it did once, 6 Nov)."""
import json
import sys

import os

if os.environ.get("LLM_API_KEY"):
    sys.exit("LLM_API_KEY is set; run with LLM_API_KEY= (empty) so nothing can reach the AI route.")
sys.path.insert(0, ".")
from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402

db.open_pool()
c = TestClient(app, base_url="http://localhost")
out = {}
print(__import__('app').__file__)


def _j(r):
    try:
        return r.json()
    except Exception:
        return r.text[:300]


def get(url, **params):
    r = c.get(url, params=params)
    out[url + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))] = [r.status_code, _j(r)]


with db.pool().connection() as conn:
    snaps = [r["id"] for r in conn.execute("SELECT id FROM snapshots ORDER BY id")]
    for s in snaps:
        get(f"/snapshots/{s}/graph")
        get(f"/snapshots/{s}/graph", min_confidence=0.5, exclude_tests="false")
        for lvl in ("folder",):
            get(f"/snapshots/{s}/graph", level=lvl, min_confidence=0.9)
            get(f"/snapshots/{s}/graph", level=lvl, min_confidence=0.5, exclude_tests="false")
        files = [r["path"] for r in conn.execute(
            "SELECT path FROM files WHERE snapshot_id = %s AND language IN"
            " ('python','javascript','typescript') ORDER BY id", (s,))]
        for p in files[:: max(1, len(files) // 25)]:
            get(f"/snapshots/{s}/graph", level="symbol", root=p, min_confidence=0.5,
                exclude_tests="false")
        syms = [r["id"] for r in conn.execute(
            "SELECT id FROM symbols WHERE snapshot_id = %s AND file_id IS NOT NULL ORDER BY id", (s,))]
        mods = [r["id"] for r in conn.execute(
            "SELECT id FROM symbols WHERE snapshot_id = %s AND kind = 'module' ORDER BY id", (s,))]
        pick = mods[:120] + syms[:: max(1, len(syms) // 150)]
        for sid in pick:
            for mc in (0.9, 0.0):
                get(f"/symbols/{sid}/dependents", min_confidence=mc)
                get(f"/symbols/{sid}/dependencies", min_confidence=mc)
        for p in files[:6]:
            r = c.post(f"/snapshots/{s}/ask", json={"question": f"Which files import {p}?"})
            out[f"ask {s} imports {p}"] = [r.status_code, _j(r)]
            r = c.post(f"/snapshots/{s}/ask", json={"question": f"What does {p} import?"})
            out[f"ask {s} deps {p}"] = [r.status_code, _j(r)]
json.dump(out, open(sys.argv[1], "w"), sort_keys=True)
print(len(out), "responses;", sum(1 for v in out.values() if v[0] != 200), "non-200")
