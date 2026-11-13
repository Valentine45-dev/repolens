# Code view syntax colours (`feat/code-highlight`), evidence

Headless Edge, throwaway profile (a temp `--user-data-dir`, deleted afterwards), 1366x768, on the eval
PC (Intel Pentium Silver N5030, 8 GB). Script: `eval/code_highlight_evidence.mjs` (no dependencies;
DevTools protocol). No `/ask` call: $0 API spend. Data: the dev database (PyGoat = snapshot 2,
express = 3, flask = 6, black = 7).

- `before` = `main` at `ed162be`, built and served on 127.0.0.1:5175.
- `after` = this branch, served on 127.0.0.1:5173.

## Screenshots (real size, 1366x768)

| | before (`main`) | after |
|---|---|---|
| Python, light, cited lines 21-28 | `before-1366-light-py.png` | `after-1366-light-py.png` |
| Python, dark | `before-1366-dark-py.png` | `after-1366-dark-py.png` |
| JavaScript, light, cited lines 10-16 | `before-1366-light-js.png` | `after-1366-light-js.png` |
| JavaScript, dark | `before-1366-dark-js.png` | `after-1366-dark-js.png` |

Python is PyGoat `introduction/views.py`; JavaScript is PyGoat `introduction/static/js/lab_manager.js`.
The cited-line band and the line numbers stay on top of the colours in both themes. The map behind
the panel can be at a different stage of its first fit in a before/after pair (screenshot timing);
it is not part of this change.

`after-1366-swap-*.png`: the biggest files still coloured, at their cited lines after the colours
arrived. `after-1366-large-*.png`: files over the limit, plain, with "Colours off for large files"
in the panel caption.

## Measurements (`measure.json`, final run, limit 3,000 lines / 256 KB)

**Lazy loading.** Home (`/`) and Findings (`/a/2/findings`) request no worker, grammar, Shiki or
WASM file (`heavy_requests: []`, page network and resource timing). The Explorer with a file open
requests `codeColours.worker-*.js` (the control). In the build output, only the Explore chunk
references the worker, and only the worker references the grammar chunks. No `.wasm` is emitted.

**Time to colours** (plain text on screen to colours on, one page, so one worker and one
highlighter):

| # | File | Lines | Final run | Earlier run |
|---|---|---|---|---|
| 1 | first file: PyGoat `introduction/views.py` (worker start, Shiki, Python grammar) | 334 | 883 ms | 2,919 ms |
| 2 | second file, first JS: `lab_manager.js` (JS grammar loads and compiles) | 589 | 3,881 ms | 3,316 ms |
| 3 | Python again: `challenge/labs/security_headers_lab/app.py` | 233 | 483 ms | 268 ms |
| 4 | JS again: express `lib/response.js` | 1,050 | 1,025 ms | 754 ms |

The earlier run is `probe-limit5000-first-run.json`; the files and order are the same, and the
limit makes no difference at these sizes. All of this time is spent in the worker. The page stays
responsive and shows plain text.

**The swap** (the main-thread task that puts the coloured runs on the page). For scale, the task
that first shows the plain text is also given:

| File | Lines | Coloured spans | Swap long task | Plain render long task |
|---|---|---|---|---|
| black `src/black/trans.py` | 2,849 | 3,177 | 433 ms | 236 ms |
| flask `src/flask/app.py` | 1,686 | 2,046 | 256 ms | 179 ms |
| express `test/app.router.js` | 1,217 | 2,890 | 278 ms | 102 ms |

Before the limit changed (`probe-limit5000-swap.json`, limit 5,000), black `tests/test_black.py`
(4,591 lines, 7,402 spans) had a **1,228 ms** swap (1,081 to 1,086 ms in two earlier runs), and
`src/black/linegen.py` (3,184 lines) had 541 to 601 ms. The brief's rule (over 200 ms on
test_black.py means drop to 3,000) applied, so the limit is 3,000 lines. Even at 3,000 lines the
swap is still about 0.25 to 0.45 s on this PC for files over about 1,200 lines.

`probe-merged-text-nodes-swap.json` records a rejected variant that joined the plain runs and line
breaks into one text node. It was slower: test_black 3.1 to 4.2 s against about 1.1 to 1.2 s.

**No shift inside the code view.** Across the swap, the panel's `scrollTop`, the `<pre>`'s height,
and the code's and band's positions relative to the panel are unchanged. The `.code` and `<pre>`
elements are the same nodes, and the aria-label is unchanged.

On the two flask/black Python files, a 0.011 layout shift was recorded in the same window. Its
source is `explore-body`: the whole Explorer body moved down 22 px when the legend strip's second
line appeared (legend 35 to 57 px). The same 22 px move happens on `main` with no colours
(probe: `explore-body` top 237 to 259 px about 8 s after load). It is not part of this change.

**Theme switch with colours on** (a real click on the toggle): keyword `rgb(0,0,255)` became
`rgb(94,163,220)`, string `rgb(163,21,21)` became `rgb(206,145,120)`, and the band
`rgb(253,243,211)` became `rgb(59,50,20)`. The `<pre>` and its first child node are the same
nodes, so only CSS changed and nothing was tokenised again.

**Large files**: `tests/test_black.py` (4,591 lines) and `profiling/list_huge.py` (22,431) have
`data-colours="off"`, 0 spans, and the caption "Python · N lines · Colours off for large files".
5 of the 768 openable code files in the four snapshots are over 3,000 lines (2 at 5,000).

## Commands

```
node eval/code_highlight_evidence.mjs --base http://127.0.0.1:5175 --out eval/results/screenshots-code-highlight --label before --mode shots
node eval/code_highlight_evidence.mjs --base http://127.0.0.1:5173 --out eval/results/screenshots-code-highlight --label after --mode shots
node eval/code_highlight_evidence.mjs --base http://127.0.0.1:5173 --out eval/results/screenshots-code-highlight --label after --mode measure
```
