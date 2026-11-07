"""Capture /rules and every /snapshots/{id}/findings page (the whole list, in API order) from the
dev DB, for a before/after comparison of the findings API. No LLM is involved.
usage: python eval/findings_capture.py <out.json>   (cwd = backend/)"""
import json
import sys

sys.path.insert(0, ".")
from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402

db.open_pool()
c = TestClient(app, base_url="http://localhost")
out = {"/rules": c.get("/rules").json()}
with db.pool().connection() as conn:
    snaps = [r["id"] for r in conn.execute("SELECT id FROM snapshots ORDER BY id")]
for s in snaps:
    first = c.get(f"/snapshots/{s}/findings", params={"limit": 200})
    if first.status_code != 200:
        out[f"snapshot {s}"] = [first.status_code, first.json()]
        continue
    page = first.json()
    items = list(page["items"])
    while len(items) < page["total"]:
        nxt = c.get(f"/snapshots/{s}/findings", params={"limit": 200, "offset": len(items)}).json()
        items += nxt["items"]
    page["items"] = items
    out[f"snapshot {s}"] = [200, page]
json.dump(out, open(sys.argv[1], "w"), sort_keys=True, indent=1)
print(len(snaps), "snapshots;", sum(len(v[1]["items"]) for k, v in out.items() if k != "/rules" and v[0] == 200), "findings")
