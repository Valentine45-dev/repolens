"""Reachability end to end: a small repo is written at test time, ingested by the real pipeline,
and the tiers, the reachability sort and the two reach endpoints are checked."""

import pytest

pytestmark = pytest.mark.db

FILES = {
    "pyproject.toml": (
        '[project]\nname = "demo"\n\n[project.scripts]\ndemo = "demo.cli:main"\n'
    ),
    "demo/__init__.py": "from .core import run\nfrom .tools import api_only\n",
    "demo/tools.py": "def api_only(cmd):\n    return eval(cmd)\n",
    "demo/core.py": (
        "def run(cmd):\n"
        "    return helper(cmd)\n\n\n"
        "def helper(cmd):\n"
        "    return eval(cmd)\n\n\n"
        "def orphan(cmd):\n"
        "    return eval(cmd)\n"
    ),
    "demo/cli.py": (
        "from .core import run\n"
        "from .handlers import pick\n\n\n"
        "def main():\n"
        "    run('x')\n"
        "    thing = pick()\n"
        "    thing.process('y')\n\n\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    ),
    "demo/handlers.py": (
        "class Handler:\n"
        "    def process(self, cmd):\n"
        "        return eval(cmd)\n\n"
        "    def never_called(self, cmd):\n"
        "        return eval(cmd)\n\n\n"
        "def pick():\n"
        "    return Handler()\n"
    ),
    "demo/unused.py": "def lonely(cmd):\n    return eval(cmd)\n",
    "docs/guide.md": 'Set `SECRET_KEY = "s3cr3t-' + 'value-xyz"` in your settings.\n',
}


@pytest.fixture
def reach_repo(client, monkeypatch):
    from app.ingest import clone

    def fetch(url, sha, dest, timeout):
        for rel, text in FILES.items():
            path = dest / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    monkeypatch.setattr(clone, "fetch_commit", fetch)
    body = client.post("/repos", json={"url": "https://github.com/example/reachdemo"}).json()
    assert client.get(f"/snapshots/{body['snapshot_id']}/status").json()["status"] == "done"
    return body["snapshot_id"]


def listing(client, snapshot, **params):
    return client.get(f"/snapshots/{snapshot}/findings",
                      params={"limit": 200, **params}).json()


def tiers_by_place(client, snapshot):
    items = listing(client, snapshot, sort="reachability")["items"]
    return {(i["path"], i["line"]): i["reach_tier"] for i in items}, items


def test_tiers_of_the_demo_repo(client, reach_repo):
    tiers, _ = tiers_by_place(client, reach_repo)
    assert tiers[("demo/core.py", 6)] == "solid"  # main -> run -> helper, and public API run
    assert tiers[("demo/core.py", 10)] == "none"  # orphan(): nothing calls it
    assert tiers[("demo/handlers.py", 3)] == "guess"  # thing.process(): receiver unknown, by name
    assert tiers[("demo/unused.py", 2)] == "none"
    assert tiers[("docs/guide.md", 1)] == "not_checked"  # documentation is not analysed code
    # an ordinary method of a class that is reached, which nothing calls: no structural edge
    assert tiers[("demo/handlers.py", 6)] == "none"
    assert tiers[("demo/tools.py", 2)] == "solid"  # exported by the package's __init__


def test_entry_class_is_recorded_per_finding_and_does_not_change_the_order(client, reach_repo):
    items = listing(client, reach_repo, sort="reachability")["items"]
    by_place = {(i["path"], i["line"]): i for i in items}
    assert by_place[("demo/core.py", 6)]["reach_entry_class"] == "app"  # a console script
    assert by_place[("demo/handlers.py", 3)]["reach_entry_class"] == "app"
    assert by_place[("demo/tools.py", 2)]["reach_entry_class"] == "public-api"  # only the API
    assert by_place[("demo/unused.py", 2)]["reach_entry_class"] is None
    assert by_place[("docs/guide.md", 1)]["reach_entry_class"] is None
    tools_id = by_place[("demo/tools.py", 2)]["id"]
    detail = client.get(f"/snapshots/{reach_repo}/findings/{tools_id}/reach").json()
    assert (detail["tier"], detail["entry_class"], detail["entry"]["kind"]) == (
        "solid", "public-api", "public-api")
    # the order key has no entry class in it: solid app and solid public-api findings are
    # ordered by severity, path and line like any two solid findings
    solid = [i for i in items if i["reach_tier"] == "solid"]
    assert {i["reach_entry_class"] for i in solid} == {"app", "public-api"}
    severity = {"high": 0, "medium": 1, "low": 2}
    expected = sorted(solid, key=lambda i: (
        severity[i["severity"]], i["path"].encode(), i["line"], i["id"]))
    assert [i["id"] for i in solid] == [i["id"] for i in expected]


def test_reachability_order_is_placeholders_last_then_tier_then_the_usual(client, reach_repo):
    _, items = tiers_by_place(client, reach_repo)
    ranks = {"solid": 0, "guess": 1, "not_checked": 1, "none": 2}
    keys = [(i["placeholder"], ranks[i["reach_tier"]]) for i in items]
    assert keys == sorted(keys)
    assert items[0]["reach_tier"] == "solid"
    assert items[-1]["reach_tier"] == "none"
    # same rows as the usual order, only arranged differently; the usual order is unchanged
    usual = listing(client, reach_repo)
    assert sorted(i["id"] for i in usual["items"]) == sorted(i["id"] for i in items)
    assert all(i["reach_tier"] is None for i in usual["items"])
    severity_then_path = sorted(
        usual["items"],
        key=lambda i: ({"high": 0, "medium": 1, "low": 2}[i["severity"]], i["path"]))
    assert [i["id"] for i in usual["items"]] == [i["id"] for i in severity_then_path]


def test_reachability_sort_pages_consistently(client, reach_repo):
    full = listing(client, reach_repo, sort="reachability")["items"]
    paged = []
    for offset in range(0, len(full), 2):
        paged += listing(client, reach_repo, sort="reachability", limit=2, offset=offset)["items"]
    assert [i["id"] for i in paged] == [i["id"] for i in full]


def test_finding_reach_path_and_entry(client, reach_repo):
    items = listing(client, reach_repo, sort="reachability")["items"]
    by_place = {(i["path"], i["line"]): i for i in items}

    def reach_of(place):
        return client.get(
            f"/snapshots/{reach_repo}/findings/{by_place[place]['id']}/reach").json()

    solid = reach_of(("demo/core.py", 6))
    assert solid["tier"] == "solid"
    assert solid["entry"]["kind"] in ("console-script", "main-block", "public-api")
    names = [s["name"] for s in solid["path"]]
    assert names[-1] == "helper"
    assert all(not s["guess"] for s in solid["path"])
    assert solid["path"][-1]["path"] == "demo/core.py" and solid["path"][-1]["start_line"] == 5

    guess = reach_of(("demo/handlers.py", 3))
    assert guess["tier"] == "guess"
    assert any(s["guess"] for s in guess["path"])

    for place, tier in ((("demo/unused.py", 2), "none"), (("docs/guide.md", 1), "not_checked")):
        none = reach_of(place)
        assert none["tier"] == tier and none["entry"] is None and none["path"] == []

    assert client.get(f"/snapshots/{reach_repo}/findings/999999999/reach").status_code == 404


def test_entry_points_listing_names_where_they_came_from(client, reach_repo):
    body = client.get(f"/snapshots/{reach_repo}/reach/entry-points").json()
    kinds = body["by_kind"]
    assert kinds["console-script"] >= 1 and kinds["main-block"] >= 1 and kinds["public-api"] >= 1
    script = next(i for i in body["items"] if i["kind"] == "console-script" and i["name"] == "main")
    assert script["label"] == "console script `demo`"
    assert script["detail"] == "pyproject.toml: demo.cli:main"
    assert script["path"] == "demo/cli.py"
    block = next(i for i in body["items"] if i["kind"] == "main-block")
    assert block["path"] == "demo/cli.py"


def test_unknown_sort_is_rejected(client, reach_repo):
    r = client.get(f"/snapshots/{reach_repo}/findings", params={"sort": "newest"})
    assert r.status_code == 422
