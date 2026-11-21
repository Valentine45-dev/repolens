"""Held-out ("locked") evaluation runner: runs RepoLens's own Ask on each question and scores it
with the frozen rules in eval/locked_metrics.py (docs/V2-EVAL-DESIGN-metrics.md).

    uv run --project backend --env-file .env python eval/locked_eval.py <command> ...

Commands:
  validate FILE             schema check, and every expected path exists in the analysed snapshot
  estimate FILE --price-in X --price-out Y
                            free: routes and retrieves every question, prices one pass
  run FILE --price-in X --price-out Y [--passes N] [--label L]
                            the run; prints the summary only (no question ids or text)
  run FILE --fake           dry run with FakeProvider (no API calls; tuning files only)
  summary RESULTS [--judgments J]
                            print a saved run's summary again (with human verdicts if given)
  sheet RESULTS --out DIR   blind judging sheet (CSV) + hidden key (JSON) for faithful_human and
                            the false-premise rule; shuffled, no configuration or pass labels
  judge RESULTS --sheet CSV --key JSON
                            read the filled sheet, save the verdicts, print the final summary
  analyse PINS [--in-process] [--label L]
                            analyse pinned repos one at a time, timing each stage, through the
                            API (POST /repos) or in this process (the API's own functions, the
                            job in a thread; no API needed); stops if search is not ready

How a question runs: the same function as POST /snapshots/{id}/ask (`app.api.ask.ask`), in this
process, so routing, retrieval (the live configuration is C), the prompt and citation validation
are the product's own. The provider is wrapped to count calls, tokens and cost, and to stop a
pass before a call whose worst case (input + LLM_MAX_TOKENS output) would take it over the cap.
The chunks sent are read from the prompt itself. Retrieval configurations A, B, C are run
separately (no LLM) for code_how, locate and purpose. There is no answer cache in the product.

Run protocol (§6): one run per configuration; tuning runs: the first result counts; locked runs:
exactly two full passes, both reported with their agreement; a void pass (stopped by the spend
cap) is kept and reported, never resumed or partly re-run. A locked run also refuses unless the
question file's SHA-256 equals eval/locked/<name>.sha256, the scoring code matches
eval/locked/scorer.sha256, and tracked files are clean. Stop the API first: this process loads
its own copy of the embedding model.
"""

import argparse
import csv
import hashlib
import json
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import locked_metrics as lm
import yaml
from runinfo import ROOT, header, run_info, save_results  # also puts backend/ on sys.path

CONFIGS = {
    "A": {"k": 8, "expand": False, "expand_max": 0},
    "B": {"k": 16, "expand": False, "expand_max": 0},
    "C": {"k": 8, "expand": True, "expand_max": 8},
}
LIVE_CONFIG = "C"  # what /ask uses with the default settings (QA_TOP_K 8, expansion on, 8)
PAIRS = [("C", "B"), ("C", "A"), ("B", "A")]
PASS_CAP_USD = 1.0
OUT_TOKENS_ESTIMATE = 700  # per AI answer, for the estimate (BASELINE-v1 max was 681)
LOCKED_PASSES = 2
LOCKED_DIR = ROOT / "eval" / "locked"
LOCKED_RESULTS = ROOT / "eval" / "results" / "locked"
MANIFEST = LOCKED_DIR / "scorer.sha256"
# Hashed into the manifest at the freeze. The runner (this file) may change for v2.1 only by
# new retrieval configurations; a run then needs --runner-changed and records the diff.
SCORING_FILES = ("eval/locked_metrics.py", "eval/score_claims.py")
RUNNER_FILE = "eval/locked_eval.py"
SNIPPET_SOURCE = re.compile(r'<snippet source="([^"]+):(\d+)-(\d+)"')
SHEET_COLUMNS = ("row", "question", "answer", "cited_lines", "premise_truth", "faithful",
                 "rejects_premise", "false_claim_cited", "note")
MAX_SHEET_LINES = 150  # per citation


class SpendCapStop(Exception):
    pass


# ---- files and guards (no database) --------------------------------------------------------

def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha256(path: Path) -> str:
    """Hash of a source file with line endings normalised (a Windows checkout has CRLF)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_questions(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    errors = lm.validate_questions(data)
    if errors:
        raise SystemExit("question file rejected:\n  " + "\n  ".join(errors))
    return data["questions"]


def read_manifest(path: Path = MANIFEST) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            digest, name = line.split(maxsplit=1)
            out[name.strip()] = digest
    return out


def manifest_problems(manifest: dict[str, str], root: Path = ROOT) -> tuple[list[str], bool]:
    """(scoring files whose hash differs, whether the runner differs)."""
    bad = [f for f in SCORING_FILES
           if manifest.get(f) != text_sha256(root / f)]
    runner_changed = manifest.get(RUNNER_FILE) != text_sha256(root / RUNNER_FILE)
    return bad, runner_changed


def read_hash_file(path: Path) -> str | None:
    """The 64-hex SHA-256 in a hash file, lower case. UTF-8 (with or without BOM) or UTF-16
    (what PowerShell's Out-File writes); Get-FileHash's upper case and `sha256sum` lines too."""
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig", errors="replace")
    m = re.search(r"\b[0-9a-fA-F]{64}\b", text)
    return m[0].lower() if m else None


def locked_guard(path: Path, *, dirty: bool, runner_changed_ok: bool,
                 manifest_path: Path = MANIFEST, root: Path = ROOT) -> dict:
    """Refuse a locked run unless everything is as frozen. Returns what to record."""
    expected_file = path.with_suffix(".sha256")
    problems = []
    if not expected_file.exists():
        problems.append(f"{expected_file.name} is not committed")
    else:
        want = read_hash_file(expected_file)
        if want is None:
            problems.append(f"{expected_file.name} holds no SHA-256")
        elif want != file_sha256(path):
            problems.append(f"{path.name} SHA-256 does not match {expected_file.name}")
    if not manifest_path.exists():
        problems.append("eval/locked/scorer.sha256 (the scorer freeze) is missing")
        bad, runner_changed = [], False
    else:
        bad, runner_changed = manifest_problems(read_manifest(manifest_path), root)
        problems += [f"{f} differs from the frozen scorer" for f in bad]
        if runner_changed and not runner_changed_ok:
            problems.append(f"{RUNNER_FILE} differs from the freeze (pass --runner-changed to "
                            "run anyway and record the diff)")
    if dirty:
        problems.append("tracked files have uncommitted changes")
    if problems:
        raise SystemExit("locked run refused:\n  " + "\n  ".join(problems))
    return {"questions_sha256": file_sha256(path), "runner_changed": runner_changed}


def check_cap(estimate_usd: float, cap: float) -> None:
    if estimate_usd > cap:
        raise SystemExit(f"estimated ${estimate_usd:.4f} per pass is over the ${cap:.2f} cap;"
                         " not running")


class Meter:
    """Wraps the provider: counts calls, tokens and cost; stops before a call whose worst case
    would take the pass over the cap."""

    def __init__(self, inner, price_in: float, price_out: float, cap: float):
        self.inner, self.price_in, self.price_out, self.cap = inner, price_in, price_out, cap
        self.name, self.settings = inner.name, inner.settings
        self.counts_toward_budget = inner.counts_toward_budget
        self.spent = 0.0
        self.log: list[dict] = []

    def cost(self, tokens_in: float, tokens_out: float) -> float:
        return (tokens_in * self.price_in + tokens_out * self.price_out) / 1e6

    def complete(self, system, prompt, max_tokens, timeout):
        worst = self.cost(len(system + prompt) / 3.5, max_tokens)
        if self.spent + worst > self.cap:
            raise SpendCapStop(f"next call could cost ${worst:.4f}; ${self.spent:.4f} spent of"
                               f" ${self.cap:.2f}")
        entry = {"sent": [{"path": p, "start": int(a), "end": int(b)}
                          for p, a, b in SNIPPET_SOURCE.findall(prompt)],
                 "ok": False, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}
        self.log.append(entry)
        c = self.inner.complete(system, prompt, max_tokens, timeout)
        cost = self.cost(c.tokens_in, c.tokens_out)
        self.spent += cost
        entry.update(ok=True, tokens_in=c.tokens_in, tokens_out=c.tokens_out, cost_usd=cost,
                     stop_reason=c.stop_reason)
        return c


# ---- the system under test (database) ------------------------------------------------------

def snapshot_facts(repo: str, commit: str) -> dict:
    from app import db

    with db.pool().connection() as conn:
        row = conn.execute(
            "SELECT s.id, s.llm_tokens_used, st.status, st.job_id, st.search_state,"
            " st.search_error, j.hit_file_limit, j.files_kept, j.files_skipped,"
            " j.files_beyond_limit,"
            " (SELECT count(*) FROM chunks c WHERE c.snapshot_id = s.id AND NOT c.in_test)"
            "   AS chunks_non_test,"
            " (SELECT count(*) FROM chunks c WHERE c.snapshot_id = s.id AND c.in_test)"
            "   AS chunks_test"
            " FROM snapshots s JOIN repos r ON r.id = s.repo_id"
            " JOIN snapshot_status st ON st.snapshot_id = s.id JOIN jobs j ON j.id = st.job_id"
            " WHERE lower(r.url) = lower(%s) AND s.commit_sha = %s",
            (f"https://github.com/{repo}", commit),
        ).fetchone()
    if row is None or row["status"] != "done":
        raise SystemExit(f"{repo}@{commit[:7]} has no finished analysis; analyse it first")
    return dict(row)


def require_search(facts: dict, repo: str) -> None:
    if facts["chunks_non_test"] == 0 or facts["search_state"] not in ("ready", "tests"):
        raise SystemExit(f"{repo}: search is not ready (state {facts['search_state']},"
                         f" {facts['chunks_non_test']} non-test chunks); retry search first")


def snippets_of(retrieval) -> list[dict]:
    return [{"path": s.path, "start": s.start_line, "end": s.end_line, "via": s.via}
            for s in retrieval.snippets]


def route_of(snapshot_id: int, text: str) -> tuple[str, dict | None]:
    from app.qa.router import graph_answer, match_route

    route = match_route(text)
    answer = graph_answer(snapshot_id, route) if route else None
    return ("graph", answer) if answer is not None else ("ai", None)


def estimate_pass(questions: list[dict], snapshots: dict, price_in: float,
                  price_out: float) -> dict:
    """Free: route and retrieve each question as /ask would, and price the prompt."""
    from app import config
    from app.qa.prompt import build_user_message, format_snippet, system_prompt
    from app.qa.retrieve import CHARS_PER_TOKEN, retrieve

    system = system_prompt().text
    ai, tokens_in, worst = 0, 0.0, 0.0
    for q in questions:
        sid = snapshots[q["repo"]]["id"]
        route, _ = route_of(sid, q["question"])
        if route == "graph":
            continue
        found = retrieve(sid, q["question"])
        if not found.snippets:
            continue
        prompt = build_user_message(q["question"], [
            format_snippet(s.path, s.qualified_name, s.start_line, s.text)
            for s in found.snippets])
        n = len(system + prompt) / CHARS_PER_TOKEN
        ai += 1
        tokens_in += n
        worst += (n * price_in + config.LLM_MAX_TOKENS * price_out) / 1e6
    est = (tokens_in * price_in + ai * OUT_TOKENS_ESTIMATE * price_out) / 1e6
    return {"ai_questions": ai, "graph_questions": len(questions) - ai,
            "input_tokens": round(tokens_in), "output_tokens_assumed": OUT_TOKENS_ESTIMATE,
            "estimate_usd": round(est, 4), "worst_case_usd": round(worst, 4)}


def run_question(q: dict, snapshot_id: int, meter: Meter) -> dict:
    from app.api.ask import AskRequest, ask
    from app.qa.retrieve import retrieve

    before = len(meter.log)
    t0 = time.monotonic()
    reply = ask(snapshot_id, AskRequest(question=q["question"]))
    latency = round(time.monotonic() - t0, 2)
    calls = meter.log[before:]
    rec = {
        "id": q["id"], "route": "graph" if reply["kind"] == "graph" else "ai",
        "status": reply["status"], "answer": reply["answer"],
        "citations": [f"{c['path']}:{c['start_line']}-{c['end_line']}"
                      for c in reply["citations"]],
        "dropped": reply["dropped"], "prompt_version": reply.get("prompt_version"),
        "graph_paths": [r.get("path") for r in reply.get("results", [])]
        if reply["kind"] == "graph" else [],
        "graph_total": reply.get("total"), "lower_confidence": reply.get("lower_confidence"),
        "retrieval_summary": reply.get("retrieval"),
        "sent": calls[-1]["sent"] if calls else [],
        "latency_s": latency, "calls": len(calls),
        "tokens_in": sum(c["tokens_in"] for c in calls),
        "tokens_out": sum(c["tokens_out"] for c in calls),
        "cost_usd": round(sum(c["cost_usd"] for c in calls), 6),
    }
    if q["type"] in lm.RETRIEVAL_TYPES:
        rec["retrieval"] = {name: snippets_of(retrieve(snapshot_id, q["question"], **cfg))
                            for name, cfg in CONFIGS.items()}
        if rec["route"] == "ai" and calls:
            live = [{k: s[k] for k in ("path", "start", "end")}
                    for s in rec["retrieval"][LIVE_CONFIG]]
            rec["sent_equals_config_" + LIVE_CONFIG] = live == rec["sent"]
    return rec


def score_pass(questions: list[dict], records: list[dict], judgments: dict | None = None):
    by_id = {q["id"]: q for q in questions}
    recs = {r["id"]: r for r in records}
    outs = {i: lm.outcomes(by_id[i], r, (judgments or {}).get(i)) for i, r in recs.items()}
    return outs, recs


def summaries(questions: list[dict], passes: list[dict], judgments: dict | None = None) -> dict:
    """Per pass (void passes included, marked), comparisons, and the agreement of passes 1-2."""
    judgments = judgments or {}
    out = {"passes": []}
    scored = []
    for p in passes:
        outs, recs = score_pass(questions, p["records"], judgments.get(str(p["pass"])))
        scored.append(outs)
        out["passes"].append({
            "pass": p["pass"], "void": p["void"], "answered": len(p["records"]),
            "grouped": lm.grouped(questions, outs, recs, list(CONFIGS)),
            "comparisons_code_hit": lm.comparisons(questions, outs, PAIRS),
        })
    valid = [o for p, o in zip(passes, scored, strict=True) if not p["void"]]
    if len(valid) >= 2:
        out["agreement_pass_1_2"] = lm.agreement(valid[0], valid[1])
    return out


# ---- printing (aggregates only) ------------------------------------------------------------

def _r(x: dict) -> str:
    return f"{x['k']}/{x['n']}" + (f" = {x['rate']:.2f}" if x["rate"] is not None else "")


def format_group(name: str, s: dict) -> list[str]:
    g, u, f = s["graph"], s["unanswerable_ok"], s["faithful_human"]
    lines = [f"[{name}] {s['questions']} questions {s['by_type']}"]
    if any(v["n"] for v in s["code_hit"].values()):
        lines.append("  code_hit@k (code_how+locate): "
                     + "  ".join(f"{c} {_r(v)}" for c, v in s["code_hit"].items()))
    if any(v["n"] for v in s["doc_hit"].values()):
        lines.append("  doc_hit@k: " + "  ".join(f"{c} {_r(v)}" for c, v in s["doc_hit"].items()))
    if s["answered_correct_file"]["n"]:
        lines.append(f"  answered_correct_file: {_r(s['answered_correct_file'])}")
    if g["routing"]["n"]:
        lines.append(f"  graph: routing {_r(g['routing'])}; exact (all) {_r(g['exact_all'])};"
                     f" exact (graph-routed) {_r(g['exact_graph_routed'])};"
                     f" precision {g['precision_mean']} recall {g['recall_mean']}")
    if u["n"]:
        lines.append(f"  unanswerable_ok: pass {u['pass']} fail {u['fail']} awaiting human"
                     f" {u['awaiting_human']} (of {u['n']})")
    if s["citation_validity"]["n"]:
        lines.append(f"  citation_validity: answers {_r(s['citation_validity'])}; citations"
                     f" {_r(s['citation_validity_citations'])}; cited_sentence_rate"
                     f" {_r(s['cited_sentence_rate'])}")
        lines.append(f"  faithful_human: yes {f['yes']} partly {f['partly']} no {f['no']}"
                     f" awaiting {f['awaiting_human']} (of {f['n']})")
    lines.append(f"  status {s['status']}; latency median {s['latency_s']['median']} s max"
                 f" {s['latency_s']['max']} s; tokens {s['tokens_in']}+{s['tokens_out']};"
                 f" calls {s['llm_calls']}; ${s['cost_usd']}")
    return lines


def format_summary(summary: dict) -> str:
    lines = []
    for p in summary["passes"]:
        g = p["grouped"]
        void = " (VOID: stopped by the spend cap)" if p["void"] else ""
        lines.append(f"=== pass {p['pass']}{void}, {p['answered']} questions answered")
        lines += format_group("overall", g["overall"])
        for key in ("per_repo", "per_writer", "per_type"):
            for name, s in g[key].items():
                lines += format_group(f"{key[4:]} {name}", s)
        lines.append("  paired code_hit: " + "; ".join(
            f"{k} wins {v['wins']} losses {v['losses']} p={v['p_mcnemar_exact']}"
            for k, v in p["comparisons_code_hit"].items()))
    if "agreement_pass_1_2" in summary:
        a = summary["agreement_pass_1_2"]
        lines.append("=== agreement, pass 1 vs pass 2: " + "; ".join(
            f"{k} {_r(v)}" + (f" ({v['left_out_pending']} pending left out)"
                              if v["left_out_pending"] else "")
            for k, v in a.items() if isinstance(v, dict))
            + f"; retrieval identical: {a['retrieval_identical']}")
    lines.append("Small differences are not conclusive (exact McNemar p-values above).")
    return "\n".join(lines)


# ---- blind sheet ---------------------------------------------------------------------------

def cited_text(conn, snapshot_id: int, citation: str) -> str:
    path, rng = citation.rsplit(":", 1)
    start, end = (int(x) for x in rng.split("-"))
    row = conn.execute("SELECT content FROM files WHERE snapshot_id = %s AND path = %s",
                       (snapshot_id, path)).fetchone()
    if row is None:
        return f"{citation}\n(file not in this analysis)"
    lines = row["content"].split("\n")[start - 1:end]
    shown = lines[:MAX_SHEET_LINES]
    body = "\n".join(f"{start + i}| {line}" for i, line in enumerate(shown))
    more = f"\n... ({len(lines) - len(shown)} more lines)" if len(lines) > len(shown) else ""
    return f"{citation}\n{body}{more}"


def sheet_rows(questions: list[dict], passes: list[dict], lookup, rng) -> tuple[list, dict]:
    """lookup(snapshot repo, citation) -> text. Returns (rows, key)."""
    by_id = {q["id"]: q for q in questions}
    rows, key = [], {}
    for p in passes:
        if p["void"]:
            continue
        for rec in p["records"]:
            q = by_id[rec["id"]]
            if not lm.needs_judging(q, rec):
                continue
            row_id = secrets.token_hex(4)
            while row_id in key:
                row_id = secrets.token_hex(4)
            key[row_id] = {"pass": p["pass"], "id": rec["id"]}
            rows.append({
                "row": row_id, "question": q["question"], "answer": rec["answer"],
                "cited_lines": "\n\n".join(lookup(q["repo"], c) for c in rec["citations"]),
                "premise_truth": q.get("premise_truth", "") if q["type"] in lm.PREMISE_TYPES
                else "",
                "faithful": "", "rejects_premise": "", "false_claim_cited": "", "note": "",
            })
    rng.shuffle(rows)
    return rows, key


def read_judgments(sheet: Path, key: dict) -> dict:
    """{pass: {question id: {faithful, rejects_premise, false_claim_cited}}}; checks values."""
    out: dict = {}
    problems = []
    with sheet.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            where = key.get(row["row"])
            if where is None:
                problems.append(f"row {row['row']} is not in the key")
                continue
            v = {k: row[k].strip().lower() for k in ("faithful", "rejects_premise",
                                                     "false_claim_cited")}
            if v["faithful"] not in ("", *lm.FAITHFUL):
                problems.append(f"row {row['row']}: faithful must be yes, partly or no")
            for k in ("rejects_premise", "false_claim_cited"):
                if v[k] not in ("", "yes", "no"):
                    problems.append(f"row {row['row']}: {k} must be yes or no")
            out.setdefault(str(where["pass"]), {})[where["id"]] = {k: x for k, x in v.items() if x}
    if problems:
        raise SystemExit("sheet rejected:\n  " + "\n  ".join(problems))
    return out


# ---- analysis through the API (run day; timing runs) ---------------------------------------

def _http(method: str, url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


class OverHttp:
    """Analyse through a running API (POST /repos, GET status)."""

    def __init__(self, api: str):
        self.api, self.threads = api, []

    def submit(self, url: str, commit: str) -> dict:
        return _http("POST", f"{self.api}/repos", {"url": url, "commit": commit})

    def status(self, snapshot_id: int) -> dict:
        return _http("GET", f"{self.api}/snapshots/{snapshot_id}/status")


class InProcess:
    """The API's own submit and status functions, called in this process; the job runs in a
    thread here. No API needs to run (and none is started, so no running job anywhere is marked
    "Interrupted by server restart"). MAX_ANALYSIS_S is this process's environment."""

    def __init__(self):
        self.threads: list = []

    def submit(self, url: str, commit: str) -> dict:
        import threading

        from app.api.repos import SubmitRepo, submit_repo
        from fastapi import BackgroundTasks

        background = BackgroundTasks()
        sub = submit_repo(SubmitRepo(url=url, commit=commit), background)
        for task in background.tasks:
            t = threading.Thread(target=task.func, args=task.args, kwargs=task.kwargs)
            t.start()
            self.threads.append(t)
        return sub

    def status(self, snapshot_id: int) -> dict:
        from app.api.snapshots import snapshot_status

        return snapshot_status(snapshot_id)


def analyse(pin: dict, via, poll_s: float = 2.0, wait_tests: bool = True) -> dict:
    url = f"https://github.com/{pin['repo']}"
    t0 = time.monotonic()
    sub = via.submit(url, pin["commit"])
    rec = {"repo": pin["repo"], "commit": pin["commit"], "snapshot_id": sub["snapshot_id"],
           "job_id": sub["job_id"], "submitted_status": sub["status"],
           "timing_only": bool(pin.get("timing_only")), "stages": []}
    if sub["status"] == "done":
        rec["note"] = "already analysed: the existing job was reused, nothing was timed"
    last = None
    while True:
        st = via.status(sub["snapshot_id"])
        now = round(time.monotonic() - t0, 1)
        state = (st["status"], st["stage"], st["features"]["search"])
        if state != last:
            rec["stages"].append({"t_s": now, "status": st["status"], "stage": st["stage"],
                                  "search": st["features"]["search"]})
            print(f"  {pin['repo']}: {now:>7.1f} s  {st['status']:<8}{st['stage']:<10}"
                  f" search={st['features']['search']}", flush=True)
            last = state
        search = st["features"]["search"]
        if st["status"] == "failed" or (st["status"] == "done" and (
                search in ("ready", "failed") or (search == "tests" and not wait_tests))):
            break
        time.sleep(poll_s)
    rec.update(final_status=st["status"], error=st["error"], receipt=st["receipt"],
               search=st["features"]["search"], search_error=st["features"]["search_error"])
    done = [s["t_s"] for s in rec["stages"] if s["status"] == "done"]
    rec["analysis_s"] = done[0] if done else None  # what MAX_ANALYSIS_S covers
    rec["total_with_tests_s"] = rec["stages"][-1]["t_s"]
    return rec


# ---- commands ------------------------------------------------------------------------------

def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def cmd_validate(args) -> None:
    from app import db

    questions = load_questions(args.file)
    db.open_pool()
    missing = 0
    try:
        with db.pool().connection() as conn:
            for q in questions:
                facts = snapshot_facts(q["repo"], q["commit"])
                paths = [e["path"] for e in q["expected"]]
                paths += q.get("expected_files_with_tests", [])
                paths += q.get("expected_files_without_tests", [])
                for p in paths:
                    if not conn.execute("SELECT 1 FROM files WHERE snapshot_id = %s AND path = %s",
                                        (facts["id"], p)).fetchone():
                        missing += 1
    finally:
        db.close_pool()
    print(f"{len(questions)} questions, schema ok; expected paths not in the analysed snapshot:"
          f" {missing}")
    if missing:
        raise SystemExit(1)


def _snapshots(questions: list[dict]) -> dict:
    out = {}
    for repo in sorted({q["repo"] for q in questions}):
        commit = next(q["commit"] for q in questions if q["repo"] == repo)
        facts = snapshot_facts(repo, commit)
        require_search(facts, repo)
        out[repo] = {**facts, "commit": commit}
    return out


def cmd_estimate(args) -> None:
    from app import db

    questions = load_questions(args.file)
    db.open_pool()
    try:
        est = estimate_pass(questions, _snapshots(questions), args.price_in, args.price_out)
    finally:
        db.close_pool()
    print(json.dumps(est, indent=1))
    check_cap(est["estimate_usd"], args.cap)


def cmd_run(args) -> None:
    from app import db
    from app.qa import llm

    questions = load_questions(args.file)
    locked = questions[0]["set"] == "locked"
    info = run_info(llm_used=True)
    guard = {"questions_sha256": file_sha256(args.file), "runner_changed": None}
    if locked:
        if args.fake or args.passes != LOCKED_PASSES or args.cap > PASS_CAP_USD:
            raise SystemExit(f"locked runs: real provider, exactly {LOCKED_PASSES} passes, cap"
                             f" <= ${PASS_CAP_USD}")
        guard = locked_guard(args.file, dirty=info["dirty"], runner_changed_ok=args.runner_changed)
    if args.fake:
        inner, price_in, price_out = llm.FakeProvider(), 0.0, 0.0
    else:
        inner = llm.get_provider()
        if inner is None:
            raise SystemExit("LLM not configured (LLM_MODEL / LLM_API_KEY)")
        if args.price_in is None or args.price_out is None:
            raise SystemExit("--price-in and --price-out are required (from the provider's"
                             " pricing page, today)")
        price_in, price_out = args.price_in, args.price_out
    meter = Meter(inner, price_in, price_out, args.cap)
    llm.get_provider = lambda: meter  # ai_answer looks the provider up on each call

    db.open_pool()
    try:
        snaps = _snapshots(questions)
        est = estimate_pass(questions, snaps, price_in, price_out)
        check_cap(est["estimate_usd"], args.cap)
        info = run_info(meter, llm_used=True)
        info["notes"] = args.notes
        info["answer_cache"] = "none (not implemented in the product)"
        info["doc_pool"] = "none (v2.0 chunks code only)"
        info["prices_usd_per_mtok"] = {"in": price_in, "out": price_out}
        print(header(info))
        print(f"{len(questions)} questions, {args.passes} pass(es), estimate per pass"
              f" ${est['estimate_usd']} (worst case ${est['worst_case_usd']}), cap ${args.cap}")
        passes = []
        for n in range(1, args.passes + 1):
            meter.spent = 0.0
            records, void, why = [], False, None
            for q in questions:
                try:
                    records.append(run_question(q, snaps[q["repo"]]["id"], meter))
                except SpendCapStop as e:
                    void, why = True, str(e)
                    break
            passes.append({"pass": n, "void": void, "void_reason": why,
                           "spent_usd": round(meter.spent, 6), "records": records})
            print(f"pass {n}: {len(records)} questions, ${meter.spent:.4f}"
                  + (f" VOID: {why}" if void else ""))
            if void:
                break  # never resumed and never re-run in part
        after = {repo: snapshot_facts(repo, f["commit"])["llm_tokens_used"]
                 for repo, f in snaps.items()}
    finally:
        db.close_pool()

    results = {
        "questions_file": _rel(args.file), "set": questions[0]["set"], **guard,
        "scoring_files_sha256": {f: text_sha256(ROOT / f) for f in (*SCORING_FILES,
                                                                     RUNNER_FILE)},
        "configs": CONFIGS, "live_config": LIVE_CONFIG, "pass_cap_usd": args.cap,
        "estimate": est, "fake_provider": bool(args.fake),
        "repos": {repo: {**f, "llm_tokens_used_after": after[repo]}
                  for repo, f in snaps.items()},
        "passes": passes,
    }
    if guard["runner_changed"]:
        frozen = subprocess.run(["git", "log", "-1", "--format=%H", "--", "eval/locked/"
                                 "scorer.sha256"], cwd=ROOT, capture_output=True, text=True
                                ).stdout.strip()
        results["runner_diff"] = subprocess.run(
            ["git", "diff", frozen, "--", RUNNER_FILE], cwd=ROOT, capture_output=True,
            text=True).stdout
    results["summary"] = summaries(questions, passes)
    name = "locked_run" + (f"-{args.label}" if args.label else "")
    path = save_results(name, info, results, LOCKED_RESULTS if locked else
                        ROOT / "eval" / "results")
    print(format_summary(results["summary"]))
    if args.details and not locked:
        for p in passes:
            for r in p["records"]:
                print(f"  pass {p['pass']} {r['id']:<6} {r['route']:<5} {r['status']:<10}"
                      f" cites={len(r['citations'])} dropped={r['dropped']}")
    print("saved", _rel(path))


def _load_results(path: Path) -> tuple[dict, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    qfile = ROOT / data["questions_file"]
    if file_sha256(qfile) != data["questions_sha256"]:
        raise SystemExit(f"{data['questions_file']} changed since this run")
    return data, load_questions(qfile)


def cmd_summary(args) -> None:
    data, questions = _load_results(args.results)
    judgments = json.loads(args.judgments.read_text(encoding="utf-8"))["judgments"] \
        if args.judgments else None
    print(format_summary(summaries(questions, data["passes"], judgments)))


def cmd_sheet(args) -> None:
    import random

    from app import db

    data, questions = _load_results(args.results)
    out = args.out.resolve()
    if data["set"] == "locked" and out.is_relative_to(ROOT):
        raise SystemExit("locked run: write the sheet and key outside the repository")
    out.mkdir(parents=True, exist_ok=True)
    ids = {repo: f["id"] for repo, f in data["repos"].items()}
    db.open_pool()
    try:
        with db.pool().connection() as conn:
            rows, key = sheet_rows(questions, data["passes"],
                                   lambda repo, c: cited_text(conn, ids[repo], c),
                                   random.Random(secrets.randbits(64)))
    finally:
        db.close_pool()
    stem = args.results.stem
    sheet, keyfile = out / f"{stem}-sheet.csv", out / f"{stem}-KEY-do-not-open.json"
    with sheet.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SHEET_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    keyfile.write_text(json.dumps({"results": _rel(args.results), "rows": key}, indent=1),
                       encoding="utf-8")
    print(f"{len(rows)} rows -> {sheet}\nkey -> {keyfile} (do not open until judging is done)")
    print("Columns to fill: faithful (yes/partly/no: is every claim supported by the cited"
          " lines?); rejects_premise and false_claim_cited (yes/no) on rows with a"
          " premise_truth.")


def cmd_judge(args) -> None:
    data, questions = _load_results(args.results)
    key = json.loads(args.key.read_text(encoding="utf-8"))["rows"]
    judgments = read_judgments(args.sheet, key)
    path = args.results.with_name(args.results.stem + "-judgments.json")
    path.write_text(json.dumps({"results": _rel(args.results), "judge": args.judge,
                                "judgments": judgments}, indent=1) + "\n", encoding="utf-8")
    print(format_summary(summaries(questions, data["passes"], judgments)))
    print("saved", _rel(path))


def cmd_analyse(args) -> None:
    from app import config, db

    pins = yaml.safe_load(args.pins.read_text(encoding="utf-8"))["repos"]
    info = run_info(llm_used=False)
    info["notes"] = args.notes
    info["analysed"] = "in this process" if args.in_process else f"through the API at {args.api}"
    if args.in_process:
        db.open_pool()
        via = InProcess()
        print(header(info), f"| in process, MAX_ANALYSIS_S {config.MAX_ANALYSIS_S}")
    else:
        via = OverHttp(args.api)
        print(header(info), "| through the API (its own MAX_ANALYSIS_S applies)")
    out = []
    try:
        for pin in pins:
            rec = analyse(pin, via, wait_tests=not args.no_wait_tests)
            out.append(rec)
            for t in via.threads:  # in process: the job (and its test-code embedding) ends here
                t.join()
            via.threads.clear()
            if rec["final_status"] != "done" or rec["search"] not in ("ready", "tests"):
                print(f"STOP: {pin['repo']} ended {rec['final_status']} with search"
                      f" {rec['search']}: {rec['error'] or rec['search_error']}")
                break
    except urllib.error.URLError as e:
        print(f"API not reachable at {args.api}: {e}")
    finally:
        if args.in_process:
            db.close_pool()
    path = save_results("analysis_timing" + (f"-{args.label}" if args.label else ""), info,
                        {"pins": _rel(args.pins), "analyses": out})
    for r in out:
        print(f"{r['repo']}: analysis {r['analysis_s']} s, with test code"
              f" {r['total_with_tests_s']} s, search {r['search']}, receipt {r['receipt']}")
    print("saved", _rel(path))


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("file", type=Path)
    for name in ("estimate", "run"):
        s = sub.add_parser(name)
        s.add_argument("file", type=Path)
        s.add_argument("--price-in", type=float, help="USD per million input tokens")
        s.add_argument("--price-out", type=float, help="USD per million output tokens")
        s.add_argument("--cap", type=float, default=PASS_CAP_USD, help="USD per pass")
    est = sub.choices["estimate"]
    est.set_defaults(price_in=None, price_out=None)
    r = sub.choices["run"]
    r.add_argument("--passes", type=int, default=1)
    r.add_argument("--label", default="")
    r.add_argument("--notes", default="", help="conditions of the run")
    r.add_argument("--fake", action="store_true", help="FakeProvider; tuning files only")
    r.add_argument("--details", action="store_true", help="tuning only: one line per answer")
    r.add_argument("--runner-changed", action="store_true",
                   help="v2.1: allow the runner to differ from the freeze; the diff is recorded")
    s = sub.add_parser("summary")
    s.add_argument("results", type=Path)
    s.add_argument("--judgments", type=Path)
    s = sub.add_parser("sheet")
    s.add_argument("results", type=Path)
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("judge")
    s.add_argument("results", type=Path)
    s.add_argument("--sheet", type=Path, required=True)
    s.add_argument("--key", type=Path, required=True)
    s.add_argument("--judge", default="", help="who judged (a pseudonym)")
    s = sub.add_parser("analyse")
    s.add_argument("pins", type=Path)
    s.add_argument("--api", default="http://127.0.0.1:8000")
    s.add_argument("--label", default="")
    s.add_argument("--notes", default="")
    s.add_argument("--in-process", action="store_true",
                   help="run the pipeline in this process (no API, none restarted)")
    s.add_argument("--no-wait-tests", action="store_true",
                   help="stop when Ask is ready instead of after test-code embedding")
    args = p.parse_args(argv)
    if args.cmd == "estimate" and (args.price_in is None or args.price_out is None):
        p.error("estimate needs --price-in and --price-out")
    {"validate": cmd_validate, "estimate": cmd_estimate, "run": cmd_run,
     "summary": cmd_summary, "sheet": cmd_sheet, "judge": cmd_judge,
     "analyse": cmd_analyse}[args.cmd](args)


if __name__ == "__main__":
    main()
