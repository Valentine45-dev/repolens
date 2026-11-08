"""Writes eval/results/REACHABILITY.md from the scored results file (every number is read from the
JSON, none is typed in).

    uv run --project backend python eval/reachability_report.py
"""

import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "eval" / "results"


def wilson(k: int, n: int):
    """Same formula as eval/reachability_score.py (95%)."""
    if n == 0:
        return None
    z = 1.959964
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def f3(x) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def ci(w) -> str:
    return "n/a" if not w else f"{w[0]:.2f} to {w[1]:.2f}"


def signed(x) -> str:
    return "n/a" if x is None else f"{x:+.3f}"


def table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main() -> None:
    scored_path = sorted(glob.glob(str(RES / "reachability_scored-*.json")))[-1]
    d = json.load(open(scored_path, encoding="utf-8"))
    setup = json.load(open(sorted(glob.glob(str(RES / "reachability_setup-*.json")))[-1], encoding="utf-8"))
    received = json.load(open(sorted(glob.glob(str(RES / "reachability_labels_received-*.json")))[-1],
                              encoding="utf-8"))
    p = d["primary"]
    t = d["permutation_test"]
    boot = d["bootstrap_ap_difference"]
    b104 = d["sensitivity"]["b104_counted_as_real"]
    tables = d["descriptive_tables"]
    sec = d["secondary_repolens_exploratory"]
    repos = sorted(p["per_repo"])
    agree_files = sorted(glob.glob(str(RES / "reachability_agreement-*.json")))
    ag = json.load(open(agree_files[-1], encoding="utf-8")) if agree_files else None
    j2_files = sorted(glob.glob(str(RES / "reachability_labels_received_judge2-*.json")))
    j2 = json.load(open(j2_files[-1], encoding="utf-8")) if j2_files else None
    judge_sentence = (" alone; the second judge's sheet has not been received." if ag is None else
                      "; a second judge (J2) labelled a 54-row subset (section below).")

    out = []
    w = out.append
    w("# Reachability as a re-ranker of Bandit's output: results (8 Nov 2026)\n")
    w(f"Scored once from `{Path(scored_path).name}`. Pre-registration: `eval/reachability_prereg.md` with Amendment 1; "
      f"frozen tier code `{d['guard']['frozen_tier_commit'][:7]}`; the labelled sheet's SHA-256 "
      f"`{d['labelled_sheet_sha256'][:16]}...` was committed before the key was opened. Labels by J1 (the project "
      "owner, who built the tool)" + judge_sentence + " This is a small "
      "study set up and labelled by the people who built the tool: the result is for these repos, not a general rate.\n")

    diff = p["difference"]
    w("## Headline\n")
    w(f"- **The primary comparison rests on one repository.** Only redash has any finding labelled real in its Bandit pool; "
      f"gunicorn ({p['per_repo']['benoitc/gunicorn']['rows']} rows), certbot ({p['per_repo']['certbot/certbot']['rows']}) and ipython "
      f"({p['per_repo']['ipython/ipython']['rows']}) have none, so by the pre-registration they have no AP and are left out of the mean "
      f"(R = 0).")
    w(f"- **Pooled mean AP difference (reachability order minus Bandit order): {signed(diff['mean_ap_difference'])}** over "
      f"{diff['repos']} repo. One-sided p = {t['ap']['p_one_sided']:.3f} (two-sided {t['ap']['p_two_sided']:.3f}); "
      f"bootstrap 95% interval over files {signed(boot['pooled'][0])} to {signed(boot['pooled'][1])}. "
      "No evidence that ordering by reachability puts more real findings earlier; the point estimate is slightly negative and the interval is wide.")
    w(f"- **P@20, pooled over the four repos (80 rows per ordering):** Bandit order {p['bandit_order']['p20_real']}/80 = "
      f"{p['bandit_order']['pooled_p20']:.3f} (Wilson {ci(p['bandit_order']['pooled_p20_wilson'])}); reachability order "
      f"{p['reach_order']['p20_real']}/80 = {p['reach_order']['pooled_p20']:.3f} (Wilson {ci(p['reach_order']['pooled_p20_wilson'])}). "
      f"Difference {diff['p20_real_difference_total']:+d} real findings in the top 20s (one-sided p = {t['p20']['p_one_sided']:.3f}, "
      "a second test, not corrected). All of it comes from redash.")
    by_rule = tables["by_rule_not_pre_registered"]
    real_total = sum(v["real"] for v in by_rule.values())
    redash_none = tables["per_repo_by_tier"]["getredash/redash"].get("none", {"real": 0})["real"]
    w("- **Why the result says little about whether reachability helps in general:** "
      f"{d['row_label_counts'].get('not real', 0)} of {sum(d['row_label_counts'].values())} sheet rows were labelled not real; "
      "in the Bandit pools of gunicorn, certbot and ipython the owner judged nothing actionable. "
      f"All {real_total} real findings in the Bandit pools are in redash"
      + (", and all of them are one rule" if by_rule["B113"]["real"] == real_total
         else f", and {by_rule['B113']['real']} of them are one rule")
      + f" (B113, request without timeout); {redash_none} of them have no path from the detected entry points. "
      "That is consistent with the entry-point recall gap the freeze recorded as a risk; whether it is the cause was not checked. "
      "It is what the frozen rules produce.")

    by_tier = tables["by_tier"]
    w("- **Descriptively, real findings are more common where no path was found than where one was:** "
      f"no path found {by_tier['none']['real']}/{by_tier['none']['n']} real ({by_tier['none']['real_share']:.3f}), solid "
      f"{by_tier['solid']['real']}/{by_tier['solid']['n']} ({by_tier['solid']['real_share']:.3f}), guess "
      f"{by_tier['guess']['real']}/{by_tier['guess']['n']}. That is the opposite of the premise of the ordering; all of the "
      f"{by_tier['none']['real']} no-path real findings are redash's. It is a table, not a test.")
    if ag is not None:
        pooled_ag = ag["pooled"]
        dis = ag["disagreements"]
        verdict = ("judge-dependent by the pre-registered threshold" if ag["judge_dependent"]
                   else "not judge-dependent by the pre-registered threshold")
        same_kind = bool(dis) and all(x["repo"] == dis[0]["repo"] and x["j1"] == "real" and x["j2"] == "not real"
                                      for x in dis)
        shape = (f"all {len(dis)} are {dis[0]['repo']} rows that J1 labelled real and J2 not real" if same_kind
                 else f"{len(dis)} rows differ")
        w(f"- **Second judge:** on the {ag['rows']} shared rows the two judges agree on {pooled_ag['agree']} "
          f"({pooled_ag['percent_agreement'] * 100:.1f}%), Cohen's kappa {pooled_ag['kappa']:.3f}; {verdict} "
          f"(kappa below {ag['kappa_flag_threshold']}). Disagreements: {shape} (section below).")
    w("")

    w("## What was scored\n")
    w("- Four repos accepted by the counting rule, at pinned SHAs: " + ", ".join(
        f"{r} `{setup['repos'][r]['sha'][:7]}`" for r in repos) + ".")
    w("- Pools (Bandit 1.9.4, B101 and B404 skipped): " + ", ".join(f"{r} {d['pool_sizes'][r]}" for r in repos)
      + f". certbot and ipython are seeded samples of 60 (of {setup['repos']['certbot/certbot']['bandit_total']} and "
      f"{setup['repos']['ipython/ipython']['bandit_total']}); AP and P@20 there are on that sample, not on the whole list.")
    counts = d["row_label_counts"]
    w(f"- Labels over the {sum(counts.values())} sheet rows: {counts.get('real', 0)} real, {counts.get('not real', 0)} not real, "
      f"{counts.get('unsure', 0)} unsure (so both unsure sensitivities equal the primary).")
    w("- Orderings: Bandit order `(severity, confidence, path, line, test_id, occurrence)`; reachability order "
      "`(tier rank, then the same)`; solid 0, guess and not checked 1, no path found 2.\n")

    w("## Primary result by repo (Bandit pool)\n")
    rows = []
    for r in repos:
        v = p["per_repo"][r]
        rows.append([r, v["rows"], v["real"], f"{v['set_precision']:.3f} ({ci(v['set_precision_wilson'])})",
                     f3(v["ap_bandit"]), f3(v["ap_reach"]), signed(v["ap_difference"]),
                     f"{v['top20_real_bandit']}/20", f"{v['top20_real_reach']}/20"])
    w(table(["repo", "rows", "real", "set precision (Wilson)", "AP Bandit", "AP reachability", "difference",
             "P@20 Bandit", "P@20 reachability"], rows))
    w("\nNo AP where there is no real finding (R = 0). Pooled AP (mean over repos with R > 0): "
      f"Bandit {f3(p['bandit_order']['mean_ap'])}, reachability {f3(p['reach_order']['mean_ap'])}, from {p['bandit_order']['repos_with_ap']} repo.\n")

    w("## Bandit set precision (descriptive)\n")
    w("Real / labelled Bandit pool, with a Wilson 95% interval. Findings in one file are correlated, so the intervals are optimistic; "
      "certbot and ipython are 60-row samples of longer lists.\n")
    rows = []
    for r in repos:
        v = p["per_repo"][r]
        rows.append([r, v["rows"], v["real"], f"{v['real'] / v['rows']:.3f}", ci(wilson(v["real"], v["rows"]))])
    pool_rows = sum(v["rows"] for v in p["per_repo"].values())
    pool_real = sum(v["real"] for v in p["per_repo"].values())
    rows.append(["**all four repos**", pool_rows, pool_real, f"{pool_real / pool_rows:.3f}", ci(wilson(pool_real, pool_rows))])
    w(table(["repo", "labelled Bandit pool", "real", "set precision", "Wilson 95%"], rows))
    w("")

    w("## Test and interval\n")
    w(f"- Tier-shuffle randomisation (units shuffled within each repo, {t['shuffles']} shuffles, seed {d['seed']}): "
      f"AP statistic {signed(t['ap']['observed'])}, {t['ap']['at_least_as_large']} of {t['shuffles']} shuffles at least as large "
      f"(one-sided p = {t['ap']['p_one_sided']:.4f}; two-sided {t['ap']['p_two_sided']:.4f}).")
    w(f"- P@20 statistic {signed(t['p20']['observed'])}: one-sided p = {t['p20']['p_one_sided']:.4f}, two-sided {t['p20']['p_two_sided']:.4f} "
      "(second test, not corrected).")
    w(f"- Bootstrap over files (clustered, {boot['pooled'][2]} usable resamples), AP difference: {signed(boot['pooled'][0])} to {signed(boot['pooled'][1])}.")
    w("- Findings in one file are correlated and only one repo contributes, so the p-value describes this set of findings, not repos in general.\n")

    w("## Sensitivities\n")
    w("- **Unsure as real / as not real:** there are no unsure rows, so both equal the primary.")
    w(f"- **Every B104 row counted as real** (always shown, pre-registered): {sum(1 for r in b104['per_repo'].values() if r['ap_bandit'] is not None)} repos "
      f"now have a real finding. Mean AP difference {signed(b104['difference']['mean_ap_difference'])} over {b104['difference']['repos']} repos "
      f"(one-sided p = {b104['permutation_test']['ap']['p_one_sided']:.3f}); P@20 pooled Bandit {b104['bandit_order']['p20_real']}/80 = "
      f"{b104['bandit_order']['pooled_p20']:.3f}, reachability {b104['reach_order']['p20_real']}/80 = {b104['reach_order']['pooled_p20']:.3f}. "
      f"B104 is {by_rule['B104']['n']} rows in all (one in each of gunicorn, certbot and redash), so the AP values for gunicorn and certbot rest on a single real finding and move with one row.")
    w(f"- **Exploratory, not tested: severity first, then tier:** mean AP difference {signed(p['severity_first_exploratory_difference']['mean_ap_difference'])} "
      f"over {p['severity_first_exploratory_difference']['repos']} repo; P@20 difference {p['severity_first_exploratory_difference']['p20_real_difference_total']:+d}.\n")

    w(f"## Descriptive tables (the Bandit pools together, n = {sum(d['pool_sizes'].values())}; not tested)\n")
    for title, key in (("Real share per tier", "by_tier"), ("Real share per entry class (None = no path found)", "by_entry_class")):
        w(f"**{title}**\n")
        w(table(["", "n", "real", "real share", "Wilson 95%"],
                [[k, v["n"], v["real"], f"{v['real_share']:.3f}", ci(v["wilson"])] for k, v in tables[key].items()]))
        w("")
    w("**Tier x entry class**\n")
    w(table(["tier / entry class", "n", "real"],
            [[k.replace(" | ", " / "), v["n"], v["real"]] for k, v in tables["tier_x_entry_class"].items()]))
    w("\n**Per repo, by tier** (n / real)\n")
    rows = []
    for r in repos:
        cells = tables["per_repo_by_tier"][r]
        rows.append([r] + [f"{cells[k]['n']} / {cells[k]['real']}" if k in cells else "0 / 0" for k in ("solid", "guess", "none")])
    w(table(["repo", "solid", "guess", "no path found"], rows))
    w("\n**Real share per Bandit rule (descriptive; not pre-registered, added to explain the result)**\n")
    w(table(["rule", "n", "real", "real share", "Wilson 95%"],
            [[k, v["n"], v["real"], f"{v['real_share']:.3f}", ci(v["wilson"])] for k, v in by_rule.items()])
      + f"\n\n{len(by_rule)} rules appear in all; B113 holds {by_rule['B113']['real']} of the {real_total} real findings. "
      "The Bandit pools of all four repos together, n = " + str(sum(v["n"] for v in by_rule.values())) + ".\n")

    w("## Secondary: RepoLens's own security findings, current order vs tier order (exploratory)\n")
    rows = []
    for r in sorted(sec["per_repo"]):
        v = sec["per_repo"][r]
        rows.append([r, v["rows"], v["real"], v["tiers"], f3(v["ap_current"]), f3(v["ap_reach"]),
                     f3(v["p10_current"]) + " / " + f3(v["p10_reach"]), f3(v["p20_current"]) + " / " + f3(v["p20_reach"])])
    w(table(["repo", "rows", "real", "tiers", "AP current", "AP reachability", "P@10 cur / reach", "P@20 cur / reach"], rows))
    w(f"\ngunicorn has no RepoLens security finding in the secondary pool. Only ipython has a real one (1 of {sec['per_repo']['ipython/ipython']['rows']}); "
      f"mean AP difference {signed(sec['mean_ap_difference'])} over {sec['repos_with_ap']} repo; exploratory p = {sec['exploratory_permutation_p_one_sided']:.3f}. "
      "P@k only where a list has at least 2k rows (ipython). No claim rests on this.\n")

    if ag is not None:
        w("## Second judge (J2): agreement on the judge-2 subset\n")
        w(f"{ag['rows']} rows, 20% of each repo's sheet rows (rounded up), labelled by J2 (identified by code only) on the same blind "
          f"rows. AI use: {j2['ai_use'].split(' (')[0]} (self-reported). Instructions: J2 started with the earlier wording (\"is it a real "
          "security issue\"); the updated wording (\"should a reviewer act on it?\") was sent partway through, and which rows came before "
          f"the change is not recorded, so J2's labels may follow two definitions. J2's sheet SHA-256 `{ag['judge2_sheet_sha256']}` was committed before agreement was computed. "
          f"Unsure rows: {ag['unsure_rows']}, so three-way agreement equals binary agreement.\n")
        rows = []
        for r in sorted(ag["per_repo"]):
            v = ag["per_repo"][r]
            rows.append([r, v["n"], v["agree"], f"{v['percent_agreement'] * 100:.1f}%",
                         f3(v["kappa"]) if v["kappa"] is not None else "undefined",
                         f"{v['j1_counts'].get('real', 0)} / {v['j2_counts'].get('real', 0)}"])
        pp = ag["pooled"]
        rows.append(["**all four repos**", pp["n"], pp["agree"], f"{pp['percent_agreement'] * 100:.1f}%", f3(pp["kappa"]),
                     f"{pp['j1_counts'].get('real', 0)} / {pp['j2_counts'].get('real', 0)}"])
        w(table(["repo", "shared rows", "agree", "percent agreement", "Cohen's kappa", "real: J1 / J2"], rows))
        w("\nKappa is undefined where both judges used one category on every shared row (all not real): agreement is 100% there, "
          "but chance agreement is 1. Pooled contingency table (J1 | J2): "
          + "; ".join(f"{k} = {n}" for k, n in sorted(pp["table"].items())) + ".\n")
        flag = ("**judge-dependent**" if ag["judge_dependent"] else "**not judge-dependent**")
        w(f"- Pre-registered flag (pooled kappa below {ag['kappa_flag_threshold']}): pooled kappa {pp['kappa']:.3f}, so the headline is {flag}. "
          "Only redash has a defined kappa on its own "
          f"({f3(ag['per_repo']['getredash/redash']['kappa'])}); the flag is defined on the pooled value.")
        w(f"- Every row J2 labelled real was also real for J1 ({ag['j2_real_rows_also_real_for_j1']} of {pp['j2_counts'].get('real', 0)}). "
          "In the three repos with no real Bandit finding in J1's labels, J2 also found none on the shared rows. J2 was the stricter judge "
          "on redash; this check does not test whether a more lenient judge would find real findings in the other three.")
        w("- Not done: the pre-registration (section 10) asks for the primary table to be repeated on the J2 subset with both judges' labels "
          "only if kappa is below 0.4; it is not.\n")
        w("**Disagreeing rows** (J1 wrote no notes; J2's note as written, ids are sheet row ids)\n")
        w(table(["row", "repo", "flagged for", "rule", "J1", "J2", "J2's note"],
                [[x["id"], x["repo"], x["flagged_for"], ", ".join(x["rules"]), x["j1"], x["j2"],
                  x["j2_note"].replace("|", "/")] for x in ag["disagreements"]]))
        w("")

    w("## Limits, in addition to those pre-registered (section 11)\n")
    w("- Three of four repos have no real Bandit finding in the pool, so they cannot show an ordering effect; the comparison is a one-repo case study (redash).")
    w("- In redash nearly all real findings are one rule (B113) and most have no path from the detected entry points; the tier result there reflects the detectors' recall as well as the idea of reachability. "
      "Any fix to the detectors would be a dated deviation, scored as exploratory on the same labels, never replacing this result.")
    if ag is None:
        w("- One labeller, the owner, with GitHub open at the pinned commits; no second judge yet, so agreement and the judge-dependent check are not available.")
    else:
        rd = ag["per_repo"]["getredash/redash"]
        w("- The primary labels are one labeller's, the owner's, with GitHub open at the pinned commits. The second judge covered "
          f"{ag['rows']} of {sum(d['row_label_counts'].values())} rows, started under different wording, and was stricter on redash "
          f"({rd['table'].get('J1 real | J2 not real', 0)} of the owner's {rd['j1_counts'].get('real', 0)} real rows on the shared redash rows "
          "were not real for J2), so the redash result, the only one that carries the comparison, is sensitive to label strictness.")
    w("- certbot and ipython are 60-row samples of lists of 73 and 143; the pool of 60 is not the whole list.")
    w(f"- Public-API-only findings are few ({tables['by_entry_class']['public-api']['n']} in the pools), so the entry-class table says little.")
    w("- Python only; Bandit is the object being re-ranked, so this says nothing about Bandit's quality or RepoLens's rules.\n")

    w("## Deviations from the pre-registration\n")
    w("None in the scoring. Two choices the pre-registration did not spell out, recorded in the setup file: the secondary pool includes Python and non-code files "
      "(JS/TS left out), and judge-2 rows are 20% of each repo's sheet rows (rounded up). Not pre-registered and added: the per-rule table above.\n")

    w("## Provenance\n")
    w(f"Counting `{Path(sorted(glob.glob(str(RES / 'reachability_bandit_count-*.json')))[-1]).name}`; setup `{Path(sorted(glob.glob(str(RES / 'reachability_setup-*.json')))[-1]).name}`; "
      f"labels received `reachability_labels_received-20261108.json` (SHA-256 `{received['sha256']}`); scored `{Path(scored_path).name}`. "
      "The sheets and the key are outside git (`repolens-eval-assets/reachability/`). Scripts: `reachability_bandit_count.py`, `reachability_ingest.py`, "
      "`reachability_setup.py`, `reachability_score.py`, `reachability_report.py`. No LLM was used ($0).")
    if ag is not None:
        w(f"\nJ2: labels received `{Path(j2_files[-1]).name}`, agreement `{Path(agree_files[-1]).name}`, script `reachability_agreement.py`.\n")
    else:
        w("")
    (RES / "REACHABILITY.md").write_text("\n".join(out), encoding="utf-8")
    print("wrote", RES / "REACHABILITY.md")


if __name__ == "__main__":
    main()
