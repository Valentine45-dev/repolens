"""Unit tests for the locked-run runner's guards, spend meter, blind sheet and summary printing
(eval/locked_eval.py). No database, no LLM, no network.

    uv run --project backend python -m pytest -q -p no:cacheprovider eval/test_locked_eval.py
"""

import csv
import hashlib
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import locked_eval as le  # noqa: E402
import pytest  # noqa: E402
from test_locked_metrics import QUESTIONS, RECORDS, q, rec  # noqa: E402


class Done:
    def __init__(self, tokens_in=1000, tokens_out=100):
        self.tokens_in, self.tokens_out, self.stop_reason = tokens_in, tokens_out, "end_turn"


class Inner:
    name, settings, counts_toward_budget = "fake", {"effort": "low", "thinking": "x"}, False

    def __init__(self):
        self.calls = 0

    def complete(self, system, prompt, max_tokens, timeout):
        self.calls += 1
        return Done()


# ---- guards --------------------------------------------------------------------------------

def frozen_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "repo"
    (root / "eval" / "locked").mkdir(parents=True)
    for f in (*le.SCORING_FILES, le.RUNNER_FILE):
        (root / f).write_bytes(b"code\r\nmore\r\n")  # CRLF checkout
    manifest = root / "eval" / "locked" / "scorer.sha256"
    manifest.write_text("".join(f"{le.text_sha256(root / f)}  {f}\n"
                                for f in (*le.SCORING_FILES, le.RUNNER_FILE)), encoding="utf-8")
    questions = root / "eval" / "locked" / "v2.0.yaml"
    questions.write_bytes(b"schema: 1\r\n")
    (root / "eval" / "locked" / "v2.0.sha256").write_text(
        hashlib.sha256(b"schema: 1\r\n").hexdigest().upper() + "\n", encoding="utf-8")
    return root, manifest, questions


def test_text_hash_ignores_line_endings(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"x\r\ny\r\n")
    b.write_bytes(b"x\ny\n")
    assert le.text_sha256(a) == le.text_sha256(b)
    assert le.file_sha256(a) != le.file_sha256(b)  # the question file hash is exact bytes


def test_locked_guard_accepts_the_frozen_state(tmp_path):
    root, manifest, questions = frozen_tree(tmp_path)
    got = le.locked_guard(questions, dirty=False, runner_changed_ok=False,
                          manifest_path=manifest, root=root)
    assert got == {"questions_sha256": hashlib.sha256(b"schema: 1\r\n").hexdigest(),
                   "runner_changed": False}


def test_locked_guard_refuses(tmp_path):
    root, manifest, questions = frozen_tree(tmp_path)
    questions.write_bytes(b"schema: 1\n")  # one byte different from the committed hash
    (root / "eval" / "locked_metrics.py").write_text("changed", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        le.locked_guard(questions, dirty=True, runner_changed_ok=False, manifest_path=manifest,
                        root=root)
    text = str(e.value)
    assert "does not match" in text and "locked_metrics.py differs" in text
    assert "uncommitted" in text


def test_locked_guard_runner_change_needs_the_flag(tmp_path):
    root, manifest, questions = frozen_tree(tmp_path)
    (root / le.RUNNER_FILE).write_text("new config D", encoding="utf-8")
    with pytest.raises(SystemExit, match="--runner-changed"):
        le.locked_guard(questions, dirty=False, runner_changed_ok=False,
                        manifest_path=manifest, root=root)
    got = le.locked_guard(questions, dirty=False, runner_changed_ok=True,
                          manifest_path=manifest, root=root)
    assert got["runner_changed"] is True


def test_locked_guard_without_hash_or_manifest(tmp_path):
    root, manifest, questions = frozen_tree(tmp_path)
    (root / "eval" / "locked" / "v2.0.sha256").unlink()
    manifest.unlink()
    with pytest.raises(SystemExit) as e:
        le.locked_guard(questions, dirty=False, runner_changed_ok=False,
                        manifest_path=manifest, root=root)
    assert "not committed" in str(e.value) and "scorer freeze" in str(e.value)


def test_check_cap():
    le.check_cap(0.99, 1.0)
    with pytest.raises(SystemExit, match="over the"):
        le.check_cap(1.01, 1.0)


# ---- spend meter ---------------------------------------------------------------------------

def test_meter_counts_and_reads_what_was_sent():
    meter = le.Meter(Inner(), price_in=2.0, price_out=10.0, cap=1.0)
    prompt = ('<snippet source="src/a.py:10-20" symbol="f">\n...\n</snippet>\n'
              '<snippet source="lib/b.js:1-5" symbol="g">\n...\n</snippet>')
    meter.complete("system", prompt, 4000, 30)
    assert meter.log[0]["sent"] == [{"path": "src/a.py", "start": 10, "end": 20},
                                    {"path": "lib/b.js", "start": 1, "end": 5}]
    assert meter.spent == pytest.approx((1000 * 2 + 100 * 10) / 1e6)


def test_meter_cap_arithmetic():
    inner = Inner()
    meter = le.Meter(inner, price_in=0.0, price_out=10.0, cap=0.08)
    meter.complete("s", "p", 4000, 30)  # worst 0.04, actual 0.001
    meter.complete("s", "p", 4000, 30)  # 0.001 + 0.04 <= 0.08
    meter.spent = 0.05
    with pytest.raises(le.SpendCapStop):
        meter.complete("s", "p", 4000, 30)  # 0.05 + 0.04 > 0.08
    assert inner.calls == 2


# ---- blind sheet ---------------------------------------------------------------------------

def passes(void_second=False):
    return [{"pass": 1, "void": False, "records": list(RECORDS.values())},
            {"pass": 2, "void": void_second, "records": list(RECORDS.values())}]


def test_sheet_rows_are_blind_and_map_back():
    rows, key = le.sheet_rows(QUESTIONS, passes(), lambda repo, c: f"{c}\n10| code",
                              random.Random(1))
    # AI answers c1, c2, p1, u1, f1 (graph-routed g1 needs no judging), twice
    assert len(rows) == 10 and len(key) == 10
    assert all(set(r) == set(le.SHEET_COLUMNS) for r in rows)
    flat = repr(rows)
    for word in ("pass", "config", "'C'", "graph", "W1", "code_how"):
        assert word not in flat
    assert sorted((v["pass"], v["id"]) for v in key.values()) == sorted(
        (p, i) for p in (1, 2) for i in ("c1", "c2", "p1", "u1", "f1"))
    f1 = [r for r in rows if key[r["row"]]["id"] == "f1"]
    assert f1[0]["premise_truth"] == "It does not exist." and "a.py:1-2" in f1[0]["cited_lines"]
    assert all(r["premise_truth"] == "" for r in rows if key[r["row"]]["id"] == "c1")


def test_sheet_skips_void_passes_and_is_shuffled():
    rows, key = le.sheet_rows(QUESTIONS, passes(void_second=True), lambda r, c: c,
                              random.Random(3))
    assert {v["pass"] for v in key.values()} == {1}
    order = [key[r["row"]]["id"] for r in rows]
    assert order != ["c1", "c2", "p1", "u1", "f1"]


def write_sheet(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=le.SHEET_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def test_read_judgments(tmp_path):
    rows, key = le.sheet_rows(QUESTIONS, passes(void_second=True), lambda r, c: c,
                              random.Random(2))
    for r in rows:
        r["faithful"] = "Yes"
        if r["premise_truth"]:
            r["rejects_premise"], r["false_claim_cited"] = "yes", "no"
    path = tmp_path / "sheet.csv"
    write_sheet(path, rows)
    got = le.read_judgments(path, key)
    assert set(got) == {"1"}
    assert got["1"]["c1"] == {"faithful": "yes"}
    assert got["1"]["f1"] == {"faithful": "yes", "rejects_premise": "yes",
                              "false_claim_cited": "no"}


def test_read_judgments_rejects_bad_values(tmp_path):
    rows, key = le.sheet_rows(QUESTIONS, passes(void_second=True), lambda r, c: c,
                              random.Random(2))
    rows[0]["faithful"] = "mostly"
    rows[1]["false_claim_cited"] = "maybe"
    rows.append({**rows[2], "row": "zzzz"})
    path = tmp_path / "sheet.csv"
    write_sheet(path, rows)
    with pytest.raises(SystemExit) as e:
        le.read_judgments(path, key)
    text = str(e.value)
    assert "yes, partly or no" in text and "must be yes or no" in text and "not in the key" in text


# ---- summaries -----------------------------------------------------------------------------

def test_summaries_two_passes_agree_and_print_no_question_content():
    s = le.summaries(QUESTIONS, passes())
    assert len(s["passes"]) == 2
    assert s["agreement_pass_1_2"]["route"]["rate"] == 1.0
    text = le.format_summary(s)
    assert "agreement" in text and "code_hit@k" in text and "not conclusive" in text
    for question in QUESTIONS:
        assert f" {question['id']} " not in text and question["question"] not in text
    for record in RECORDS.values():
        assert record["answer"] not in text


def test_summaries_void_pass_reported_but_not_agreed():
    s = le.summaries(QUESTIONS, passes(void_second=True))
    assert s["passes"][1]["void"] and "agreement_pass_1_2" not in s
    assert "VOID" in le.format_summary(s)


def test_judgments_flow_into_the_summary():
    judgments = {"1": {"f1": {"rejects_premise": "yes", "false_claim_cited": "no",
                              "faithful": "yes"}}}
    s = le.summaries(QUESTIONS, passes(), judgments)
    assert s["passes"][0]["grouped"]["overall"]["unanswerable_ok"]["pass"] == 2
    assert s["passes"][1]["grouped"]["overall"]["unanswerable_ok"]["pass"] == 1


def test_fixtures_are_valid_question_entries():
    from locked_metrics import validate_questions

    assert validate_questions({"schema": 1, "questions": QUESTIONS}) == []
    assert rec()["route"] == "ai" and q()["type"] == "code_how"
