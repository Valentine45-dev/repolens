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

## Round 2 (after the owner's Firefox test): precompiled grammars, warm-up, ligatures

The owner found the first colouring in a Firefox session slow: about 3 s for the first Python file
and about 6 s for the first JS file. After that, colours were instant.

### Precompiled grammars (`precompiled-bench.json`, `precompiled-colour-compare.txt`; harness in `eval/precompiled_bench/`)
Median time from the file text to colours on a cold start (3 runs each, fresh headless browser and
throwaway profile for every run, machine otherwise idle). The current setup is the regex engine
with regular grammars; precompiled is the raw engine with precompiled grammars:

| Browser | Python (`views.py`) current → precompiled | JS (`lab_manager.js`) current → precompiled |
|---|---|---|
| Edge | 1,038 → 744 ms | 3,412 → 3,204 ms |
| Firefox | 4,339 → 3,022 ms | 14,273 → 8,642 ms |

The colours were then compared character by character in Node:
- **JavaScript, TypeScript and TSX are identical:** 0 differing characters over 4 express files
  and 6 TS/TSX files.
- **Python is wrong:** 39 to 87% of characters change colour, usually because everything after
  some line becomes string colour. This is shikijs/shiki#918, still open.

Python's apparent speed-up came from that broken output. Kept: precompiled grammars for JS, TS
and TSX only (about +1.0 kB gzip per grammar). Python stays on the regex engine.
`codeColoursCore.test.ts` checks on every test run that the precompiled JS/TS/TSX colours equal
the regex engine's on real files.

### Warm-up (`warmup.json`; script `eval/code_warmup_evidence.mjs`)
This is an A/B on the same flow. Each run opens PyGoat's Explorer map, waits 20 s after the map
draws, then opens a Python file and then a JS file in-app. The **with** build is this branch; the
**without** build is the same tree with only `scheduleWarmUp` turned off, served on 5175. Both ran
in Edge (DevTools protocol) and Firefox (WebDriver BiDi), headless with throwaway profiles, 3 runs
each, alternating which build ran first.

The PC was under outside load during these runs (the owner's Chrome and Windows background tasks
after a restart, CPU at 100%), so absolute times are inflated. The with/without comparison is
like for like. Plain text to colours:

| | Python, 1st file: without → with | JS, 2nd file: without → with |
|---|---|---|
| Edge | 780–1,069 → 128–146 ms | 1,734–2,604 → 1,934–3,781 ms |
| Firefox | 1,230–2,345 → 532–682 ms | 2,557–6,240 → 2,436–6,051 ms |

Warming Python helps clearly. Warming JS gives nothing: its precompiled grammar has no compile
step left, and the remaining cost is running the tokenizer over the file. The shipped warm-up
therefore loads Python only, which also starts the worker and Shiki's core for every later file.

Effect on the map:
- The warm-up starts only after the map's React Flow canvas reports ready, plus an idle callback.
- Map draw times show no systematic difference: Edge 5.5–14.2 s with against 7.0–9.4 s without,
  under load.
- Main-thread long tasks after the map while waiting (Edge) were 82–153 ms with against 85–92 ms
  without.
- Firefox has no long-task API.

### Lazy loading, re-checked with the warm-up (`measure-lazy-ligatures.json`)
- Home and Findings request no worker, grammar or Shiki file after 7 s, which is longer than the
  warm-up's 5 s idle timeout.
- The Explorer with a file open loads the worker.
- The Explorer map with no file open now loads it too: that is the warm-up.

### Ligatures (`measure-lazy-ligatures.json`, `after-1366-ligatures-closeup.png`)
- With a JS file open, 1,787 elements drawn in JetBrains Mono have `font-variant-ligatures: none`
  and none have ligatures on.
- The close-up of `lab_manager.js` line 10 shows `!==` as three characters.
- `web/src/monoFont.test.ts` checks that every CSS rule that sets the mono font also turns
  ligatures off.
