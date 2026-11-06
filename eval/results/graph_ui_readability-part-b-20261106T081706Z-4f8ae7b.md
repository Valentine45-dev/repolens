# Folder-map UI readability (before vs after)

Commit `4f8ae7b`. Rule: web/src/mapModel.ts `selectEdges`, budget 40, whole tiers of equal count, circular-import edges always drawn.

Before = the old default (flat file graph, 300 most connected files). After = the view a visitor now opens, with edges drawn at rest. Hovering or selecting a node adds all of its edges; "Show all edges" draws every one.

## Setting: default

| Repo | Before (nodes / edges) | After: opens as | nodes | edges total | edges drawn | Worst folder view: nodes / edges total / drawn |
|---|---|---|---|---|---|---|
| itsdangerous | 9 / 21 | file at root | 9 | 21 | 21 | src/itsdangerous: 8 / 21 / 21 |
| pygoat | 114 / 31 | folder at root | 9 | 4 | 4 | scoring: 12 / 10 / 10 |
| express | 7 / 7 | file at root | 7 | 7 | 7 | lib: 6 / 6 / 6 |
| flask | 25 / 95 | file at root | 25 | 95 | 24 | src/flask: 20 / 82 / 24 |
| black | 55 / 129 | folder at root | 5 | 1 | 1 | src/black: 25 / 66 / 28 |

## Setting: everything

| Repo | Before (nodes / edges) | After: opens as | nodes | edges total | edges drawn | Worst folder view: nodes / edges total / drawn |
|---|---|---|---|---|---|---|
| itsdangerous | 15 / 37 | file at root | 15 | 37 | 37 | src/itsdangerous: 8 / 21 / 21 |
| pygoat | 117 / 69 | folder at root | 9 | 7 | 7 | scoring: 13 / 13 / 13 |
| express | 142 / 291 | folder at root | 4 | 6 | 6 | test: 61 / 12 / 12 |
| flask | 83 / 353 | folder at root | 4 | 4 | 4 | src/flask: 20 / 91 / 40 |
| black | 300 / 225 (capped from 426) | folder at root | 6 | 5 | 5 | src/black: 25 / 69 / 36 |

## Symbol views (default setting, every non-test file)

| Repo | Views | Most nodes | Most edges | Most drawn | Views with hidden edges |
|---|---|---|---|---|---|
| itsdangerous | 9 | 26 | 34 | 34 | 0 |
| pygoat | 114 | 32 | 40 | 40 | 0 |
| express | 7 | 29 | 27 | 27 | 0 |
| flask | 25 | 54 | 80 | 40 | 5 |
| black | 55 | 61 | 186 | 40 | 10 |

## Every folder view (default setting)

### itsdangerous

| Folder | Files under it | Flat edges among them (before) | Nodes | Edges total | Edges drawn |
|---|---|---|---|---|---|
| `/` | 9 | 21 | 2 | 0 | 0 |
| `src/itsdangerous` | 8 | 21 | 8 | 21 | 21 |

### pygoat

| Folder | Files under it | Flat edges among them (before) | Nodes | Edges total | Edges drawn |
|---|---|---|---|---|---|
| `/` | 114 | 31 | 9 | 4 | 4 |
| `challenge` | 22 | 7 | 11 | 5 | 5 |
| `challenge/labs` | 3 | 0 | 3 | 0 | 0 |
| `challenge/management/commands` | 3 | 0 | 3 | 0 | 0 |
| `challenge/migrations` | 8 | 0 | 8 | 0 | 0 |
| `dockerized_labs` | 32 | 3 | 21 | 0 | 0 |
| `dockerized_labs/insufficient_logging_lab` | 1 | 0 | 1 | 0 | 0 |
| `dockerized_labs/sec_misconfig` | 1 | 0 | 1 | 0 | 0 |
| `dockerized_labs/sensitive_data_exposure` | 12 | 3 | 3 | 0 | 0 |
| `dockerized_labs/sensitive_data_exposure/dataexposure` | 7 | 3 | 6 | 3 | 3 |
| `dockerized_labs/sensitive_data_exposure/dataexposure/migrations` | 2 | 0 | 2 | 0 | 0 |
| `dockerized_labs/sensitive_data_exposure/sensitive_data_lab` | 4 | 0 | 4 | 0 | 0 |
| `introduction` | 35 | 2 | 9 | 2 | 2 |
| `introduction/migrations` | 26 | 0 | 26 | 0 | 0 |
| `introduction/static/js` | 2 | 0 | 2 | 0 | 0 |
| `pygoat` | 5 | 0 | 5 | 0 | 0 |
| `scoring` | 16 | 10 | 12 | 10 | 10 |
| `scoring/management` | 3 | 0 | 2 | 0 | 0 |
| `scoring/management/commands` | 2 | 0 | 2 | 0 | 0 |
| `scoring/migrations` | 3 | 0 | 3 | 0 | 0 |

### express

| Folder | Files under it | Flat edges among them (before) | Nodes | Edges total | Edges drawn |
|---|---|---|---|---|---|
| `/` | 7 | 7 | 2 | 1 | 1 |
| `lib` | 6 | 6 | 6 | 6 | 6 |

### flask

| Folder | Files under it | Flat edges among them (before) | Nodes | Edges total | Edges drawn |
|---|---|---|---|---|---|
| `/` | 25 | 95 | 2 | 0 | 0 |
| `docs` | 1 | 0 | 1 | 0 | 0 |
| `src/flask` | 24 | 95 | 20 | 82 | 24 |
| `src/flask/json` | 3 | 2 | 3 | 2 | 2 |
| `src/flask/sansio` | 3 | 4 | 3 | 4 | 4 |

### black

| Folder | Files under it | Flat edges among them (before) | Nodes | Edges total | Edges drawn |
|---|---|---|---|---|---|
| `/` | 55 | 129 | 5 | 1 | 1 |
| `profiling` | 5 | 0 | 5 | 0 | 0 |
| `scripts` | 7 | 0 | 7 | 0 | 0 |
| `src` | 41 | 127 | 4 | 4 | 4 |
| `src/black` | 25 | 66 | 25 | 66 | 28 |
| `src/blackd` | 4 | 2 | 4 | 2 | 2 |
| `src/blib2to3` | 11 | 22 | 4 | 4 | 4 |
| `src/blib2to3/pgen2` | 8 | 15 | 8 | 15 | 15 |
