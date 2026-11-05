"""The folder-first map: folder -> file -> symbol views of one snapshot. Pure, no database.

Rules (docs/repolens-system-design.md section 10):
- A folder view shows the direct children of a folder. A folder with no files and one subfolder
  is merged with it (`src/itsdangerous`); a folder holding one code file, nothing else with a
  finding and no subfolder is shown as that file (`scoring/admin.py`).
- An aggregated edge A -> B adds up every file edge from anything under A to anything under B.
  Every edge between visible files is counted once for a view: on an edge between two nodes, in
  a node's `internal_count`, or in a node's outside_in / outside_out. Edges with neither end
  under the root do not belong to that view.
- A view has at most VIEW_NODE_LIMIT nodes plus one "N more" node, which takes over the edges of
  what it hides. Nothing is cut silently.
- Cycles are strongly connected components of top-level imports between visible files. Edges
  between two folders in both directions are NOT a cycle: only `cycle_edges` says so.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.paths import is_test_path

VIEW_NODE_LIMIT = 60
GUESS_BELOW = 0.9  # same threshold as the flat graph's dashed edges (web/src/graphModel.ts)
CYCLE_SCOPE = "top_level_imports"


@dataclass(frozen=True)
class CodeFile:
    id: int
    symbol_id: int
    path: str
    language: str
    loc: int
    external_imports: int = 0
    unresolved_imports: int = 0
    findings: int = 0


@dataclass
class FileLink:
    """All edges from one file to another that passed the confidence filter."""
    source: str
    target: str
    imports: int = 0  # 0 or 1: one import edge per (file, target)
    calls: int = 0  # one per (caller symbol, callee symbol)
    guess_calls: int = 0  # of `calls`, below GUESS_BELOW
    confidence: float = 0.0  # the highest among them
    top_level_import: bool = False

    @property
    def count(self) -> int:
        return self.imports + self.calls


def find_cycles(paths: Iterable[str], edges: Iterable[tuple[str, str]]) -> list[list[str]]:
    """Strongly connected components with more than one member: Tarjan's algorithm, iterative
    because a long import chain would overflow Python's stack. Sorted, so the ids are stable."""
    graph: dict[str, list[str]] = {p: [] for p in paths}
    for a, b in edges:
        if a in graph and b in graph and a != b:
            graph[a].append(b)

    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    found: list[list[str]] = []
    for start in graph:
        if start in index:
            continue
        index[start] = low[start] = len(index)
        stack.append(start)
        on_stack.add(start)
        work = [(start, iter(graph[start]))]
        while work:
            node, neighbours = work[-1]
            for next_node in neighbours:
                if next_node not in index:
                    index[next_node] = low[next_node] = len(index)
                    stack.append(next_node)
                    on_stack.add(next_node)
                    work.append((next_node, iter(graph[next_node])))
                    break
                if next_node in on_stack:
                    low[node] = min(low[node], index[next_node])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == index[node]:
                    component = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        component.append(member)
                        if member == node:
                            break
                    if len(component) > 1:
                        found.append(sorted(component))
    return sorted(found)


def _parent(path: str) -> str:
    return path.rpartition("/")[0]


def _join(folder: str, name: str) -> str:
    return f"{folder}/{name}" if folder else name


def _relative(path: str, root: str) -> str:
    return path[len(root) + 1:] if root else path


def _under(path: str, folder: str) -> bool:
    """The folder itself, or anything below it."""
    return not folder or path == folder or path.startswith(folder + "/")


@dataclass
class _Member:
    """One node of a view before its numbers are added up."""
    id: str
    kind: str  # folder|file
    path: str
    label: str
    files: list[CodeFile] = field(default_factory=list)


@dataclass
class _Tally:
    edges: dict[tuple[str, str], dict] = field(default_factory=dict)
    internal: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    outside_in: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    outside_out: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def connectivity(self) -> dict[str, int]:
        """Node id -> every edge it can be seen on: to other nodes and across the root."""
        total: dict[str, int] = defaultdict(int)
        for (a, b), edge in self.edges.items():
            total[a] += edge["count"]
            total[b] += edge["count"]
        for side in (self.outside_in, self.outside_out):
            for node_id, count in side.items():
                total[node_id] += count
        return total


class RepoMap:
    """One snapshot's code files and file-to-file links, with test files filtered as asked."""

    def __init__(self, files: list[CodeFile], links: list[FileLink],
                 other_findings: dict[str, int], *, exclude_tests: bool,
                 cycles_available: bool = True):
        """`other_findings`: finding counts of files that are not code files (README, YAML)."""
        self.all_files = files
        self.exclude_tests = exclude_tests
        self.cycles_available = cycles_available
        self.files = [f for f in files if not (exclude_tests and is_test_path(f.path))]
        self.by_path = {f.path: f for f in self.files}
        self.all_by_path = {f.path: f for f in files}
        self.links = [li for li in links if li.source in self.by_path and li.target in self.by_path]
        self.other_findings = {p: n for p, n in other_findings.items()
                               if not (exclude_tests and is_test_path(p))}

        self.known_folders = {""}
        self.test_files: dict[str, int] = defaultdict(int)
        for f in files:
            folder = _parent(f.path)
            while True:
                self.known_folders.add(folder)
                if is_test_path(f.path):
                    self.test_files[folder] += 1
                if not folder:
                    break
                folder = _parent(folder)

        self.subfolders: dict[str, set[str]] = defaultdict(set)
        self.direct_files: dict[str, list[CodeFile]] = defaultdict(list)
        for f in sorted(self.files, key=lambda f: f.path):
            self.direct_files[_parent(f.path)].append(f)
            folder = _parent(f.path)
            while folder:
                up = _parent(folder)
                self.subfolders[up].add(folder)
                folder = up

        self.cycles = find_cycles(
            self.by_path,
            ((li.source, li.target) for li in self.links if li.top_level_import),
        ) if cycles_available else []
        self.cycle_of = {p: i for i, c in enumerate(self.cycles, start=1) for p in c}

    # --- the folder tree -------------------------------------------------------------------

    def is_folder(self, path: str) -> bool:
        return path in self.known_folders

    def follow_chain(self, folder: str) -> str:
        """Down through folders that hold nothing but one subfolder."""
        while (not self.direct_files.get(folder)
               and len(self.subfolders.get(folder, ())) == 1):
            folder = next(iter(self.subfolders[folder]))
        return folder

    def canonical_root(self, root: str) -> str:
        """`src` -> `src/itsdangerous`: a view always opens where there is something to see."""
        return self.follow_chain(root)

    def breadcrumbs(self, root: str) -> list[dict]:
        """From the repo down to `root`, one crumb per merged chain, each a folder that opens as
        itself. The first crumb is the repo (label '': the caller knows its name)."""
        start = self.follow_chain("")
        if not _under(root, start):  # a folder with only hidden test files
            start = ""
        crumbs = [{"path": start, "label": ""}]
        current = start
        while current != root:
            next_part = _relative(root, current).split("/", 1)[0]
            folder = _join(current, next_part)
            chain_end = self.follow_chain(folder)
            if _under(root, chain_end):
                folder = chain_end
            crumbs.append({"path": folder, "label": _relative(folder, current)})
            current = folder
        return crumbs

    def _files_under(self, folder: str) -> list[CodeFile]:
        found = list(self.direct_files.get(folder, ()))
        for sub in self.subfolders.get(folder, ()):
            found += self._files_under(sub)
        return found

    def _shows_as_file(self, folder: str) -> bool:
        files = self.direct_files.get(folder, ())
        return (len(files) == 1 and not self.subfolders.get(folder)
                # A finding in its README or YAML must stay visible on the folder.
                and not any(_under(p, folder) for p in self.other_findings))

    def _folder_members(self, root: str) -> list[_Member]:
        members = []
        for sub in sorted(self.subfolders.get(root, ())):
            end = self.follow_chain(sub)
            if self._shows_as_file(end):
                f = self.direct_files[end][0]
                members.append(_Member(f"file:{f.path}", "file", f.path,
                                       _relative(f.path, root), [f]))
            else:
                members.append(_Member(f"dir:{end}", "folder", end, _relative(end, root),
                                       self._files_under(end)))
        for f in self.direct_files.get(root, ()):
            members.append(_Member(f"file:{f.path}", "file", f.path, _relative(f.path, root), [f]))
        return members

    # --- views -----------------------------------------------------------------------------

    def folder_view(self, root: str) -> dict:
        root = self.canonical_root(root)
        return self._view("folder", root, self._folder_members(root))

    def file_view(self, root: str) -> dict:
        """Every file under the folder, at any depth."""
        root = self.canonical_root(root)
        members = [_Member(f"file:{f.path}", "file", f.path, _relative(f.path, root), [f])
                   for f in sorted(self._files_under(root), key=lambda f: f.path)]
        return self._view("file", root, members)

    def _tally(self, node_of: dict[str, str]) -> _Tally:
        tally = _Tally()
        for link in self.links:
            a, b = node_of.get(link.source), node_of.get(link.target)
            if a is None and b is None:
                continue
            if a == b:
                tally.internal[a] += link.count
            elif a is None:
                tally.outside_in[b] += link.count
            elif b is None:
                tally.outside_out[a] += link.count
            else:
                edge = tally.edges.setdefault((a, b), {
                    "source": a, "target": b, "count": 0, "imports": 0, "calls": 0,
                    "guess_calls": 0, "confidence": 0.0, "cycle_edges": 0,
                })
                edge["count"] += link.count
                edge["imports"] += link.imports
                edge["calls"] += link.calls
                edge["guess_calls"] += link.guess_calls
                edge["confidence"] = max(edge["confidence"], link.confidence)
                cycle = self.cycle_of.get(link.source)
                if (link.top_level_import and cycle is not None
                        and cycle == self.cycle_of.get(link.target)):
                    edge["cycle_edges"] += 1
        return tally

    def _view(self, level: str, root: str, members: list[_Member]) -> dict:
        node_of = {f.path: m.id for m in members for f in m.files}
        tally = self._tally(node_of)

        hidden: list[_Member] = []
        kept = members
        if len(members) > VIEW_NODE_LIMIT:
            # Subfolders first: they are the only way down. Then the most connected.
            connected = tally.connectivity()
            ranked = sorted(members, key=lambda m: (m.kind != "folder", -connected[m.id], m.path))
            kept, hidden = ranked[:VIEW_NODE_LIMIT], ranked[VIEW_NODE_LIMIT:]
            more_id = f"more:{root}"
            for m in hidden:
                for f in m.files:
                    node_of[f.path] = more_id
            tally = self._tally(node_of)

        nodes = [self._node(m, tally) for m in sorted(
            kept, key=lambda m: (m.kind != "folder", m.path))]
        if hidden:
            nodes.append(self._more_node(root, hidden, tally))

        edges = sorted(tally.edges.values(), key=lambda e: (e["source"], e["target"]))
        for e in edges:
            e["guess"] = e["confidence"] < GUESS_BELOW
            if not self.cycles_available:
                e["cycle_edges"] = None

        under_root = sum(f.findings for f in self.files if _under(f.path, root)) + sum(
            n for p, n in self.other_findings.items() if _under(p, root))
        return {
            "level": level,
            "root": root,
            "breadcrumbs": self.breadcrumbs(root),
            "view_limit": VIEW_NODE_LIMIT,
            "total_files": len(self.files),
            "hidden_files": len(self.all_files) - len(self.files),
            "hidden_files_under_root": sum(
                1 for f in self.all_files
                if f.path not in self.by_path and _under(f.path, root)),
            "hidden_count": len(hidden),
            # Findings under the root that no node carries: a README beside the code, say.
            "other_findings": under_root - sum(n["finding_count"] for n in nodes),
            **self.cycle_summary(),
            "nodes": nodes,
            "edges": edges,
        }

    def cycle_summary(self) -> dict:
        return {
            "cycle_scope": CYCLE_SCOPE,
            # False means "not known yet", never "none": the snapshot needs its edges rebuilt.
            "cycles_available": self.cycles_available,
            "cycles": [{"id": i, "size": len(c), "files": c}
                       for i, c in enumerate(self.cycles, start=1)],
        }

    def _cycle_fields(self, files: Iterable[CodeFile]) -> dict:
        if not self.cycles_available:
            return {"in_cycle": None, "cycle_files": None, "cycle_ids": []}
        ids = [self.cycle_of[f.path] for f in files if f.path in self.cycle_of]
        return {"in_cycle": bool(ids), "cycle_files": len(ids), "cycle_ids": sorted(set(ids))}

    def _test_file_count(self, m: _Member) -> int:
        return self.test_files.get(m.path, 0) if m.kind == "folder" else int(is_test_path(m.path))

    def _finding_count(self, m: _Member) -> int:
        count = sum(f.findings for f in m.files)
        if m.kind == "folder":
            count += sum(n for p, n in self.other_findings.items() if _under(p, m.path))
        return count

    def _node(self, m: _Member, tally: _Tally) -> dict:
        node = {
            "id": m.id,
            "kind": m.kind,
            "path": m.path,
            "label": m.label,
            "file_count": len(m.files),
            "test_file_count": self._test_file_count(m),
            "finding_count": self._finding_count(m),
            **self._cycle_fields(m.files),
            "internal_count": tally.internal[m.id],
            "outside_in": tally.outside_in[m.id],
            "outside_out": tally.outside_out[m.id],
        }
        if m.kind == "file":
            f = m.files[0]
            node.update(file_id=f.id, symbol_id=f.symbol_id, language=f.language, loc=f.loc,
                        external_imports=f.external_imports,
                        unresolved_imports=f.unresolved_imports)
        return node

    def _more_node(self, root: str, hidden: list[_Member], tally: _Tally) -> dict:
        node_id = f"more:{root}"
        files = [f for m in hidden for f in m.files]
        return {
            "id": node_id,
            "kind": "more",
            "path": root,
            "label": f"{len(hidden)} more",
            "hidden_count": len(hidden),
            "file_count": len(files),
            "test_file_count": sum(self._test_file_count(m) for m in hidden),
            "finding_count": sum(self._finding_count(m) for m in hidden),
            **self._cycle_fields(files),
            "internal_count": tally.internal[node_id],
            "outside_in": tally.outside_in[node_id],
            "outside_out": tally.outside_out[node_id],
        }


@dataclass(frozen=True)
class MapSymbol:
    id: int
    kind: str
    name: str
    qualified_name: str
    path: str
    file_id: int
    start_line: int | None
    end_line: int | None
    findings: int = 0


@dataclass(frozen=True)
class SymbolEdge:
    source: int
    target: int
    type: str  # calls|defines
    confidence: float


def symbol_view(repo: RepoMap, file: CodeFile, symbols: list[MapSymbol],
                edges: list[SymbolEdge]) -> dict:
    """One file's classes and functions plus their direct neighbours in other files. Its own
    symbols rank first in the node limit; the module itself is a node only if something connects
    to it or a finding sits on it. Neighbours in hidden test files are left out and counted."""
    by_id = {s.id: s for s in symbols}
    own = {s.id for s in symbols if s.path == file.path}
    kept_edges = []
    hidden_neighbours = set()
    for e in edges:
        other = e.target if e.source in own else e.source
        if other in own:
            kept_edges.append(e)
        elif repo.exclude_tests and is_test_path(by_id[other].path):
            hidden_neighbours.add(other)
        else:
            kept_edges.append(e)

    connected = {i for e in kept_edges for i in (e.source, e.target)}
    members = [s for s in symbols
               if s.id in connected
               or (s.id in own and (s.kind != "module" or s.findings))]
    degree: dict[int, int] = defaultdict(int)
    best: dict[int, float] = defaultdict(float)
    for e in kept_edges:
        for i in (e.source, e.target):
            degree[i] += 1
            best[i] = max(best[i], e.confidence)
    ranked = sorted(members, key=lambda s: (s.id not in own, -best[s.id], -degree[s.id],
                                            s.path, s.start_line or 0, s.qualified_name))
    kept, hidden = ranked[:VIEW_NODE_LIMIT], ranked[VIEW_NODE_LIMIT:]
    more_id = f"more:{file.path}"
    node_of = {s.id: f"sym:{s.id}" for s in kept}
    node_of.update({s.id: more_id for s in hidden})

    grouped: dict[tuple[str, str, str], dict] = {}
    internal = 0
    for e in kept_edges:
        a, b = node_of[e.source], node_of[e.target]
        if a == b:  # both hidden
            internal += 1
            continue
        edge = grouped.setdefault((a, b, e.type), {
            "source": a, "target": b, "type": e.type, "count": 0, "confidence": 0.0,
        })
        edge["count"] += 1
        edge["confidence"] = max(edge["confidence"], e.confidence)
    out_edges = sorted(grouped.values(), key=lambda e: (e["source"], e["target"], e["type"]))
    for e in out_edges:
        e["guess"] = e["confidence"] < GUESS_BELOW

    nodes = [{
        "id": f"sym:{s.id}",
        "kind": s.kind,
        "symbol_id": s.id,
        "label": s.name,
        "qualified_name": s.qualified_name,
        "path": s.path,
        "file_id": s.file_id,
        "start_line": s.start_line,
        "end_line": s.end_line,
        "own": s.id in own,
        "finding_count": s.findings,
    } for s in kept]
    if hidden:
        nodes.append({
            "id": more_id, "kind": "more", "path": file.path, "label": f"{len(hidden)} more",
            "hidden_count": len(hidden), "internal_count": internal,
            "finding_count": sum(s.findings for s in hidden),
        })

    folder = _parent(file.path)
    crumbs = repo.breadcrumbs(repo.canonical_root(folder))
    crumbs.append({"path": file.path, "label": _relative(file.path, crumbs[-1]["path"])})
    return {
        "level": "symbol",
        "root": file.path,
        "breadcrumbs": crumbs,
        "view_limit": VIEW_NODE_LIMIT,
        "total_files": len(repo.files),
        "hidden_files": len(repo.all_files) - len(repo.files),
        "hidden_symbols": len(hidden_neighbours),
        "hidden_count": len(hidden),
        "file": {
            "file_id": file.id,
            "symbol_id": file.symbol_id,
            "path": file.path,
            "language": file.language,
            "loc": file.loc,
            "finding_count": file.findings,
            **repo._cycle_fields([file]),
        },
        **repo.cycle_summary(),
        "nodes": nodes,
        "edges": out_edges,
    }
