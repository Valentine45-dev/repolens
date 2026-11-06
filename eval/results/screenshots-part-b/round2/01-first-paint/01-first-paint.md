# Item 1: first-paint skeleton, before and after

Measured by `eval/layout_shift.mjs` in headless Edge at 1440x900, production build, normal load and a load with the app's scripts blocked (so only what `index.html` ships is on screen). Overlays: `eval/layout_overlay.py` (red = skeleton, cyan = loaded).

| Page | CLS before | CLS after | Shifts before | Shifts after | Largest skeleton-vs-loaded landmark offset after |
|---|---|---|---|---|---|
| home | 0.00019 | 0 | 1 | 0 | 0.0 px |
| explore | 0.08099 | 0.00011 | 5 | 1 | 0.0 px |
| findings | 0.00271 | 0 | 4 | 0 | 0.5 px |

Before, the skeleton had no counterpart for the page's elements (three cards on every page), so a landmark comparison does not apply; the CLS numbers are small only because the old placeholders were replaced rather than moved. The overlays show the mismatch.

What the remaining shift is: Explorer 0.00011 is the right-aligned counts text (`p.toolbar-note`) changing from a 168 px grey bar to 100 px of text.

## Landmarks after (skeleton rect vs loaded rect, x y w h)

### home

| Element | Skeleton | Loaded | Offset |
|---|---|---|---|
| `.topbar` | [[0, 0, 1440, 52]] | [[0, 0, 1440, 52]] | 0 |
| `.page-title` | [[400, 178, 640, 33.6]] | [[400, 178, 640, 33.6]] | 0 |
| `.lede` | [[400, 223.6, 605.6, 48]] | [[400, 223.6, 605.6, 48]] | 0 |
| `form` | [[400, 303.6, 640, 66]] | [[400, 303.6, 640, 66]] | 0 |
| `.submit-row` | [[400, 303.6, 640, 40]] | [[400, 303.6, 640, 40]] | 0 |
| `#repo-url` | [[400, 303.6, 544.2, 40]] | [[400, 303.6, 544.2, 40]] | 0 |
| `.submit-row .button` | [[952.2, 303.6, 87.8, 40]] | [[952.2, 303.6, 87.8, 40]] | 0 |
| `.field-message` | [[400, 351.6, 640, 18]] | [[400, 351.6, 640, 18]] | 0 |
| `.examples` | [[400, 393.6, 640, 64]] | [[400, 393.6, 640, 64]] | 0 |
| `.examples .chip` | [[513.4, 393.6, 170, 28]] | [[513.4, 393.6, 170, 28]] | 0 |
| `.section` | [[400, 505.6, 640, 123]] | [[400, 505.6, 640, 123]] | 0 |
| `.list-row` | [[401, 539.6, 638, 43.5]] | [[401, 539.6, 638, 43.5]] | 0 |

### explore

| Element | Skeleton | Loaded | Offset |
|---|---|---|---|
| `.topbar` | [[0, 0, 1440, 52]] | [[0, 0, 1440, 52]] | 0 |
| `.analysis-header` | [[0, 52, 1440, 55]] | [[0, 52, 1440, 55]] | 0 |
| `.analysis-heading` | [[24, 69.7, 200.7, 36.3]] | [[24, 69.7, 200.7, 36.3]] | 0 |
| `.analysis-tabs` | [[248.7, 70, 161.9, 36]] | [[248.7, 70, 161.9, 36]] | 0 |
| `.analysis-tab` | [[248.7, 70, 55.7, 36]] | [[248.7, 70, 55.7, 36]] | 0 |
| `.analysis-ask` | [[1368.4, 68, 47.6, 30]] | [[1368.4, 68, 47.6, 30]] | 0 |
| `.crumb-row` | [[0, 107, 1440, 38]] | [[0, 107, 1440, 38]] | 0 |
| `.breadcrumbs-up` | [[24, 115, 30, 30]] | [[24, 115, 30, 30]] | 0 |
| `.toolbar` | [[0, 145, 1440, 53]] | [[0, 145, 1440, 53]] | 0 |
| `.segmented` | [[24, 153, 109.4, 32]] | [[24, 153, 109.4, 32]] | 0 |
| `.check` | [[349.5, 158.5, 176.7, 21]] | [[349.5, 158.5, 176.7, 21]] | 0 |
| `.toolbar .button` | [[877.9, 154, 40.2, 30]] | [[877.9, 154, 40.2, 30]] | 0 |
| `.legend` | [[0, 198, 1440, 57]] | [[0, 198, 1440, 57]] | 0 |
| `.explore-body` | [[0, 255, 1440, 645]] | [[0, 255, 1440, 645]] | 0 |

### findings

| Element | Skeleton | Loaded | Offset |
|---|---|---|---|
| `.analysis-header` | [[0, 52, 1440, 55]] | [[0, 52, 1440, 55]] | 0 |
| `.analysis-heading` | [[24, 69.7, 281, 36.3]] | [[24, 69.7, 281, 36.3]] | 0 |
| `.analysis-tabs` | [[329, 70, 161.9, 36]] | [[329, 70, 161.9, 36]] | 0 |
| `.analysis-ask` | [[1368.4, 68, 47.6, 30]] | [[1368.4, 68, 47.6, 30]] | 0 |
| `.findings-head` | [[0, 107, 1425, 71]] | [[0, 107, 1425, 71.5]] | 0.5 |
| `.section-title` | [[24, 123, 1377, 21]] | [[24, 123, 1377, 21.5]] | 0.5 |
| `.findings-filters` | [[0, 178, 1425, 43]] | [[0, 178.5, 1425, 43]] | 0.5 |
| `.filter` | [[24, 178, 174.2, 30]] | [[24, 178.5, 174.2, 30]] | 0.5 |
| `.select-rule` | [[259, 178, 260, 30]] | [[259, 178.5, 260, 30]] | 0.5 |
| `.input-small` | [[883, 178, 140, 30]] | [[883, 178.5, 140, 30]] | 0.5 |
| `.findings-filters .check` | [[1047, 182.5, 208.4, 21]] | [[1047, 183, 208.4, 21]] | 0.5 |
