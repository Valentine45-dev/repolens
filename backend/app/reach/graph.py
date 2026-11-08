"""Reachability tiers: is there a path from a detected entry point to the code a finding is in?

Pure functions over symbols, edges and entry points; the database is read in `load.py`. Rules
(docs/reachability-design.md has the reasoning; they are fixed before the evaluation repos are
touched):
- Edges: import (a top-level import runs with its module), call (confidence 1.0 or 0.9 is solid,
  0.5 is a guess), a class body runs when the code that defines it runs, a class reaches its
  `__init__` (solid) and its other methods (guess), a function defined inside a function is a
  guess, and importing a module first runs the `__init__.py` of each package above it.
- Tier of a finding = tier of the innermost symbol (function, method, class, else module) that
  contains its line: solid path (reached with solid edges only), guess path (needs at least one
  guess), no path found; "not checked" for a file that is not analysed code.
- A path with the fewest guesses wins, then the fewest steps.
"""

import heapq
from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath

SOLID = "solid"
GUESS = "guess"
NOT_CHECKED = "not_checked"
NONE = "none"
# "Not checked" sorts with the guess tier, never as a path tier of its own.
TIER_RANK = {SOLID: 0, GUESS: 1, NOT_CHECKED: 1, NONE: 2}

SOLID_CALL_CONFIDENCE = 0.9  # calibration: 1.0 and 0.9 were 30/30 correct, 0.5 was 21/30
_CODE_KINDS = ("module", "class", "function", "method")


@dataclass(frozen=True)
class Sym:
    id: int
    file_id: int
    kind: str
    name: str
    qualified: str
    start: int
    end: int


@dataclass(frozen=True)
class Edge:
    src: int
    dst: int
    guess: bool
    kind: str  # imports|calls|contains|package


@dataclass(frozen=True)
class Seed:
    symbol_id: int
    kind: str  # an entry-point kind from entries.py
    label: str  # "console script `black`"
    detail: str = ""  # where it was found


@dataclass(frozen=True)
class Step:
    symbol_id: int
    via: str | None  # edge kind used to get here; None for the entry point itself
    guess: bool


def parents_of(symbols: list[Sym]) -> dict[int, int | None]:
    """Innermost enclosing symbol of each symbol, by line ranges within one file."""
    parent: dict[int, int | None] = {}
    by_file: dict[int, list[Sym]] = defaultdict(list)
    for s in symbols:
        by_file[s.file_id].append(s)
    for items in by_file.values():
        # outer first: earlier start, then the longer range; a module wins a tie
        items.sort(key=lambda s: (s.start, -s.end, s.kind != "module", s.id))
        stack: list[Sym] = []
        for s in items:
            while stack and not (stack[-1].start <= s.start and s.end <= stack[-1].end):
                stack.pop()
            parent[s.id] = stack[-1].id if stack else None
            stack.append(s)
    return parent


def structural_edges(symbols: list[Sym], file_paths: dict[int, str]) -> list[Edge]:
    """Edges that come from where code is defined, not from calls or imports."""
    by_id = {s.id: s for s in symbols}
    parents = parents_of(symbols)
    edges = []
    for s in symbols:
        p = by_id.get(parents.get(s.id) or -1)
        if p is None:
            continue
        if s.kind == "class":
            edges.append(Edge(p.id, s.id, False, "contains"))  # a class body runs with its parent
        elif s.kind == "method" and p.kind == "class":
            edges.append(Edge(p.id, s.id, s.name != "__init__", "contains"))
        elif s.kind in ("function", "method") and p.kind in ("function", "method"):
            edges.append(Edge(p.id, s.id, True, "contains"))  # defined inside a function: a guess
    modules = {s.file_id: s for s in symbols if s.kind == "module"}
    by_path = {path: modules[fid] for fid, path in file_paths.items() if fid in modules}
    for fid, module in modules.items():
        path = PurePosixPath(file_paths[fid])
        if path.suffix not in (".py", ".pyi"):
            continue
        for ancestor in list(path.parents)[:-1]:  # the package inits above this module
            init = by_path.get((ancestor / "__init__.py").as_posix())
            if init is not None and init.id != module.id:
                edges.append(Edge(module.id, init.id, False, "package"))
    return edges


def innermost(items, line: int | None) -> Sym | None:
    """The smallest symbol of one file that contains `line`; the module when the line is in no
    other (or `line` is unknown)."""
    best, module = None, None
    for s in items:
        if s.kind == "module":
            module = s
        if line is not None and s.start <= line <= s.end:
            if best is None or (s.end - s.start, -s.start) < (best.end - best.start, -best.start):
                best = s
    return best or module


class Reach:
    """Tiers and paths for one snapshot."""

    def __init__(self, symbols: list[Sym], edges: list[Edge], seeds: list[Seed],
                 analysed_files: set[int]):
        self.symbols = {s.id: s for s in symbols if s.kind in _CODE_KINDS}
        self.seeds = seeds
        self.analysed_files = analysed_files
        self._by_file: dict[int, list[Sym]] = defaultdict(list)
        for s in self.symbols.values():
            self._by_file[s.file_id].append(s)
        out: dict[int, list[Edge]] = defaultdict(list)
        for e in edges:
            if e.src in self.symbols and e.dst in self.symbols:
                out[e.src].append(e)
        self._cost: dict[int, tuple[int, int]] = {}
        self._came: dict[int, tuple[int, Edge] | None] = {}
        self._seed_of: dict[int, Seed] = {}
        heap: list[tuple[int, int, int]] = []
        for seed in sorted(seeds, key=lambda x: (x.kind, x.label, x.symbol_id)):
            if seed.symbol_id in self.symbols and seed.symbol_id not in self._cost:
                self._cost[seed.symbol_id] = (0, 0)
                self._came[seed.symbol_id] = None
                self._seed_of[seed.symbol_id] = seed
                heapq.heappush(heap, (0, 0, seed.symbol_id))
        while heap:
            guesses, hops, node = heapq.heappop(heap)
            if self._cost.get(node) != (guesses, hops):
                continue
            for e in out.get(node, ()):
                cost = (guesses + (1 if e.guess else 0), hops + 1)
                if e.dst not in self._cost or cost < self._cost[e.dst]:
                    self._cost[e.dst] = cost
                    self._came[e.dst] = (node, e)
                    heapq.heappush(heap, (cost[0], cost[1], e.dst))

    # -- lookups -----------------------------------------------------------------------------

    def symbol_at(self, file_id: int, line: int | None) -> int | None:
        chosen = innermost(self._by_file.get(file_id, ()), line)
        return chosen.id if chosen else None

    def tier_of_symbol(self, symbol_id: int | None) -> str:
        if symbol_id is None or symbol_id not in self.symbols:
            return NOT_CHECKED
        cost = self._cost.get(symbol_id)
        if cost is None:
            return NONE
        return SOLID if cost[0] == 0 else GUESS

    def tier(self, file_id: int, line: int | None) -> str:
        if file_id not in self.analysed_files:
            return NOT_CHECKED
        return self.tier_of_symbol(self.symbol_at(file_id, line))

    def path_to(self, symbol_id: int) -> list[Step]:
        """Entry point first, `symbol_id` last. Empty when no path was found."""
        if symbol_id not in self._cost:
            return []
        steps = []
        node: int | None = symbol_id
        while node is not None:
            came = self._came[node]
            via = came[1] if came else None
            steps.append(Step(node, via.kind if via else None, via.guess if via else False))
            node = came[0] if came else None
        return steps[::-1]

    def seed_for(self, symbol_id: int) -> Seed | None:
        path = self.path_to(symbol_id)
        return self._seed_of.get(path[0].symbol_id) if path else None
