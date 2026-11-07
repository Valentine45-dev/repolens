"""Categories, placeholders, documentation and quality findings, end to end: a small repo written
at test time (secrets are assembled here so no fake credential sits in the source tree)."""

import pytest
from conftest import query

pytestmark = pytest.mark.db

FILES = {
    "src/config.py": 'API_KEY = "changeme-' + 'please"\nPASSWORD = "admin' + '123"\n',
    "docs/guide.md": 'Set `SECRET_KEY = "s3cr3t-' + 'value-xyz"` in your settings.\n',
    "src/app.py": (
        "from .gone import thing\n"
        "try:\n    from .optional import fast\nexcept ImportError:\n    fast = None\n\n\n"
        "def handler(items=[]):\n    return undefined_name\n"
    ),
    "src/__init__.py": "",
    "tests/test_app.py": "from .gone import x\n\n\ndef test_it():\n    return also_undefined\n",
}


@pytest.fixture
def quality_repo(client, monkeypatch):
    from app.ingest import clone

    def fetch(url, sha, dest, timeout):
        for rel, text in FILES.items():
            path = dest / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    monkeypatch.setattr(clone, "fetch_commit", fetch)
    body = client.post("/repos", json={"url": "https://github.com/example/quality"}).json()
    assert client.get(f"/snapshots/{body['snapshot_id']}/status").json()["status"] == "done"
    return body["snapshot_id"]


def findings(client, snapshot, **params):
    return client.get(f"/snapshots/{snapshot}/findings", params={"limit": 200, **params}).json()


def test_secret_flags_and_severity(client, quality_repo):
    items = {i["path"] + ":" + str(i["line"]): i
             for i in findings(client, quality_repo)["items"] if i["rule_id"] == "hardcoded-secret"}
    placeholder = items["src/config.py:1"]
    assert (placeholder["placeholder"], placeholder["severity"], placeholder["in_docs"]) == (
        True, "low", False)
    assert placeholder["message"].endswith("; the value looks like a placeholder.")
    weak = items["src/config.py:2"]  # a weak real password is NOT a placeholder
    assert (weak["placeholder"], weak["severity"]) == (False, "high")
    docs = items["docs/guide.md:1"]
    assert (docs["in_docs"], docs["severity"], docs["in_test"], docs["placeholder"]) == (
        True, "low", False, False)
    assert docs["message"] == "Possible hardcoded secret (secret-assignment) in documentation."
    assert all(i["category"] == "security" for i in items.values())


def test_values_are_never_stored(client, quality_repo):
    for text in ("changeme-please", "admin123", "s3cr3t-value-xyz"):
        assert not query("SELECT 1 FROM files WHERE content LIKE %s", f"%{text}%")
        assert not query("SELECT 1 FROM findings WHERE snippet LIKE %s OR message LIKE %s",
                         f"%{text}%", f"%{text}%")


def test_placeholders_sort_last_and_can_be_hidden(client, quality_repo):
    all_items = findings(client, quality_repo)["items"]
    flags = [i["placeholder"] for i in all_items]
    assert flags == sorted(flags)  # False first; the placeholder is the last row
    assert all_items[-1]["placeholder"] is True
    hidden = findings(client, quality_repo, placeholder="false")
    assert all(not i["placeholder"] for i in hidden["items"])
    assert hidden["total"] == len(all_items) - 1
    counts = findings(client, quality_repo)["counts"]
    assert (counts["placeholders"], counts["documentation"]) == (1, 1)


def test_quality_findings_and_category_filter(client, quality_repo):
    body = findings(client, quality_repo)
    quality = findings(client, quality_repo, category="quality")["items"]
    security = findings(client, quality_repo, category="security")["items"]
    assert {i["rule_id"] for i in quality} == {
        "broken-internal-import", "ruff-B006", "ruff-F821",
    }
    assert {i["category"] for i in quality} == {"quality"}
    assert all(i["category"] == "security" for i in security)
    assert len(quality) + len(security) == body["total"]
    assert body["counts"]["by_category"] == {"security": len(security), "quality": len(quality)}
    assert body["notes"] == []

    broken = next(i for i in quality if i["rule_id"] == "broken-internal-import")
    assert (broken["path"], broken["line"], broken["severity"]) == ("src/app.py", 1, "medium")
    assert broken["message"] == "Import of `src.gone` matches no file in this repository."
    assert broken["symbol"] is None  # module level
    undefined = next(i for i in quality if i["rule_id"] == "ruff-F821")
    assert (undefined["path"], undefined["line"], undefined["symbol"]) == (
        "src/app.py", 9, "handler")


def test_tests_are_not_checked_by_the_new_quality_checks(client, quality_repo):
    paths = {i["path"] for i in findings(client, quality_repo, category="quality")["items"]}
    assert paths == {"src/app.py"}  # tests/test_app.py has a broken import and an undefined name


def test_unknown_category_is_rejected(client, quality_repo):
    r = client.get(f"/snapshots/{quality_repo}/findings", params={"category": "style"})
    assert r.status_code == 422


def test_a_ruff_failure_is_reported_in_notes_and_other_findings_stay(
    client, monkeypatch
):
    from app.detect.ruff import RuffError
    from app.ingest import clone, pipeline

    def broken(files):
        raise RuffError("Code-quality checks timed out after 60 s.")

    def fetch(url, sha, dest, timeout):
        for rel, text in FILES.items():
            path = dest / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    monkeypatch.setattr(clone, "fetch_commit", fetch)
    monkeypatch.setattr(pipeline, "run_ruff", broken)
    body = client.post("/repos", json={"url": "https://github.com/example/quality2"}).json()
    snapshot = body["snapshot_id"]
    assert client.get(f"/snapshots/{snapshot}/status").json()["status"] == "done"
    result = findings(client, snapshot)
    assert result["notes"] == ["Code-quality checks timed out after 60 s."]
    rules = {i["rule_id"] for i in result["items"]}
    assert "broken-internal-import" in rules and "hardcoded-secret" in rules
    assert not any(r.startswith("ruff-") for r in rules)


def test_rules_endpoint_carries_categories(client):
    rules = {r["id"]: r for r in client.get("/rules").json()}
    assert rules["py-bare-except"]["category"] == "quality"
    assert rules["hardcoded-secret"]["category"] == "security"
    assert rules["ruff-F821"]["category"] == "quality"
    assert rules["broken-internal-import"]["category"] == "quality"
    assert {r["category"] for r in rules.values() if r["id"].startswith(("py-eval", "js-"))} == {
        "security"}
