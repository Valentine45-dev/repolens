# Folder-first map: every folder view (Part A)

Generated from `graph_readability-part-a-20261105T191225Z-845379a.json` (commit `845379a`). Nodes include the "N more" node when a view overflows; hidden = nodes behind it.
**default** = tests and guessed calls hidden. **everything** = both shown.

Conditions: API stopped, Chrome closed, Claude desktop app open, Docker db only. flask analysed with Chrome and a Remotion headless shell open (low RAM); non-test embedding stopped at MAX_ANALYSIS_S=600, graph unaffected. black analysed with MAX_ANALYSIS_S=3600 and MAX_TEST_EMBED_S=60, Chrome closed partway through.

## itsdangerous (snapshot 1, `672971d`)

### default: flat graph 9 nodes, 21 edges; root 2 nodes, 0 edges; 2 folder views, max 8 nodes, 21 edges

| Folder | Nodes | Edges | Hidden |
|---|---:|---:|---:|
| `/` | 2 | 0 | 0 |
| `src/itsdangerous` | 8 | 21 | 0 |

### everything: flat graph 15 nodes, 37 edges; root 3 nodes, 2 edges; 3 folder views, max 8 nodes, 21 edges

| Folder | Nodes | Edges | Hidden |
|---|---:|---:|---:|
| `/` | 3 | 2 | 0 |
| `src/itsdangerous` | 8 | 21 | 0 |
| `tests/test_itsdangerous` | 6 | 4 | 0 |

## pygoat (snapshot 2, `46fef96`)

### default: flat graph 114 nodes, 31 edges; root 9 nodes, 4 edges; 20 folder views, max 26 nodes, 10 edges

| Folder | Nodes | Edges | Hidden |
|---|---:|---:|---:|
| `/` | 9 | 4 | 0 |
| `challenge` | 11 | 5 | 0 |
| `challenge/labs` | 3 | 0 | 0 |
| `challenge/management/commands` | 3 | 0 | 0 |
| `challenge/migrations` | 8 | 0 | 0 |
| `dockerized_labs` | 21 | 0 | 0 |
| `dockerized_labs/insufficient_logging_lab` | 1 | 0 | 0 |
| `dockerized_labs/sec_misconfig` | 1 | 0 | 0 |
| `dockerized_labs/sensitive_data_exposure` | 3 | 0 | 0 |
| `dockerized_labs/sensitive_data_exposure/dataexposure` | 6 | 3 | 0 |
| `dockerized_labs/sensitive_data_exposure/dataexposure/migrations` | 2 | 0 | 0 |
| `dockerized_labs/sensitive_data_exposure/sensitive_data_lab` | 4 | 0 | 0 |
| `introduction` | 9 | 2 | 0 |
| `introduction/migrations` | 26 | 0 | 0 |
| `introduction/static/js` | 2 | 0 | 0 |
| `pygoat` | 5 | 0 | 0 |
| `scoring` | 12 | 10 | 0 |
| `scoring/management` | 2 | 0 | 0 |
| `scoring/management/commands` | 2 | 0 | 0 |
| `scoring/migrations` | 3 | 0 | 0 |

### everything: flat graph 117 nodes, 69 edges; root 9 nodes, 7 edges; 20 folder views, max 26 nodes, 13 edges

| Folder | Nodes | Edges | Hidden |
|---|---:|---:|---:|
| `/` | 9 | 7 | 0 |
| `challenge` | 12 | 9 | 0 |
| `challenge/labs` | 3 | 0 | 0 |
| `challenge/management/commands` | 3 | 0 | 0 |
| `challenge/migrations` | 8 | 0 | 0 |
| `dockerized_labs` | 21 | 0 | 0 |
| `dockerized_labs/insufficient_logging_lab` | 1 | 0 | 0 |
| `dockerized_labs/sec_misconfig` | 1 | 0 | 0 |
| `dockerized_labs/sensitive_data_exposure` | 3 | 0 | 0 |
| `dockerized_labs/sensitive_data_exposure/dataexposure` | 6 | 3 | 0 |
| `dockerized_labs/sensitive_data_exposure/dataexposure/migrations` | 2 | 0 | 0 |
| `dockerized_labs/sensitive_data_exposure/sensitive_data_lab` | 4 | 0 | 0 |
| `introduction` | 10 | 2 | 0 |
| `introduction/migrations` | 26 | 0 | 0 |
| `introduction/static/js` | 2 | 0 | 0 |
| `pygoat` | 5 | 0 | 0 |
| `scoring` | 13 | 13 | 0 |
| `scoring/management` | 2 | 0 | 0 |
| `scoring/management/commands` | 2 | 0 | 0 |
| `scoring/migrations` | 3 | 0 | 0 |

## express (snapshot 3, `1c6f1b0`)

### default: flat graph 7 nodes, 7 edges; root 2 nodes, 1 edges; 2 folder views, max 6 nodes, 6 edges

| Folder | Nodes | Edges | Hidden |
|---|---:|---:|---:|
| `/` | 2 | 1 | 0 |
| `lib` | 6 | 6 | 0 |

### everything: flat graph 142 nodes, 291 edges; root 4 nodes, 6 edges; 17 folder views, max 61 nodes, 12 edges

| Folder | Nodes | Edges | Hidden |
|---|---:|---:|---:|
| `/` | 4 | 6 | 0 |
| `examples` | 25 | 0 | 0 |
| `examples/content-negotiation` | 3 | 2 | 0 |
| `examples/multi-router` | 2 | 1 | 0 |
| `examples/multi-router/controllers` | 2 | 0 | 0 |
| `examples/mvc` | 4 | 2 | 0 |
| `examples/mvc/controllers` | 4 | 0 | 0 |
| `examples/route-separation` | 4 | 3 | 0 |
| `examples/search` | 2 | 0 | 0 |
| `examples/session` | 2 | 0 | 0 |
| `examples/static-files` | 2 | 0 | 0 |
| `examples/view-constructor` | 2 | 1 | 0 |
| `examples/view-locals` | 2 | 1 | 0 |
| `lib` | 6 | 8 | 0 |
| `test` | 61 | 12 | 13 |
| `test/acceptance` | 18 | 0 | 0 |
| `test/support` | 3 | 0 | 0 |

## flask (snapshot 6, `49943b5`)

### default: flat graph 25 nodes, 95 edges; root 2 nodes, 0 edges; 5 folder views, max 20 nodes, 82 edges

| Folder | Nodes | Edges | Hidden |
|---|---:|---:|---:|
| `/` | 2 | 0 | 0 |
| `docs` | 1 | 0 | 0 |
| `src/flask` | 20 | 82 | 0 |
| `src/flask/json` | 3 | 2 | 0 |
| `src/flask/sansio` | 3 | 4 | 0 |

### everything: flat graph 83 nodes, 353 edges; root 4 nodes, 4 edges; 23 folder views, max 25 nodes, 91 edges

| Folder | Nodes | Edges | Hidden |
|---|---:|---:|---:|
| `/` | 4 | 4 | 0 |
| `docs` | 1 | 0 | 0 |
| `examples` | 3 | 0 | 0 |
| `examples/celery` | 2 | 1 | 0 |
| `examples/celery/src/task_app` | 3 | 2 | 0 |
| `examples/javascript` | 2 | 1 | 0 |
| `examples/javascript/js_example` | 2 | 2 | 0 |
| `examples/javascript/tests` | 2 | 0 | 0 |
| `examples/tutorial` | 2 | 1 | 0 |
| `examples/tutorial/flaskr` | 4 | 6 | 0 |
| `examples/tutorial/tests` | 5 | 2 | 0 |
| `src/flask` | 20 | 91 | 0 |
| `src/flask/json` | 3 | 2 | 0 |
| `src/flask/sansio` | 3 | 4 | 0 |
| `tests` | 25 | 9 | 0 |
| `tests/test_apps` | 4 | 0 | 0 |
| `tests/test_apps/blueprintapp` | 2 | 1 | 0 |
| `tests/test_apps/blueprintapp/apps` | 3 | 0 | 0 |
| `tests/test_apps/cliapp` | 6 | 0 | 0 |
| `tests/test_apps/cliapp/inner1` | 2 | 0 | 0 |
| `tests/test_apps/cliapp/inner1/inner2` | 2 | 0 | 0 |
| `tests/test_apps/helloworld` | 2 | 0 | 0 |
| `tests/type_check` | 3 | 0 | 0 |

## black (snapshot 7, `b4f1fca`)

### default: flat graph 55 nodes, 129 edges; root 5 nodes, 1 edges; 8 folder views, max 25 nodes, 66 edges

| Folder | Nodes | Edges | Hidden |
|---|---:|---:|---:|
| `/` | 5 | 1 | 0 |
| `profiling` | 5 | 0 | 0 |
| `scripts` | 7 | 0 | 0 |
| `src` | 4 | 4 | 0 |
| `src/black` | 25 | 66 | 0 |
| `src/blackd` | 4 | 2 | 0 |
| `src/blib2to3` | 4 | 4 | 0 |
| `src/blib2to3/pgen2` | 8 | 15 | 0 |

### everything: flat graph 426 nodes, 225 edges; root 6 nodes, 5 edges; 29 folder views, max 61 nodes, 69 edges

| Folder | Nodes | Edges | Hidden |
|---|---:|---:|---:|
| `/` | 6 | 5 | 0 |
| `profiling` | 5 | 0 | 0 |
| `scripts` | 7 | 1 | 0 |
| `src` | 4 | 5 | 0 |
| `src/black` | 25 | 69 | 0 |
| `src/blackd` | 4 | 2 | 0 |
| `src/blib2to3` | 4 | 4 | 0 |
| `src/blib2to3/pgen2` | 8 | 15 | 0 |
| `tests` | 19 | 8 | 0 |
| `tests/data` | 10 | 0 | 0 |
| `tests/data/cases` | 61 | 3 | 244 |
| `tests/data/gitignore_used_on_multiple_sources` | 2 | 0 | 0 |
| `tests/data/gitignore_used_on_multiple_sources/dir1` | 2 | 0 | 0 |
| `tests/data/gitignore_used_on_multiple_sources/dir2` | 2 | 0 | 0 |
| `tests/data/ignore_directory_gitignore_tests` | 3 | 0 | 0 |
| `tests/data/ignore_directory_gitignore_tests/large_ignored_dir_two` | 4 | 0 | 0 |
| `tests/data/ignore_subfolders_gitignore_tests` | 2 | 0 | 0 |
| `tests/data/ignore_subfolders_gitignore_tests/subdir` | 2 | 0 | 0 |
| `tests/data/include_exclude_tests/b` | 3 | 0 | 0 |
| `tests/data/include_exclude_tests/b/.definitely_exclude` | 2 | 0 | 0 |
| `tests/data/include_exclude_tests/b/dont_exclude` | 2 | 0 | 0 |
| `tests/data/include_exclude_tests/b/exclude` | 3 | 0 | 0 |
| `tests/data/include_exclude_tests/b/exclude/still_exclude` | 2 | 0 | 0 |
| `tests/data/invalid_nested_gitignore_tests` | 2 | 0 | 0 |
| `tests/data/line_ranges_formatted` | 6 | 0 | 0 |
| `tests/data/miscellaneous` | 12 | 0 | 0 |
| `tests/data/nested_gitignore_tests` | 2 | 0 | 0 |
| `tests/data/nested_gitignore_tests/root` | 4 | 0 | 0 |
| `tests/data/nested_gitignore_tests/root/child` | 3 | 0 | 0 |
