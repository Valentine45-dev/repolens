# Item 4: edge tooltips, hit test (PyGoat root, 4 edges, production build, in-app browser)

`document.elementFromPoint` at the edge line and 8 px either side is what a real mouse hits.

| | Before (`9f9a31b`) | After |
|---|---|---|
| computed `pointer-events` of an edge | `none` (React Flow marks it `inactive`) | `visiblestroke` |
| hit test on the line, +8 px, -8 px | pane, pane, pane (4 of 4 edges) | edge, edge, edge (4 of 4 edges) |
| tooltip on the line | never (native `<title>` unreachable) | "challenge → scoring: 4 imports · 6 calls" |
| tooltip on the count label ("10") | none (label ignored the pointer) | same text |
| node tooltip (challenge) | "challenge" (the name again) | "challenge/ / 22 files · 1 of them tests or examples · 8 findings" |

Hit zone: `interactionWidth` 18 px. Tooltip: our own element that follows the pointer (no native delay).
Screenshot: `04-edge-tooltip-after.jpg` (tooltip under the challenge -> scoring edge).
