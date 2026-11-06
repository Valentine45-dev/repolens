# Edge crossings, before and after

Commit `2d8e967`. Yardstick: straight lines between node centres (`edgeMetrics` in `web/src/mapLayout.ts`). 'Back+same' = edges pointing back + edges inside one column.

| View | Nodes | Edges | Drawn before | Crossings before | Through nodes before | Back+same before | Drawn after | Crossings after | Through nodes after | Back+same after |
|---|---|---|---|---|---|---|---|---|---|---|
| flask src/flask (folder level) | 20 | 82 | 24 | 35 | 15 | 7+3 | 8 | 0 | 3 | 0+0 |
| pygoat (root) (folder level) | 9 | 4 | 4 | 0 | 0 | 1+0 | 4 | 0 | 0 | 1+0 |
| black src/black (folder level) | 25 | 66 | 28 | 75 | 43 | 9+0 | 19 | 5 | 22 | 0+0 |
| flask (root) (file level) | 25 | 95 | 24 | 27 | 15 | 6+2 | 8 | 0 | 4 | 0+0 |

All 38 folder views (default setting): 4 have any crossing.

| Measure | Before | After |
|---|---|---|
| crossings, total | 141 | 5 |
| edges through nodes, total | 107 | 43 |
| crossings, most in one view | 75 | 5 |
| edges drawn, most in one view | 28 | 19 |
| median crossings (views with any) | 31.0 | 0.0 |
