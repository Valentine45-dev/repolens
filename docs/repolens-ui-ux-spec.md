# RepoLens: UI/UX Specification

How the product looks, behaves, and flows, from the first click to a verified answer.

| | |
|---|---|
| **Companion documents** | `PRD.md` (what and why), `repolens-system-design.md` (backend, schema, API) |
| **Theme** | White and black, professional, minimal |
| **Status** | Draft v1 (planning) |

> Where this document needs backend support that the design doc does not yet have, it says so in section 9.4 ("API additions"). Performance numbers are targets, not measurements.

---

## 1. Purpose and design principles

RepoLens takes a repository nobody has read and turns it into something a person can navigate, question, and trust. The interface has one job: **get the user from "I pasted a URL" to "I understand where things are and why" with as little friction and as little doubt as possible.**

### Principles (used to settle every design argument)

1. **Orient first.** Every screen answers three questions without effort: *Where am I? What can I do here? What comes next?*
2. **One primary action per screen.** One black button. Everything else is secondary.
3. **Evidence over assertion.** Anything the system claims (an answer, a finding, a dependency) shows its evidence: file, line, code. Nothing is presented as certain when it is a best guess.
4. **Honest by default.** No "All clear," no "0 issues" without context, no "works with any language." Confidence and limits are visible, not hidden in a report.
5. **Progressive disclosure.** Show a calm overview first, details on demand. Never draw thousands of nodes at once.
6. **Calm and professional.** Black, white, gray, one restrained accent set for meaning. No decoration that does not carry information.
7. **The URL is the state.** Every view is linkable, and the browser back button works.
8. **Degrade gracefully.** If the AI is down, the graph and findings still work, and the interface says exactly what is unavailable and why.

---

## 2. Users and what they come to do

| User | Typical job | Success looks like |
|---|---|---|
| **New team member / student** | "Help me understand this project" | Finds the main files and how they connect within minutes |
| **Reviewer / security-minded developer** | "Show me risky code" | Opens a high-severity finding, reads the exact code, decides if it is real |
| **Dependency evaluator** | "Is this library well structured?" | Sees structure, hubs, cycles, and external dependencies at a glance |
| **Course evaluator** | "Does this work and is it measured?" | Completes a demo flow without help, sees honest limits |

**Primary demo journey:** paste a URL of a small or mid-sized Python repo, watch progress, land on Overview, open Explorer, click a hub file, ask "where is authentication handled?", click a citation, open the exact code.

---

## 3. Website structure (information architecture)

The site is small on purpose. **Five routes, two levels deep, one global navigation bar.**

### 3.1 Site map

```
RepoLens
│
├── /                      Home: start a new analysis (+ examples + recent)
│
├── /a/:id                 Analysis (one repository snapshot)
│   ├── (progress)         Shown while ingestion runs
│   ├── /overview          Summary, key insights, language breakdown
│   ├── /explore           Graph + file tree + node panel  (core screen)
│   ├── /findings          Bugs, security issues, code smells
│   └── /dependencies      Internal and external dependencies
│
│   [Ask panel]            Persistent right-hand drawer, available on every tab
│
├── /about                 How RepoLens works, supported languages, limits
│
└── /unlock                Shared access key (only on a public hosted demo)
```

### 3.2 Why this structure

- **A top bar, not a sidebar.** The mock used a left sidebar with Home, Analysis, Repositories, Graphs, Reports, Settings. That suits an app with many sections and accounts. RepoLens has few top-level pages, and the graph needs maximum width. A top bar keeps width for the Explorer and keeps the navigation to a handful of items.
- **Four tabs inside an analysis, never more.** Overview, Explorer, Findings, Dependencies. If a feature does not fit one of these, it does not get a tab.
- **Ask is not a tab.** Question answering is the project's main technical contribution, and it should be reachable from everywhere. It is a drawer that slides in from the right and stays open while the user moves between tabs.
- **No login, no settings, no billing, no "Repositories" list page.** These are out of scope (see section 17). A short "Recent analyses" list from the browser covers the real need.

### 3.3 Global navigation (top bar, on every page)

```
◼ RepoLens     New analysis     Recent ▾     How it works                 ◐
```

| Item | Behavior |
|---|---|
| **Logo** | Goes to Home |
| **New analysis** | Goes to Home with the URL field focused |
| **Recent ▾** | Dropdown of the last 10 analyses from this browser (name, status, age). Click to open |
| **How it works** | Goes to `/about` |
| **Theme toggle** (◐) | Light/dark. Light is default. See section 11.7 |

### 3.4 Inside an analysis (header, on every tab)

```
owner/repo  ·  commit a1b2c3d  ·  Python 78%  JavaScript 20%  Other 2%       [Ask ✦]
Overview   Explorer   Findings (14)   Dependencies
```

- Repo name links to the GitHub repo (opens in a new tab).
- The commit SHA shows exactly which version was analyzed. This also tells the user the snapshot will not change under them.
- Language chips link to the Explorer filtered by that language.
- The Findings tab carries a count badge.
- **Ask ✦** opens the drawer.

### 3.5 Navigation rules

1. The current location is always visible (active tab underlined, breadcrumb in Explorer).
2. The way back to "start something new" is always one click away.
3. No feature lives only in a menu. Shortcuts (section 12.5) speed things up but are never required.
4. Maximum depth: Home, Analysis, Tab. Deeper context (a node, a finding) opens in a **panel**, not a new page.
5. The browser back button undoes the last meaningful navigation (tab change, node selection, level change).

### 3.6 URL scheme (state lives in the URL)

| URL | Meaning |
|---|---|
| `/a/42/overview` | Overview of snapshot 42 |
| `/a/42/explore?level=file&root=src/auth` | Explorer, file level, scoped to a folder |
| `/a/42/explore?node=sym_981&panel=code` | Node selected, code tab open |
| `/a/42/findings?severity=high&rule=eval-use` | Filtered findings |
| `/a/42/explore?node=sym_981&ask=1` | Ask drawer open |

This gives free deep links (share a view with a teammate), working back and forward buttons, and a reproducible state for screenshots in the report.

---

## 4. User journeys

### 4.1 First-time user (primary)

```
Home → paste URL (or click an example) → Analyze
  → Progress (stages, counts, can leave and come back)
  → Overview (insight cards)
  → Click an insight card (e.g. "3 circular imports")
  → Explorer, already scoped to those files
  → Click a node → read code, see dependents
  → Ask: "What depends on this?" (answered from the graph, instantly)
  → Ask: "Where is authentication handled?" (AI answer with citations)
  → Click a citation → exact lines highlighted
```

### 4.2 Security review

```
Findings → filter severity: high → open a finding
  → side panel shows masked snippet, rule, why it matters
  → "Open in Explorer" → node and its callers highlighted
  → decide: real issue or false positive
```

### 4.3 Returning user

```
Home → Recent → open previous analysis (instant, already stored)
```

### 4.4 Failure journeys (designed, not afterthoughts)

| Situation | What the user sees | What they can do |
|---|---|---|
| Invalid URL | Inline message under the field | Fix and retry |
| Repo too large | Explanation with the actual numbers and the limit | Try a smaller repo or pick an example |
| Clone failed (private or missing repo) | "We could only access public repositories on GitHub" | Check the URL |
| Parse errors in some files | Overview notes "12 files skipped (syntax errors)" with a list | Continue normally |
| AI provider down | Ask drawer shows a clear unavailable state; everything else works | Use graph queries, retry later |
| Worker crashed | Progress shows "Taking longer than usual" and recovers automatically | Wait or reopen the URL later |

---

## 5. Screen specifications

Every screen below lists: purpose, layout, components, states, data, and interactions. Wireframes are schematic.

### 5.1 Home (`/`)

**Purpose:** start an analysis in one step. Merge of the mock's landing page and "New Analysis" screen, so there is no separate marketing page to click through.

```
┌──────────────────────────────────────────────────────────────────┐
│ ◼ RepoLens    New analysis   Recent ▾   How it works          ◐ │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│            Understand a codebase before you read it.             │
│    Dependency graph, security findings, and answers with         │
│    citations. Deep analysis for Python and JavaScript.           │
│                                                                  │
│    [ https://github.com/owner/repo                 ] [ Analyze ] │
│    Public GitHub repositories only · up to ~2,000 files          │
│                                                                  │
│    Try an example:  [ flask-sample ]  [ express-sample ]         │
│                     [ vulnerable-app ]                           │
│                                                                  │
│    Recent analyses (this browser)                                │
│    ● owner/repo     Ready · 2 days ago · 432 files               │
│    ● owner/repo2    Failed · too large                           │
│                                                                  │
│    ── What you get ──────────────────────────────────────────    │
│    [ Graph map ]   [ Findings ]   [ Cited answers ]              │
└──────────────────────────────────────────────────────────────────┘
```

**Components:** headline, URL input with inline validation, primary button, example chips, recent list, three short capability cards.

**States**
- *Empty:* as drawn.
- *Typing:* validates format live (`https://github.com/owner/repo`), shows a green check or a specific message.
- *Submitting:* button shows a spinner and is disabled.
- *Error:* message under the field, field keeps its text.

**Rules**
- Examples are **small, pre-analyzed repos you tested** (instant results, no waiting, no risk in a live demo). Do not suggest huge repos like React or VS Code, which exceed the limits.
- State the limits right under the field, so a rejection never feels like a surprise.
- Do not claim "any codebase." Say which languages get deep analysis.

**Data:** `POST /repos` on submit. Recent list comes from browser storage (see section 9.6).

### 5.2 Progress (`/a/:id`, while ingesting)

**Purpose:** make waiting feel informed, and unlock results as early as possible.

```
 owner/repo @ a1b2c3d
 Analyzing…  about 2 minutes for a repo this size

 ✔  Cloning repository                      12s
 ✔  Finding source files                     2s   (1,204 files)
 ◐  Parsing code                  340 / 1,204 files
 ○  Resolving dependencies
 ○  Running detectors
 ○  Preparing search for questions

 You can leave this page. Bookmark this URL and come back anytime.

 Ready so far:   Overview ✔   Explorer ○   Findings ○   Ask ○
```

**Progressive availability (key UX decision):** the backend finishes some features before others. The UI should unlock each as soon as it is ready instead of waiting for everything.

| Feature | Unlocks after |
|---|---|
| Overview (basic counts) | File discovery and parsing |
| Explorer (graph) | Dependency resolution |
| Findings | Detectors |
| Ask | Embedding |

Tabs for not-yet-ready features show a small "preparing" state with the stage name, not an error and not a blank screen.

**States:** running, slow ("taking longer than usual"), failed (message, what to try, link back to Home), done (auto-navigate to Overview with a brief "Analysis complete" notice).

**Rules**
- Show real counts ("340 / 1,204"), not a fake progress bar.
- Never promise a precise time. Say "about" and base it on the count.
- Announce stage changes to screen readers (`aria-live="polite"`).

### 5.3 Overview (`/a/:id/overview`)

**Purpose:** a calm, honest summary and a launchpad into deeper views.

```
┌ header + tabs ───────────────────────────────────────────────────┐
│ Summary                                  Key numbers             │
│ 432 files · 6 languages                  Files        432        │
│ [AI summary, generated on demand] ▸      Symbols      3,870      │
│                                          Dependencies 1,204      │
│                                          Lines        48.2K      │
│ Insights (click to explore)                                      │
│ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐      │
│ │ 14 findings│ │ 3 circular │ │ Top hubs   │ │ 21 unused  │      │
│ │ 2 high     │ │ imports    │ │ 5 files    │ │ functions  │      │
│ └────────────┘ └────────────┘ └────────────┘ └────────────┘      │
│                                                                  │
│ Languages                    Analysis depth                      │
│ ▇▇▇▇▇▇▇▇ Python 78%          Python, JS/TS: full                 │
│ ▇▇ JavaScript 20%            Other: structure and search only    │
│                                                                  │
│ Notes: 12 files skipped (syntax errors) ▸                        │
└──────────────────────────────────────────────────────────────────┘
```

**Insight cards (the engagement core, all computed without the AI)**

| Card | Source | Click goes to |
|---|---|---|
| Findings by severity | `findings` table | Findings, pre-filtered |
| Circular imports | Graph cycle detection | Explorer, cycle highlighted |
| Most depended-on files (hubs) | In-degree on the graph | Explorer, hub selected |
| Unused functions | Detector | Findings, rule filtered |
| Largest or most complex files | Parse metrics | Explorer, file selected |

**AI project summary:** optional and **generated on demand** (a button, not automatic), cached per snapshot, labeled "AI-generated, based on these files" with citations. If the AI is unavailable, the card simply does not offer the button.

**Rules**
- Always show the "analysis depth" note so users know which languages were fully analyzed.
- Skipped files and parse errors are surfaced, not hidden.
- Do not invent metrics (no "average analysis time," no growth percentages).

### 5.4 Explorer (`/a/:id/explore`): the core screen

**Purpose:** navigate structure visually, inspect any element, and connect code to answers.

```
┌ header + tabs ───────────────────────────────────────────────────────┐
├──────────────┬────────────────────────────────────┬──────────────────┤
│ File tree    │ owner/repo › src › auth            │ auth/service.py  │
│ [ search ]   │ [Folders|Files|Symbols] [Fit] [List]│ Python · 312 loc │
│              │                                    │ ──────────────── │
│ ▾ src        │        ◯────▶◯                     │ [Code][Used by]  │
│  ▾ auth      │         ╲   ▲                      │ [Findings 2]     │
│    service.py│          ▶◯─┘     ┌ legend ┐       │                  │
│    jwt.py    │      ◯ ┄┄▶ ◯      │ ▭ file │       │ Used by 4 files  │
│  ▸ api       │     (dashed = low  │ ○ func │       │ Uses 7 symbols   │
│  ▸ db        │      confidence)   │ ◇ class│       │ ──────────────── │
│              │                    └────────┘       │ [Ask about this] │
└──────────────┴────────────────────────────────────┴──────────────────┘
```

**Three panes, one rule: selection drives everything.** Select something in any pane (tree, graph, search, citation, finding) and all three update.

| Pane | Contents |
|---|---|
| **Left: file tree** | Folder tree with search. Click a file to select it. Files in Tier 1 languages are shown with a "basic support" badge and have no graph edges |
| **Center: graph** | Level-of-detail graph (below), breadcrumb, level switch, fit-to-screen, list-view toggle, legend |
| **Right: node panel** | Tabs: Code (highlighted, with the relevant lines marked), Used by (dependents), Uses (dependencies), Findings. A button "Ask about this" opens the Ask drawer with context |

#### Level of detail (how we avoid the hairball)

| Level | Shows | How you get there |
|---|---|---|
| **Folders** | One node per top-level folder, edges sized by how many imports cross them | Default view |
| **Files** | Files in the selected folder, edges between them (and to outside neighbors, collapsed) | Double-click a folder, or switch level |
| **Symbols** | Functions and classes in the selected file, with call edges | Double-click a file |

Rules:
- **Render cap:** never draw more than a set number of nodes at once (target around 300, to be tuned by an early spike). If a view exceeds it, cluster the rest into expandable "+ 87 more" nodes.
- **Focus mode:** selecting a node dims everything except its 1 to 2 hop neighborhood. A "show all" toggle restores the full view.
- **Breadcrumb** reflects the current scope and is clickable.
- **Neighbor clarity:** edges leaving the scope are drawn to small "outside" stubs with labels instead of loading the rest of the repo.

#### Encoding (what the picture means)

Meaning is never carried by color alone.

| Thing | Shape | Color | Other cue |
|---|---|---|---|
| Folder | Rounded rectangle | Neutral gray | Chevron icon |
| File | Rectangle | By language (muted) | Language label on hover |
| Class | Diamond | Dark | Label |
| Function / method | Circle | Medium | Label |
| External package | Dashed outline | Light gray | "external" tag |
| Selected | Thick black outline | Black | Always visible |
| Has high-severity finding | Small badge | Red | Count |
| Edge: import | Solid line, arrowhead | Gray | |
| Edge: call | Thinner line, arrowhead | Gray | |
| **Edge: low confidence** | **Dashed line** | Gray | Tooltip explains why |

#### Interactions

- **Click** a node: select it (panel updates, URL updates).
- **Double-click:** drill down one level.
- **Hover:** tooltip with name, kind, file, line range, finding count.
- **Drag/zoom/pan:** standard. **Fit** button resets.
- **Search** (tree or `Ctrl/Cmd+K`): jump to any file or symbol, which centers and selects it.
- **List view toggle:** the same data as an expandable table/tree. This is the accessible alternative, and often faster for large scopes.

#### States

| State | Presentation |
|---|---|
| Graph not ready | Preparing state with the current stage |
| Empty scope | "No dependencies found in this folder" |
| Too large for the view | Cluster nodes plus a note "showing top N by connections" |
| Tier 1 file selected | Panel shows structure and code; note "Dependency analysis is not available for this language" |
| Tier 2 file with unresolved imports | Listed under Uses as "unresolved (n)" with an explanation |

### 5.5 Ask drawer (available on every tab)

**Purpose:** question answering with evidence, honest about how each answer was produced.

```
┌ Ask about owner/repo ────────────────── ✕ ┐
│ Suggested                                  │
│  • What depends on auth/service.py?        │
│  • What does the top hub file do?          │
│  • Where is "login" referenced?            │
│                                            │
│ You: Where is authentication handled?      │
│                                            │
│ RepoLens  [AI answer]                      │
│ Authentication is handled in the login     │
│ route, which calls the token check in      │
│ the auth service before the request…       │
│  Sources:                                  │
│  [auth/service.py:40-72] [api/login.py:12-30]│
│                                            │
│ You: Which files import jwt.py?            │
│ RepoLens  [From the graph]                 │
│  5 files: api/login.py, api/users.py …     │
│                                            │
│ [ Ask a question about this codebase…   ➤ ]│
└────────────────────────────────────────────┘
```

**Key behaviors**

1. **Two kinds of answers, labeled.** "From the graph" (instant, deterministic) and "AI answer" (generated, with sources). Users learn which to trust for what.
2. **Citations are chips, not footnotes.** Each chip is `path:start-end`. Click one: the Explorer selects that node, the node panel opens the code, and the cited lines are highlighted.
3. **Citation validation is visible.** Only validated citations render as chips. If the system had to drop an invalid citation, the answer shows a small note: "1 source could not be verified and was removed."
4. **Context-aware.** "Ask about this" from the node panel pre-fills the context ("About auth/service.py: …").
5. **Suggested questions come from the data**, using templates over real names (top hubs, files with findings, symbols matching common terms), not generic filler.
6. **Honest empty and failure states**
   - No relevant code found: "I could not find code related to that in this repository." (no invented answer)
   - AI unavailable: "AI answers are unavailable right now. Graph questions still work."
   - Rate limit reached: say so, with when it resets.
7. **Streaming** the answer text if the backend supports it (feels faster). Citations appear when validated at the end.
8. **Conversation is per snapshot** and kept in the session. Clearing is one click.

### 5.6 Findings (`/a/:id/findings`)

**Purpose:** a trustworthy, scannable list of potential issues.

```
┌ header + tabs ───────────────────────────────────────────────────┐
│ Findings (14)   Severity: [All ▾]  Rule: [All ▾]  Language: [All ▾]│
│ These are rule-based checks. They can miss issues and can flag     │
│ safe code. Review each one.                                  [i]   │
├──────────────────────────────────────────────────────────────────┤
│ ● High    Use of eval()          api/render.py:88                  │
│ ● High    SQL built from strings db/queries.py:41                  │
│ ● Medium  Hardcoded secret       config.py:12   (value hidden)     │
│ ○ Low     Bare except            utils/io.py:55                    │
└──────────────────────────────────────────────────────────────────┘
        click a row → right panel: why it matters, masked snippet,
        [Open in Explorer]  [Copy location]
```

**Rules**
- **Never show "All clear" or "0 issues" as a verdict.** If there are none, say: "No findings from our current rules. This does not guarantee the code is safe."
- Severity uses **color plus an icon plus text** (not color alone).
- Secrets are **always masked** in the UI ("value hidden"). No reveal button.
- Group or sort by severity by default, with filters for severity, rule, language, and file path.
- Each finding explains **what the rule looks for and why it can be risky**, in plain language, plus a short "possible false positive if…" hint.
- Optional "Explain this finding" uses the AI, clearly labeled, and never decides whether the finding exists.
- Export (P2): Markdown or JSON of the current filtered list.

### 5.7 Dependencies (`/a/:id/dependencies`)

**Purpose:** answer "what does this project rely on, and how is it wired internally?"

Two sub-views as a segmented control:
- **Internal** (default, comes from the graph we already build): table of files/modules with "used by" and "uses" counts, sortable, plus a hub/cycle highlight. Click a row to open it in Explorer.
- **External packages:** third-party imports found in the code, with how many files use each. Version information requires reading manifest files (`requirements.txt`, `package.json`), which is a **separate, optional parser** and a P2 item. Without it, the table shows package name and usage count only.

**Rules**
- Say clearly that third-party packages are **not installed or executed** and appear as external nodes.
- Cycles are listed explicitly with the files involved.

### 5.8 About / How it works (`/about`)

**Purpose:** build trust and set expectations. One short page.

Sections: what RepoLens does (3 sentences), supported languages and depth tiers, how answers are produced (graph, retrieval, AI, citations), limits (size, public repos only), known limitations (approximate call graphs in dynamic languages, rule-based detection can miss issues, secrets detection is best-effort), privacy (the clone is deleted after analysis, only redacted file text is kept, secrets are redacted), and the evaluation summary once available.

This page is also where honesty is made concrete. Link to it from the Overview "analysis depth" note and from tooltips on low-confidence edges.

### 5.9 Unlock (`/unlock`, public hosted demo only)

A single field for the shared access key and a Continue button. No accounts, no registration. Shown only if the server requires a key. Local development and the laptop demo skip this entirely.

---

## 6. Screens from the mock: keep, change, cut

| Mock screen | Decision | Notes |
|---|---|---|
| 1. Landing page | **Merged into Home** | One screen, no marketing page |
| 2. Login / Sign up | **Cut** | Accounts are out of scope. Optional shared key replaces it |
| 3. Dashboard (stats, "tokens used") | **Replaced by Recent list** | Invented metrics removed |
| 4. New Analysis | **Merged into Home** | Upload ZIP is P2 |
| 5. Analysis in progress | **Keep, improved** | Real counts, progressive availability |
| 6. Results overview | **Keep, changed** | Insight cards from real computed data |
| 7. Code structure (tree + graph) | **Keep, enlarged** | Becomes the Explorer, graph is the main area, adds code viewer and Ask |
| 8. Dependencies | **Keep, reduced** | Internal first, external later |
| 9. AI Insights | **Reshaped** | Becomes the Ask drawer and an on-demand summary. "Suggested improvements" removed |
| 10. Security report | **Replaced by Findings** | List with evidence, no "All clear" |
| 11. Saved reports | **Cut** | Recent list covers it |
| 12. Settings, plans, upgrade | **Cut** | No accounts or billing |
| 13. Mobile view | **Reduced** | See section 10 |

---

## 7. User engagement and experience

For a developer tool, "engagement" means **reaching insight quickly and wanting to keep exploring**, not retention tricks. No gamification, no streaks, no popups.

### 7.1 What keeps users moving

1. **Insight cards on Overview.** Real, specific, clickable ("3 circular imports"). Each is a doorway into Explorer or Findings with the right filter applied.
2. **Suggested questions built from the repo.** The first useful question is one click away.
3. **Instant graph answers.** Structural questions return immediately, which makes the Ask panel feel responsive.
4. **Everything is connected.** A finding opens in the Explorer, a citation opens code, a node opens Ask. Users never hit a dead end.
5. **Examples that work instantly.** Pre-analyzed repos mean the first experience takes seconds.
6. **Shareable views.** Because state is in the URL, a user can send "this node, this finding" to a teammate.
7. **Recent analyses.** Returning is one click.

### 7.2 Onboarding (lightweight)

- **First-run tour (3 steps, skippable, shown once):** (1) "Click any node to inspect it," (2) "Double-click to go deeper," (3) "Ask questions, answers show their sources." Stored in browser storage so it does not repeat.
- **Contextual hints** on first use of a feature (a one-line hint near the level switch, near the confidence dashes).
- No modal walls, no required steps, no email capture.

### 7.3 Making waiting feel good

- Real stage names and counts, not a spinner.
- Progressive unlocking (section 5.2).
- Skeleton screens that match the final layout, not blank panels.
- A clear "you can leave" message with the URL.

### 7.4 Trust-building details (these are UX, not decoration)

- Commit SHA shown in the header.
- Confidence shown on uncertain edges.
- Analysis depth shown per language.
- Citations always visible, always clickable.
- Skipped files and parse errors listed.
- A visible "How it works" page.

### 7.5 Tone of voice (microcopy)

Plain, direct, specific, never cute.

| Situation | Copy |
|---|---|
| Too large | "This repository has 4,210 source files. The limit is 2,000. Try a smaller repository." |
| No findings | "No findings from our current rules. This does not guarantee the code is safe." |
| No answer | "I could not find code related to that question in this repository." |
| AI down | "AI answers are unavailable right now. Graph questions still work." |
| Low confidence edge | "Dashed: this link is a best guess. Dynamic code makes some calls hard to resolve." |
| Tier 1 file | "Basic support: structure and search only for this language." |

### 7.6 Measuring the experience (for the project)

We will not add tracking to a course project. Instead, a short **usability test** (section 15) measures whether the design works, and the results go in the report.

---

## 8. Visual design system (white and black, professional)

### 8.1 Personality

Quiet, precise, confident. A developer tool that looks like it belongs next to a code editor: lots of white space, crisp 1px borders, strong black primary actions, restrained color used only for meaning.

### 8.2 Color tokens

Define as CSS variables so light and dark themes are a token swap, not a redesign.

```css
:root {
  /* Neutrals */
  --bg:            #FFFFFF;
  --surface:       #FAFAFA;   /* panels, cards */
  --surface-2:     #F4F4F5;   /* hover, table stripes */
  --border:        #E4E4E7;
  --border-strong: #D4D4D8;
  --text:          #0A0A0A;
  --text-muted:    #52525B;
  --text-subtle:   #71717A;

  /* Primary action = black */
  --primary:       #0A0A0A;
  --primary-hover: #27272A;
  --primary-text:  #FFFFFF;

  /* Focus */
  --focus-ring:    #0A0A0A;

  /* Semantic (used only for meaning) */
  --danger:        #B42318;   /* high severity, errors */
  --warning:       #B54708;   /* medium severity */
  --info:          #175CD3;   /* low severity, links */
  --success:       #067647;   /* done, passed checks */

  /* Graph (muted, distinguishable) */
  --node-python:   #2F5D8A;
  --node-js:       #A16207;
  --node-other:    #52525B;
  --node-external: #A1A1AA;
}

:root[data-theme="dark"] {
  --bg: #09090B;  --surface: #111113;  --surface-2: #18181B;
  --border: #27272A;  --border-strong: #3F3F46;
  --text: #FAFAFA;  --text-muted: #A1A1AA;  --text-subtle: #71717A;
  --primary: #FAFAFA;  --primary-hover: #E4E4E7;  --primary-text: #0A0A0A;
  --focus-ring: #FAFAFA;
}
```

The exact hex values are a starting palette. Check contrast with a tool once the screens exist (target WCAG AA: 4.5:1 for body text, 3:1 for large text and UI components).

### 8.3 Typography

| Use | Font | Notes |
|---|---|---|
| UI text | Inter (or system sans fallback) | Weights 400, 500, 600 |
| Code, paths, line ranges | JetBrains Mono (or system mono fallback) | Always for file paths and snippets |

Scale: 12 (captions) / 14 (body, default) / 16 (emphasis) / 20 (section titles) / 28 to 32 (page headline). Line height about 1.5 for body. Provide font fallbacks, so the UI still works if a font fails to load.

### 8.4 Spacing, shape, depth

- 4px base grid. Common steps: 4, 8, 12, 16, 24, 32, 48.
- Radius: 6px for inputs and buttons, 10px for cards and panels.
- Borders over shadows. One subtle shadow only for popovers and the Ask drawer.
- Generous white space. Content width capped on text-heavy pages (Overview, About), full width for Explorer.

### 8.5 Components (inventory)

Button (primary black, secondary outlined, ghost), Input with validation, Tabs, Segmented control, Chip (example, citation, language), Badge (severity, count, "Basic support"), Card (insight card), Table (sortable, filterable), Tree (file tree), Breadcrumb, Tooltip, Drawer (Ask), Side panel (node, finding), Code viewer (highlighted, line markers), Stepper (progress), Skeleton, Toast, Empty state, Error state, Command palette, Theme toggle.

Build these once, with the same spacing and states, and reuse them everywhere. Consistency is the main thing that makes a student project look professional.

### 8.6 Icons and imagery

One icon set (line icons, consistent stroke). No stock photos, no 3D illustrations. The only "illustration" is the graph itself.

### 8.7 Dark mode

The mock includes a theme toggle. Recommendation: **light is the default and the design target. Dark is a stretch goal** that costs little if all colors come from tokens from day one. Do not hardcode colors in components.

### 8.8 Motion

Short, functional (150 to 200 ms): panel slide-in, tab underline, graph focus fade. No decorative animation. Respect `prefers-reduced-motion` by disabling nonessential animation.

---

## 9. Data flow (frontend view)

### 9.1 End-to-end sequence

```
User          React app              FastAPI                Worker / DB
 │ paste URL     │                      │                        │
 ├─────────────▶ │ validate format      │                        │
 │               ├─POST /repos─────────▶│ validate, create       │
 │               │                      │ snapshot + job ───────▶│ (job queued)
 │               │◀──── snapshot id ────┤                        │
 │ (route /a/42) │                      │                        │
 │               ├─GET status (poll)───▶│◀── stage, percent ─────┤
 │               │◀── stage, features ──┤       (worker runs     │
 │ progress UI   │   (repeat, backoff)  │        pipeline)       │
 │               │                      │                        │
 │               ├─GET summary─────────▶│                        │
 │ Overview      │◀── counts, insights ─┤                        │
 │               ├─GET graph?level=… ──▶│ (NetworkX, cached)     │
 │ Explorer      │◀── nodes, edges ─────┤                        │
 │ click node    ├─GET file/symbol ────▶│                        │
 │               │◀── code, findings ───┤                        │
 │ ask question  ├─POST ask ───────────▶│ route → graph or       │
 │               │                      │ retrieve → LLM →       │
 │               │◀── answer+citations ─┤ validate citations     │
```

### 9.2 Screen to API map

| Screen | Calls | Caching |
|---|---|---|
| Home | `POST /repos`; none else | Recent list from browser storage |
| Progress | `GET /snapshots/{id}/status` (poll) | None, polled |
| Overview | `GET /snapshots/{id}/summary` | Cache until snapshot changes (never, since snapshots are immutable) |
| Explorer | `GET .../graph?level=&root=`, `GET .../symbols/{id}`, `GET .../files/{id}/content`, `GET .../search?q=` | Cache per (level, root); snapshots are immutable, so long cache lifetimes are safe |
| Findings | `GET .../findings?severity=&rule=&language=` | Cache per filter set |
| Dependencies | `GET .../dependencies?kind=internal\|external` | Cache |
| Ask | `POST .../ask` | Not cached; conversation kept in session |

**Key property:** a snapshot is immutable (repo + commit SHA). Once `ready`, every read endpoint can be cached aggressively on the client, which makes navigation feel instant.

### 9.3 Frontend state architecture

| Kind of state | Where it lives | Why |
|---|---|---|
| Server data (graph, findings, summary) | A data-fetching cache (TanStack Query suggested) | Handles caching, loading, error, retries |
| Navigation and view state (tab, level, root, selected node, filters, drawer open) | **URL** (router search params) | Shareable, back button works |
| Ephemeral UI state (hover, tooltip, input text) | Component state | Not worth persisting |
| Preferences (theme, tour completed, recent analyses) | Browser local storage | Survives reloads, never leaves the browser |
| Ask conversation | Session state (in memory, optionally session storage) | Per snapshot, cleared on demand |

### 9.4 API additions needed (not yet in the design doc)

The design doc's API covers most of this, but the UI needs a few more endpoints and fields. These should be added to the backend plan.

| Addition | Purpose |
|---|---|
| `GET /snapshots/{id}/summary` | Counts (files, symbols, edges, lines), language breakdown, findings by severity, number of cycles, top hubs, skipped files. Powers Overview and insight cards |
| `GET /snapshots/{id}/search?q=` | Symbol and file search for the tree, command palette, and suggested questions |
| `GET /snapshots/{id}/files/{file_id}/content` | Source for the code viewer (file text is stored redacted in `files.content`) |
| `features` field on the status response | `{overview, graph, findings, ask}` booleans for progressive unlocking |
| `confidence` and `finding_count` on graph nodes and edges | Dashed edges and badges in the graph |
| Answer `kind` field on `/ask` | `graph` or `ai`, for the label on each answer |
| Optional `POST /snapshots/{id}/summary/generate` | On-demand AI project summary, cached per snapshot |

**Graph response shape (sketch)**

```json
{
  "level": "file",
  "root": "src/auth",
  "nodes": [
    {"id": "f_12", "kind": "file", "label": "service.py", "path": "src/auth/service.py",
     "language": "python", "loc": 312, "findings": {"high": 1, "medium": 0, "low": 1},
     "in_degree": 4, "expandable": true}
  ],
  "edges": [
    {"id": "e_77", "source": "f_12", "target": "f_30", "type": "imports", "confidence": 1.0}
  ],
  "truncated": false,
  "hidden_count": 0
}
```

### 9.5 Polling versus streaming

- **Progress:** poll the status endpoint (every 1 to 2 seconds, slowing down over time). Simple and robust. Server-sent events are an optional upgrade, not required.
- **Ask:** stream text if the backend and provider support it, otherwise show a typing state and render the full answer.

### 9.6 What the browser stores

Only convenience data: recent analyses (snapshot id, repo name, status, time), theme, and whether the tour was completed. No source code is stored in the browser beyond the current view. Storage access is wrapped in error handling and the UI works with empty storage (private browsing).

### 9.7 Trust boundaries in the UI

- All text coming from the repository (file names, code, comments) and from the AI is **untrusted**. Render it as text. Never inject raw HTML.
- Render AI answers through a safe markdown renderer with HTML disabled and links restricted.
- Citation chips are generated only from server-validated references.
- Secrets never reach the client unmasked, because the backend redacts them before storage.

---

## 10. Responsive behavior

The product is desktop-first because the Explorer needs space.

| Width | Behavior |
|---|---|
| **Desktop (1280 and up)** | Full three-pane Explorer, Ask drawer docked beside content |
| **Laptop / small desktop (1024 to 1279)** | Left tree collapsible, Ask drawer overlays |
| **Tablet (768 to 1023)** | Tree and node panel become toggled drawers over the graph |
| **Phone (under 768)** | Home, Progress, Overview, Findings, and Ask work fully. **Explorer graph shows the list view only**, with a note "The graph view needs a larger screen." |

Rationale: a readable code graph on a phone is a poor experience, and pretending otherwise would hurt more than a clear, honest fallback. The list view keeps the data reachable.

---

## 11. Accessibility

- **Contrast:** meet WCAG AA for text and UI components. Verify the palette with a checker.
- **Keyboard:** every action reachable by keyboard, logical tab order, visible focus ring (2px, token `--focus-ring`), `Esc` closes panels and drawers.
- **Graph:** the **list view** is the accessible equivalent of the graph. Graph nodes are also focusable and navigable with arrow keys where the library supports it.
- **Not color alone:** severity has icon plus text, edge confidence uses dashes, node kind uses shape.
- **Screen readers:** `aria-live` on progress and Ask answers, labeled landmarks (header, nav, main, complementary), accessible names on icon buttons.
- **Motion:** respect `prefers-reduced-motion`.
- **Language and sizing:** body text at least 14px, page works at 200% zoom.

---

## 12. Interaction details worth getting right

### 12.1 Loading, empty, and error states (catalog)

| Context | Loading | Empty | Error |
|---|---|---|---|
| Home recent list | None | "No analyses yet. Try an example." | Hide the list silently |
| Progress | Stage list | n/a | Message plus "Back to Home" |
| Overview | Skeleton cards | n/a | "Could not load summary" with retry |
| Graph | Skeleton plus "Laying out…" | "No dependencies in this folder" | "Could not load graph" with retry |
| Node panel | Skeleton | "Select a node to see details" | Inline error with retry |
| Findings | Skeleton rows | "No findings from our current rules…" | Retry |
| Ask | Typing indicator | Suggested questions | Specific message (AI down, rate limit, timeout) |

Rule: **every error says what happened and what the user can do next.** No raw error codes or stack traces.

### 12.2 Feedback timing

- Under 100 ms: feels instant (selection, hover, tab switch with cached data).
- 100 ms to 1 s: show a subtle pending state.
- Over 1 s: show a skeleton or spinner with a label.
- Over 10 s: show what is happening and that the user may leave.

### 12.3 Destructive or irreversible actions

There are very few: clearing recent analyses and clearing the Ask conversation. Both ask for confirmation in one short sentence.

### 12.4 Forms

One real form (the URL field). Validate on input and on submit. Keep the user's text on error. Pressing Enter submits.

### 12.5 Keyboard shortcuts (accelerators only)

| Key | Action |
|---|---|
| `/` | Focus the search field |
| `Ctrl/Cmd + K` | Open the command palette (jump to file or symbol, switch tab) |
| `Esc` | Close the current panel or drawer |
| `F` | Fit the graph to the screen |
| `?` | Show the shortcuts list |

Shortcuts are listed in a small help overlay and never required for any task.

### 12.6 Command palette

One input that searches files, symbols, and actions ("Go to Findings"). It reuses the search endpoint. It is an accelerator for experienced users and a cheap way to make large repos navigable.

---

## 13. Frontend technical suggestions

These are suggestions to confirm during Week 1. Verify current versions and licenses when you install.

| Concern | Suggestion | Notes |
|---|---|---|
| Framework | React with TypeScript, a Vite single-page app, React Router | Backend is a separate FastAPI service, so a server-rendering framework is not required |
| Styling | Tailwind CSS with CSS-variable tokens, plus shadcn/ui-style components | Matches the black and white look, and the components are easy to restyle |
| Server state | TanStack Query | Caching and retries |
| Graph | **Cytoscape.js** or **React Flow** | See tradeoff below |
| Code viewer | A lightweight highlighter (for example Shiki or Prism) with line markers | A full editor component is heavier than needed for read-only code |
| Markdown (AI answers) | A markdown renderer with HTML disabled | Security |
| Icons | One line-icon set (for example Lucide) | Consistency |

**Graph library tradeoff**

| | React Flow | Cytoscape.js |
|---|---|---|
| Fit with React | Native, custom node components are easy | Imperative API, wrapped in a component |
| Rendering | DOM-based, good for tens to a few hundred nodes | Canvas-based, generally handles larger graphs |
| Graph algorithms and layouts | Layouts via add-ons | Many built in and as extensions |
| Styling | Fully custom with HTML and CSS | Stylesheet-based, less flexible for rich nodes |

**Recommendation:** run a **half-day spike at the start of Week 2** with a realistic 300 to 500 node graph in both. Pick the one that stays smooth and readable. Because we cap rendered nodes with level of detail, either can work, and the spike replaces guessing with a measurement.

### Suggested folder structure

```
web/
  src/
    routes/                # Home, Analysis (shell), Overview, Explore,
                           # Findings, Dependencies, About, Unlock
    features/
      explorer/            # GraphCanvas, FileTree, NodePanel, Legend, LevelSwitch
      ask/                 # AskDrawer, MessageList, CitationChip, Suggestions
      findings/            # FindingsTable, FindingPanel, Filters
      overview/            # InsightCard, LanguageBar, Summary
      progress/            # StageList
    components/ui/         # Button, Tabs, Badge, Chip, Tooltip, Drawer, Skeleton…
    api/                   # typed client, one function per endpoint
    hooks/                 # useSnapshot, useGraph, useUrlState, useRecent
    lib/                   # url state helpers, formatters, storage wrapper
    styles/                # tokens.css, base.css
```

---

## 14. Performance experience

Targets (to be measured, not assumed):

| Interaction | Target |
|---|---|
| Home to first paint | Under 2 seconds on a normal connection |
| Tab switch with cached data | Feels instant |
| Graph drill-down | Under 1 second |
| Node selection to code visible | Under 300 ms (cached) or a skeleton |
| Ask, graph-answered | Under 1 second |
| Ask, AI-answered | Around 5 seconds, with typing or streaming feedback |

How we get there: cache aggressively (snapshots are immutable), cap rendered nodes, virtualize long lists (findings, file tree, tables), lazy-load the graph library and the code viewer, debounce search input, and avoid re-laying out the graph when only the selection changes.

---

## 15. Usability testing plan

A small test gives real evidence for the report.

- **Participants:** about 5 people (classmates, one or two non-technical). A small group commonly reveals most major usability problems.
- **Prepared environment:** pre-analyzed example repo, so the test measures the interface and not the clone time.
- **Tasks (no hints):**
  1. Start an analysis from an example.
  2. Find the file that the most other files depend on.
  3. Find a high-severity finding and open the exact code.
  4. Ask where a feature is handled, then verify the answer using its citation.
  5. Find which files import a given module.
- **Measures:** task success, time per task, errors and wrong turns, confidence rating (1 to 5), and a short standard questionnaire (for example the System Usability Scale).
- **Output:** a table of issues ranked by severity, what was changed in response, and before/after notes. Report negative findings honestly.

---

## 16. Build plan for the UI

| Week | UI work |
|---|---|
| 1 | Design tokens, base components (button, input, tabs, badge), router with route shells, Home with working submit, Progress screen on top of the status endpoint |
| 2 | Graph spike, Explorer shell (tree, canvas, panel), folder to file to symbol levels, node panel with code viewer, Findings table |
| 3 | Ask drawer with citations and labels, Overview insight cards, Dependencies internal view, error and empty states |
| 4 | Usability test and fixes, About page, accessibility pass, polish, demo repos and example chips, optional dark mode |

**If time is short, the minimum viable UI is:** Home, Progress, Explorer (graph, tree, node panel), Findings list, Ask drawer with citations. Everything else (Overview extras, Dependencies external view, dark mode, command palette, export, tour) is cut first, in that order.

---

## 17. Explicitly out of scope for the UI (v1)

Login and accounts, user profiles, settings pages, plans and billing, saved or shared reports on the server, team features, notifications, mobile graph exploration, ZIP upload (P2), export (P2), manifest-based package versions (P2), editing or fixing code, light and dark theme beyond a token swap.

---

## 18. UX acceptance checklist

- A first-time user can start an analysis from Home without instructions.
- The current location is always clear (tab, breadcrumb, header).
- Any view can be reopened from its URL, and the back button behaves sensibly.
- No screen shows more than the render cap of nodes at once.
- Every AI answer is labeled and shows validated, clickable citations.
- Graph-answered and AI-answered responses are visibly distinct.
- Findings never claim "all clear," and secrets are always masked.
- Uncertain edges are visually distinct and explained.
- Every error states what happened and what to do next.
- Core flows work by keyboard alone, and the graph has a list-view alternative.
- Text meets contrast guidelines in the light theme.
- If the AI provider is unavailable, graph, findings, and structural questions still work.
- Progress shows real stages and counts, and features unlock as they become ready.

---

## 19. Open questions

1. Final graph library (decided by the Week 2 spike).
2. ~~Store file contents or re-fetch?~~ **Decided:** store redacted file text (see PRD open question 5).
3. Do we include the on-demand AI project summary, or leave AI to the Ask drawer only?
4. Public hosted demo or laptop only? (Decides whether the Unlock screen exists.)
5. Which three example repos do we pre-analyze, and do they include one with known security issues?
6. Do we ship dark mode, or only guarantee that tokens make it possible?
