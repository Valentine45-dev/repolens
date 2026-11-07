"""Categories, placeholders, documentation and quality findings, end to end: a small repo written
at test time (secrets are assembled here so no fake credential sits in the source tree)."""

import pytest
from conftest import query

pytestmark = pytest.mark.db

FILES = {
    "src/config.py": 'API_KEY = "changeme-' + 'please"\nPASSWORD = "admin' + '123"\n',
    "docs/guide.md": 'Set `SECRET_KEY = "s3cr3t-' + 'value-xyz"` in your settings.\n',
    "docs/setup.md": 'Use `TOKEN = "<your-' + 'token>"` here.\n',
    "src/settings.example.py": 'SECRET_KEY = "your-secret-' + 'key-here"\n',
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
    # a stand-in value in code keeps its severity and is only noted
    template = items["src/config.py:1"]
    assert (template["template_value"], template["placeholder"], template["severity"]) == (
        True, False, "high")
    assert template["message"].endswith("; looks like a template value.")
    weak = items["src/config.py:2"]  # a weak real password is NOT a placeholder
    assert (weak["placeholder"], weak["template_value"], weak["severity"]) == (False, False, "high")
    # the same kind of value in files that do not run is demoted
    for key in ("src/settings.example.py:1", "docs/setup.md:1"):
        item = items[key]
        assert (item["placeholder"], item["template_value"], item["severity"]) == (
            True, False, "low")
        assert item["message"].endswith("; the value looks like a placeholder.")
    docs = items["docs/guide.md:1"]
    assert (docs["in_docs"], docs["severity"], docs["in_test"], docs["placeholder"]) == (
        True, "low", False, False)
    assert docs["message"] == "Possible hardcoded secret (secret-assignment) in documentation."
    assert items["docs/setup.md:1"]["in_docs"] and not items["src/settings.example.py:1"]["in_docs"]
    assert all(i["category"] == "security" for i in items.values())


def test_values_are_never_stored(client, quality_repo):
    for text in ("changeme-please", "admin123", "s3cr3t-value-xyz", "your-secret-key-here"):
        assert not query("SELECT 1 FROM files WHERE content LIKE %s", f"%{text}%")
        assert not query("SELECT 1 FROM findings WHERE snippet LIKE %s OR message LIKE %s",
                         f"%{text}%", f"%{text}%")


def test_placeholders_sort_last_and_can_be_hidden(client, quality_repo):
    all_items = findings(client, quality_repo)["items"]
    flags = [i["placeholder"] for i in all_items]
    assert flags == sorted(flags)  # False first; the two demoted placeholders are the last rows
    assert flags[-2:] == [True, True] and flags.count(True) == 2
    hidden = findings(client, quality_repo, placeholder="false")
    assert all(not i["placeholder"] for i in hidden["items"])
    assert hidden["total"] == len(all_items) - 2
    counts = findings(client, quality_repo)["counts"]
    assert (counts["placeholders"], counts["documentation"], counts["template_values"]) == (2, 2, 1)


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


def test_detect_replaces_rows_of_rules_no_longer_in_the_catalogue(client, quality_repo):
    from app.ingest import pipeline

    file_id = query("SELECT id FROM files WHERE snapshot_id = %s AND path = 'src/app.py'",
                    quality_repo)[0]["id"]
    query("INSERT INTO findings (snapshot_id, file_id, line, rule_id, severity, message)"
          " VALUES (%s, %s, 1, 'ruff-GONE', 'low', 'stale') RETURNING id", quality_repo, file_id)
    pipeline.store_findings(quality_repo, pipeline.parse_stored(quality_repo))
    rules = {r["rule_id"] for r in query(
        "SELECT rule_id FROM findings WHERE snapshot_id = %s", quality_repo)}
    assert "ruff-GONE" not in rules
    assert {"hardcoded-secret", "ruff-F821"} <= rules  # secrets stay, current rules are rebuilt


def test_rules_endpoint_carries_categories(client):
    rules = {r["id"]: r for r in client.get("/rules").json()}
    assert rules["py-bare-except"]["category"] == "quality"
    assert rules["hardcoded-secret"]["category"] == "security"
    assert rules["ruff-F821"]["category"] == "quality"
    assert rules["broken-internal-import"]["category"] == "quality"
    assert {r["category"] for r in rules.values() if r["id"].startswith(("py-eval", "js-"))} == {
        "security"}
