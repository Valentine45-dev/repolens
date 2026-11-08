# Reachability: design note (v2 step 6b, `feat/reachability`)

Status: written with the code on `feat/reachability`. Once the branch is merged, the commit that contains these rules is referenced from the pre-registration
(`eval/reachability_prereg.md` on `eval/precision-at-20`) as the frozen tier code. This note is the plain-words version of `backend/app/reach/`.

## What it answers
For a finding: **is there a path from a detected entry point to the code the finding is in?** It is shown in the finding panel and as an additive sort
(`?sort=reachability`, UI "Order: Reachability"). The default order is unchanged. It never says "unreachable", "unused", "dead" or "safe": a path is a way the code *could* run, found by
following imports and name-based calls, and "no path found" only means this analysis found none.

## No schema change, nothing new stored
Everything is worked out from what the pipeline already stores: `symbols` (with line ranges), `edges` (imports with scope, calls with confidence), `edge_sites` (the lines of nested imports) and the
redacted file text in `files.content`. Discover already keeps `pyproject.toml`, `setup.cfg`, `package.json` and other config files (language NULL), so console scripts are read from stored text:
`tomllib` for TOML, `configparser` for INI, `json` for JSON, and `ast` for `setup.py` (parsed as a literal, never run). The result is built per snapshot on first use and cached in memory
keyed by (snapshot, latest job), so a re-analysis in place starts fresh.

## Entry points (found by pattern; the list is a heuristic and misses things)
Test and example files (`app.paths.is_test_path`) are never entry points.

| Kind | Rule |
|---|---|
| `main-block` | A Python file with a top-level `if __name__ == "__main__":` block: its module. |
| `main-module` | A `__main__.py` file (`python -m pkg`): its module. |
| `console-script` | `[project.scripts]` / `[project.gui-scripts]` in `pyproject.toml`, `[tool.poetry.scripts]`, `[tool.flit.scripts]`, `console_scripts` under `[options.entry_points]` in `setup.cfg`, and `setup(entry_points=...)` in `setup.py` when it is a literal (a name bound to a literal at the top of the file is followed once). `module:function` is matched with a file (source roots and `src/` are tried relative to the packaging file, then the repo's module map) and a top-level function or class in it; if only the module can be matched, the module is the entry. |
| `plugin-entry` | The other entry-point groups of the same files (`[project.entry-points.*]`, `[tool.poetry.plugins.*]`, other groups under `[options.entry_points]`). |
| `route-or-command` | A function or class with a decorator that registers a handler: dotted `route get post put delete patch head options websocket api_route command group task shared_task periodic_task on_event errorhandler exception_handler before_request after_request teardown_request teardown_appcontext before_app_request after_app_request context_processor app_context_processor template_filter template_global url_value_preprocessor listener middleware receiver event_handler subscriber`; bare `shared_task task receiver periodic_task`. The decorated symbol and its module. |
| `url-handler` | Django: the handler named in `path()` / `re_path()` / `url()` in a `urls.py` (`.as_view()` removed, `include(...)` skipped), matched by name with a function or class in a file whose path contains "view". |
| `framework-module` | Django project (a `manage.py`, or a `settings.py` with `INSTALLED_APPS`): `urls.py models.py admin.py apps.py signals.py middleware.py consumers.py routing.py tasks.py wsgi.py asgi.py settings.py`, `templatetags/`, and the `Command` class of `management/commands/`. |
| `public-api` | Every `__init__.py` outside tests, in a package with no underscore-prefixed directory above it: the module itself, and what it exposes (names in a literal `__all__`, else every imported name and public function or class defined in it). A name that is a submodule exposes that module; a class exposes its public methods and `__init__`/`__call__`. |
| `shebang` | A Python or JS file whose first line is `#!` naming python or node. |
| `package-main` | JS/TS: `main`, `module`, `bin`, `exports` (strings, `./` paths, not `.json`) and files run by `node`/`nodemon`/`ts-node`/`tsx`/`babel-node`/`bun` in `scripts` of a `package.json`; with no `main`, the package's `index` file. |

Every function or class entry also makes its module an entry point (importing it ran the module's top-level code).

## Edges that carry a path
| Edge | Counts as |
|---|---|
| import of an internal module, top-level | solid (it runs with the importing module) |
| import inside a function | solid from the function that contains the import line (`edge_sites`); a guess from the module if the lines were not stored |
| import under `TYPE_CHECKING` / `import type` | not an edge (never runs) |
| call, confidence 1.0 or 0.9 | solid (calibration, 7 Nov: 30/30 correct in each band) |
| call, confidence 0.5 | guess (21/30 = 0.70 correct) |
| a class defined inside the code that runs | solid (a class body runs with its parent) |
| a class to its constructor (`__init__`, JS `constructor`) | solid (instantiation runs it) |
| a class to a special method (`__enter__`, `__call__`, `__deepcopy__` ...) | guess (Python calls these implicitly; no call is in the code) |
| a class to an ordinary method | no edge: only a call reaches it (changed 8 Nov: it used to be a guess for every method) |
| a function defined inside a function | guess (it runs if the enclosing function hands it out, as a decorator's wrapper does) |
| a module to the `__init__.py` of each package above it | solid (Python runs them first) |

## Tiers
The tier of a finding is the tier of the innermost symbol (function, method, class, otherwise the module) whose line range contains the finding's line.
Among the paths to a symbol, the one with the fewest guessed steps wins; then the fewest *structural* guesses (so a path whose guess is a call matched by name beats one whose guess is "special
method of a reached class"); then the fewest steps. The tier does not depend on the second and third keys, only the path that is shown.

**Entry class (recorded, not ranked).** For a finding with a path, `app` if the same tier is reached without the public-API entry points, `public-api` if it needs them (a library's exports are entry
points, so most of a library is reached through them). It is stored alongside the tier (`reach_entry_class` in the API) and reported as a descriptive table in the study; it is not part of any sort key.
Decided 8 Nov: one solid tier in the ranking, no split.

| Tier | Meaning | Sort rank |
|---|---|---|
| solid path | A path of solid edges only. UI: "Reachable from `<entry>` via a → b → c". | 0 |
| guess path | Every path needs at least one guessed step. UI: "Reachable only through guessed steps (a call matched by name, a special method Python calls implicitly, or a function defined inside code that is reached)". | 1 |
| not checked | The file is not analysed code (configuration, documentation, templates). UI: "Not in analysed code, so reachability was not checked". Sorts with the guess tier; it is never counted as one. | 1 |
| no path found | Analysed code with no path from any detected entry point. UI: "No path found from a detected entry point". | 2 |

Order with `sort=reachability`: `(placeholder, tier rank, severity rank, path, line, id)`. The default order is `(placeholder, severity rank, path, line, id)` and is unchanged.

## Known limits (they are shown in the UI caption or here)
- Entry points are found by pattern and can be missed; everything reached only through them is then "no path found".
- Calls are matched by name. Dynamic dispatch, decorators that register code by side effect (other than the listed ones), plugins loaded by name, and callbacks passed as arguments leave no edge.
- JS/TS is the weaker side: Express-style code assigns methods onto objects (`res.send = function…`) and passes handlers as arguments, so on the express checkout 68 of its 70 non-test functions are "no path found" although all its modules are reached.
- In a library, much of the code is public API and so is an entry point; most findings then land in the solid tier and an ordering by tier changes little.
- An ordinary method nothing calls (by a name the resolver can match) shows "no path found" even when its class is used; a function defined inside a function is a guess.

## For the evaluation
The reachability code is built and checked on the development set only (PyGoat, flask, black, express, itsdangerous). The four Bandit evaluation repos are not opened, ingested or inspected until this branch is merged and
its commit is referenced from the pre-registration. `python -m app.reach.report [snapshot_id ...]` prints entry points per kind, the tier of every finding and traced paths for hand checking.
