"""Tiers and paths on a small hand-made graph."""

from app.reach.graph import (
    GUESS,
    NONE,
    NOT_CHECKED,
    SOLID,
    TIER_RANK,
    Edge,
    Reach,
    Seed,
    Sym,
    structural_edges,
)

#   file 1 pkg/__init__.py   module 1
#   file 2 pkg/core.py       module 2, class 3 (4-20) with __init__ 4 (5-6) and run 5 (8-12),
#                            function 6 (22-30) with inner function 7 (24-26), function 8 (32-40)
#   file 3 pkg/other.py      module 9
#   file 4 notes.md          (not analysed code)
SYMS = [
    Sym(1, 1, "module", "pkg", "pkg", 1, 5),
    Sym(2, 2, "module", "core", "pkg.core", 1, 40),
    Sym(3, 2, "class", "Worker", "pkg.core.Worker", 4, 20),
    Sym(4, 2, "method", "__init__", "pkg.core.Worker.__init__", 5, 6),
    Sym(5, 2, "method", "run", "pkg.core.Worker.run", 8, 12),
    Sym(6, 2, "function", "main", "pkg.core.main", 22, 30),
    Sym(7, 2, "function", "inner", "pkg.core.main.inner", 24, 26),
    Sym(8, 2, "function", "lonely", "pkg.core.lonely", 32, 40),
    Sym(9, 3, "module", "other", "pkg.other", 1, 10),
]
PATHS = {1: "pkg/__init__.py", 2: "pkg/core.py", 3: "pkg/other.py", 4: "notes.md"}


def reach(extra_edges=(), seeds=None):
    seeds = seeds or [Seed(6, "console-script", "console script `x`")]
    edges = structural_edges(SYMS, PATHS) + list(extra_edges)
    return Reach(SYMS, edges, list(seeds), {1, 2, 3})


def test_class_body_runs_with_module_methods_are_guesses_init_is_solid():
    r = reach(seeds=[Seed(2, "main-block", "m")])
    assert r.tier_of_symbol(3) == SOLID  # class body runs when the module does
    assert r.tier_of_symbol(4) == SOLID  # __init__ runs on instantiation
    assert r.tier_of_symbol(5) == GUESS  # another method: only if something calls it
    assert r.tier_of_symbol(6) == NONE  # a function is not run by importing its module
    assert r.tier_of_symbol(1) == SOLID  # the package __init__ runs before a module in it


def test_calls_solid_or_guess_and_the_path_with_fewest_guesses_wins():
    assert reach([Edge(6, 8, False, "calls")]).tier_of_symbol(8) == SOLID
    assert reach([Edge(6, 8, True, "calls")]).tier_of_symbol(8) == GUESS
    r = reach([Edge(6, 8, True, "calls"), Edge(6, 5, False, "calls"), Edge(5, 8, False, "calls")])
    assert r.tier_of_symbol(8) == SOLID  # the longer solid path beats the short guessed one
    assert [s.symbol_id for s in r.path_to(8)] == [6, 5, 8]


def test_inner_function_is_a_guess_and_nothing_else_is_reached():
    r = reach()
    assert r.tier_of_symbol(7) == GUESS
    assert r.tier_of_symbol(8) == NONE
    assert r.tier_of_symbol(9) == NONE


def test_tier_of_a_line_uses_the_innermost_symbol_and_not_checked_for_other_files():
    r = reach()
    assert r.tier(2, 25) == GUESS  # inside inner() inside main()
    assert r.tier(2, 23) == SOLID  # inside main() but outside inner()
    assert r.tier(2, 31) == NONE  # between main and lonely: module level, module not entered
    assert r.tier(4, 1) == NOT_CHECKED  # a markdown file


def test_path_and_entry():
    r = reach([Edge(6, 8, False, "calls")])
    assert [(s.symbol_id, s.via) for s in r.path_to(8)] == [(6, None), (8, "calls")]
    assert r.seed_for(8).label == "console script `x`"
    assert r.path_to(9) == []


def test_not_checked_sorts_with_guess_never_as_a_path_tier():
    assert TIER_RANK[SOLID] < TIER_RANK[GUESS] == TIER_RANK[NOT_CHECKED] < TIER_RANK[NONE]
