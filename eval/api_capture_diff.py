"""Compare two api_capture.py outputs with the new edge-site fields stripped (and the ids of
external/unresolved symbols ignored: they change when edges are rebuilt).
    python eval/api_capture_diff.py old.json new.json"""
import json
import sys

NEW = {"sites", "site_count", "site_file_id", "site_path"}


def strip(x):
    if isinstance(x, dict):
        out = {k: strip(v) for k, v in x.items() if k not in NEW}
        if out.get("kind") in ("external", "unresolved"):
            for k in ("id", "node_id"):
                if k in out:
                    out[k] = None
        return out
    if isinstance(x, list):
        return [strip(i) for i in x]
    return x


old, new = (json.load(open(p)) for p in sys.argv[1:3])
bad = [k for k in old if k not in new or strip(old[k]) != strip(new[k])]
print("responses", len(old), "same keys", set(old) == set(new), "differ", len(bad))
for k in bad:
    print("DIFF", k)
