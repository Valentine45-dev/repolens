"""The retrieval eval's scoring rule (fixed before the first run): a hit at k is any retrieved
chunk overlapping any labelled range of the same path. Synthetic data only."""

import importlib.util
import sys
from pathlib import Path

from app.qa.retrieve import Snippet

EVAL = Path(__file__).resolve().parents[2] / "eval"


def load():
    sys.path.insert(0, str(EVAL))  # retrieval_recall imports runinfo as a sibling
    spec = importlib.util.spec_from_file_location("retrieval_recall", EVAL / "retrieval_recall.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snip(path, start, end):
    return Snippet(0, 0, 0, path, "q", start, end, "", False, 0.1, "search")


LABELS = [{"path": "lib/a.js", "start": 10, "end": 20}, {"path": "lib/b.js", "start": 5, "end": 5}]


def test_overlap_rule():
    rr = load()
    assert rr.is_hit([snip("lib/a.js", 18, 40)], LABELS)  # partial overlap counts
    assert rr.is_hit([snip("lib/a.js", 20, 20)], LABELS)  # touching the last line counts
    assert rr.is_hit([snip("lib/b.js", 1, 9)], LABELS)  # a range containing the label
    assert not rr.is_hit([snip("lib/a.js", 21, 30)], LABELS)  # just after
    assert not rr.is_hit([snip("lib/c.js", 10, 20)], LABELS)  # same lines, other file
    assert not rr.is_hit([], LABELS)


def test_first_hit_rank():
    rr = load()
    ranked = [snip("lib/c.js", 1, 9), snip("lib/a.js", 1, 9), snip("lib/a.js", 9, 12)]
    assert rr.first_hit_rank(ranked, LABELS) == 3
    assert rr.first_hit_rank(ranked[:2], LABELS) is None


def test_unanswerable_questions_are_not_scored():
    rr = load()
    hit = {"hit": True}
    miss = {"hit": False}
    rows = [
        {"repo": "a", "unanswerable": False, "first_hit_rank": 2,
         "configs": {"A": miss, "B": hit, "C": hit}},
        {"repo": "a", "unanswerable": True, "top_paths": ["x.py:1-2"]},  # no hits: never scored
    ]
    summary = rr.summarise(rows)
    assert summary["all"]["questions"] == 1 and summary["a"]["questions"] == 1
    assert summary["all"]["recall"] == {"A": 0.0, "B": 1.0, "C": 1.0}
    assert summary["all"]["mrr_search_16"] == 0.5


def test_configs_compare_c_with_b_at_equal_size():
    configs = load().CONFIGS
    assert configs["A"] == {"k": 8, "expand": False, "expand_max": 0}
    assert configs["B"]["k"] == configs["C"]["k"] + configs["C"]["expand_max"] == 16


def test_questions_file_is_well_formed():
    rr = load()
    repos = rr.load_questions(EVAL / "questions.yaml")
    ids = [q["id"] for repo in repos for q in repo["questions"]]
    assert ids == list(range(1, 17))
    for repo in repos:
        assert len(repo["commit"]) == 40
        for q in repo["questions"]:
            assert q["question"] and not q["question"].startswith("(")
            if q.get("unanswerable"):
                assert "expected" not in q and q["expected_behaviour"]
            else:
                assert q["expected"]
                for e in q["expected"]:
                    assert 1 <= e["start"] <= e["end"] and not e["path"].startswith("/")
