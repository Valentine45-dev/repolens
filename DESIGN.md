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
  text-muted: "#52525b"
  text-subtle: "#71717a"
  success: "#067647"
  danger: "#b42318"
  warning: "#b54708"
  node-python: "#2f5d8a"
  node-js: "#a16207"
  node-other: "#52525b"
  node-external: "#71717a"
  edge: "#8a8a93"
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
  control: "6px"
  panel: "10px"
  pill: "999px"
spacing:
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

RepoLens looks like a measuring tool laid on a white bench: black ink on white paper, hairline rules, and nothing that does not report something real. One narrow left-aligned column (640px of content) carries each screen; it starts well down the page so the single primary action sits in calm space rather than under a hero. The world is pinned by `docs/repolens-ui-ux-spec.md` §8 and shipped in light only; there is no dark theme and no theme toggle by project rule.

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
- **Ink** (`ink`): the primary button fill, the wordmark mark, the active-nav underline, the focus ring, text selection, and body text. Black is the only "brand" colour.
- **Ink Lifted** (`ink-hover`): primary button hover; a one-step lift, not a new colour.

### Neutral
- **Paper** (`paper`): page ground, top bar, input and chip fill, and text on Ink.
- **Bench Grey** (`panel`): callout panels and list-row hover; the one tonal step that stands in for elevation.
- **Sunk Grey** (`panel-sunk`): secondary-button and chip hover, loading skeletons.
- **Hairline** (`rule`): every 1px divider, list border, ledger rule, top-bar bottom edge, callout border.
- **Strong Hairline** (`rule-strong`): control borders (input, secondary button) and the scrollbar thumb.
- **Graphite** (`text-muted`): ledes, status lines, nav links at rest, notes.
- **Ash** (`text-subtle`): captions, placeholders, pending ledger rows, meta in lists, the SHA beside a repo name, input hover border. Holds 4.5:1 on Paper.

### Semantic (state only)
- **Done Green** (`success`): check icons on finished stages, "Ready" status, the valid-URL check, success callout titles.
- **Failed Red** (`danger`): failed ledger row, "Failed" status, invalid input border and focus ring, error messages, error callout title; the error callout border mixes 35% of it into Hairline.
- **Slow Amber** (`warning`): the "taking longer than usual" note only.

### Graph (Explorer)
- **Python Blue** (`node-python`) and **JS Ochre** (`node-js`, also TypeScript): fill of the small language mark on a file node, which also carries the text `py` / `js` / `ts`, so colour is never the only cue. **Other** (`node-other`) for anything else.
- **External Grey** (`node-external`): the dashed outline of the "external" tag in the node panel. Corrected from #a1a1aa (2.6:1 on Paper) to #71717a (4.8:1) when the Explorer shipped.
- **Edge Grey** (`edge`): every graph edge at rest and the legend lines (3.4:1 on Paper, above the 3:1 floor for graphics). Edges touching the selected file turn Ink; a best-guess edge is dashed, never a different colour.

`--info` is declared in the stylesheet but no shipped surface uses it yet.

### Named Rules
**The Ink Is The Accent Rule.** Black is the only emphasis colour. There is no brand hue; a new surface that wants attention uses Ink, weight, or position, never a new colour.

**The State-Only Colour Rule.** Green, red and amber appear only to report job or input state, and always beside an icon or word that says the same thing; colour is never the only carrier of meaning.

## Typography

**Body Font:** Inter Variable (self-hosted via @fontsource-variable/inter, falls back to system UI sans), with `cv11` and `ss01` enabled.
**Mono Font:** JetBrains Mono 400 and 500 (self-hosted via @fontsource/jetbrains-mono), ligatures off.

**Character:** A neutral grotesk for sentences and a coder's mono for facts; the pairing reads like a terminal printout annotated by a careful editor.

### Hierarchy
- **Headline** (600, 28px, 1.2, -0.02em, balanced wrap): one page title per screen ("Understand a codebase before you read it.").
- **Title Mono** (JetBrains Mono 500, 20px, -0.01em): the `owner/repo @ sha` heading on analysis pages; the SHA drops to 400 in Ash. Wraps anywhere.
- **Wordmark** (600, 16px, -0.01em): "RepoLens" in the top bar beside a 12px black square.
- **Body Large** (400, 16px, 1.5, max 60ch): the lede under a headline and the live status line.
- **Body** (400, 14px, 1.5): the base size for everything else, including ledger rows.
- **Label** (500, 14px): buttons, nav links, active ledger rows, status words, list names. Section titles use the same size at 600.
- **Caption** (400, 12px): limits beneath the URL field, field messages, list meta, "this browser".
- **Data Mono** (JetBrains Mono 400, 12px, tabular figures): ledger values and example chips. Inline mono inside prose runs at 0.93em; the URL input runs mono at 13px.

### Named Rules
**The Facts Are Mono Rule.** Every repository name, commit SHA, URL, path and progress number is set in JetBrains Mono; prose never is. Numbers that change in place use tabular figures.

**The Fourteen Base Rule.** The working size is 14px. Only the page headline (28px) and the repo title (20px) rise above 16px.

## Layout

A single centred column, `max-width: 688px` (640px content plus 24px gutters), left-aligned inside. Top padding is `clamp(32px, 14vh, 128px)` so the first action lands about a fifth down the viewport; bottom padding 48px. The sticky top bar is 52px tall with 24px side padding and a 1px Hairline bottom edge.

Spacing runs on a 4px grid using the seven steps in the frontmatter: 8px between a control and its neighbour, 12px from headline to lede and inside list rows, 24px before example chips and after the ledger, 32px from lede to the URL row and from status line to ledger, 48px between page sections.

Three breakpoints:
- **900px (Explorer):** below it the node panel stops docking beside the canvas and overlays it from the right as a drawer (`min(100%, 480px)`); the selected file is re-centred in the part of the canvas the panel leaves free.
- **767px (Explorer, spec §10):** phones get the list view only. The Graph/List control is replaced by the caption "The graph view needs a larger screen."; the URL keeps its `view` value.
- **560px (all screens):** gutters drop to 16px, the URL field and Analyze button stack with the button full width, recent-analysis rows collapse from name-plus-meta to a single column, the node panel's four facts become two columns, and the file list hides its Language, External and Unresolved columns (the panel still shows those counts). File paths wrap only after a "/".

### Named Rules
**The One Column Rule.** Shell screens are one narrow column with one primary action. No side rails, no card grids, no sidebar items for features that do not exist. The Explorer is the one full-width screen (the graph needs the width): a header row, a ruled toolbar, the canvas, and the node panel docked on the right.

## Elevation & Depth

The system is flat. No element carries a `box-shadow`. Depth is conveyed by 1px Hairline rules (dividers, list borders, the top bar's bottom edge) and by a single tonal step from Paper to Bench Grey for callouts and hovered rows. Focus is shown with a 2px Ink outline at 2px offset (0 offset on inputs, where the border also turns Ink).

### Named Rules
**The Rule Not Shadow Rule.** Separation is a 1px line or a one-step tonal shift. If a surface seems to need a shadow, give it a Hairline border instead.

## Shapes

Two radii and a pill. Controls (buttons, inputs) use gently rounded corners (6px). Grouped containers (the recent-analyses list, callouts) use slightly softer corners (10px) and clip their rows. Example chips are full pills (999px). Small marks stay nearly square: the wordmark square at 2px, skeleton bars at 4px. The stage ledger has no container at all, only a top rule and a rule under each row.

Icons are authored inline SVG on a 16px grid, one 1.5 stroke, round caps and joins, `currentColor`: check, x, circle, spinner, arrow-right. They inherit the state colour of their row.

## Components

### Buttons
Quiet and solid; one black button per screen.
- **Shape:** gently rounded (6px), 40px tall, 16px side padding, 500 weight, icon gap 8px.
- **Primary:** Ink fill and border, Paper text. Hover lifts to Ink Lifted over 150ms on the shared ease-out curve.
- **Secondary:** Paper fill, Strong Hairline border, Ink text; hover fills Sunk Grey. Used for "Try again" and "Retry analysis" inside callouts.
- **Pending / Disabled:** 60% opacity, default cursor; pending swaps in a spinner icon and a present-participle label ("Starting").

### Chips
- **Style:** full pill, 28px tall, 12px side padding, Paper fill, Hairline border, Data Mono text (repo names).
- **State:** hover fills Sunk Grey and strengthens the border; disabled text drops to Ash. Chips are actions (start an example analysis), not filters.

### Inputs / Fields
- **Style:** 40px, 6px radius, Strong Hairline border, Paper fill, mono 13px text, Ash placeholder; 36px right padding reserves room for an inline status icon.
- **Hover / Focus:** hover darkens the border to Ash; focus sets a 2px Ink outline at 0 offset and an Ink border.
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
- **Top bar:** wordmark left, links right of it at 24px gap. Links are Label weight in Graphite; hover goes Ink; the current page goes Ink with a 1px Ink underline (border-bottom). Only links to pages that exist.

### Stage Ledger (signature)
A ruled vertical list: a 20px icon column, the stage label, and a right-aligned Data Mono value column. Rows are at least 48px with a Hairline under each. Pending rows are Ash with a hollow circle; the active row is Ink at 500 with a spinner and the only number on the ledger (when the backend reports one); done rows return to Ink at 400 with a Done Green check; a failed row is Failed Red with an x. Colour changes ease over 200ms. Below it: a Graphite note saying the visitor can leave, and an amber note only after a stage has stalled for a minute.

### Explorer
- **File node:** 200×44 Paper rectangle, 1px Strong Hairline, 4px radius. A 22px language mark (`py`/`js`/`ts`, mono 10px on its graph colour) then the file name (mono 12/500) over its folder (mono 10, Ash, truncated from the left so the end of the path stays visible). Selected: Ink border plus 2px Ink outline. Focus mode dims everything outside the selected file's neighbours to 28%.
- **Edges:** Edge Grey, 1.25px, closed arrowhead pointing at the file being used; Ink at 1.75px when touching the selection; dashed (5 4) when the link is only a best guess (confidence under 0.9). Native tooltip says what the edge is.
- **Legend:** a Bench Grey strip between the toolbar and the canvas (graph view only), Hairline bottom border, 12px text: solid line, then dashed line with the spec's microcopy. It never floats over the canvas, so it can never hide a node.
- **First view:** fits the whole graph only when names stay readable (zoom 0.8 or more); otherwise it opens on the most connected file and its neighbours. Fit always shows everything. A selected file is centred in the canvas area the panel leaves free.
- **Toolbar:** segmented Graph/List control (Bench Grey track, Paper pressed segment), native checkboxes with Ink accent for "Show test files" and "Show guessed calls", a small secondary Fit button, and a right-aligned caption carrying the file count, the render-cap note and hidden-test count.
- **Node panel:** docked right, `min(480px, 42vw)`, Hairline left border (an overlay under 900px). Path in mono, a four-fact row (Used by, Uses, External imports, Unresolved imports), underline tabs (Code, Used by, Uses), and a code view with a sticky Bench Grey line-number gutter. Neighbours are grouped by file; external and unresolved entries carry a small tag (dashed External Grey for external).
- **List view:** a full-width table with a sticky Bench Grey header, 36px rows, mono numbers right-aligned; the selected row takes Sunk Grey.

### Loading
Skeleton bars in Sunk Grey at 4px radius, sized to the text they replace. Spinners rotate at 900ms linear; under reduced motion they slow to 2.4s and transitions collapse.

## Do's and Don'ts

### Do:
- **Do** set every repository name, SHA, URL, path and number in JetBrains Mono, with tabular figures where it updates in place.
- **Do** keep one Ink primary button per screen; secondary actions use the Paper button with a Strong Hairline border.
- **Do** separate with 1px Hairline rules and the Paper-to-Bench-Grey tonal step.
- **Do** pair every state colour with an icon or word saying the same thing.
- **Do** use the authored 16px line icons (1.5 stroke, `currentColor`) and add new glyphs in the same grid and stroke.
- **Do** animate only colour and background, 150ms on `cubic-bezier(0.16, 1, 0.3, 1)`, and honour reduced motion.
- **Do** show a number only where the backend reports real progress.

### Don't:
- **Don't** add `box-shadow` to any surface.
- **Don't** introduce a brand hue or use Done Green, Failed Red or Slow Amber for decoration.
- **Don't** hardcode colours in components; every colour comes from a CSS variable on `:root`.
- **Don't** add a dark theme or theme toggle; this build is light only.
- **Don't** show placeholder data, fake progress bars, or navigation for features that do not exist.
- **Don't** show "Safe", "All clear" or "0 issues" as a verdict.
