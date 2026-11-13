# Citation chip opens the File tab (`fix/citation-opens-file`)

Evidence for the real-mouse bug: below 1600px (File | Ask tabs share the right column),
clicking a citation chip for a file already open behind Ask left Ask in front, and the code
view could scroll while the panel was `display:none`, landing on the wrong offset (often
line 1) once the tab was opened by hand.

Captured headless in Edge (throwaway profile, real mouse clicks at element centres, never a
window shown to the owner) with `eval/citation_tab_evidence.mjs` against the real API
(snapshot 2, `adeyosemanputra/pygoat`) and a seeded Ask conversation (one real graph-routed
answer from `/snapshots/2/ask`, one hand-written AI-shaped turn whose own text says no model
was called — **$0 API spend**, no LLM call anywhere in this evidence).

```
node eval/citation_tab_evidence.mjs --base <url> --out DIR --label before|after --width 1366|1920 [--reduced 1]
```

## Folders
- `before/` — `main` (`8e6a787`), built and served on its own port.
- `after/` — this branch, built and served on :5173.
- `after-reduced-motion/` — this branch with `--force-prefers-reduced-motion`.

Each run writes `<label>-<width>.json` (DOM state after every step) and one screenshot per
step (`<label>-<width>-<step>.png`).

## Steps
| Step | What it does |
|---|---|
| a0/a1 | Ask open, no file yet; type a draft; click a citation chip (lab_manager.js:53-56) |
| a2 | Back to Ask: conversation, draft and scroll position |
| b1 | Same file already open behind Ask: a chip for other lines in it (380-390) |
| b2/b3 | Scroll the code away, then click the **same** chip again (address unchanged) |
| c1 | A citation chip for a different file (views.py:300-310) |
| d1 | Graph answer: a "called at" site chip (lab_manager.js:212) |
| e1 | Graph answer: a result row (launchLab, 103-230 — taller than the panel) |
| f1 | File panel, Uses tab: a site chip (same-file; panel is already in front here) |
| g0/g1 | Finding panel beside Ask, then "Open in Explorer" |
| h1 | A reachability path chip in the finding panel |
| i1 | A deep link with `lines=` and `ask=1` |

## Pass/fail by entry point (below 1600px)

| Entry point | main (`before`) | this branch (`after`) |
|---|---|---|
| Ask citation chip, file not yet open (a1) | pass (tab switches: `node` was unset) | pass |
| Ask citation chip, **same file already open**, new lines (b1) | **fail** — tab stays on Ask, panel never shown | **fixed** — File tab comes forward, lines centred |
| Same chip clicked again, address unchanged (b3) | **fail** — same as b1 | **fixed** |
| Ask citation chip, different file (c1) | pass (tab switches: `node` changes) | pass |
| Graph "called at" site chip (d1) | tab switches (file id changes), but **scroll lands on the wrong lines** (old `useEffect` scrolled before the panel had layout) | **fixed** — tab switches and lines are centred |
| Graph result row, same file as current (e1) | **fail** — tab stays on Ask (file id unchanged) | **fixed** |
| File panel Uses-tab site chip (f1) | pass — panel is already in front to reach this tab | pass (unchanged) |
| Finding panel → "Open in Explorer" (g1) | Ask closes (the link never carried `ask=1`); not the tab bug | unchanged — pre-existing, out of this fix's scope |
| Reachability path chip in a finding (h1) | Ask closes (same reason as g1) | unchanged — pre-existing, out of this fix's scope |
| Deep link with `lines=` and `ask=1` (i1) | pass (tab switches: `node` is set on load) | pass |

`g1` and `h1` never carry `ask=1` in their link on either branch (`ReachBlock.tsx`,
Findings.tsx's "Open in Explorer"), so Ask closes instead of sharing the column — a
pre-existing, unrelated behaviour, unchanged here and left alone per the bug report's scope
("fix any that fail **the same way**").

## 1600px and above (three columns)
No tabs exist (`.right-tabs` absent); Ask and the panel sit side by side and neither is ever
`display:none`. Checked identical on `before` and `after` at 1920px for every step above:
same final scroll positions, same highlighted ranges. The scroll-while-hidden bug could not
occur there even on `main`, confirming the fix only changes behaviour below 1600px.

## Reduced motion
`after-reduced-motion/` repeats the branch's 1366 and 1920 runs with
`prefers-reduced-motion: reduce` forced; same tab/scroll outcomes (the instant-vs-smooth
distinction is covered deterministically by the Vitest unit tests in
`web/src/components/CodeView.dom.test.tsx`, not by this screenshot capture).

## Other checks for this branch
- `web`: 221/221 tests pass, `tsc` clean.
- `backend`: ruff clean, 491 passed, 3 network skips.
- `git diff main -- web/src/graphModel.ts web/src/mapModel.ts web/src/mapLayout.ts web/src/api.ts backend/` — empty.
- 457-view check: `eval/results/ui_drawn_counts-after-citation-tab-20261113T134550Z-8e6a787.json`
  vs the last approved baseline — 457 of 457 views identical.
- $0 API spend: every question used in this evidence is graph-routed or a hand-seeded,
  clearly-labelled test turn; no LLM call was made.
