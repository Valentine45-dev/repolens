---
name: RepoLens
description: A quiet instrument for reading an unfamiliar repository; white ground, black ink, mono for every fact.
colors:
  ink: "#0a0a0a"
  ink-hover: "#27272a"
  paper: "#ffffff"
  panel: "#fafafa"
  panel-sunk: "#f4f4f5"
  rule: "#e4e4e7"
  rule-strong: "#d4d4d8"
  control-border: "#8a8a93"
  text-muted: "#52525b"
  text-subtle: "#6b6b74"
  success: "#067647"
  danger: "#b42318"
  warning: "#b54708"
  node-python: "#2f5d8a"
  node-js: "#a16207"
  node-other: "#52525b"
  node-external: "#71717a"
  edge: "#8a8a93"
  highlight: "#fdf3d3"
colors-dark:
  ink: "#f4f4f5"
  ink-hover: "#d4d4d8"
  paper: "#111113"
  panel: "#18181b"
  panel-sunk: "#232327"
  rule: "#2c2c31"
  rule-strong: "#3f3f46"
  control-border: "#63636c"
  text-muted: "#b4b4bc"
  text-subtle: "#94949e"
  success: "#4ccf8a"
  danger: "#f97066"
  warning: "#f5a524"
  info: "#7cacf8"
  node-python: "#7fb2e5"
  node-js: "#e0b04a"
  node-other: "#b4b4bc"
  node-external: "#94949e"
  edge: "#7c7c86"
  highlight: "#3b3214"
typography:
  headline:
    fontFamily: "Inter Variable, Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  title-mono:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "1.25rem"
    fontWeight: 500
    letterSpacing: "-0.01em"
  wordmark:
    fontFamily: "Inter Variable, Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    letterSpacing: "-0.01em"
  body-lg:
    fontFamily: "Inter Variable, Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  body:
    fontFamily: "Inter Variable, Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "\"cv11\", \"ss01\""
  label:
    fontFamily: "Inter Variable, Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: 1.5
  micro:
    fontFamily: "Inter Variable, Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 400
  caption:
    fontFamily: "Inter Variable, Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.5
  data-mono:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
    fontFeature: "\"tnum\""
rounded:
  small: "4px"
  control: "6px"
  panel: "10px"
  pill: "999px"
sizes:
  tag: "20px"
  chip: "24px"
  control-small: "32px"
  control: "40px"
spacing:
  space-0-5: "2px"
  space-1: "4px"
  space-2: "8px"
  space-3: "12px"
  space-4: "16px"
  space-6: "24px"
  space-8: "32px"
  space-12: "48px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "40px"
  button-primary-hover:
    backgroundColor: "{colors.ink-hover}"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "40px"
  button-secondary-hover:
    backgroundColor: "{colors.panel-sunk}"
  input-url:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 36px 0 12px"
    height: "40px"
  chip-example:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.data-mono}"
    rounded: "{rounded.pill}"
    padding: "0 12px"
    height: "28px"
  chip-example-hover:
    backgroundColor: "{colors.panel-sunk}"
  topbar:
    backgroundColor: "{colors.paper}"
    padding: "0 24px"
    height: "52px"
  list-row:
    backgroundColor: "{colors.paper}"
    padding: "12px 16px"
  list-row-hover:
    backgroundColor: "{colors.panel}"
  ledger-row:
    textColor: "{colors.text-subtle}"
    height: "48px"
  ledger-row-active:
    textColor: "{colors.ink}"
    typography: "{typography.label}"
  callout:
    backgroundColor: "{colors.panel}"
    rounded: "{rounded.panel}"
    padding: "16px"
---

# Design System: RepoLens

## Overview

**Creative North Star: "The Quiet Instrument"**

RepoLens looks like a measuring tool laid on a white bench: black ink on white paper, hairline rules, and nothing that does not report something real. One narrow left-aligned column (640px of content) carries each screen; it starts well down the page so the single primary action sits in calm space rather than under a hero. The world is pinned by `docs/repolens-ui-ux-spec.md` §8. Light is the design reference; a dark theme carries the same roles (see "Dark theme" below).

Two voices share the page. Inter speaks in sentences (headlines, explanations, labels). JetBrains Mono speaks in facts: every repository name, commit SHA, path, URL and number. A reader can tell at a glance which text is prose and which text is data copied from the analysis. Colour is withheld until state demands it: green appears only when something finished, red only when something failed, amber only when something is slow.

Depth comes from 1px rules and a one-step tonal shift, never from shadow. The signature pattern is the stage ledger: a ruled vertical list of the backend's real stages with a tabular mono column on the right that carries a number only where the backend reports real progress.

**Key Characteristics:**
- White ground, black primary, zinc neutrals; semantic colour only for state.
- Inter for prose, JetBrains Mono for every fact and number.
- Flat: 1px rules and tonal panels, no shadows.
- One narrow column, one primary action per screen.
- Authored 16px line icons at a single 1.5 stroke.

## Colors

A monochrome zinc palette where black does the work of an accent and three semantic hues are reserved for job state.

### Primary
- **Ink** (`ink`): the primary button fill, the logo mark (`web/public/logo-mark.svg`), the active-nav underline, the focus ring, text selection, and body text. Black is the only "brand" colour.
- **Ink Lifted** (`ink-hover`): primary button hover; a one-step lift, not a new colour.

### Neutral
- **Paper** (`paper`): page ground, top bar, input and chip fill, and text on Ink.
- **Bench Grey** (`panel`): callout panels and list-row hover; the one tonal step that stands in for elevation.
- **Sunk Grey** (`panel-sunk`): secondary-button and chip hover, loading skeletons.
- **Hairline** (`rule`): every 1px divider, list border, ledger rule, top-bar bottom edge, callout border.
- **Strong Hairline** (`rule-strong`): control borders (input, secondary button) and the scrollbar thumb.
- **Graphite** (`text-muted`): ledes, status lines, nav links at rest, notes.
- **Ash** (`text-subtle`): captions, placeholders, pending ledger rows, meta in lists, the SHA beside a repo name. #6b6b74 since the UI polish: 5.3:1 on Paper and 4.8:1 on Sunk Grey (the old #71717a was 4.4:1 there).
- **Control Border** (`control-border`): the border of fields, selects, segmented controls, secondary buttons and the Up button, 3.4:1 on Paper (WCAG 1.4.11; Strong Hairline is 1.5:1). Graph nodes and chips keep Strong Hairline: their text identifies them.

### Semantic (state only)
- **Done Green** (`success`): check icons on finished stages, "Ready" status, the valid-URL check, success callout titles.
- **Failed Red** (`danger`): failed ledger row, "Failed" status, invalid input border and focus ring, error messages, error callout title; the error callout border mixes 35% of it into Hairline.
- **Slow Amber** (`warning`): the "taking longer than usual" note only.

### Graph (Explorer)
- **Python Blue** (`node-python`) and **JS Ochre** (`node-js`, also TypeScript): fill of the small language mark on a file node, which also carries the text `py` / `js` / `ts`, so colour is never the only cue. **Other** (`node-other`) for anything else.
- **External Grey** (`node-external`): the dashed outline of the "external" tag in the node panel. Corrected from #a1a1aa (2.6:1 on Paper) to #71717a (4.8:1) when the Explorer shipped.
- **Edge Grey** (`edge`): every graph edge at rest and the legend lines (3.4:1 on Paper, above the 3:1 floor for graphics). Edges touching the selected file turn Ink; a best-guess edge is dashed, never a different colour.

- **Highlight** (`highlight`): the band behind cited or flagged code lines in the code view (a citation chip or "Open in Explorer" from a finding). Ink text on it stays above 15:1. It marks a location, not a state, so it is not Slow Amber.

`--info` colours the Low severity (icon and word, never colour alone).

### Code colours (file panel code view)
VS Code-style (light-plus based), adjusted for contrast. They are the one place hues appear that aren't state: they are scoped to code text in the file panel and say nothing about the code's quality or safety. Each token kind (role) is a CSS token `--code-<role>` with a light and a dark value, used through a `.tk-<role>` class that sets only `color`. Plain code text stays `--text`. Roles come from one tokenising pass against light-plus's scope rules (`web/src/codeColoursCore.ts`), so light and dark are pure CSS.

| Role | Light | Dark | Light on Paper / band | Dark on Paper / band |
|---|---|---|---|---|
| keyword (`def`, `const`, `import`) | #0000ff | **#5ea3dc** (dark-plus #569cd6: 4.3 on the band) | 8.6 / 7.7 | 7.0 / 4.7 |
| control (`if`, `return`, `for`) | #af00db | #c586c0 | 5.5 / 4.9 | 6.8 / 4.6 |
| variable, property | #001080, #0451a5 | #9cdcfe | 15.2 / 13.7, 7.7 / 6.9 | 12.6 / 8.5 |
| constant | #0070c1 | #4fc1ff | 5.1 / 4.6 | 9.3 / 6.3 |
| function | #795e26 | #dcdcaa | 6.1 / 5.5 | 13.3 / 9.0 |
| type, class | **#1f6e85** (light-plus #267f99: 4.1 on the band) | #4ec9b0 | 5.8 / 5.2 | 9.3 / 6.2 |
| string | #a31515 | #ce9178 | 7.8 / 7.1 | 7.1 / 4.8 |
| escape (`\n` in a string) | **#c50000** (#ee0000: 4.1) | #d7ba7d | 6.2 / 5.6 | 10.1 / 6.8 |
| regex | #811f3f | **#e58282** (#d16969: 3.6) | 9.5 / 8.6 | 7.1 / 4.8 |
| number | **#08734b** (#098658: 4.2) | #b5cea8 | 5.9 / 5.3 | 11.1 / 7.5 |
| comment | #008000 | **#7fae69** (#6a9955: 3.8) | 5.1 / 4.6 | 7.3 / 4.9 |
| tag (JSX) | #800000 | **#5ea3dc** (#569cd6: 4.3) | 10.9 / 9.9 | 7.0 / 4.7 |
| attribute (JSX) | **#c50000** (#e50000: 4.4) | #9cdcfe | 6.2 / 5.6 | 12.6 / 8.5 |

Changed from VS Code (bold above): light type, escape, number, attribute; dark keyword, tag, regex, comment. All other values are light-plus / dark-plus as they are. Every role holds 4.5:1 on Paper and on the highlight band in both themes; `web/src/codeColoursCss.test.ts` computes this from `styles.css`. Line numbers are unaffected: the gutter is opaque and above the code.

- **Languages:** Python (`.py`, `.pyi`), JavaScript (`.js .mjs .cjs .jsx`, VS Code's JavaScript grammar, which includes JSX), TypeScript (`.ts .mts .cts`) and TSX. Everything else is plain text.
- **Limit:** files over **3,000 lines or 256 KB** stay plain, and the panel caption adds "Colours off for large files" (known from the line count before the text arrives, so nothing moves). Lines over 1,000 characters stay uncoloured. Why 3,000: tokenising runs in a Web Worker, but putting the coloured spans on the page is one main-thread task that grows with the file. On the eval PC it took about 1.2 s for a 4,591-line file and about 0.25 to 0.45 s for 1,200 to 2,850 lines (`eval/results/screenshots-code-highlight/`).
- **Loading:** plain text first, then colours swap in, in the same `<pre>` (same text, font and line height), so the scroll position, the cited-line band, selection and copy stay as they are. Shiki and the worker load only when a code view first needs them (never on Home or Findings). If anything fails, the code stays plain and a note goes to the console.
- **Theme switch:** the role colours are CSS tokens, so the circular reveal's variable swap recolours the code in the new snapshot. Nothing is tokenised again.
- **Not coloured:** the Findings panel's one-line snippet. A line shown without its file can be coloured wrongly (a line inside a docstring), and "Open in Explorer" shows it in colour.

### Dark theme
Same roles, other values (frontmatter `colors-dark`). Ink becomes a light grey and Paper a near-black; state colours are lifted to hold 4.5:1 on the dark ground. Only colours change: sizes, spacing and the graph's layout are identical. A script at the top of `index.html` sets `data-theme` on `<html>` before anything paints (a stored pick, else `prefers-color-scheme`), and `web/src/theme.ts` follows the system until the user picks with the top-bar toggle (`aria-pressed`, name "Dark theme"; remembered in `localStorage` as `repolens.theme`). Switching is a circular reveal from the toggle (see Motion); instant under reduced motion.

Contrast (WCAG 2.x; text 4.5:1, UI parts and graph strokes 3:1), light / dark:

| Pair | Light | Dark |
|---|---|---|
| text on Paper / Bench / Sunk | 19.8 / 19.0 / 18.0 | 17.2 / 16.1 / 14.3 |
| muted on Paper / Bench / Sunk | 7.7 / 7.4 / 7.0 | 9.2 / 8.6 / 7.6 |
| subtle on Paper / Bench / Sunk | 5.3 / 5.1 / 4.8 | 6.3 / 5.9 / 5.2 |
| primary button label | 19.8 | 17.2 |
| danger / warning / info / success on Paper | 6.6 / 5.4 / 6.0 / 5.7 | 6.8 / 9.2 / 8.2 / 9.5 |
| lang mark text on python / js / other | 6.9 / 4.9 / 7.7 | 8.4 / 9.4 / 9.2 |
| code text on the highlight band | 17.9 | 11.6 |
| edge (solid and dashed) on the canvas | 3.4 | 4.6 |
| legend line on Bench | 3.3 | 4.3 |
| active / cycle edge, cycle border, focus ring | 19.8 | 17.2 |
| control border on Paper | 3.4 | 3.2 |
| external tag border | 4.8 | 6.3 |

Node and chip borders (Strong Hairline, 1.5 / 1.8) and the folder fill against the canvas (1.04 / 1.06) are below 3:1 in both themes by design: a node is identified by its text, icon and word, not its outline. Dimmed nodes (28%) and edges (15%) are de-emphasis on purpose.

### Named Rules
**The Ink Is The Accent Rule.** Black is the only emphasis colour. There is no brand hue; a new surface that wants attention uses Ink, weight, or position, never a new colour. (Code colours, above, are the one exception: they live only inside the code view's text.)

**The State-Only Colour Rule.** Green, red and amber appear only to report job or input state, and always beside an icon or word that says the same thing; colour is never the only carrier of meaning.

## Typography

**Body Font:** Inter Variable (self-hosted via @fontsource-variable/inter, falls back to system UI sans), with `cv11` and `ss01` enabled.
**Mono Font:** JetBrains Mono 400 and 500 (self-hosted via @fontsource/jetbrains-mono), ligatures off.

**Character:** A neutral grotesk for sentences and a coder's mono for facts; the pairing reads like a terminal printout annotated by a careful editor.

### Hierarchy
- **Headline** (600, 28px, 1.2, -0.02em, balanced wrap): one page title per screen ("Understand a codebase before you read it.").
- **Title Mono** (JetBrains Mono 500, 20px, -0.01em): the `owner/repo @ sha` heading on analysis pages; the SHA drops to 400 in Ash. Wraps anywhere.
- **Wordmark** (600, 16px, -0.01em): "RepoLens" in the top bar beside the 20px logo mark (a three-node graph inside a lens).
- **Body Large** (400, 16px, 1.5, max 60ch): the lede under a headline and the live status line.
- **Body** (400, 14px, 1.5): the base size for everything else, including ledger rows.
- **Label** (500, 14px): buttons, nav links, active ledger rows, status words, list names. Section titles use the same size at 600.
- **Caption** (400, 12px): limits beneath the URL field, field messages, list meta, "this browser".
- **Micro** (400, 11px, `--text-2xs`): tags, count badges, edge counts, panel fact labels. Inside graph nodes the 10px and 11px sizes stay as they are: the node boxes are layout constants.
- **Data Mono** (JetBrains Mono 400, 12px, tabular figures): ledger values and example chips. Inline mono inside prose runs at 0.93em; mono rows and the URL input run at 13px (`--text-mono-sm`).

### Named Rules
**The Facts Are Mono Rule.** Every repository name, commit SHA, URL, path and progress number is set in JetBrains Mono; prose never is. Numbers that change in place use tabular figures.

**The Fourteen Base Rule.** The working size is 14px. Only the page headline (28px) and the repo title (20px) rise above 16px.

## Layout

A single centred column, `max-width: 688px` (640px content plus 24px gutters), left-aligned inside. Top padding is `clamp(32px, 14vh, 128px)` so the first action lands about a fifth down the viewport; bottom padding 48px. The sticky top bar is 52px tall with 24px side padding and a 1px Hairline bottom edge.

Spacing runs on a 4px grid using the steps in the frontmatter (2px only inside a control): 8px between a control and its neighbour, 12px from headline to lede and inside list rows, 24px before example chips and after the ledger, 32px from lede to the URL row and from status line to ledger, 48px between page sections.

Three breakpoints:
- **1600px (Ask open):** from 901 to 1599px with Ask open, a file or finding panel shares Ask's column as tabs ("File | Ask" or "Finding | Ask", a 40px tab strip at the top of that column) instead of overlaying the map or list, which keep their full width. Both stay mounted (Ask keeps its conversation behind the tab, out of sight and `inert`); which tab is in front is view state, not URL state. From 1600px three columns dock.
- **900px (Explorer):** below it the node panel stops docking beside the canvas and overlays it from the right as a drawer (`min(100%, 480px)`); the selected file is re-centred in the part of the canvas the panel leaves free.
- **767px (Explorer, spec §10):** phones get the list view only. The Graph/List control is replaced by the caption "The graph view needs a larger screen."; the URL keeps its `view` value.
- **560px (all screens):** gutters drop to 16px, the URL field and Analyze button stack with the button full width, recent-analysis rows collapse from name-plus-meta to a single column, the node panel's four facts become two columns, and the file list hides its Language, External and Unresolved columns (the panel still shows those counts). File paths wrap only after a "/".

### Named Rules
**The One Column Rule.** Shell screens are one narrow column with one primary action. No side rails, no card grids, no sidebar items for features that do not exist. The Explorer is the one full-width screen (the graph needs the width): a header row, a ruled toolbar, the canvas, and the node panel docked on the right.

## Elevation & Depth

The system is flat. No element carries a `box-shadow`. Depth is conveyed by 1px Hairline rules (dividers, list borders, the top bar's bottom edge) and by a single tonal step from Paper to Bench Grey for callouts and hovered rows. Focus is shown with a 2px Ink outline at 2px offset (0 offset on inputs, where the border also turns Ink); graph nodes take the same ring.

### Named Rules
**The Rule Not Shadow Rule.** Separation is a 1px line or a one-step tonal shift. If a surface seems to need a shadow, give it a Hairline border instead.

## Shapes

Two radii and a pill. Controls (buttons, inputs) use gently rounded corners (6px). Grouped containers (the recent-analyses list, callouts) use slightly softer corners (10px) and clip their rows. Example chips are full pills (999px). Skeleton bars use 4px. The stage ledger has no container at all, only a top rule and a rule under each row.

Icons are authored inline SVG on a 16px grid, one 1.5 stroke, round caps and joins, `currentColor`: check, x, circle, spinner, arrow-right, send, copy, the severity marks, and for the Ask drawer file, package, symbol (braces), graph (three nodes), spark (AI answer), expand and collapse. They inherit the state colour of their row.

## Components

### Buttons
Quiet and solid; one black button per screen.
- **Shape:** gently rounded (6px), 40px tall (small: 32px), 16px side padding, 500 weight, icon gap 8px.
- **Primary:** Ink fill and border, Paper text. Hover lifts to Ink Lifted over 150ms on the shared ease-out curve.
- **Secondary:** Paper fill, Control Border, Ink text; hover fills Sunk Grey. Used for "Try again" and "Retry analysis" inside callouts.
- **Pending / Disabled:** 60% opacity, default cursor; pending swaps in a spinner icon and a present-participle label ("Starting").

### Chips
- **Style:** full pill, 28px tall, 12px side padding, Paper fill, Hairline border, Data Mono text (repo names).
- **State:** hover fills Sunk Grey and strengthens the border; disabled text drops to Ash. Chips are actions (start an example analysis), not filters.
- **Site chips** (`.site-chip`, `SiteChips.tsx`): where an import or call happens, as `file:line` (the file's base name; the full path is the hover title). Radius-control corners (not a pill), 22px tall, Data Mono 12px, Paper fill, strong border; hover fills Sunk Grey. At most three per import or call, then "+N more" as a caption. A chip opens the code at that line, highlighted (Used by / Uses in the node panel, graph answers in Ask); with no way to open the file (a test file the graph hides) it is plain grey text. An analysis that predates sites shows no chips: no line is better than a wrong one. "+N more" is a button in the same chip style (`aria-expanded`) that lists the rest of the row's lines, and "Show fewer" folds them again; a site under 0.9 confidence has a dashed border and subdued text (best guess). A row lists at most 20 lines, the most the server stores per edge, and says "N more not listed" beyond that. Calls in a row are items in a wrapping flex group, with no separating commas. In the symbol view the call lines live in the edge tooltip ("Called at views.py:12, 40 (+2 more)"), not as chips.

### Inputs / Fields
- **Style:** 40px, 6px radius, Control Border, Paper fill, mono 13px text, Ash placeholder; 36px right padding reserves room for an inline status icon.
- **Hover / Focus:** hover darkens the border to Graphite; focus sets a 2px Ink outline at 0 offset and an Ink border.
- **Valid:** a Done Green check sits inside the right edge.
- **Error:** border and focus outline turn Failed Red; the caption beneath becomes the error message in Failed Red with `role="alert"`.

### Lists
- **Recent list:** one 10px-radius container with a Hairline border; rows divided by Hairline; each row is a two-column grid (mono name, right-aligned meta in Caption Ash joined by middots). Row hover fills Bench Grey.
- **Status word:** icon plus word at 500; Done Green for Ready, Failed Red for Failed, Graphite with a spinner for Analyzing.

### Callouts
- **Corner Style:** 10px.
- **Background:** Bench Grey, Hairline border, 16px padding.
- **Tone:** error tints the border with 35% Failed Red and colours the 600-weight title red; success colours the title green. Actions sit in a wrapped row 16px below.

### Navigation
- **Top bar:** wordmark left (the logo mark is inline SVG in `currentColor`, so it follows the theme), links right of it at 24px gap, the theme toggle (a 32px icon button, sun or moon) at the far right. Links are Label weight in Graphite; hover goes Ink; the current page goes Ink with a 1px Ink underline (border-bottom). Only links to pages that exist.
- **Browser tab title:** where you are, most specific first: "challenge · Explorer · adeyosemanputra/pygoat — RepoLens", "src/flask/cli.py:1022 · Findings · pallets/flask — RepoLens".
- **Side panels:** file panel, finding panel and Ask share one close button (`CloseButton`: x, "Close (Esc)" on hover, a name per panel). Esc closes the panel that holds focus, else the most recently opened one that can be seen; one per press (`escapeStack.ts`).

- **File-limit notice:** one 12px Graphite line under the analysis header, Hairline bottom border, on every analysis tab, shown only when the file limit cut the analysis short. It says how many files were analysed and that the rest were not. Neutral: it reports coverage, not a state or a verdict.

### Stage Ledger (signature)
A ruled vertical list: a 20px icon column, the stage label, and a right-aligned Data Mono value column. Rows are at least 48px with a Hairline under each. Pending rows are Ash with a hollow circle; the active row is Ink at 500 with a spinner and the only number on the ledger (when the backend reports one); done rows return to Ink at 400 with a Done Green check; a failed row is Failed Red with an x. Colour changes ease over 200ms. Below it: a Graphite note saying the visitor can leave, and an amber note only after a stage has stalled for a minute.

### Explorer
- **File node:** 200×44 Paper rectangle, 1px Strong Hairline, 4px radius. A 22px language mark (`py`/`js`/`ts`, mono 10px on its graph colour) then the file name (mono 12/500) over its folder (mono 10, Ash, truncated from the left so the end of the path stays visible). Selected: Ink border plus 2px Ink outline. Focus mode dims everything outside the selected file's neighbours to 28%.
- **Edges:** Edge Grey, 1.25px, closed arrowhead pointing at the file being used; Ink at 1.75px when touching the selection; dashed (5 4) when the link is only a best guess (confidence under 0.9). Native tooltip says what the edge is.
- **Legend:** a Bench Grey strip between the toolbar and the canvas (graph view only), Hairline bottom border, 12px text, two lines at most. Line 1 is the key: "Import or call, arrow to the one used · number = how many · thicker = more", then the dashed sample "Mostly guesses (hidden; turn on “Guessed calls”)" or "(calls matched by name only)" (the flat graph says "Guess": one edge is one guess), and "Circular imports (top-level imports only)" only when the view has one. Line 2 exists only when edges are left out or the first view is zoomed in: "Showing the 8 strongest of 95 connections (3 or more each). Hover or select a node to see all of its connections. … Fit shows the whole map." (wording in `legendText.ts`, from the real selection). It never floats over the canvas, so it can never hide a node.
- **First visit:** a "How to read this map" card (three lines, "Got it" and a close button) at the bottom left of the canvas, shown until closed once (`repolens.mapHintSeen`).
- **First view:** fits the whole graph when that needs zoom 0.6 or closer; otherwise it opens on the most connected file and its neighbours at zoom 0.8, and a caption over the canvas names that file ("Fit shows all files") until the user picks a file or presses Fit. Fit always shows everything. A selected file is centred in the canvas area the panel leaves free. Enter or Space on a focused file node opens it, like a click.
- **Toolbar:** one row beside the Ask panel at 1366px: segmented Graph/List control (Bench Grey track, Paper pressed segment, 32px), a second segmented control for the level of detail (Folders / Files / Flat), a small secondary Fit button, then a "Show" group of native checkboxes with Ink accent: "Tests & examples" (it hides `examples/` with the tests), "Guessed calls", "All edges" (dimmed when the map leaves nothing out; its hover text and description then say "All connections are already shown."). What is in view and what is hidden ("25 files · 58 test or example files hidden here") sits at the right of the breadcrumb row; List view keeps it at the right of the toolbar. While the next folder loads, the old map dims, stops taking clicks and shows "Opening `folder`…"; the breadcrumbs already show the target.
- **Node panel:** docked right, `min(480px, 42vw)`, Hairline left border (an overlay under 900px). Path in mono, a four-fact row (Used by, Uses, External imports, Unresolved imports), underline tabs (Code, Used by, Uses), and a code view with a sticky Bench Grey line-number gutter and syntax colours (see Code colours). Neighbours are grouped by file; external and unresolved entries carry a small tag (dashed External Grey for external). The title is the folder over the file name, each on one line cut with an ellipsis (the folder from the left, so the part next to the file stays); a name is never broken mid-word, and the full path is the hover text and accessible name. The panel never grows past the canvas area (`max-height: 100%`): the code area takes what is left and scrolls both ways inside it. The line-number gutter is sticky on the left with an opaque Bench Grey background and sits above the code and the highlight band.
- **List view:** a full-width table with a sticky Bench Grey header, 36px rows, mono numbers right-aligned; the selected row takes Sunk Grey.

### Findings page
- **Category control:** a segmented control ("Security", "Bug / Quality", "All") at the start of the filter toolbar, each segment with its count in mono at a fixed width (`.seg-count`, so loading the counts moves nothing). Security is the default and is not written to the address; the others are `?category=quality|all`. Categories are told apart by words only, never by colour. Rule choices in the Rule filter follow the chosen category. Bug / Quality adds one caption: these are code-quality checks (Ruff and an import check), not security results, and test and example code is not checked.
- **Tags** after a finding's text, the same pill as "test or example": "documentation" (a secret in a `.md`, `.rst` or `.txt` file) and "probably placeholder" (the value looks like a stand-in such as `changeme` or `<your-key>`, in a file that does not run: documentation, or an example or template file). Both rank low; the second also sorts last. The same kind of value in code or runtime config keeps its severity and gets no tag: its message ends "looks like a template value" and the panel adds "if deployed as-is, it's a publicly known key". "Hide probable placeholders" sits beside "Hide test and example code" and is dimmed when the analysis has none.
- **Notes:** when the quality checks did not finish (for example Ruff timed out), one `note` line says so under the toolbar, so an empty Bug / Quality list is never read as "nothing found".
- **Order control:** a labelled select ("Order": Default, Reachability) after the path filter, at a fixed width (`.select-order`). Default is the usual order and stays the default. With Reachability, a caption under the toolbar says what the order is and that entry points are detected by pattern and can be missed, and each row gets a tag (`.tag`): "reachable", "reachable by guess", "not checked" or "no path found".
- **Reachability block** in the finding panel, under the notes: one sentence, then the path as `.site-chip` chips that open the code (Explorer at that line). Words are fixed: "Reachable from `<entry>` via a → b → c", "Reachable only through guessed steps (a call matched by name, a special method Python calls implicitly, or a function defined inside code that is reached)" (guessed steps have a dashed chip, the same dashed treatment as guessed calls in the graph), "Not in analysed code, so reachability was not checked", "No path found from a detected entry point". A path of more than 7 steps shows the first two and last three with "+N more". A caption always follows: entry points are detected by pattern and can be missed; this says where a path was found, not whether the code runs. Never "unreachable", "unused", "dead" or "safe".

### Folder map (Explorer, level Folders / Files / Symbols)
The default map: folder, then file, then function. Never more than 60 nodes (the server adds a "N more" node). No new colour: folders, cycles and overflow are told apart by fill, border, icon and a word.
- **Breadcrumbs:** a row above the toolbar: an Up icon button (Hairline border, disabled and dimmed at the repo), then `repo / src / itsdangerous` in mono 14. Earlier crumbs are Graphite links that go Ink and underline on hover; the last is Ink at 500 with `aria-current`. Each is a real link, so Back undoes it and a view can be shared.
- **Folder node:** 208×76 Bench Grey rectangle, 1px Strong Hairline, 4px radius. A 16px folder icon and the folder path (mono 12/500), then "N files · N findings" (11px Graphite; "N findings" is a link to Findings under that folder; the findings part is left out at zero, so nothing reads as a verdict), then the boundary line "↑ N in · N out" (mono 10, Ash) when edges cross the view's edge. A click opens the folder.
- **File node (map):** the flat file node's language mark and name over its folder, on Paper, plus the same findings and boundary lines. A click opens the file panel. The panel has a "Functions" button for the symbol view.
- **Symbol node:** 248×56 Paper; a mark (`fn`, `cls`, `mod` on Edge Grey text colour), the name (13px), and `lines a–b` (or the file path for a neighbour in another file). A click opens its file on those lines.
- **"N more" node:** dashed Strong Hairline on Sunk Grey: "+ N more" and "open in List view →" (in a symbol view: "not drawn"). It takes over the edges of what it hides. A click opens List view for that folder.
- **Circular imports:** member nodes get a 2px Ink border and a small outlined "circular" tag with the cycle icon, so it reads without colour. A cycle edge is Ink. The legend strip names it "Circular imports (top-level imports only)" and only when something in the view is part of one. A folder that holds a cycle inside it has the tag but no Ink edge (open it to see the files). Two folders that import each other are not shown as circular.
- **Edges:** Edge Grey on a log scale of count, 1.25px for 1 up to 5px; a count label (mono 11 on Paper, Hairline border, 3px radius) at the middle of each edge (all of them up to 12 drawn edges, above that only counts of 2 or more and edges of the focused node). Dashed (5 4) when most of the connections are guesses. The tooltip carries the split: "6 imports · 155 calls (152 guesses)", so a dashed edge never hides its solid imports. A two-way pair is two parallel lines 20px apart; an edge that points back to an earlier layer leaves from the left side of its node. Hovering a line (an invisible 18px zone around it) or its count shows a tooltip: Paper, Hairline, no shadow, 12px, following the pointer, with the endpoints and the split. A node's tooltip says what it holds (path, files, tests, findings, what crosses its edge), never its name again.
- **Edge density:** at rest the canvas draws about three edges for every four nodes (12 to 40: a view of 20 nodes draws at most 15, one of 60 draws 40), whole tiers of equal count (never splitting a tie), plus every circular edge; if even the strongest tier is too big it draws a sample (calls before `defines`, solid before guesses) and says so. Hovering, focusing or selecting a node draws all of its edges and dims the rest. A node with connections that are not drawn says so in 10px Ash ("5 connections not drawn"), so a node in the grid of loose nodes is never mistaken for one with no connections. The line in the legend strip says what is drawn ("Showing 8 of 82 connections, the strongest (3 or more dependencies each). Hover or select a node to see all of its connections."); "Show all edges" draws every one. The checkbox is always in the toolbar (dimmed when nothing is left out), so the toolbar never changes shape.
- **Hover never moves anything:** nodes and edges are built from the view only and keep their identity; hover (after a 100 ms delay, 60 ms to clear), keyboard focus and selection are read from a context and only restyle: a node dims, an edge appears (edges outside the resting set are not drawn until an end of them is focused) or dims. Arrowheads take the edge's colour (`currentColor`), so focus never swaps markers. Replacing node objects made React Flow hide every node until it re-measured them, which blanked the canvas on each hover and lost clicks.
- **Layout:** dagre, left to right, arranged for the edges drawn at rest and not for the hidden ones. Six dagre settings are tried (three rankers, each with and without the greedy cycle breaker); the one with the fewest edge crossings, then the fewest edges through other nodes, then the smallest area wins. Layers taller than 720px wrap into columns, chains longer than 1800px continue on a new row, and nodes with no drawn connection form a grid below (as many columns as fit a screen at the readable zoom). Edges between nodes side by side leave the right side and arrive at the left (back the other way round); edges inside one column leave the bottom and arrive at the top, a short straight line instead of a loop out to the side. Arrowheads are a fixed 20px box (a thick edge does not get a bigger one). The first view fits everything when that keeps names readable (zoom 0.75 or more, at most 1.1); otherwise it opens at 0.75 on the top left of the map and the legend's notes row says so ("Zoomed in so names stay readable; drag to move, Fit shows everything.").
- **List filter bar:** above the table when opened from "N more": a Bench Grey strip with "Showing N files under `folder` (of M)" and a small secondary "Show all files" button.

### Ask drawer
- **Frame:** docked right with a Hairline left edge, `min(480px, 40vw)`; an expand toggle widens it to `min(760px, 62vw)` (remembered in this browser). Under 900px it overlays the canvas at `min(100%, 560px)` with the same Hairline edge, never a shadow, and the toggle is hidden. The repo name in "Ask about owner/repo" is mono, truncated with an ellipsis, full name in the title.
- **Banner:** one neutral callout at the top for whatever limits AI answers (no model, search being prepared with real chunk counts, search failed with a secondary "Retry preparing search" button). Not amber: nothing here is "slow". Graph questions are always said to work.
- **Turns:** the question in its own Bench Grey box with a Hairline border (6px); the answer under a 600-weight header with its icon, "AI answer" (spark) or "From the graph" (graph); 24px and a Hairline between turns. A failed AI question is one muted line with an x.
- **Graph results:** one ruled 10px container, a 40px row per result: kind icon (file / package / symbol) in Ash, the name in mono (paths wrap only after "/"), the file path under a symbol in Ash, and right-aligned real metadata only: `imports` / `calls`, `external` / `unresolved` / `test` tags, the line count where the result has lines. Five rows, then "Show all N". On phones the metadata moves under the name.
- **Sources:** "Relevant source files", chips with a file icon and mono `path:start-end`, linking to the cited lines.
- **Code locations:** when the LLM could not answer, the failed line is followed by "Code that matches this question", the same chips as Sources, and "Ranked by search, not read by AI." in Ash, so they never read as an AI answer.
- **Scroll area:** only the list of suggestions or turns scrolls; the header and the question box stay put. A soft fade into Paper (24px, `--bg` to transparent, either theme) sits on an edge only while the list continues past it (`useScrollEdges`); it fades in over 150ms, instantly under reduced motion, and never takes the pointer.
- **Scope line:** above the input after "Ask about this": a file icon, "This question includes" in Ash, the path in mono, and an x to remove it. It applies to the next question only.

### Loading
Skeleton bars in Sunk Grey at 4px radius, sized to the text they replace, with one shared shimmer: a soft band (`--shimmer`, lighter than Sunk Grey; a faint light band in dark) moved by `transform` on a pseudo-element, 1.5s per sweep, every bar on the same start time so they sweep together; static under reduced motion. Containers carry `aria-busy`. Loaders shown over content that is already there (the "Opening `folder`…" pill over the dimmed map) appear after 200ms and stay at least 400ms (`useDelayedFlag`), so a fast load shows nothing and a slow one does not blink; layout-keeping skeletons show at once. The file panel's code area fills with placeholder lines at the code's line height and a gutter already as wide as the file's last line number; the Findings list loads as its own table (header and eight 40px rows); a link to a finding draws the panel frame at once; the reachability block keeps its shape. Ask says "Working on it…" and only after 1.5s "this can take up to 40 seconds". `REPOLENS_DEV_API_DELAY_MS` (dev and preview server only, README) slows the API to see all of this. Where a surface has a shape, the skeleton keeps it, and it is the real surface wherever the page already knows the answer: the Explorer draws its breadcrumb row (real Up button, real folder names from the address, only the repo name grey), toolbar, legend and notes row at once and only the repo name and counts are grey; the map placeholder is plain rows of grey cards at the real node size and gap (208×76, 14px), not a drawn graph; List view shows nine 36px ruled rows. `index.html` ships one page-shaped template per kind of page (home, Explorer, Findings) built from the real markup and class names, so every placeholder sits where its element will be: home is its real text (the recent list from this browser, only the status grey), an analysis started in this browser shows its real title, and the rest of the screen's room is reserved (the Findings count badge, the filter widths, the scrollbar gutter, the caption row). The three first-screen fonts are preloaded. Measured with `eval/layout_shift.mjs`: layout shift 0 on home and Findings, 0.0001 on the Explorer, every landmark within 0.5px of its placeholder. The words ("Laying out…", "Loading files…") stay for screen readers only. Skeletons are still: no shimmer.

## Motion

Motion is small and never in the way: colour eases of 150–200ms on `cubic-bezier(0.16, 1, 0.3, 1)` (hover, the Stage Ledger, the Ask list fades), the skeleton shimmer by `transform`, and the theme switch below. Under `prefers-reduced-motion: reduce` every one of them is off or instant.

**Theme switch (circular reveal).** Pressing the toggle reveals the new theme in a circle that grows from the toggle's centre to the farthest window corner, 450ms, `ease-in-out`, the same in both directions. It is a View Transition (`web/src/theme.ts`, rules in `styles.css`):
- Inside the update callback the theme variables are swapped with every transition off (`theme-instant` on `<html>`, swap, one style read, class removed), so the new snapshot has no element half way through its own colour ease.
- Only `::view-transition-new(root)` animates, by a CSS `@keyframes theme-reveal` on `clip-path: circle()`; its centre, radius and duration come from `--theme-reveal-x/-y/-r/-ms`, set on `<html>` with the `theme-reveal` class for the switch only. The default cross-fade is off (`animation: none` on old and new); the new image sits above the old. (A CSS animation, not `element.animate()`: Firefox 159 does not apply the latter to View Transition pseudo-elements.)
- The centre is the toggle's box, not the pointer, so a keyboard press looks the same.
- While a reveal runs, further toggle presses are ignored (no stacking); the browser itself sends pointer clicks during a View Transition to `<html>`, so a click elsewhere in that ~0.5s does nothing, while typing is unaffected. The class, the properties and the guard are cleared when the transition finishes, is skipped or fails.
- No View Transitions in the browser, or reduced motion: the same instant swap (transitions off for that one style change), no View Transition.

No element ever gets a colour `transition` for the switch: the old approach (a class that gave every element 200ms colour transitions) started over 1,000 transitions per switch and blocked the page for up to 1.6s on the eval PC.

## Do's and Don'ts

### Do:
- **Do** set every repository name, SHA, URL, path and number in JetBrains Mono, with tabular figures where it updates in place.
- **Do** keep one Ink primary button per screen; secondary actions use the Paper button with a Strong Hairline border.
- **Do** separate with 1px Hairline rules and the Paper-to-Bench-Grey tonal step.
- **Do** pair every state colour with an icon or word saying the same thing.
- **Do** use the authored 16px line icons (1.5 stroke, `currentColor`) and add new glyphs in the same grid and stroke.
- **Do** animate only colour and background, 150ms on `cubic-bezier(0.16, 1, 0.3, 1)` (the theme switch: a View Transition clip, not element transitions; the skeleton shimmer: transform only), and honour reduced motion.
- **Do** show a number only where the backend reports real progress.

### Don't:
- **Don't** add `box-shadow` to any surface.
- **Don't** introduce a brand hue or use Done Green, Failed Red or Slow Amber for decoration.
- **Don't** hardcode colours in components; every colour comes from a CSS variable on `:root`.
- **Don't** give a colour a value for one theme only; every token has a light and a dark value, and light stays the reference.
- **Don't** show placeholder data, fake progress bars, or navigation for features that do not exist.
- **Don't** show "Safe", "All clear" or "0 issues" as a verdict.
