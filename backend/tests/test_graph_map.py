"""The folder-first map's rules, without a database. test_graph_levels_db.py runs them on a real
ingested fixture repo."""

import random

from app.graph_map import (
    VIEW_NODE_LIMIT,
    CodeFile,
    FileLink,
    MapSymbol,
    RepoMap,
    SymbolEdge,
    find_cycles,
    symbol_view,
)


def files(*paths: str, findings: dict[str, int] | None = None) -> list[CodeFile]:
    return [CodeFile(i, 1000 + i, p, "python", 10, findings=(findings or {}).get(p, 0))
            for i, p in enumerate(paths, start=1)]


def link(source: str, target: str, *, imports=1, calls=0, guess_calls=0, top=True,
         confidence=1.0) -> FileLink:
    return FileLink(source, target, imports, calls, guess_calls, confidence, top and imports == 1)


def repo(paths, links=(), other=None, *, exclude_tests=True, findings=None, available=True):
    return RepoMap(files(*paths, findings=findings), list(links), other or {},
                   exclude_tests=exclude_tests, cycles_available=available)


def ids(view) -> list[str]:
    return [n["id"] for n in view["nodes"]]


def by_id(view) -> dict[str, dict]:
    return {n["id"]: n for n in view["nodes"]}


def edge_map(view) -> dict[tuple[str, str], dict]:
    return {(e["source"], e["target"]): e for e in view["edges"]}


# --- cycles ------------------------------------------------------------------------------------

def test_find_cycles_two_components_sorted_and_no_self_loop():
    assert find_cycles("abcdef", [
        ("a", "b"), ("b", "a"),  # two
        ("c", "d"), ("d", "e"), ("e", "c"),  # three
        ("a", "c"),  # one way between them: still two components
        ("f", "f"),  # a self loop is not a cycle
    ]) == [["a", "b"], ["c", "d", "e"]]


def test_find_cycles_none_in_a_dag_and_ignores_unknown_files():
    assert find_cycles("abc", [("a", "b"), ("b", "c"), ("a", "c"), ("c", "x"), ("x", "a")]) == []


def test_find_cycles_survives_a_chain_deeper_than_the_recursion_limit():
    n = 20_000
    names = [f"m{i}" for i in range(n)]
    chain = [(names[i], names[i + 1]) for i in range(n - 1)]
    assert find_cycles(names, chain) == []
    ring = find_cycles(names, [*chain, (names[-1], names[0])])
    assert len(ring) == 1 and len(ring[0]) == n


def test_two_way_folder_edges_are_not_a_cycle():
    """challenge <-> scoring in PyGoat: both folders use each other, no file imports itself back,
    even with every import at the top level."""
    r = repo(["challenge/models.py", "challenge/views.py", "scoring/admin.py",
              "scoring/services.py"],
             [link("challenge/models.py", "scoring/services.py"),
              link("scoring/admin.py", "challenge/views.py")])
    view = r.folder_view("")
    edges = edge_map(view)
    assert set(edges) == {("dir:challenge", "dir:scoring"), ("dir:scoring", "dir:challenge")}
    assert [e["cycle_edges"] for e in edges.values()] == [0, 0]
    assert view["cycles"] == [] and view["cycles_available"] is True
    assert not any(n["in_cycle"] for n in view["nodes"])


def test_cycle_edges_count_only_imports_inside_one_file_cycle():
    r = repo(["a/p.py", "a/x.py", "b/q.py", "b/y.py"],
             [link("a/p.py", "b/q.py"), link("b/q.py", "a/p.py"),  # the cycle
              link("a/x.py", "b/y.py"),  # same folders, not in the cycle
              link("b/y.py", "a/p.py", top=False)])  # a function-local import
    view = r.folder_view("")
    edges = edge_map(view)
    assert edges["dir:a", "dir:b"]["cycle_edges"] == 1 and edges["dir:a", "dir:b"]["imports"] == 2
    assert edges["dir:b", "dir:a"]["cycle_edges"] == 1 and edges["dir:b", "dir:a"]["imports"] == 2
    assert view["cycles"] == [{"id": 1, "size": 2, "files": ["a/p.py", "b/q.py"]}]
    assert by_id(view)["dir:a"]["cycle_files"] == 1 and by_id(view)["dir:a"]["cycle_ids"] == [1]


def test_cycles_unknown_are_never_reported_as_none():
    r = repo(["a/p.py", "b/q.py"], [link("a/p.py", "b/q.py"), link("b/q.py", "a/p.py")],
             available=False)
    view = r.file_view("")
    assert view["cycles_available"] is False and view["cycles"] == []
    assert all(n["in_cycle"] is None and n["cycle_files"] is None for n in view["nodes"])
    assert all(e["cycle_edges"] is None for e in view["edges"])


def test_a_cycle_through_a_hidden_test_file_shows_only_with_tests():
    paths = ["src/a.py", "tests/b.py"]
    links = [link("src/a.py", "tests/b.py"), link("tests/b.py", "src/a.py")]
    assert repo(paths, links).folder_view("")["cycles"] == []
    assert repo(paths, links, exclude_tests=False).folder_view("")["cycles"] == [
        {"id": 1, "size": 2, "files": ["src/a.py", "tests/b.py"]}]


# --- the tree ----------------------------------------------------------------------------------

def test_chain_is_one_node_and_root_opens_where_there_is_something():
    r = repo(["src/pkg/deep/a.py", "src/pkg/deep/b.py"])
    for root in ("", "src", "src/pkg", "src/pkg/deep"):
        view = r.folder_view(root)
        assert view["root"] == "src/pkg/deep"
        assert view["breadcrumbs"] == [{"path": "src/pkg/deep", "label": ""}]
        assert ids(view) == ["file:src/pkg/deep/a.py", "file:src/pkg/deep/b.py"]
        assert [n["label"] for n in view["nodes"]] == ["a.py", "b.py"]


def test_merged_label_and_breadcrumbs():
    r = repo(["src/pkg/a.py", "src/pkg/b.py", "src/pkg/sub/inner/c.py", "src/pkg/sub/inner/d.py",
              "other/e.py", "other/f.py"])
    view = r.folder_view("")
    assert [(n["id"], n["label"]) for n in view["nodes"]] == [
        ("dir:other", "other"), ("dir:src/pkg", "src/pkg")]
    assert view["breadcrumbs"] == [{"path": "", "label": ""}]
    deep = r.folder_view("src/pkg/sub/inner")
    assert deep["breadcrumbs"] == [
        {"path": "", "label": ""}, {"path": "src/pkg", "label": "src/pkg"},
        {"path": "src/pkg/sub/inner", "label": "sub/inner"}]


def test_single_file_folder_is_a_file_node_with_its_folder_in_the_label():
    r = repo(["scoring/admin.py", "deep/er/only.py", "two/a.py", "two/b.py", "root.py"])
    view = r.folder_view("")
    assert [(n["id"], n["kind"], n["label"]) for n in view["nodes"]] == [
        ("dir:two", "folder", "two"),
        ("file:deep/er/only.py", "file", "deep/er/only.py"),
        ("file:root.py", "file", "root.py"),
        ("file:scoring/admin.py", "file", "scoring/admin.py"),
    ]
    assert by_id(view)["file:scoring/admin.py"]["file_id"] == 1


def test_single_file_folder_stays_a_folder_when_another_file_has_a_finding():
    """Otherwise a finding in its docker-compose.yml would vanish from the map."""
    r = repo(["lab/manage.py", "plain/manage.py"],
             other={"lab/docker-compose.yml": 2, "README.md": 1})
    view = r.folder_view("")
    assert [(n["id"], n["finding_count"]) for n in view["nodes"]] == [
        ("dir:lab", 2), ("file:plain/manage.py", 0)]
    assert view["other_findings"] == 1  # the README: on no node, still accounted for


def test_counts_on_a_folder_node_with_tests_hidden_and_shown():
    paths = ["pkg/a.py", "pkg/b.py", "pkg/tests.py", "pkg/sub/test_c.py", "pkg/sub/d.py"]
    finding = {"pkg/a.py": 2, "pkg/tests.py": 5}
    hidden = repo(paths, findings=finding, other={"pkg/x.yml": 1, "pkg/sub/tests/y.yml": 7})
    view = hidden.folder_view("")
    assert view["root"] == "pkg"  # nothing else at the top
    assert ids(view) == ["file:pkg/a.py", "file:pkg/b.py", "file:pkg/sub/d.py"]
    assert view["hidden_files"] == 2 and view["hidden_files_under_root"] == 2
    assert by_id(view)["file:pkg/a.py"]["finding_count"] == 2
    assert view["other_findings"] == 1  # pkg/x.yml; the one under tests/ is hidden

    shown = repo(paths, findings=finding, exclude_tests=False,
                 other={"pkg/x.yml": 1, "pkg/sub/tests/y.yml": 7}).folder_view("")
    assert shown["root"] == "pkg"
    node = by_id(shown)["dir:pkg/sub"]
    assert (node["file_count"], node["test_file_count"], node["finding_count"]) == (2, 1, 7)


def test_a_folder_with_only_hidden_files_is_an_empty_view_not_an_error():
    r = repo(["src/a.py", "src/b.py", "tests/unit/test_a.py"])
    assert r.is_folder("tests/unit") and not r.is_folder("nope") and not r.is_folder("src/a.py")
    view = r.folder_view("tests/unit")
    assert view["nodes"] == [] and view["hidden_files_under_root"] == 1
    assert view["breadcrumbs"] == [
        {"path": "", "label": ""}, {"path": "tests", "label": "tests"},
        {"path": "tests/unit", "label": "unit"}]


# --- aggregation -------------------------------------------------------------------------------

def test_aggregated_edge_adds_everything_and_keeps_the_best_confidence():
    r = repo(["a/x.py", "a/y.py", "b/z.py", "b/w.py"], [
        link("a/x.py", "b/z.py", imports=1, calls=3, guess_calls=2),
        link("a/y.py", "b/z.py", imports=0, calls=1, guess_calls=1, confidence=0.5),
    ])
    assert edge_map(r.folder_view(""))["dir:a", "dir:b"] == {
        "source": "dir:a", "target": "dir:b", "count": 5, "imports": 1, "calls": 4,
        "guess_calls": 3, "confidence": 1.0, "cycle_edges": 0, "guess": False,
    }


def test_all_guess_edge_stays_a_guess():
    r = repo(["a/x.py", "a/y.py", "b/z.py", "b/w.py"], [
        link("a/x.py", "b/z.py", imports=0, calls=2, guess_calls=2, confidence=0.5)])
    edge = edge_map(r.folder_view(""))["dir:a", "dir:b"]
    assert edge["guess"] is True and edge["confidence"] == 0.5 and edge["guess_calls"] == 2


def test_inside_and_outside_counts():
    r = repo(["a/x.py", "a/y.py", "b/z.py", "b/w.py", "c/v.py", "c/u.py"], [
        link("a/x.py", "a/y.py", calls=1),  # inside a
        link("a/x.py", "b/z.py"),  # crosses into the view of b
        link("c/v.py", "b/z.py", calls=2),
        link("b/z.py", "c/u.py"),
    ])
    root = by_id(r.folder_view(""))
    assert root["dir:a"]["internal_count"] == 2
    assert root["dir:a"]["outside_in"] == root["dir:a"]["outside_out"] == 0
    view = r.folder_view("b")
    assert view["edges"] == []
    node = by_id(view)["file:b/z.py"]
    assert (node["outside_in"], node["outside_out"]) == (1 + 3, 1)


def test_file_level_shows_every_file_under_the_folder():
    r = repo(["pkg/a.py", "pkg/sub/b.py", "pkg/sub/c.py", "other/d.py"],
             [link("pkg/a.py", "pkg/sub/b.py"), link("other/d.py", "pkg/a.py")])
    view = r.file_view("pkg")
    assert (view["level"], view["root"]) == ("file", "pkg")
    assert [n["label"] for n in view["nodes"]] == ["a.py", "sub/b.py", "sub/c.py"]
    assert set(edge_map(view)) == {("file:pkg/a.py", "file:pkg/sub/b.py")}
    assert by_id(view)["file:pkg/a.py"]["outside_in"] == 1


def _random_repo(seed: int) -> tuple[RepoMap, list[FileLink]]:
    rng = random.Random(seed)
    folders = ["", "a", "a/b", "a/b/c", "d", "d/e", "tests", "f/g/h", "big"]
    paths = sorted({f"{rng.choice(folders)}/m{i}.py".lstrip("/") for i in range(140)}
                   | {f"big/n{i}.py" for i in range(80)})
    links = []
    seen = set()
    for _ in range(600):
        a, b = rng.sample(paths, 2)
        if (a, b) in seen:
            continue
        seen.add((a, b))
        imports = rng.random() < 0.5
        calls = rng.randint(0 if imports else 1, 3)
        links.append(link(a, b, imports=int(imports), calls=calls,
                          guess_calls=rng.randint(0, calls), top=rng.random() < 0.7))
    return RepoMap(files(*paths), links, {}, exclude_tests=False), links


def test_conservation_on_every_folder_of_random_repos():
    """Every link touching the root is counted exactly once, and an aggregated edge is exactly
    the links from one node's files to the other's."""
    for seed in range(5):
        r, links = _random_repo(seed)
        queue = [""]
        visited = 0
        while queue:
            root = queue.pop()
            view = r.folder_view(root)
            visited += 1
            root = view["root"]
            inside = {f.path for f in r._files_under(root)}
            touching = sum(li.count for li in links if li.source in inside or li.target in inside)
            assert touching == (sum(e["count"] for e in view["edges"])
                                + sum(n["internal_count"] + n["outside_in"] + n["outside_out"]
                                      for n in view["nodes"]))
            for edge in view["edges"]:
                assert edge["count"] == edge["imports"] + edge["calls"]
            nodes = by_id(view)
            if not view["hidden_count"]:
                for (a, b), edge in edge_map(view).items():
                    under = [{f.path for f in r._files_under(nodes[x]["path"])}
                             if nodes[x]["kind"] == "folder" else {nodes[x]["path"]}
                             for x in (a, b)]
                    assert edge["count"] == sum(li.count for li in links if li.source in under[0]
                                                and li.target in under[1])
            assert len(view["nodes"]) <= VIEW_NODE_LIMIT + 1
            queue += [n["path"] for n in view["nodes"] if n["kind"] == "folder"]
        assert visited > 3


# --- the view limit ----------------------------------------------------------------------------

def _flat(n: int) -> list[str]:
    return [f"pkg/m{i:03}.py" for i in range(n)]


def test_exactly_the_limit_has_no_overflow():
    view = repo(_flat(VIEW_NODE_LIMIT) + ["other/a.py", "other/b.py"]).folder_view("pkg")
    assert len(view["nodes"]) == VIEW_NODE_LIMIT and view["hidden_count"] == 0
    assert not any(n["kind"] == "more" for n in view["nodes"])


def test_one_over_the_limit_hides_one_and_says_so():
    paths = _flat(VIEW_NODE_LIMIT + 1) + ["other/a.py", "other/b.py"]
    view = repo(paths).folder_view("pkg")
    assert len(view["nodes"]) == VIEW_NODE_LIMIT + 1 and view["hidden_count"] == 1
    more = view["nodes"][-1]
    assert (more["id"], more["kind"], more["label"], more["path"], more["hidden_count"]) == (
        "more:pkg", "more", "1 more", "pkg", 1)
    assert more["file_count"] == 1


def test_overflow_keeps_subfolders_then_the_most_connected_and_moves_edges_to_more():
    paths = _flat(70) + ["pkg/sub/a.py", "pkg/sub/b.py", "other/o.py", "other/p.py"]
    last = "pkg/m069.py"  # alphabetically last, but the most connected: must stay
    links = [link(p, last) for p in _flat(5)] + [
        link("pkg/m060.py", "other/o.py"),  # a hidden file's edge across the root
        link("pkg/m068.py", "pkg/m067.py"),  # both hidden: inside the "more" node
        link("pkg/m068.py", last, calls=2),  # hidden -> kept
    ]
    view = repo(paths, links).folder_view("pkg")
    assert view["hidden_count"] == 11
    nodes = by_id(view)
    assert "dir:pkg/sub" in nodes and f"file:{last}" in nodes
    assert view["nodes"][0]["id"] == "dir:pkg/sub"
    more = nodes["more:pkg"]
    assert more["label"] == "11 more" and more["file_count"] == 11
    # Connected files stay however late their name sorts; unconnected ones fill up by path.
    assert {"file:pkg/m060.py", "file:pkg/m067.py", "file:pkg/m068.py", "file:pkg/m054.py"} <= set(
        nodes)
    assert "file:pkg/m055.py" not in nodes and "file:pkg/m066.py" not in nodes
    assert more["internal_count"] == 0
    assert view["edges"] == sorted(view["edges"], key=lambda e: (e["source"], e["target"]))


def test_overflow_conserves_edges_on_the_more_node():
    paths = _flat(62) + ["other/o.py", "other/p.py"]
    hub = "pkg/m000.py"
    links = [link(p, hub, calls=1) for p in _flat(62)[1:]]
    view = repo(paths, links).folder_view("pkg")
    assert view["hidden_count"] == 2
    edges = edge_map(view)
    assert edges["more:pkg", f"file:{hub}"]["count"] == 4
    assert edges["more:pkg", f"file:{hub}"]["imports"] == 2
    assert sum(e["count"] for e in view["edges"]) == 61 * 2


# --- symbols -----------------------------------------------------------------------------------

def _symbol(i, name, path, kind="function", findings=0):
    return MapSymbol(i, kind, name, f"{path}:{name}", path, 1, i, i, findings)


def test_symbol_view_own_symbols_first_and_neighbours_capped():
    r = repo(["app/main.py", "app/lib.py", "tests/test_main.py"])
    file = r.by_path["app/main.py"]
    own = [_symbol(i, f"own{i}", "app/main.py") for i in range(1, 6)]
    module = _symbol(100, "main", "app/main.py", "module")
    others = [_symbol(200 + i, f"other{i}", "app/lib.py") for i in range(70)]
    test = _symbol(999, "check", "tests/test_main.py")
    edges = [SymbolEdge(1, s.id, "calls", 1.0) for s in others]
    edges.append(SymbolEdge(999, 1, "calls", 1.0))  # hidden neighbour
    edges.append(SymbolEdge(1, 2, "calls", 0.5))  # inside the file, a guess
    view = symbol_view(r, file, [*own, module, *others, test], edges)
    assert view["level"] == "symbol" and view["root"] == "app/main.py"
    assert view["hidden_symbols"] == 1
    assert [n["label"] for n in view["nodes"][:5]] == ["own1", "own2", "own3", "own4", "own5"]
    assert sum(n.get("own", False) for n in view["nodes"]) == 5  # module left out: no edges
    assert len(view["nodes"]) == VIEW_NODE_LIMIT + 1 and view["hidden_count"] == 15
    more = view["nodes"][-1]
    assert more["label"] == "15 more"
    edge = edge_map(view)["sym:1", "more:app/main.py"]
    assert edge["count"] == 15 and edge["type"] == "calls"
    assert edge_map(view)["sym:1", "sym:2"]["guess"] is True
    assert view["breadcrumbs"] == [{"path": "app", "label": ""},
                                   {"path": "app/main.py", "label": "main.py"}]


def test_symbol_view_module_node_only_with_edges_or_findings():
    r = repo(["a.py", "b.py"])
    module = _symbol(1, "a", "a.py", "module", findings=1)
    assert [n["id"] for n in symbol_view(r, r.by_path["a.py"], [module], [])["nodes"]] == ["sym:1"]
    bare = _symbol(2, "a", "a.py", "module")
    assert symbol_view(r, r.by_path["a.py"], [bare], [])["nodes"] == []
