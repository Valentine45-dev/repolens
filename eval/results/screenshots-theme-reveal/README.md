# Evidence: the theme switch as a circular reveal (`fix/theme-transition`)

Recorded 10 Nov 2026 on the eval PC (Pentium Silver N5030, UHD 605, 8 GB, 1366x768 screen at 60 Hz).
A production build of the branch (`5b78a13` plus the CSS-keyframes fix in the next commit) was served by
`vite preview` on :4180, with the API on :8000. Script: `eval/theme_reveal_evidence.mjs`, which reads the
test window through `eval/theme_reveal_window.ps1`. No API calls with a key, so $0.

| Folder | Browser | Pictures | Viewport |
|---|---|---|---|
| `edge/` | Edge 156.0.4314.58 | yes (page screenshots) | 1358x636 (maximised) |
| `firefox/` | Firefox 159.0.1 | no, `run.json` only (see below) | 1366x635 (screen-sized) |
| `edge-reduced-motion/` | Edge, `prefers-reduced-motion: reduce` emulated | yes | 1358x636 |
| `firefox-reduced-motion/` | Firefox, `ui.prefersReducedMotion=1` | no | 1366x635 |

## Method
- **Real windows** on this screen and a fresh throwaway profile for each run.
- **Pages:** Explorer for getredash/redash (map, `redash/handlers/queries.py` open in the file panel, Ask open; first-visit card dismissed) and Findings with All selected.
- **The real toggle,** clicked with real input: the DevTools protocol for Edge, WebDriver BiDi for Firefox.
- **A test-only hook** injected through that protocol (not in the app):
  - It counts `document.startViewTransition` calls.
  - Once a transition is ready, it can hold the reveal animation (the CSS animation on `::view-transition-new(root)`) at a set time, so the frame can be recorded, then lets it finish.
- **Held frames:** 25%, 50% and 75% of 450 ms on Explorer, and 50% on Findings, each in both directions. After each frame, one switch runs unheld.
- **Firefox has no pictures, on purpose:**
  - Its screenshot command, and `PrintWindow`, draw the page without the View Transition layer, so they show the new theme at once.
  - A screen capture would catch whatever window is in front. One attempt did catch the owner's own windows; those images were deleted and never committed.
  - So for Firefox each held frame is recorded as the browser's computed style of the transition's pseudo-elements. The test window is sized to the screen without being activated.

## Results

**Both browsers, every switch:**
- **One View Transition per switch.** The theme flips and the choice is stored. `aria-pressed` follows.
- **Nothing left behind:** `<html>` has no class after each switch (`theme-reveal` and `theme-instant` are gone), and the reveal's custom properties are removed.

**The circle while held**, from Firefox's computed `clip-path` of `::view-transition-new(root)`, the same in both directions and on both pages:

| Held at | Progress | `::view-transition-new(root)` | `::view-transition-old(root)` |
|---|---|---|---|
| 25% (112.5 ms) | 0.25 | `circle(188.495px at 1326px 25.5px)` | no clip, `animation: none` |
| 50% (225 ms) | 0.5 | `circle(729.686px at 1326px 25.5px)` | no clip, `animation: none` |
| 75% (337.5 ms) | 0.75 | `circle(1270.88px at 1326px 25.5px)` | no clip, `animation: none` |

- **The centre** is the toggle's centre. The full radius, 1459.37 px, reaches the farthest corner (bottom left).
- **The radii** are 12.9%, 50% and 87.1% of the full radius, which is ease-in-out.

In Edge, the pictures `edge/*-25pct.jpg`, `*-50pct.jpg` and `*-75pct.jpg` show the same circle from the toggle (1318, 25.5) in both directions.

**Unheld reveal, click to `finished`:**

| Edge | Explorer | Findings |
|---|---|---|
| `ready` (old picture shown until then) | 84 / 107 ms | 152 / 161 ms |
| `finished` | 579 / 588 ms | 654 / 754 ms |

The Firefox times in `firefox/run.json` come from a window behind other windows, so they don't reflect normal use. For Firefox in front, see the earlier probe in PROGRESS: `ready` about 56 ms, `finished` about 538 ms.

**No stacking:**
- **Clicks, both browsers:** two real clicks 80 ms apart start one transition and switch the theme once.
- **Enter in Edge:** two presses 80 ms apart on the focused toggle start one transition and switch once. The circle starts at the toggle's box, so it looks the same from the keyboard.
- **Enter in Firefox:** not shown. WebDriver BiDi keys need the window to have OS focus, and the test window deliberately never takes it. Left to the owner's real test.

**Reduced motion, both browsers, both pages, both directions:**
- **No View Transition is started** (0 calls), and the theme switches.
- **Edge pictures,** taken 120 ms after the click (`edge-reduced-motion/`), show the switch already complete.

## What this does not cover
- How smooth the reveal looks to the eye in Firefox. The owner's real-mouse test in Firefox and Chrome covers that.
- Chrome itself. Chrome 139 is the same engine as Edge, with older timings (see the probe numbers in PROGRESS).
