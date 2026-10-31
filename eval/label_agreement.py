"""Compare the new blind PyGoat labels with v1's labels on the findings both samples contain.

    uv run --project backend python eval/label_agreement.py

This is agreement between two AI-assisted labellings (v1: Claude-proposed labels confirmed by the owner; now: AI-drafted labels reviewed and finalised by the owner), not same-person consistency and not independent agreement. An independent human second judge is still needed (planned for v2 phase 3).
v1's labels were proposed by Claude and confirmed by the owner on 28 Oct; the new ones were drafted
by an AI session from the sheet and the rule and reviewed by the owner. The owner had seen the
shared findings before, so the blinding hid the tool, not the findings. Findings are matched on (tool, path, line, rule).
"""

import glob
import json

import yaml
from runinfo import RESULTS, ROOT, run_info, save_results


def main() -> None:
    old_samples = json.loads((RESULTS / "realworld_precision-20261028T101058Z-986f0b6.json")
                             .read_text(encoding="utf-8"))["samples"]
    old_labels = yaml.safe_load((ROOT / "eval" / "labels" / "pygoat-46fef96.yaml")
                                .read_text(encoding="utf-8"))
    new = json.loads(open(sorted(glob.glob(str(RESULTS / "realworld_precision_blind_scored-*.json")))[-1],
                          encoding="utf-8").read())
    shared, only_old, disagree = 0, [], []
    for tool, sample in old_samples.items():
        new_by_key = {(f["path"], f["line"], f["rule"]): f for f in new["tools"][tool]["findings"]}
        matched = set()
        for i, f in enumerate(sample, 1):
            key = (f["path"], f["line"], f["rule"])
            old = "real" if old_labels[tool][i]["label"] == "real" else "not real"
            if key not in new_by_key:
                only_old.append({"tool": tool, "v1_index": i, "path": f["path"], "line": f["line"],
                                 "rule": f["rule"], "v1_label": old})
                continue
            matched.add(key)
            shared += 1
            n = new_by_key[key]
            if n["label"] != old:
                disagree.append({"tool": tool, "path": f["path"], "line": f["line"],
                                 "rule": f["rule"], "v1_label": old, "new_label": n["label"],
                                 "row": n["id"], "v1_reason": old_labels[tool][i]["reason"]})
        only_new = [k for k in new_by_key if k not in matched]
        print(f"{tool}: {len(matched)} shared, only in new sample: {len(only_new)}")
    agree = shared - len(disagree)
    print(f"shared findings {shared}: same label {agree}, different {len(disagree)}")
    for d in disagree:
        print("DIFF", d)
    for o in only_old:
        print("only in v1 sample:", o)
    out = {"shared": shared, "agree": agree, "disagreements": disagree,
           "only_in_v1_sample": only_old,
           "reading": "agreement between two AI-assisted labellings, not same-person consistency and not independent agreement; an independent human second judge is still needed (planned for v2 phase 3)"}
    print("saved", save_results("realworld_label_agreement", run_info(llm_used=False), out))


if __name__ == "__main__":
    main()
