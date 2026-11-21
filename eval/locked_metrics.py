"""Scoring rules for the held-out ("locked") evaluation. Pure functions: no database, no LLM.

FROZEN before the locked run: eval/locked/scorer.sha256 holds this file's hash, and a locked run
refuses to start if it differs. The rules implement docs/V2-EVAL-DESIGN-metrics.md (§5, §6) and
the decisions recorded at its end. In short:

Question file (schema 1): `questions:` list, each with id, set (tuning|locked), repo (owner/name),
commit (40-char sha), question, type (code_how|locate|purpose|graph|unanswerable|false_premise),
expected [{path, start, end, source: code|doc}], expected_files_with_tests and
expected_files_without_tests (graph only), premise_truth (unanswerable/false_premise only),
author, written_from, labeller, notes (optional). Locked files: author is W1, W2 or W3.

Retrieval (code_how, locate, purpose only): a hit is any chunk SENT in that configuration's
context (after the token budget) on the same path whose lines overlap an expected range
(inclusive ranges: a.start <= b.end and b.start <= a.end). code_hit uses `source: code` ranges,
headline over code_how + locate; doc_hit uses `source: doc` ranges, over the three types, for the
questions that have one. A question with no range of that source is not in that denominator.
Paired comparisons: wins/losses and an exact two-sided McNemar (sign) test.

Graph questions: routed_to = the route the live Ask took. Returned file set = the distinct paths
of the graph answer's results (packages and unresolved imports have no path and are left out;
an ambiguous answer returns nothing); for an AI answer, the paths of its validated citations.
Compared with expected_files_with_tests (the default graph answer lists test files too).
Exact match, precision |R∩E|/|R|, recall |R∩E|/|E|; an empty denominator gives 1.0 when both
sets are empty and 0.0 otherwise. Routing rate is reported separately.

Q&A:
- answered_correct_file (code_how, locate, purpose): the AI route answered and a validated
  citation is on an expected path (any source). A graph-routed answer has no citations: false.
- citation_validity: share of AI answers (status answered or unverified: text the LLM wrote)
  with no dropped citation; citation level too.
- cited_sentence_rate: eval/score_claims.py's frozen splitting rules (31 Oct), over AI answers.
- unanswerable_ok (unanswerable, false_premise): automatic PASS = AI route, the "could not find"
  sentence and zero citations. Automatic FAIL = no answer (any status other than answered /
  unverified). Everything else waits for a human: PASS when the judge says it rejects the
  premise (or says it could not find it) and that no citation supports a false claim.
- faithful_human: the judge's yes / partly / no per AI answer, from the blind sheet.
"""

import math
import re
import statistics
from collections import Counter

TYPES = ("code_how", "locate", "purpose", "graph", "unanswerable", "false_premise")
RETRIEVAL_TYPES = ("code_how", "locate", "purpose")
HEADLINE_TYPES = ("code_how", "locate")
PREMISE_TYPES = ("unanswerable", "false_premise")
WRITERS = ("W1", "W2", "W3")
SOURCES = ("code", "doc")
# The product's sentence (app/qa/prompt.py COULD_NOT_FIND), without the full stop.
COULD_NOT_FIND = "i could not find this in the provided code"
ANSWERED = ("answered", "unverified")
PASS, FAIL, PENDING = "pass", "fail", "pending"
FAITHFUL = ("yes", "partly", "no")
SHA = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


# ---- question file -------------------------------------------------------------------------

def validate_questions(data: dict) -> list[str]:
    """Every problem with a question file; empty means it is accepted."""
    errors: list[str] = []
    if not isinstance(data, dict) or data.get("schema") != 1:
        return ["top level must be a mapping with `schema: 1` and `questions:`"]
    qs = data.get("questions")
    if not isinstance(qs, list) or not qs:
        return ["`questions` must be a non-empty list"]
    ids: Counter = Counter()
    sets, commits = set(), {}
    for n, q in enumerate(qs, 1):
        where = f"question {n} ({q.get('id', '?') if isinstance(q, dict) else '?'})"
        if not isinstance(q, dict):
            errors.append(f"{where}: not a mapping")
            continue
        for key in ("id", "set", "repo", "commit", "question", "type", "author", "written_from",
                    "labeller"):
            if key not in q or q[key] in (None, ""):
                errors.append(f"{where}: missing {key}")
        ids[str(q.get("id"))] += 1
        sets.add(q.get("set"))
        if q.get("set") not in ("tuning", "locked"):
            errors.append(f"{where}: set must be tuning or locked")
        if not REPO.match(str(q.get("repo", ""))):
            errors.append(f"{where}: repo must be owner/name")
        if not SHA.match(str(q.get("commit", ""))):
            errors.append(f"{where}: commit must be a 40-character lower-case sha")
        elif q.get("repo"):
            if commits.setdefault(q["repo"], q["commit"]) != q["commit"]:
                errors.append(f"{where}: {q['repo']} has two commits in this file")
        if q.get("set") == "locked" and q.get("author") not in WRITERS:
            errors.append(f"{where}: author must be W1, W2 or W3 in a locked file")
        kind = q.get("type")
        if kind not in TYPES:
            errors.append(f"{where}: type must be one of {', '.join(TYPES)}")
            continue
        expected = q.get("expected") or []
        if not isinstance(expected, list):
            errors.append(f"{where}: expected must be a list")
            expected = []
        for r in expected:
            errors += [f"{where}: {e}" for e in _range_errors(r)]
        if kind in RETRIEVAL_TYPES and not expected:
            errors.append(f"{where}: {kind} needs at least one expected range")
        if kind not in RETRIEVAL_TYPES and expected:
            errors.append(f"{where}: {kind} takes no expected ranges")
        has_lists = [k in q for k in ("expected_files_with_tests", "expected_files_without_tests")]
        if kind == "graph":
            for key in ("expected_files_with_tests", "expected_files_without_tests"):
                value = q.get(key)
                if not isinstance(value, list) or not all(_good_path(p) for p in value):
                    errors.append(f"{where}: {key} must be a list of repo-relative paths")
        elif any(has_lists):
            errors.append(f"{where}: only graph questions take expected_files_* lists")
        if kind in PREMISE_TYPES:
            if not str(q.get("premise_truth") or "").strip():
                errors.append(f"{where}: {kind} needs premise_truth")
        elif "premise_truth" in q:
            errors.append(f"{where}: only unanswerable/false_premise take premise_truth")
    errors += [f"id {i!r} appears {c} times" for i, c in ids.items() if c > 1]
    if len(sets) > 1:
        errors.append("all questions in one file must have the same set")
    return errors


def _good_path(p) -> bool:
    return (isinstance(p, str) and p != "" and not p.startswith(("/", "./")) and "\\" not in p
            and ".." not in p.split("/"))


def _range_errors(r) -> list[str]:
    if not isinstance(r, dict):
        return ["expected entry is not a mapping"]
    out = []
    if not _good_path(r.get("path")):
        out.append(f"bad path {r.get('path')!r}")
    s, e = r.get("start"), r.get("end")
    if not (isinstance(s, int) and isinstance(e, int) and not isinstance(s, bool)
            and 1 <= s <= e):
        out.append(f"{r.get('path')}: start/end must be integers with 1 <= start <= end")
    if r.get("source") not in SOURCES:
        out.append(f"{r.get('path')}: source must be code or doc")
    return out


# ---- retrieval -----------------------------------------------------------------------------

def overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start <= b_end and b_start <= a_end


def range_hit(sent: list[dict], expected: list[dict], source: str) -> bool | None:
    """sent: [{path, start, end}]. None when the question has no range of this source."""
    wanted = [e for e in expected if e["source"] == source]
    if not wanted:
        return None
    return any(s["path"] == e["path"] and overlaps(s["start"], s["end"], e["start"], e["end"])
               for s in sent for e in wanted)


def mcnemar_exact(wins: int, losses: int) -> float:
    """Two-sided exact sign test on the discordant pairs; 1.0 when there are none."""
    n = wins + losses
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(wins, losses) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def paired(hits_x: dict, hits_y: dict) -> dict:
    """Per question id: X hit and Y missed = win for X. Only ids scored in both."""
    ids = sorted(i for i in hits_x if i in hits_y)
    wins = sum(1 for i in ids if hits_x[i] and not hits_y[i])
    losses = sum(1 for i in ids if hits_y[i] and not hits_x[i])
    return {"questions": len(ids), "wins": wins, "losses": losses,
            "p_mcnemar_exact": round(mcnemar_exact(wins, losses), 4)}


# ---- graph ---------------------------------------------------------------------------------

def returned_files(rec: dict) -> set[str]:
    if rec["route"] == "graph":
        if rec.get("status") != "answered":
            return set()  # ambiguous: candidates are not an answer
        return {p for p in rec.get("graph_paths", []) if p}
    return {c.rsplit(":", 1)[0] for c in rec.get("citations", [])}


def set_scores(returned: set, expected: set) -> dict:
    both = len(returned & expected)

    def ratio(den: set) -> float:
        if den:
            return both / len(den)
        return 1.0 if not returned and not expected else 0.0

    return {"exact": returned == expected, "precision": ratio(returned),
            "recall": ratio(expected)}


# ---- Q&A -----------------------------------------------------------------------------------

def cited_paths(rec: dict) -> set[str]:
    return {c.rsplit(":", 1)[0] for c in rec.get("citations", [])}


def answered_correct_file(q: dict, rec: dict) -> bool:
    return rec["route"] == "ai" and bool(cited_paths(rec) & {e["path"] for e in q["expected"]})


def says_could_not_find(answer: str) -> bool:
    return COULD_NOT_FIND in " ".join(answer.lower().split())


def unanswerable_auto(rec: dict) -> str:
    if rec["route"] == "ai" and rec["status"] not in ANSWERED:
        return FAIL
    if rec["route"] == "ai" and says_could_not_find(rec["answer"]) and not rec["citations"]:
        return PASS
    return PENDING


def unanswerable_final(rec: dict, judgment: dict | None) -> str:
    auto = unanswerable_auto(rec)
    if auto != PENDING or not judgment:
        return auto
    rejects, false_cited = judgment.get("rejects_premise"), judgment.get("false_claim_cited")
    if rejects not in ("yes", "no") or false_cited not in ("yes", "no"):
        return PENDING
    return PASS if rejects == "yes" and false_cited == "no" else FAIL


def needs_judging(q: dict, rec: dict) -> bool:
    """On the blind sheet: every AI answer (faithful_human), and every unanswerable or
    false-premise answer the automatic rule could not decide."""
    return is_ai_answer(rec) or (q["type"] in PREMISE_TYPES
                                 and unanswerable_auto(rec) == PENDING)


def is_ai_answer(rec: dict) -> bool:
    """An answer the LLM wrote (not unavailable, refused, cap reached or no context)."""
    return rec["route"] == "ai" and rec["status"] in ANSWERED


def sentence_counts(rec: dict) -> tuple[int, int]:
    """(sentences, sentences with a valid citation) by score_claims.py's frozen rules."""
    from score_claims import score_answer  # imported here: it pulls in the backend config

    row = score_answer({"id": rec["id"], "answer": rec["answer"],
                        "citations": rec["citations"], "status": rec["status"]})
    return row["sentences"], row["cited_sentences"]


# ---- per-question outcomes, summary, agreement ---------------------------------------------

def outcomes(q: dict, rec: dict, judgment: dict | None = None) -> dict:
    """Everything scored for one question in one pass (the summary is built from these)."""
    out: dict = {"type": q["type"], "route": rec["route"], "status": rec["status"]}
    if q["type"] in RETRIEVAL_TYPES:
        out["code_hit"] = {c: range_hit(v, q["expected"], "code")
                           for c, v in rec["retrieval"].items()}
        out["doc_hit"] = {c: range_hit(v, q["expected"], "doc")
                          for c, v in rec["retrieval"].items()}
        out["answered_correct_file"] = answered_correct_file(q, rec)
    if q["type"] == "graph":
        out["routed_to_graph"] = rec["route"] == "graph"
        out.update(set_scores(returned_files(rec), set(q["expected_files_with_tests"])))
    if q["type"] in PREMISE_TYPES:
        out["unanswerable_ok"] = unanswerable_final(rec, judgment)
    if is_ai_answer(rec):
        out["citation_valid"] = rec["dropped"] == 0
        out["citations"], out["dropped"] = len(rec["citations"]), rec["dropped"]
        out["sentences"], out["cited_sentences"] = sentence_counts(rec)
        if judgment and judgment.get("faithful") in FAITHFUL:
            out["faithful_human"] = judgment["faithful"]
    return out


def _rate(k: int, n: int) -> dict:
    return {"k": k, "n": n, "rate": round(k / n, 3) if n else None}


def summarise(questions: list[dict], outs: dict, recs: dict, configs: list[str]) -> dict:
    """Aggregates only: no question ids or text. `outs` and `recs` are keyed by question id."""
    qs = [q for q in questions if q["id"] in outs]
    s: dict = {"questions": len(qs), "by_type": dict(Counter(q["type"] for q in qs))}
    o = {q["id"]: outs[q["id"]] for q in qs}
    head = [i for i, x in o.items() if x["type"] in HEADLINE_TYPES]
    ret = [i for i, x in o.items() if x["type"] in RETRIEVAL_TYPES]
    s["code_hit"] = {c: _rate(sum(1 for i in head if o[i]["code_hit"][c]),
                              sum(1 for i in head if o[i]["code_hit"][c] is not None))
                     for c in configs}
    s["doc_hit"] = {c: _rate(sum(1 for i in ret if o[i]["doc_hit"][c]),
                             sum(1 for i in ret if o[i]["doc_hit"][c] is not None))
                    for c in configs}
    s["answered_correct_file"] = _rate(sum(o[i]["answered_correct_file"] for i in ret), len(ret))
    graph = [i for i, x in o.items() if x["type"] == "graph"]
    routed = [i for i in graph if o[i]["routed_to_graph"]]
    s["graph"] = {
        "routing": _rate(len(routed), len(graph)),
        "exact_all": _rate(sum(o[i]["exact"] for i in graph), len(graph)),
        "exact_graph_routed": _rate(sum(o[i]["exact"] for i in routed), len(routed)),
        "precision_mean": _mean([o[i]["precision"] for i in graph]),
        "recall_mean": _mean([o[i]["recall"] for i in graph]),
    }
    prem = [i for i, x in o.items() if x["type"] in PREMISE_TYPES]
    verdicts = Counter(o[i]["unanswerable_ok"] for i in prem)
    s["unanswerable_ok"] = {"n": len(prem), PASS: verdicts[PASS], FAIL: verdicts[FAIL],
                            "awaiting_human": verdicts[PENDING]}
    ai = [i for i, x in o.items() if "citation_valid" in x]
    cites = sum(o[i]["citations"] for i in ai)
    dropped = sum(o[i]["dropped"] for i in ai)
    s["citation_validity"] = _rate(sum(o[i]["citation_valid"] for i in ai), len(ai))
    s["citation_validity_citations"] = _rate(cites, cites + dropped)
    s["cited_sentence_rate"] = _rate(sum(o[i]["cited_sentences"] for i in ai),
                                     sum(o[i]["sentences"] for i in ai))
    judged = Counter(o[i].get("faithful_human") for i in ai)
    s["faithful_human"] = {"n": len(ai), **{v: judged[v] for v in FAITHFUL},
                           "awaiting_human": judged[None]}
    s["status"] = dict(Counter(o[i]["status"] for i in o))
    r = [recs[i] for i in o]
    secs = sorted(x["latency_s"] for x in r)
    s["latency_s"] = {"median": round(statistics.median(secs), 2) if secs else None,
                      "max": secs[-1] if secs else None}
    s["tokens_in"] = sum(x["tokens_in"] for x in r)
    s["tokens_out"] = sum(x["tokens_out"] for x in r)
    s["llm_calls"] = sum(x["calls"] for x in r)
    s["cost_usd"] = round(sum(x["cost_usd"] for x in r), 4)
    return s


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def comparisons(questions: list[dict], outs: dict, pairs: list[tuple[str, str]]) -> dict:
    """code_hit paired comparisons over the headline questions."""
    head = {q["id"] for q in questions if q["type"] in HEADLINE_TYPES and q["id"] in outs}
    out = {}
    for x, y in pairs:
        hx = {i: outs[i]["code_hit"][x] for i in head if outs[i]["code_hit"][x] is not None}
        hy = {i: outs[i]["code_hit"][y] for i in head if outs[i]["code_hit"][y] is not None}
        out[f"{x} vs {y}"] = paired(hx, hy)
    return out


def grouped(questions: list[dict], outs: dict, recs: dict, configs: list[str]) -> dict:
    """Overall, per repo, per writer (author) and per type."""
    def sub(pred) -> dict:
        ids = {q["id"] for q in questions if pred(q)}
        return summarise([q for q in questions if q["id"] in ids],
                         {i: v for i, v in outs.items() if i in ids}, recs, configs)

    return {
        "overall": summarise(questions, outs, recs, configs),
        "per_repo": {r: sub(lambda q, r=r: q["repo"] == r)
                     for r in sorted({q["repo"] for q in questions})},
        "per_writer": {a: sub(lambda q, a=a: q["author"] == a)
                       for a in sorted({q["author"] for q in questions})},
        "per_type": {t: sub(lambda q, t=t: q["type"] == t)
                     for t in TYPES if any(q["type"] == t for q in questions)},
    }


AGREEMENT_KEYS = ("route", "answered_correct_file", "exact", "unanswerable_ok", "citation_valid")


def agreement(outs_1: dict, outs_2: dict) -> dict:
    """Per outcome: share of questions with the same value in both passes. A question awaiting
    a human verdict in either pass is left out of unanswerable_ok and counted."""
    res = {}
    for key in AGREEMENT_KEYS:
        ids = [i for i in outs_1 if i in outs_2 and key in outs_1[i] and key in outs_2[i]]
        skipped = 0
        if key == "unanswerable_ok":
            keep = [i for i in ids if PENDING not in (outs_1[i][key], outs_2[i][key])]
            skipped, ids = len(ids) - len(keep), keep
        same = sum(1 for i in ids if outs_1[i][key] == outs_2[i][key])
        res[key] = {**_rate(same, len(ids)), "left_out_pending": skipped}
    hits = [i for i in outs_1 if i in outs_2 and "code_hit" in outs_1[i]]
    res["retrieval_identical"] = all(
        outs_1[i]["code_hit"] == outs_2[i]["code_hit"]
        and outs_1[i]["doc_hit"] == outs_2[i]["doc_hit"] for i in hits)
    return res
