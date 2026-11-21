"""Unit tests for the locked-run scoring rules (eval/locked_metrics.py). Hand-made records with
known answers; no database, no LLM, no network.

    uv run --project backend python -m pytest -q -p no:cacheprovider eval/test_locked_metrics.py
"""

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import locked_metrics as m  # noqa: E402
import pytest  # noqa: E402

SHA = "a" * 40
CNF = "I could not find this in the provided code."


def q(id_="Q1", type_="code_how", **kw) -> dict:
    base = {"id": id_, "set": "tuning", "repo": "o/r", "commit": SHA, "question": "How?",
            "type": type_, "author": "W1", "written_from": "README", "labeller": "L",
            "expected": [{"path": "a.py", "start": 10, "end": 20, "source": "code"}]}
    if type_ == "graph":
        base["expected"] = []
        base["expected_files_with_tests"] = ["a.py", "tests/test_a.py"]
        base["expected_files_without_tests"] = ["a.py"]
    if type_ in m.PREMISE_TYPES:
        base["expected"] = []
        base["premise_truth"] = "It does not exist."
    base.update(kw)
    return base


def rec(id_="Q1", route="ai", status="answered", answer="It does x (a.py:10-12).",
        citations=("a.py:10-12",), dropped=0, retrieval=None, graph_paths=(), **kw) -> dict:
    r = {"id": id_, "route": route, "status": status, "answer": answer,
         "citations": list(citations), "dropped": dropped,
         "retrieval": retrieval or {"A": [], "B": [], "C": []},
         "graph_paths": list(graph_paths), "latency_s": 1.0, "tokens_in": 100,
         "tokens_out": 10, "calls": 1 if route == "ai" else 0, "cost_usd": 0.001}
    r.update(kw)
    return r


def sent(path, start, end):
    return {"path": path, "start": start, "end": end}


# ---- schema --------------------------------------------------------------------------------

def test_valid_file_has_no_errors():
    data = {"schema": 1, "questions": [q("1"), q("2", "graph"), q("3", "false_premise"),
                                       q("4", "purpose", expected=[
                                           {"path": "README.md", "start": 1, "end": 3,
                                            "source": "doc"}])]}
    assert m.validate_questions(data) == []


@pytest.mark.parametrize("change, message", [
    ({"commit": "abc"}, "40-character"),
    ({"commit": "A" * 40}, "40-character"),
    ({"type": "injection"}, "type must be one of"),
    ({"expected": []}, "needs at least one expected range"),
    ({"expected": [{"path": "a.py", "start": 5, "end": 4, "source": "code"}]}, "start/end"),
    ({"expected": [{"path": "a.py", "start": 0, "end": 4, "source": "code"}]}, "start/end"),
    ({"expected": [{"path": "a.py", "start": 1, "end": 4, "source": "docs"}]}, "code or doc"),
    ({"expected": [{"path": "/abs.py", "start": 1, "end": 4, "source": "code"}]}, "bad path"),
    ({"expected": [{"path": "../x.py", "start": 1, "end": 4, "source": "code"}]}, "bad path"),
    ({"repo": "just-a-name"}, "owner/name"),
    ({"set": "held-out"}, "tuning or locked"),
    ({"author": ""}, "missing author"),
    ({"premise_truth": "x"}, "only unanswerable/false_premise"),
    ({"expected_files_with_tests": []}, "only graph questions"),
])
def test_schema_errors(change, message):
    data = {"schema": 1, "questions": [q(**change)]}
    errors = m.validate_questions(data)
    assert any(message in e for e in errors), errors


def test_schema_type_rules():
    graph = q("g", "graph")
    del graph["expected_files_without_tests"]
    prem = q("p", "unanswerable", premise_truth="")
    fp = q("f", "false_premise", expected=[{"path": "a.py", "start": 1, "end": 2,
                                            "source": "code"}])
    errors = m.validate_questions({"schema": 1, "questions": [graph, prem, fp]})
    assert any("expected_files_without_tests" in e for e in errors)
    assert any("needs premise_truth" in e for e in errors)
    assert any("takes no expected ranges" in e for e in errors)


def test_schema_file_rules():
    two = [q("1"), q("1", commit="b" * 40), q("2", set="locked")]
    errors = m.validate_questions({"schema": 1, "questions": two})
    assert any("appears 2 times" in e for e in errors)
    assert any("two commits" in e for e in errors)
    assert any("same set" in e for e in errors)
    assert m.validate_questions({"questions": [q()]})[0].startswith("top level")
    assert m.validate_questions({"schema": 1, "questions": []})


def test_locked_author_must_be_a_writer_code():
    errors = m.validate_questions({"schema": 1, "questions": [q(set="locked", author="Ann")]})
    assert any("W1, W2 or W3" in e for e in errors)
    assert m.validate_questions({"schema": 1, "questions": [q(set="locked", author="W3")]}) == []


# ---- retrieval -----------------------------------------------------------------------------

@pytest.mark.parametrize("a, b, hit", [
    ((10, 20), (20, 30), True),   # touching end lines overlap (inclusive)
    ((10, 20), (21, 30), False),  # adjacent, no shared line
    ((15, 15), (10, 20), True),   # one-line chunk inside
    ((10, 20), (15, 15), True),   # one-line label inside
    ((1, 9), (10, 20), False),
    ((5, 30), (10, 20), True),    # chunk covers label
])
def test_overlap_edges(a, b, hit):
    assert m.overlaps(*a, *b) is hit


def test_range_hit_needs_same_path_and_source():
    expected = [{"path": "a.py", "start": 10, "end": 20, "source": "code"},
                {"path": "README.md", "start": 1, "end": 5, "source": "doc"}]
    assert m.range_hit([sent("b.py", 10, 20)], expected, "code") is False
    assert m.range_hit([sent("a.py", 18, 40)], expected, "code") is True
    assert m.range_hit([sent("a.py", 18, 40)], expected, "doc") is False
    assert m.range_hit([sent("README.md", 5, 9)], expected, "doc") is True
    assert m.range_hit([sent("README.md", 5, 9)], expected, "code") is False
    assert m.range_hit([], expected, "code") is False


def test_range_hit_none_without_ranges_of_that_source():
    code_only = [{"path": "a.py", "start": 1, "end": 2, "source": "code"}]
    assert m.range_hit([sent("a.py", 1, 2)], code_only, "doc") is None


def test_mcnemar_exact():
    assert m.mcnemar_exact(0, 0) == 1.0
    assert m.mcnemar_exact(1, 0) == 1.0
    assert m.mcnemar_exact(5, 0) == pytest.approx(0.0625)
    assert m.mcnemar_exact(0, 5) == pytest.approx(0.0625)
    assert m.mcnemar_exact(6, 1) == pytest.approx(0.125)
    assert m.mcnemar_exact(10, 0) == pytest.approx(2 / 1024)


def test_paired_counts_only_common_questions():
    x = {"1": True, "2": True, "3": False, "4": True}
    y = {"1": False, "2": True, "3": True}
    assert m.paired(x, y) == {"questions": 3, "wins": 1, "losses": 1, "p_mcnemar_exact": 1.0}


# ---- graph ---------------------------------------------------------------------------------

def test_set_scores():
    assert m.set_scores({"a", "b"}, {"a", "b"}) == {"exact": True, "precision": 1.0,
                                                    "recall": 1.0}
    assert m.set_scores({"a", "c"}, {"a", "b"}) == {"exact": False, "precision": 0.5,
                                                    "recall": 0.5}
    assert m.set_scores(set(), set()) == {"exact": True, "precision": 1.0, "recall": 1.0}
    assert m.set_scores(set(), {"a"}) == {"exact": False, "precision": 0.0, "recall": 0.0}
    assert m.set_scores({"a"}, set()) == {"exact": False, "precision": 0.0, "recall": 0.0}


def test_returned_files():
    graph = rec(route="graph", status="answered", citations=(),
                graph_paths=["a.py", "a.py", None, "tests/test_a.py"])
    assert m.returned_files(graph) == {"a.py", "tests/test_a.py"}  # packages have no path
    ambiguous = rec(route="graph", status="ambiguous", citations=(), graph_paths=["a.py"])
    assert m.returned_files(ambiguous) == set()
    ai = rec(citations=["a.py:1-2", "a.py:5-9", "lib/b.js:3-3"])
    assert m.returned_files(ai) == {"a.py", "lib/b.js"}


def test_graph_outcome_with_tests_and_routing():
    question = q("g", "graph")
    good = m.outcomes(question, rec("g", route="graph", citations=(),
                                    graph_paths=["a.py", "tests/test_a.py"]))
    assert good["routed_to_graph"] and good["exact"]
    no_tests = m.outcomes(question, rec("g", route="graph", citations=(), graph_paths=["a.py"]))
    assert not no_tests["exact"] and no_tests["recall"] == 0.5 and no_tests["precision"] == 1.0
    via_ai = m.outcomes(question, rec("g", citations=["a.py:1-2", "tests/test_a.py:3-4"]))
    assert not via_ai["routed_to_graph"] and via_ai["exact"]  # exact, but a routing miss


# ---- Q&A -----------------------------------------------------------------------------------

def test_answered_correct_file():
    question = q(expected=[{"path": "a.py", "start": 10, "end": 20, "source": "code"},
                           {"path": "README.md", "start": 1, "end": 2, "source": "doc"}])
    assert m.answered_correct_file(question, rec(citations=["a.py:90-99"]))  # file, not lines
    assert m.answered_correct_file(question, rec(citations=["README.md:1-1"]))
    assert not m.answered_correct_file(question, rec(citations=["b.py:10-20"]))
    assert not m.answered_correct_file(question, rec(citations=()))
    graph_routed = rec(route="graph", citations=(), graph_paths=["a.py"])
    assert not m.answered_correct_file(question, graph_routed)


@pytest.mark.parametrize("record, verdict", [
    (rec(answer=CNF, citations=()), m.PASS),
    (rec(answer="**I could not   find this in the provided code.**", citations=()), m.PASS),
    (rec(answer=CNF + " But see a.py:1-2.", citations=["a.py:1-2"]), m.PENDING),
    (rec(answer="It signs, it does not encrypt (a.py:1-2).", citations=["a.py:1-2"]),
     m.PENDING),
    (rec(answer="It does not exist here.", citations=()), m.PENDING),
    (rec(status="unavailable", answer="AI answers are unavailable", citations=()), m.FAIL),
    (rec(status="refused", answer="declined", citations=()), m.FAIL),
    (rec(route="graph", status="answered", answer="Nothing in the graph calls x.",
         citations=()), m.PENDING),
])
def test_unanswerable_auto(record, verdict):
    assert m.unanswerable_auto(record) == verdict


@pytest.mark.parametrize("judgment, verdict", [
    (None, m.PENDING),
    ({}, m.PENDING),
    ({"rejects_premise": "yes", "false_claim_cited": "no"}, m.PASS),
    ({"rejects_premise": "yes", "false_claim_cited": "yes"}, m.FAIL),  # cites a false claim
    ({"rejects_premise": "no", "false_claim_cited": "no"}, m.FAIL),    # went along with it
    ({"rejects_premise": "yes", "false_claim_cited": ""}, m.PENDING),
])
def test_false_premise_revised_rule(judgment, verdict):
    rejection_with_citations = rec(answer="It signs the data; it does not encrypt it "
                                          "(a.py:1-2).", citations=["a.py:1-2"])
    assert m.unanswerable_final(rejection_with_citations, judgment) == verdict


def test_automatic_verdicts_are_not_overridden_by_a_judge():
    judgment = {"rejects_premise": "no", "false_claim_cited": "yes"}
    assert m.unanswerable_final(rec(answer=CNF, citations=()), judgment) == m.PASS
    failed = rec(status="unavailable", citations=())
    assert m.unanswerable_final(failed, {"rejects_premise": "yes",
                                         "false_claim_cited": "no"}) == m.FAIL


def test_needs_judging():
    assert m.needs_judging(q(), rec())
    assert not m.needs_judging(q(), rec(status="unavailable", citations=()))
    assert not m.needs_judging(q("g", "graph"), rec(route="graph", citations=()))
    prem = q("p", "unanswerable")
    assert m.needs_judging(prem, rec(route="graph", citations=(), answer="Nothing calls x."))
    assert m.needs_judging(prem, rec(answer=CNF, citations=()))  # AI answer: faithful_human


def test_citation_and_sentence_outcomes():
    record = rec(answer="The signer appends a signature (a.py:10-12). It also checks keys "
                        "carefully here. ```code. here.```", citations=["a.py:10-12"], dropped=2)
    out = m.outcomes(q(), record)
    assert out["citation_valid"] is False and out["citations"] == 1 and out["dropped"] == 2
    assert (out["sentences"], out["cited_sentences"]) == (2, 1)
    unavailable = m.outcomes(q(), rec(status="unavailable", answer="", citations=()))
    assert "citation_valid" not in unavailable and "sentences" not in unavailable


# ---- summary and agreement -----------------------------------------------------------------

def build(records: dict, questions: list[dict], judgments=None):
    judgments = judgments or {}
    return {i: m.outcomes(next(x for x in questions if x["id"] == i), r, judgments.get(i))
            for i, r in records.items()}


QUESTIONS = [
    q("c1"), q("c2", "locate", repo="o/s", author="W2"),
    q("p1", "purpose", expected=[{"path": "README.md", "start": 1, "end": 5, "source": "doc"},
                                 {"path": "a.py", "start": 1, "end": 5, "source": "code"}]),
    q("g1", "graph"), q("u1", "unanswerable"), q("f1", "false_premise", author="W3"),
]
RECORDS = {
    "c1": rec("c1", retrieval={"A": [sent("a.py", 1, 9)], "B": [sent("a.py", 15, 30)],
                               "C": [sent("a.py", 15, 30)]}),
    "c2": rec("c2", citations=["b.py:1-2"], dropped=1,
              retrieval={"A": [sent("a.py", 15, 16)], "B": [sent("a.py", 15, 16)],
                         "C": [sent("a.py", 15, 16)]}),
    "p1": rec("p1", citations=["README.md:1-2"], retrieval={"A": [sent("README.md", 2, 3)],
                                                           "B": [], "C": []}),
    "g1": rec("g1", route="graph", citations=(), answer="2 files import a.py.",
              graph_paths=["a.py", "tests/test_a.py"], calls=0, cost_usd=0, tokens_in=0,
              tokens_out=0),
    "u1": rec("u1", answer=CNF, citations=()),
    "f1": rec("f1", answer="It has no such feature (a.py:1-2).", citations=["a.py:1-2"]),
}


def test_summary_numbers():
    outs = build(RECORDS, QUESTIONS)
    s = m.summarise(QUESTIONS, outs, RECORDS, ["A", "B", "C"])
    assert s["questions"] == 6
    assert s["code_hit"]["A"] == {"k": 1, "n": 2, "rate": 0.5}   # c2 only
    assert s["code_hit"]["B"] == {"k": 2, "n": 2, "rate": 1.0}   # purpose not in the headline
    assert s["doc_hit"]["A"] == {"k": 1, "n": 1, "rate": 1.0}    # only p1 has a doc range
    assert s["doc_hit"]["C"] == {"k": 0, "n": 1, "rate": 0.0}
    assert s["answered_correct_file"] == {"k": 2, "n": 3, "rate": 0.667}
    assert s["graph"]["routing"]["k"] == 1 and s["graph"]["exact_all"]["rate"] == 1.0
    assert s["unanswerable_ok"] == {"n": 2, "pass": 1, "fail": 0, "awaiting_human": 1}
    assert s["citation_validity"] == {"k": 4, "n": 5, "rate": 0.8}
    assert s["citation_validity_citations"] == {"k": 4, "n": 5, "rate": 0.8}
    assert s["faithful_human"]["awaiting_human"] == 5
    assert s["llm_calls"] == 5 and s["tokens_in"] == 500


def test_summary_has_no_question_ids_or_text():
    outs = build(RECORDS, QUESTIONS)
    text = repr(m.grouped(QUESTIONS, outs, RECORDS, ["A", "B", "C"]))
    for question in QUESTIONS:
        assert f"'{question['id']}'" not in text
    for record in RECORDS.values():
        assert record["answer"] not in text
    assert "How?" not in text


def test_grouped_breakdowns():
    outs = build(RECORDS, QUESTIONS)
    g = m.grouped(QUESTIONS, outs, RECORDS, ["A", "B", "C"])
    assert set(g["per_repo"]) == {"o/r", "o/s"} and g["per_repo"]["o/s"]["questions"] == 1
    assert g["per_writer"]["W3"]["questions"] == 1 and g["per_writer"]["W1"]["questions"] == 4
    assert set(g["per_type"]) == set(m.TYPES)


def test_judgments_complete_the_summary():
    judgments = {"f1": {"rejects_premise": "yes", "false_claim_cited": "no",
                        "faithful": "partly"}, "c1": {"faithful": "yes"}}
    outs = build(RECORDS, QUESTIONS, judgments)
    s = m.summarise(QUESTIONS, outs, RECORDS, ["A", "B", "C"])
    assert s["unanswerable_ok"] == {"n": 2, "pass": 2, "fail": 0, "awaiting_human": 0}
    assert s["faithful_human"]["yes"] == 1 and s["faithful_human"]["partly"] == 1
    assert s["faithful_human"]["awaiting_human"] == 3


def test_comparisons_over_headline_questions():
    outs = build(RECORDS, QUESTIONS)
    c = m.comparisons(QUESTIONS, outs, [("B", "A"), ("C", "B")])
    assert c["B vs A"] == {"questions": 2, "wins": 1, "losses": 0, "p_mcnemar_exact": 1.0}
    assert c["C vs B"]["wins"] == 0 and c["C vs B"]["losses"] == 0


def test_agreement():
    outs_1 = build(RECORDS, QUESTIONS)
    records_2 = copy.deepcopy(RECORDS)
    records_2["c1"]["citations"] = ["z.py:1-2"]         # answered_correct_file flips
    records_2["u1"]["answer"] = "Not here (a.py:1-2)."  # now pending: left out
    records_2["u1"]["citations"] = ["a.py:1-2"]
    outs_2 = build(records_2, QUESTIONS)
    a = m.agreement(outs_1, outs_2)
    assert a["answered_correct_file"] == {"k": 2, "n": 3, "rate": 0.667, "left_out_pending": 0}
    assert a["route"]["rate"] == 1.0
    assert a["unanswerable_ok"]["n"] == 0 and a["unanswerable_ok"]["left_out_pending"] == 2
    assert a["retrieval_identical"] is True
    records_2["c1"]["retrieval"]["A"] = [sent("a.py", 10, 10)]
    assert m.agreement(outs_1, build(records_2, QUESTIONS))["retrieval_identical"] is False


def test_empty_groups_do_not_divide_by_zero():
    only_graph = [q("g1", "graph")]
    outs = build({"g1": RECORDS["g1"]}, only_graph)
    s = m.summarise(only_graph, outs, RECORDS, ["A", "B", "C"])
    assert s["code_hit"]["A"] == {"k": 0, "n": 0, "rate": None}
    assert s["citation_validity"]["rate"] is None and s["cited_sentence_rate"]["rate"] is None
