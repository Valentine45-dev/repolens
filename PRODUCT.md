# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Drawn from `docs/repolens-ui-ux-spec.md` §2 and `docs/PRD.md` §4 (confirmed 27 Oct 2026).

- **New team member / student:** "help me understand this project"; succeeds when they find the main files and how they connect within minutes.
- **Reviewer / security-minded developer:** "show me risky code"; opens a high-severity finding, reads the exact code, decides if it is real.
- **Dependency evaluator:** "is this library well structured?"; sees structure, hubs, cycles and external dependencies at a glance.
- **Course evaluator:** "does this work and is it measured?"; completes the demo flow without help and sees honest limits.

Primary demo journey: paste the URL of a small or mid-sized repo, watch progress, open the graph, click a hub file, ask a question, click a citation, read the exact code.

## Product Purpose

RepoLens analyzes a public GitHub repository and helps a developer understand it quickly: a file-level dependency and call graph, rule-based findings, and answers to questions with validated `path:start-end` citations. Success is getting from "I pasted a URL" to "I understand where things are and why" with little friction and little doubt.

## Positioning

Deterministic analysis (parsing, graphs, rules) does the work; the LLM is used only for explanation and answers, and every answer is checkable through server-validated citations. Structural questions are answered from the graph without the LLM. Uncertain links (name-based call edges) carry a visible confidence instead of being presented as fact.

## Operating Context

A 4-day course build (deadline 30 Oct 2026), demoed locally with `docker compose up`. Used on a laptop next to a code editor and GitHub. Analyses are snapshots of one exact commit; a URL identifies an analysis and can be revisited.

## Capabilities and Constraints

- Input: `https://github.com/<owner>/<repo>` only, public repos, up to ~2,000 files, files over 1 MB skipped.
- Deep analysis for Python and JavaScript/TypeScript (symbols, import edges, call edges with confidence 1.0 / 0.9 / 0.5).
- The analyzed code is never executed; secrets are redacted before storage.
- Binding UI constraints from `CLAUDE.md`: light theme only (no dark mode, no theme toggle); no sidebar items, notifications, avatars or placeholders for features that do not exist; never show "Safe", "All clear" or "0 issues" as a verdict; finding labels match real detector rules; no invented data (stars, commits, PR counts, fake charts); graph answers labeled "From the graph"; AI answers always show citation chips.
- Not in this build: accounts, private repos, zip upload, dark mode, command palette, Dependencies tab, SSE.
- Built so far (27 Oct): ingestion, graph/file/symbol APIs. Findings, Q&A and Overview arrive later; the UI must not show them before they exist.

## Brand Commitments

- Name: RepoLens.
- Voice: plain, direct, specific, never cute (spec §7.5). Limits stated up front, not discovered by failure.
- The visual system is pinned by `docs/repolens-ui-ux-spec.md` §8 (white and black, professional; tokens in §8.2, Inter + JetBrains Mono, 4px grid, borders over shadows).

## Evidence on Hand

- Repos ingested and hand-checked end to end: `pallets/itsdangerous` (Python), `expressjs/express` (CommonJS), `sindresorhus/ky` (TypeScript). See `PROGRESS.md` for counts.
- No users, testimonials, benchmarks or usage numbers exist; none may be shown.

## Product Principles

1. Orient first: every screen answers where am I, what can I do here, what comes next.
2. One primary action per screen.
3. Evidence over assertion: claims show their file, line and code; best guesses are marked as guesses.
4. Honest by default: no verdicts of safety, limits visible.
5. The URL is the state: every view is linkable and the back button works.

## Accessibility & Inclusion

WCAG AA contrast (4.5:1 body, 3:1 large text and UI components), visible keyboard focus, stage changes announced with `aria-live="polite"`, color never the only carrier of meaning, `prefers-reduced-motion` respected (spec §11).
