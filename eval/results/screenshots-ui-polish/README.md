# Screenshots: UI/UX polish and dark mode (`feat/ui-polish`)

Headless Microsoft Edge (`--headless=new --screenshot`, `--virtual-time-budget=20000` so the data has
arrived), saved as JPEG (quality 72). Every view is reached by its URL; nothing is clicked.

| Folder | What | Served from |
|---|---|---|
| `before/` | `main` (`f57f523`), light only | main's build, `vite preview` on :5174 |
| `after-light/` | this branch, light | this branch's build, `vite preview` on :5173 |
| `after-dark/` | this branch, dark | same |
| `loaders/` | loading states, with `REPOLENS_DEV_API_DELAY_MS` | see below |
| `first-visit/` | the "How to read this map" card on a first visit (profile seeded without `mapHintSeen`) | :5173 |
| `no-key/` | Ask with the API started without `LLM_API_KEY` (one process, then restarted normally) | :5173 |

Each set has `1366/` and `1920/` (window 1366x768 and 1920x1080).

**Theme:** set by the app's own stored choice, not the OS. Each set uses a throwaway Edge profile
seeded once through a page on the same origin (`/__seed.html`, not in the repo) that writes
`repolens.theme` (`light` or `dark`), the same recent-analyses list as the owner's browser, and
`repolens.mapHintSeen` (so the first-visit card does not cover the map; it has its own shot). This PC's
OS theme is dark, and headless Edge follows it, so without the stored choice every "light" shot would
have been dark.

**Loaders** (`loaders-light/`, `loaders-dark/`, 1366 and 1920): headless Edge driven over its DevTools
protocol from a small Node script (Node's own WebSocket, no packages; the approach of
`eval/layout_shift.mjs`), because `--screenshot` either waits for every request (with a time budget)
or shoots before the app has run. Two `vite preview` servers of this branch's build:
`REPOLENS_DEV_API_DELAY_MS=8000` (every `/api` request) and `=60000` with
`REPOLENS_DEV_API_DELAY_MATCH=/files/|/reach` (only the file text and the reachability path). The
screenshot is taken once the loading element is on screen. `loaders-shimmer-sync.json` records, for each
shot, how many skeleton bars were shimmering and the spread of their phases (0 = in step).
Retakes: `loaders-dark/1366/L02` was first taken after the browser had cached the file from the previous case; it was retaken with the browser cache off (`loaders-shimmer-sync-retake.json`). `loaders-light/1920/L02` showed the file already loaded on both tries and was left out; the light code-loading state is `loaders-light/1366/L02`. In `loaders-shimmer-sync.json` every shot with bars has all of them at one phase except light 1920 L02 (bars at 0 and 650 ms: bars added in the same frame as the measurement, before their start time was set).
L07 asks "Which files import src/flask/helpers.py?", which the router answers from the graph (checked
offline before the run: no LLM call, $0).

| # | Loading state | Server and URL |
|---|---|---|
| L01 | Explorer, first load | 8 s, `/a/6/explore` |
| L02 | File panel, code area | files 60 s, `/a/6/explore?level=file&root=src/flask&node=789` |
| L03 | Findings opened from a link to a finding | 8 s, `/a/6/findings?finding=5488` |
| L04 | Reachability block | reach 60 s, `/a/7/findings?category=all&order=reachability&finding=5335` |
| L05 | Opening a folder ("Opening challenge…") | 8 s, `/a/2/explore`, then a client-side move to `challenge` |
| L06 | Home, status of recent analyses | 8 s, `/` |
| L07 | Ask, "Working on it…" | 8 s, `/a/6/explore?ask=1`, one graph question |

**Reduced motion** (`reduced-motion/`): a page on the same origin with the real stylesheet and one
skeleton bar, shown in headless Edge without and with `--force-prefers-reduced-motion`; it prints the
computed style of the bar's shimmer. Normal: `display=block animation-name=skeleton-shimmer`, 1
animation. Reduced: `display=none animation-name=none`, 0 animations (a static block).

| # | View | URL |
|---|---|---|
| 01 | Home with recent analyses | `/` |
| 02 | Explorer, flask root (files) | `/a/6/explore` |
| 03 | same, Ask open | `/a/6/explore?ask=1` |
| 04 | file panel and Ask together (tabs below 1600px) | `/a/6/explore?ask=1&node=789&level=file&root=src/flask` |
| 05 | PyGoat folders (no hidden edges: no line 2, "All edges" dimmed) | `/a/2/explore` |
| 06 | flask `js_example`, a real cycle | `/a/6/explore?level=folder&root=examples/javascript/js_example&tests=1` |
| 07 | express `test/`, overflow and zoomed first view | `/a/3/explore?level=folder&root=test&tests=1` |
| 08 | List view filtered to `test/` | `/a/3/explore?view=list&root=test&tests=1` |
| 09 | Flat view, black | `/a/7/explore?level=flat` |
| 10 | Function view | `/a/2/explore?level=symbol&root=introduction/views.py` |
| 11 | Empty folder (all files are tests) | `/a/3/explore?level=folder&root=test` |
| 12 | Findings, PyGoat | `/a/2/findings` |
| 13 | Finding panel with a reachability path, black | `/a/7/findings?category=all&order=reachability&finding=5335` |
| 14 | Empty filter result | `/a/1/findings?tests=hide` |
| 15 | Finding panel and Ask together | `/a/6/findings?ask=1&finding=5488` |
