---
version: 1
slug: "web-src-pages-home-tsx"
primary_target: "web/src/pages/Home.tsx"
related_targets: ["web/src/pages/Progress.tsx"]
---

# Surface: web shell — Home (`/`) and Progress (`/a/:id`)

Mode: Operate. Build path: code-led (Operate surfaces are always code-led).
Audience/job: a developer about to open an unfamiliar repo; paste a URL, then watch the real pipeline. Constraints: spec §5.1, §5.2, §8; CLAUDE.md UI rules (light only, nothing for unbuilt features). Confirmed 27 Oct: example chips for itsdangerous, express, ky; recent analyses from this browser included.

## Direction contract

THESIS: A quiet instrument for one job: paste a URL, then see exactly what the analysis is doing and on which commit. Refuses the category default of a marketing hero, feature-card grid and fake progress bar.

OWN-WORLD: Spec §8 pinned: white ground, #FAFAFA panels, 1px #E4E4E7 rules, black primary button, Inter 400/500/600 on a 14px base, JetBrains Mono for every repo name, commit SHA, path and number; semantic colour only for state (success when done, danger when failed). Radius 6/10, no shadows.

STORY: Before submitting the visitor knows what RepoLens does, for which languages, and its limits; after submitting they see the exact commit, each real stage advancing, and that they can leave and come back.

FIRST VIEWPORT: Top bar: wordmark left, "New analysis" link. Home: one left-aligned column, max 640px, starting about a fifth down: 28px headline, one-line explainer, URL field and black Analyze button on one row, limits caption beneath, example repos as mono chips, then the recent list. Progress: owner/repo @ sha in mono, a status line, the stage ledger, the leave-and-return note.

FORM: Signature move: the stage ledger. The backend's real stages (clone, find files, parse, resolve) as a ruled vertical list with a tabular mono column on the right; the active row is live, finished rows keep their result. Position: brief-pinned (spec §5.1, §5.2, §8), no concept roll. seed: none (unavailable)

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
