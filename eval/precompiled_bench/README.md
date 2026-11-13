# Precompiled grammars against the regex engine (feat/code-highlight)

This answers whether Shiki's precompiled grammars (`@shikijs/langs-precompiled` with
`createJavaScriptRawEngine`) colour sooner on a cold start than the regular grammars with
`createJavaScriptRegexEngine`, and whether their colours are the same. Both are Shiki 4.6.0. No
repository code runs: the page only tokenises text.

- `index.html` and `bench.js`: one cold start per page load. The page takes `?engine=regex|pre`,
  `&lang=python|javascript` and `&warm=0|1`. It times loading the core, engine and grammar, then
  the first and second tokenising of a real file (PyGoat `introduction/views.py`, 334 lines, or
  `introduction/static/js/lab_manager.js`, 589 lines, copied next to the page). It checks that the
  tokens give back the text exactly, then POSTs the result to `/result`.
- `bench_run.mjs <dist> <out.json> [runs]`: serves the built page on 127.0.0.1:5199 and opens each
  configuration in a fresh headless Edge or Firefox with its own throwaway profile. The browser
  never shows a window. It records the POSTed result (tagged with its own query string), then
  kills only that browser's process tree. `WARMS=0` is the default.
- `compare_pre.mjs <shiki install> <samples dir>`: in Node, colours every sample with both setups
  and counts the characters whose colour differs.

These were built with Vite from a scratch install (`shiki@4.6.0`,
`@shikijs/langs-precompiled@4.6.0`). The results are in
`eval/results/screenshots-code-highlight/precompiled-bench.json` and
`precompiled-colour-compare.txt`, and the conclusions are in that folder's README.
