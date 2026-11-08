"""Scoring of the reachability study, exactly as pre-registered (eval/reachability_prereg.md sections 2 to
5, 9 and Amendment 1).

    uv run --project backend --env-file .env python eval/reachability_score.py

Reads the owner's labelled sheet (J1) and the key. It refuses to run unless the labelled sheet's SHA-256 is
the one committed in eval/results/reachability_labels_received-*.json, the pre-registration is committed
and the tier code is the frozen commit. Run once; the first result counts. Writes
eval/results/reachability_scored-<time>-<sha7>.json (numbers only).

- Primary: pooled mean over repos (with R > 0) of AP(reachability order) - AP(Bandit order) on the labelled
  pool; unsure rows removed first; P@20 alongside (a repo needs 40 rows left); per repo and pooled.
- Test: tier-shuffle randomisation, units shuffled within a repo, 10,000 shuffles, random.Random(20261108).
- Bootstrap interval for the AP difference over files (clustered), 10,000 resamples.
- Sensitivity: unsure as real / as not real; every B104 row counted as real.
- Exploratory (never tested, never the headline): severity first, then tier.
- Secondary (exploratory): RepoLens's own security findings, current order vs tier order.
- Descriptive: tier shares, real share per tier and per entry class, tier x entry class.
"""

import csv
import glob
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

import reachability_guard
from runinfo import ROOT, header, run_info, save_results

SEED = 20261108
SHUFFLES = 10_000
BOOTSTRAPS = 10_000
ASSETS = Path(r"C:\projects\repolens-eval-assets\reachability")
TIER_RANK = {"solid": 0, "guess": 1, "not_checked": 1, "none": 2}
LEVEL = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "high": 0, "medium": 1, "low": 2}
Z = 1.959964


# --- small statistics ------------------------------------------------------------------------

def wilson(k: int, n: int) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + Z * Z / n
    centre = (p + Z * Z / (2 * n)) / d
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def average_precision(labels: list[int]) -> float | None:
    real = sum(labels)
    if real == 0:
        return None
    hits, total = 0, 0.0
    for i, label in enumerate(labels, 1):
        if label:
            hits += 1
            total += hits / i
    return total / real


def precision_at(labels: list[int], k: int) -> float | None:
    """Only for a list of at least 2k rows."""
    return sum(labels[:k]) / k if len(labels) >= 2 * k else None


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


# --- orderings ----------------------------------------------------------------------------------

def tail(f: dict) -> tuple:
    return (LEVEL[f["severity"]], LEVEL.get(f["confidence"], 0), f["path"].encode(), f["line"],
            f["rule"], f["occurrence"])


def bandit_key(f: dict, tier: str) -> tuple:
    return tail(f)


def reach_key(f: dict, tier: str) -> tuple:
    return (TIER_RANK[tier], *tail(f))


def severity_first_key(f: dict, tier: str) -> tuple:
    t = tail(f)
    return (t[0], TIER_RANK[tier], *t[1:])


def ordered_labels(items: list[dict], key, tiers: dict | None = None) -> list[int]:
    return [i["label"] for i in sorted(items, key=lambda f: key(f, (tiers or {}).get(id(f), f["tier"])))]


def repo_metrics(items: list[dict], tiers: dict | None = None, variants=None) -> dict:
    """AP and P@20 of every ordering for one repo's labelled pool (unsure already removed)."""
    out = {}
    for name, key in (variants or {"bandit": bandit_key, "reach": reach_key}).items():
        labels = ordered_labels(items, key, tiers)
        out[name] = {"ap": average_precision(labels), "p20": precision_at(labels, 20),
                     "top20_real": sum(labels[:20]) if len(labels) >= 40 else None}
    return out


def pooled(per_repo: dict[str, dict], name: str) -> dict:
    aps = [m[name]["ap"] for m in per_repo.values() if m[name]["ap"] is not None]
    p20 = [m[name]["top20_real"] for m in per_repo.values() if m[name]["top20_real"] is not None]
    return {"mean_ap": mean(aps), "repos_with_ap": len(aps),
            "pooled_p20": (sum(p20) / (20 * len(p20))) if p20 else None,
            "p20_repos": len(p20), "p20_real": sum(p20), "p20_n": 20 * len(p20)}


def difference(per_repo: dict[str, dict]) -> dict:
    d_ap = [m["reach"]["ap"] - m["bandit"]["ap"] for m in per_repo.values()
            if m["bandit"]["ap"] is not None]
    d_p = [m["reach"]["top20_real"] - m["bandit"]["top20_real"] for m in per_repo.values()
           if m["bandit"]["top20_real"] is not None]
    return {"mean_ap_difference": mean(d_ap), "repos": len(d_ap),
            "p20_real_difference_total": sum(d_p) if d_p else None,
            "pooled_p20_difference": (sum(d_p) / (20 * len(d_p))) if d_p else None}


# --- tests ----------------------------------------------------------------------------------

def unit_of(f: dict) -> tuple:
    return ("u", f["unit"]) if f.get("unit") is not None else ("f", id(f))


def permutation_test(pools: dict[str, list[dict]], observed: dict, variants=None) -> dict:
    """Shuffle the tier values among the units that hold at least one pool finding, within each repo;
    every finding keeps its unit's (shuffled) tier. Same shuffles for AP and P@20."""
    rng = random.Random(SEED)
    units = {}
    for repo, items in pools.items():
        by_unit: dict[tuple, str] = {}
        for f in items:
            by_unit.setdefault(unit_of(f), f["tier"])
        units[repo] = by_unit
    ge_ap = ge_ap_abs = ge_p = ge_p_abs = 0
    obs_ap, obs_p = observed["mean_ap_difference"], observed["pooled_p20_difference"]
    for _ in range(SHUFFLES):
        per_repo = {}
        for repo, items in pools.items():
            keys = list(units[repo])
            values = [units[repo][k] for k in keys]
            rng.shuffle(values)
            shuffled = dict(zip(keys, values, strict=True))
            tiers = {id(f): shuffled[unit_of(f)] for f in items}
            per_repo[repo] = repo_metrics(items, tiers)
        d = difference(per_repo)
        if obs_ap is not None and d["mean_ap_difference"] is not None:
            ge_ap += d["mean_ap_difference"] >= obs_ap - 1e-12
            ge_ap_abs += abs(d["mean_ap_difference"]) >= abs(obs_ap) - 1e-12
        if obs_p is not None and d["pooled_p20_difference"] is not None:
            ge_p += d["pooled_p20_difference"] >= obs_p - 1e-12
            ge_p_abs += abs(d["pooled_p20_difference"]) >= abs(obs_p) - 1e-12
    return {"shuffles": SHUFFLES,
            "ap": {"observed": obs_ap, "at_least_as_large": ge_ap, "p_one_sided": ge_ap / SHUFFLES,
                   "p_two_sided": ge_ap_abs / SHUFFLES},
            "p20": {"observed": obs_p, "at_least_as_large": ge_p, "p_one_sided": ge_p / SHUFFLES,
                    "p_two_sided": ge_p_abs / SHUFFLES, "note": "second test, not corrected"}}


def bootstrap(pools: dict[str, list[dict]]) -> dict:
    """Resample files (clusters) with replacement within each repo; interval of the AP difference."""
    rng = random.Random(SEED)
    clusters = {repo: _by_file(items) for repo, items in pools.items()}
    pooled_d, per_repo_d = [], defaultdict(list)
    for _ in range(BOOTSTRAPS):
        per_repo = {}
        for repo, groups in clusters.items():
            names = list(groups)
            picked = [rng.choice(names) for _ in names]
            items = [f for name in picked for f in groups[name]]
            per_repo[repo] = repo_metrics(items)
        d = difference(per_repo)
        if d["mean_ap_difference"] is not None:
            pooled_d.append(d["mean_ap_difference"])
        for repo, m in per_repo.items():
            if m["bandit"]["ap"] is not None:
                per_repo_d[repo].append(m["reach"]["ap"] - m["bandit"]["ap"])

    def interval(values: list[float]):
        if len(values) < 100:
            return None
        values = sorted(values)
        return [round(values[int(0.025 * len(values))], 4), round(values[int(0.975 * len(values)) - 1], 4),
                len(values)]
    return {"pooled": interval(pooled_d), "per_repo": {r: interval(v) for r, v in per_repo_d.items()}}


def _by_file(items: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for f in items:
        groups[f["path"]].append(f)
    return groups


# --- tables -----------------------------------------------------------------------------------

def share_table(items: list[dict], field: str) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for f in items:
        groups[str(f[field])].append(f)
    return {k: {"n": len(v), "real": sum(f["label"] for f in v),
                "real_share": round(sum(f["label"] for f in v) / len(v), 4),
                "wilson": wilson(sum(f["label"] for f in v), len(v))} for k, v in sorted(groups.items())}


def cross_table(items: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for f in items:
        groups[f"{f['tier']} | {f['entry_class']}"].append(f)
    return {k: {"n": len(v), "real": sum(f["label"] for f in v)} for k, v in sorted(groups.items())}


# --- main ---------------------------------------------------------------------------------------

def load_labels(received: dict) -> dict[str, str]:
    path = ASSETS / "sheet-labelled.csv"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != received["sha256"]:
        raise SystemExit("The labelled sheet is not the one whose hash was committed.")
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    return {r[0]: r[6].strip().lower() for r in rows[1:]}


def finalise(findings: list[dict], labels: dict[str, str], unsure_as: str | None,
             b104_real: bool = False) -> tuple[list[dict], int]:
    """Attach 0/1 labels; remove unsure rows unless `unsure_as` says how to count them."""
    out, unsure = [], 0
    for f in findings:
        label = labels[f["row"]]
        if label == "unsure":
            unsure += 1
            if unsure_as is None:
                continue
            value = 1 if unsure_as == "real" else 0
        elif label in ("real", "not real"):
            value = 1 if label == "real" else 0
        else:
            raise SystemExit(f"unexpected label {label!r}")
        if b104_real and f.get("rule") == "B104":
            value = 1
        out.append({**f, "label": value})
    return out, unsure


def score_bandit(pools_raw: dict[str, list[dict]], labels, unsure_as=None, b104_real=False,
                 with_tests=False) -> dict:
    pools, unsure = {}, 0
    for repo, items in pools_raw.items():
        pools[repo], u = finalise(items, labels, unsure_as, b104_real)
        unsure += u
    per_repo = {repo: repo_metrics(items, variants={
        "bandit": bandit_key, "reach": reach_key, "severity_first": severity_first_key})
        for repo, items in pools.items()}
    result = {"unsure_rows": unsure, "per_repo": {}, "rows_left": {r: len(i) for r, i in pools.items()}}
    for repo, items in pools.items():
        m = per_repo[repo]
        real = sum(f["label"] for f in items)
        result["per_repo"][repo] = {
            "rows": len(items), "real": real, "not_real": len(items) - real,
            "set_precision": round(real / len(items), 4) if items else None,
            "set_precision_wilson": wilson(real, len(items)),
            "ap_bandit": m["bandit"]["ap"], "ap_reach": m["reach"]["ap"],
            "ap_difference": (m["reach"]["ap"] - m["bandit"]["ap"]) if m["bandit"]["ap"] is not None else None,
            "ap_severity_first_exploratory": m["severity_first"]["ap"],
            "p20_bandit": m["bandit"]["p20"], "p20_reach": m["reach"]["p20"],
            "p20_severity_first_exploratory": m["severity_first"]["p20"],
            "top20_real_bandit": m["bandit"]["top20_real"], "top20_real_reach": m["reach"]["top20_real"],
            "p20_wilson_bandit": wilson(m["bandit"]["top20_real"], 20) if m["bandit"]["top20_real"] is not None else None,
            "p20_wilson_reach": wilson(m["reach"]["top20_real"], 20) if m["reach"]["top20_real"] is not None else None,
            "note": "no real findings in the pool: no AP, left out of the means" if real == 0 else None,
        }
    two = {r: {"bandit": m["bandit"], "reach": m["reach"]} for r, m in per_repo.items()}
    result["bandit_order"] = pooled(two, "bandit")
    result["reach_order"] = pooled(two, "reach")
    result["difference"] = difference(two)
    sf = {r: {"bandit": m["bandit"], "reach": m["severity_first"]} for r, m in per_repo.items()}
    result["severity_first_exploratory_difference"] = difference(sf)
    p_b = result["bandit_order"]
    p_r = result["reach_order"]
    for tag, p in (("bandit", p_b), ("reach", p_r)):
        p["pooled_p20_wilson"] = wilson(p["p20_real"], p["p20_n"]) if p["p20_n"] else None
    result["_pools"] = pools
    return result


def score_repolens(pools_raw: dict[str, list[dict]], labels) -> dict:
    """Current order (severity, path, line, id; placeholders are not in the pool) against the tier order."""
    out = {"per_repo": {}}
    pools = {}
    for repo, items in pools_raw.items():
        pools[repo], _ = finalise(items, labels, None)

    def cur(f, tier):
        return (LEVEL[f["severity"]], f["path"].encode(), f["line"], f["finding_id"])

    def reach(f, tier):
        return (TIER_RANK[tier], *cur(f, tier))

    for repo, items in pools.items():
        labels_cur, labels_reach = ordered_labels(items, cur), ordered_labels(items, reach)
        real = sum(labels_cur)
        entry = {"rows": len(items), "real": real, "tiers": dict(Counter(f["tier"] for f in items)),
                 "set_precision": round(real / len(items), 4) if items else None,
                 "set_precision_wilson": wilson(real, len(items)),
                 "ap_current": average_precision(labels_cur), "ap_reach": average_precision(labels_reach)}
        for k in (10, 20):
            entry[f"p{k}_current"] = precision_at(labels_cur, k)
            entry[f"p{k}_reach"] = precision_at(labels_reach, k)
        out["per_repo"][repo] = entry
    diffs = [e["ap_reach"] - e["ap_current"] for e in out["per_repo"].values() if e["ap_current"] is not None]
    out["mean_ap_difference"] = mean(diffs)
    out["repos_with_ap"] = len(diffs)
    # exploratory tier-shuffle test on the pooled set, same procedure
    rng = random.Random(SEED)
    units = {r: {} for r in pools}
    for repo, items in pools.items():
        for f in items:
            units[repo].setdefault(unit_of(f), f["tier"])
    ge = 0
    for _ in range(SHUFFLES):
        d = []
        for repo, items in pools.items():
            keys = list(units[repo])
            values = [units[repo][k] for k in keys]
            rng.shuffle(values)
            shuffled = dict(zip(keys, values, strict=True))
            lc = ordered_labels(items, cur)
            lr = ordered_labels(items, reach, {id(f): shuffled[unit_of(f)] for f in items})
            if average_precision(lc) is not None:
                d.append(average_precision(lr) - average_precision(lc))
        if d and out["mean_ap_difference"] is not None:
            ge += mean(d) >= out["mean_ap_difference"] - 1e-12
    out["exploratory_permutation_p_one_sided"] = ge / SHUFFLES
    out["note"] = "exploratory; short lists; no claim rests on it"
    return out


def main() -> None:
    facts = reachability_guard.check()
    received = json.load(open(sorted(glob.glob(str(ROOT / "eval" / "results" /
                                                  "reachability_labels_received-*.json")))[-1], encoding="utf-8"))
    labels = load_labels(received)
    key = json.load(open(ASSETS / "key.json", encoding="utf-8"))
    row_label = {r["id"]: labels[r["id"]] for r in key["rows"]}
    bandit_raw: dict[str, list[dict]] = defaultdict(list)
    repolens_raw: dict[str, list[dict]] = defaultdict(list)
    for row in key["rows"]:
        for f in row["findings"]:
            item = {**f, "row": row["id"]}
            (bandit_raw if f["tool"] == "bandit" else repolens_raw)[row["repo"]].append(item)
    repos = sorted(bandit_raw)

    primary = score_bandit(bandit_raw, labels)
    pools = primary.pop("_pools")
    test = permutation_test(pools, primary["difference"])
    boot = bootstrap(pools)

    as_real = score_bandit(bandit_raw, labels, unsure_as="real")
    as_not = score_bandit(bandit_raw, labels, unsure_as="not real")
    b104 = score_bandit(bandit_raw, labels, b104_real=True)
    b104_pools = b104.pop("_pools")
    b104_test = permutation_test(b104_pools, b104["difference"])
    for s in (as_real, as_not):
        s.pop("_pools")

    all_items = [f for items in pools.values() for f in items]
    tables = {
        "by_tier": share_table(all_items, "tier"),
        "by_entry_class": share_table(all_items, "entry_class"),
        "tier_x_entry_class": cross_table(all_items),
        "by_rule_not_pre_registered": share_table(all_items, "rule"),
        "per_repo_by_tier": {r: share_table(pools[r], "tier") for r in repos},
        "per_repo_by_entry_class": {r: share_table(pools[r], "entry_class") for r in repos},
    }
    secondary = score_repolens(repolens_raw, labels)

    results = {
        "guard": facts, "labelled_sheet_sha256": received["sha256"], "judge": "J1", "second_judge": "not received",
        "seed": SEED, "shuffles": SHUFFLES, "bootstraps": BOOTSTRAPS,
        "pool_sizes": {r: len(pools[r]) for r in repos},
        "primary": primary, "permutation_test": test, "bootstrap_ap_difference": boot,
        "sensitivity": {
            "unsure_as_real": {"unsure_rows": as_real["unsure_rows"], "difference": as_real["difference"]},
            "unsure_as_not_real": {"unsure_rows": as_not["unsure_rows"], "difference": as_not["difference"]},
            "b104_counted_as_real": {"difference": b104["difference"], "per_repo": b104["per_repo"],
                                     "bandit_order": b104["bandit_order"], "reach_order": b104["reach_order"],
                                     "permutation_test": b104_test},
        },
        "descriptive_tables": tables,
        "secondary_repolens_exploratory": secondary,
        "row_label_counts": dict(Counter(row_label.values())),
    }
    info = run_info(llm_used=False)
    print(header(info))
    path = save_results("reachability_scored", info, results)
    print("saved", path)
    d, t = primary["difference"], test
    print("primary: mean AP difference", d["mean_ap_difference"], "over", d["repos"], "repos;",
          "p one-sided", t["ap"]["p_one_sided"], "two-sided", t["ap"]["p_two_sided"])
    print("P@20 pooled bandit", primary["bandit_order"]["pooled_p20"], "reach", primary["reach_order"]["pooled_p20"])


if __name__ == "__main__":
    main()
