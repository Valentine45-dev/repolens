"""Compare two findings_capture.py outputs. New fields (category, in_docs, placeholder, notes,
counts.by_category / placeholders / documentation, rule.category) are additive and ignored.
Rows are matched on (rule, path, line, occurrence on that line), so a re-run that gives findings
new ids still compares row by row. Prints every row whose old fields changed, any row present
in only one file, any change in list order, and any change in /rules old fields.
    python eval/findings_capture_diff.py before.json after.json"""
import json
import sys
from collections import Counter

ROW_NEW = {"category", "in_docs", "placeholder", "template_value", "id", "file_id", "node_id"}
COUNT_NEW = {"by_category", "placeholders", "documentation", "template_values"}


def keyed(items):
    seen = Counter()
    out = {}
    for i in items:
        base = (i["rule_id"], i["path"], i["line"])
        out[(*base, seen[base])] = i
        seen[base] += 1
    return out


old, new = (json.load(open(p, encoding="utf-8")) for p in sys.argv[1:3])
changed = 0

# /rules: old fields must be equal for every rule that existed
new_rules = {r["id"]: r for r in new["/rules"]}
for r in old["/rules"]:
    n = new_rules.get(r["id"])
    if n is None or any(n[k] != v for k, v in r.items()):
        print("RULE CHANGED", r["id"])
        changed += 1
print(f"/rules: {len(old['/rules'])} before, {len(new['/rules'])} after "
      f"({len(new['/rules']) - len(old['/rules'])} added)")

for key in sorted(k for k in old if k.startswith("snapshot")):
    o, n = old[key][1], new[key][1]
    ko, kn = keyed(o["items"]), keyed(n["items"])
    for k in sorted(set(ko) | set(kn)):
        if k not in kn or k not in ko:
            print(f"{key}: ROW ONLY IN {'BEFORE' if k in ko else 'AFTER'}: {k[:3]}")
            changed += 1
            continue
        diffs = {f: (ko[k][f], kn[k][f]) for f in ko[k] if f not in ROW_NEW and ko[k][f] != kn[k][f]}
        if diffs:
            changed += 1
            print(f"{key}: {k[1]}:{k[2]} {k[0]}")
            for f, (a, b) in diffs.items():
                print(f"    {f}: {a!r} -> {b!r}")
    common = [k for k in kn if k in ko]
    order_o = [k for k in ko if k in kn]
    if order_o != common:
        print(f"{key}: LIST ORDER CHANGED")
        changed += 1
    for f in ("total",):
        if o[f] != n[f]:
            print(f"{key}: total {o[f]} -> {n[f]}")
    co, cn = o["counts"], {k: v for k, v in n["counts"].items() if k not in COUNT_NEW}
    if co != cn:
        print(f"{key}: counts {co} -> {cn}")
print("differences:", changed)
