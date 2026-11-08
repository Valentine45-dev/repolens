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
    Sym(10, 2, "method", "__enter__", "pkg.core.Worker.__enter__", 14, 16),
]
PATHS = {1: "pkg/__init__.py", 2: "pkg/core.py", 3: "pkg/other.py", 4: "notes.md"}


def reach(extra_edges=(), seeds=None):
    seeds = seeds or [Seed(6, "console-script", "console script `x`")]
    edges = structural_edges(SYMS, PATHS) + list(extra_edges)
    return Reach(SYMS, edges, list(seeds), {1, 2, 3})


def test_class_body_runs_with_module_init_is_solid_special_methods_guess_others_need_a_call():
    r = reach(seeds=[Seed(2, "main-block", "m")])
    assert r.tier_of_symbol(3) == SOLID  # class body runs when the module does
    assert r.tier_of_symbol(4) == SOLID  # __init__ runs on instantiation
    assert r.tier_of_symbol(10) == GUESS  # __enter__: Python calls it implicitly, a guess
    assert r.tier_of_symbol(5) == NONE  # an ordinary method nothing calls: no structural edge
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


def test_a_file_that_is_one_function_maps_a_line_to_the_function_not_the_module():
    one = [Sym(20, 7, "module", "tiny", "tiny", 1, 2),
           Sym(21, 7, "function", "only", "tiny.only", 1, 2)]
    r = Reach(one, [Edge(20, 21, True, "calls")], [Seed(20, "main-block", "m")], {7})
    assert r.symbol_at(7, 2) == 21
    assert r.tier(7, 2) == GUESS  # the function, not its module (which is solid)
    assert r.tier(7, None) == SOLID  # no line: the module


def test_path_and_entry():
    r = reach([Edge(6, 8, False, "calls")])
    assert [(s.symbol_id, s.via) for s in r.path_to(8)] == [(6, None), (8, "calls")]
    assert r.seed_for(8).label == "console script `x`"
    assert r.path_to(9) == []


def test_an_ordinary_method_is_reached_by_a_call_and_only_by_a_call():
    r = reach([Edge(6, 5, False, "calls")], seeds=[Seed(6, "console-script", "x"),
                                                    Seed(2, "main-block", "m")])
    assert r.tier_of_symbol(5) == SOLID
    r = reach([Edge(6, 5, True, "calls")], seeds=[Seed(6, "console-script", "x"),
                                                   Seed(2, "main-block", "m")])
    assert r.tier_of_symbol(5) == GUESS


def test_equal_guess_counts_prefer_the_path_whose_guess_is_a_call():
    # symbol 10 (a special method) is reached two ways, each with exactly one guess:
    #   module 2 -> class 3 -> 10          (structural guess, 2 steps)
    #   6 -> 8 -> 5 -> 10                  (a guessed call, 3 steps)
    edges = [Edge(6, 8, False, "calls"), Edge(8, 5, False, "calls"), Edge(5, 10, True, "calls")]
    r = reach(edges, seeds=[Seed(2, "main-block", "m"), Seed(6, "console-script", "x")])
    assert r.tier_of_symbol(10) == GUESS
    assert [(s.symbol_id, s.via) for s in r.path_to(10)] == [
        (6, None), (8, "calls"), (5, "calls"), (10, "calls")]
    # with no call path, the structural guess is what remains
    r = reach(seeds=[Seed(2, "main-block", "m")])
    assert [(s.symbol_id, s.via) for s in r.path_to(10)] == [
        (2, None), (3, "contains"), (10, "contains")]


def test_entry_class_records_whether_the_tier_needs_a_public_api_entry():
    seeds = [Seed(6, "console-script", "x"), Seed(8, "public-api", "api")]
    edges = [Edge(6, 5, False, "calls"), Edge(8, 5, False, "calls"), Edge(8, 7, False, "calls")]
    r = reach(edges, seeds=seeds)
    assert r.tier_of_symbol(5) == SOLID and r.entry_class_of_symbol(5) == "app"  # both reach it
    assert r.tier_of_symbol(7) == SOLID and r.entry_class_of_symbol(7) == "public-api"
    assert r.entry_class_of_symbol(8) == "public-api"  # the public entry itself
    assert r.entry_class_of_symbol(6) == "app"
    assert r.entry_class_of_symbol(9) is None  # no path found
    # solid only through the public API, guess through an app entry: the class is public-api
    r = reach([Edge(6, 5, True, "calls"), Edge(8, 5, False, "calls")], seeds=seeds)
    assert r.tier_of_symbol(5) == SOLID and r.entry_class_of_symbol(5) == "public-api"
    assert r.entry_class(4, 1) is None  # a file that is not analysed code


def test_the_entry_class_does_not_change_the_tier_or_the_order_key():
    edges = [Edge(8, 5, False, "calls")]
    with_public = reach(edges, seeds=[Seed(8, "public-api", "api")])
    as_app = reach(edges, seeds=[Seed(8, "console-script", "x")])
    assert with_public.tier_of_symbol(5) == as_app.tier_of_symbol(5) == SOLID
    assert TIER_RANK[with_public.tier_of_symbol(5)] == TIER_RANK[as_app.tier_of_symbol(5)]


def test_not_checked_sorts_with_guess_never_as_a_path_tier():
    assert TIER_RANK[SOLID] < TIER_RANK[GUESS] == TIER_RANK[NOT_CHECKED] < TIER_RANK[NONE]
