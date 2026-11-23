"""Unit tests for eval/judging_mix.py on synthetic sheets and keys written in the same format as
`locked_eval.py sheet`. No database, no LLM, no network.

    uv run --project backend python -m pytest -q -p no:cacheprovider eval/test_judging_mix.py
"""

import csv
import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import judging_mix as jm  # noqa: E402
import locked_eval as le  # noqa: E402
import pytest  # noqa: E402

LABELS = ("alphaversion", "betaversion")


def make_source(folder: Path, label: str, n_questions: int = 50, pass2: int = 47,
                premise_every: int = 10) -> tuple[Path, Path]:
    """A sheet + key like cmd_sheet writes: hex row ids, pass 1 for every question, pass 2 for
    the first `pass2`, shuffled order, BOM, the sheet's own columns."""
    folder.mkdir(parents=True, exist_ok=True)
    rows, key = [], {}
    for p, count in ((1, n_questions), (2, pass2)):
        for i in range(count):
            row_id = secrets.token_hex(4)
            while row_id in key:
                row_id = secrets.token_hex(4)
            qid = f"Q{i:02d}"
            key[row_id] = {"pass": p, "id": qid}
            rows.append({
                "row": row_id, "question": f"question text {qid}?",
                "answer": f"answer {secrets.token_hex(3)} {qid} body",
                "cited_lines": f"a.py:1-2\n1| x{i}",
                "premise_truth": "premise" if i % premise_every == 0 else "",
                "faithful": "", "rejects_premise": "", "false_claim_cited": "", "note": "",
            })
    rows.reverse()
    sheet = folder / f"locked-{label}-sheet.csv"
    keyfile = folder / f"locked-{label}-KEY-do-not-open.json"
    with sheet.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=le.SHEET_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    keyfile.write_text(json.dumps({"results": "eval/results/x.json", "rows": key}, indent=1),
                       encoding="utf-8")
    return sheet, keyfile


@pytest.fixture
def sources(tmp_path):
    return [(label, *make_source(tmp_path / label, label)) for label in LABELS]


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_mix_keeps_pass_1_only_and_maps_every_row_back_once(sources, tmp_path, capsys):
    sheet, keyfile = jm.mix(sources, tmp_path / "mixed")
    rows, combined = read(sheet), json.loads(keyfile.read_text(encoding="utf-8"))
    assert len(rows) == 100 and [r["row"] for r in rows] == [str(n) for n in range(1, 101)]
    assert tuple(read(sheet)[0]) == le.SHEET_COLUMNS
    assert all(r[c] == "" for r in rows for c in jm.JUDGED)
    # every pass-1 row of each version exactly once; no pass-2 row
    mapped = [(m["version"], m["row"]) for m in combined["rows"].values()]
    assert len(mapped) == len(set(mapped)) == 100
    for label, _, kf in sources:
        key = json.loads(kf.read_text(encoding="utf-8"))["rows"]
        mine = {row for v, row in mapped if v == label}
        assert mine == {i for i, k in key.items() if k["pass"] == 1}
    # text copied from the right original row
    originals = {label: {r["row"]: r for r in read(s)} for label, s, _ in sources}
    for r in rows:
        m = combined["rows"][r["row"]]
        o = originals[m["version"]][m["row"]]
        assert all(r[c] == o[c] for c in ("question", "answer", "cited_lines", "premise_truth"))
    # no version, pass or configuration in the sheet or the file names
    text = sheet.read_text(encoding="utf-8-sig")
    assert not any(label in text for label in LABELS)
    assert not any(label in p.name for p in (sheet, keyfile) for label in LABELS)
    # counts only on stdout
    out = capsys.readouterr().out
    assert "question text" not in out and "answer " not in out and "a.py" not in out
    assert f"seed {jm.DEFAULT_SEED}" in out


def test_seed_is_reproducible(sources, tmp_path):
    a, _ = jm.mix(sources, tmp_path / "a", seed=7)
    b, _ = jm.mix(sources, tmp_path / "b", seed=7)
    c, _ = jm.mix(sources, tmp_path / "c", seed=8)
    assert a.read_bytes() == b.read_bytes()
    assert a.read_bytes() != c.read_bytes()


def test_mix_checks_counts_and_ids(tmp_path):
    good = ("alphaversion", *make_source(tmp_path / "g", "alphaversion"))
    short = ("betaversion", *make_source(tmp_path / "s", "betaversion", n_questions=49))
    with pytest.raises(SystemExit, match="exactly 50"):
        jm.mix([good, short], tmp_path / "o1")
    other = ("betaversion", *make_source(tmp_path / "x", "betaversion"))
    key = json.loads(other[2].read_text(encoding="utf-8"))
    first_p1 = next(i for i, k in key["rows"].items() if k["pass"] == 1)
    key["rows"][first_p1]["id"] = "Q99"  # a question only this version has
    other[2].write_text(json.dumps(key), encoding="utf-8")
    with pytest.raises(SystemExit, match="question ids differ"):
        jm.mix([good, other], tmp_path / "o2")
    key["rows"][first_p1]["id"] = "Q01"  # now Q01 twice in pass 1
    other[2].write_text(json.dumps(key), encoding="utf-8")
    with pytest.raises(SystemExit, match="1 repeats"):
        jm.mix([good, other], tmp_path / "o3")
    assert not any((tmp_path / f"o{i}").exists() for i in (1, 2, 3))


def test_mix_never_overwrites(sources, tmp_path):
    jm.mix(sources, tmp_path / "m")
    with pytest.raises(SystemExit, match="never overwritten"):
        jm.mix(sources, tmp_path / "m")


def test_find_inputs_from_folder(sources, tmp_path):
    label, sheet, keyfile = sources[0]
    assert jm.find_inputs([label, str(sheet.parent)]) == (label, sheet, keyfile)
    with pytest.raises(SystemExit, match="expected one"):
        jm.find_inputs([label, str(tmp_path)])


def fill(sheet: Path) -> None:
    """Judge the mixed sheet blind: the verdict depends only on the row's own answer text."""
    rows = read(sheet)
    for r in rows:
        r["faithful"] = ("yes", "partly", "no")[sum(map(ord, r["answer"])) % 3]
        if r["premise_truth"]:
            r["rejects_premise"], r["false_claim_cited"] = "yes", "no"
        r["note"] = "n" + r["row"]
    jm.write_sheet(sheet, rows)


def test_unmix_round_trip_is_read_by_judge(sources, tmp_path, capsys):
    sheet, keyfile = jm.mix(sources, tmp_path / "mixed")
    fill(sheet)
    written = jm.unmix(sheet, keyfile, tmp_path / "filled")
    for label, orig_sheet, orig_key in sources:
        orig = read(orig_sheet)
        got = read(written[label])
        key = json.loads(orig_key.read_text(encoding="utf-8"))["rows"]
        assert [r["row"] for r in got] == [r["row"] for r in orig]  # same rows, same order
        for o, g in zip(orig, got, strict=True):
            assert all(o[c] == g[c] for c in ("question", "answer", "cited_lines",
                                               "premise_truth"))
            if key[g["row"]]["pass"] == 1:
                assert g["faithful"] == ("yes", "partly", "no")[sum(map(ord, g["answer"])) % 3]
                assert g["note"].startswith("n")
                assert (g["rejects_premise"] == "yes") == bool(g["premise_truth"])
            else:
                assert all(g[c] == "" for c in jm.JUDGED)
        # the existing judge command's reader takes it unchanged; pass 2 is awaiting
        judgments = le.read_judgments(written[label], key)
        assert len(judgments["1"]) == 50
        assert all(v["faithful"] in ("yes", "partly", "no") for v in judgments["1"].values())
        assert all(v == {} for v in judgments["2"].values()) and len(judgments["2"]) == 47
    out = capsys.readouterr().out
    assert "question text" not in out and "answer " not in out


def test_unmix_rejects_bad_values_and_changed_sources(sources, tmp_path):
    sheet, keyfile = jm.mix(sources, tmp_path / "mixed")
    rows = read(sheet)
    rows[0]["faithful"] = "maybe"
    jm.write_sheet(sheet, rows)
    with pytest.raises(SystemExit, match="faithful must be"):
        jm.unmix(sheet, keyfile, tmp_path / "f1")
    rows[0]["faithful"] = "yes"
    jm.write_sheet(sheet, rows[1:])  # a row lost
    with pytest.raises(SystemExit, match="do not match"):
        jm.unmix(sheet, keyfile, tmp_path / "f2")
    jm.write_sheet(sheet, rows)
    sources[0][1].write_text(sources[0][1].read_text(encoding="utf-8-sig") + "\n",
                             encoding="utf-8-sig")
    with pytest.raises(SystemExit, match="changed since mix"):
        jm.unmix(sheet, keyfile, tmp_path / "f3")


def test_refuses_inside_the_repo(sources, tmp_path):
    inside = le.ROOT / "eval" / "_judging_mix_should_not_exist"
    with pytest.raises(SystemExit, match="outside the repository"):
        jm.mix(sources, inside)
    sheet, keyfile = jm.mix(sources, tmp_path / "mixed")
    with pytest.raises(SystemExit, match="outside the repository"):
        jm.unmix(sheet, keyfile, inside)
    assert not inside.exists()
