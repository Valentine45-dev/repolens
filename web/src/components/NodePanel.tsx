import { useQuery } from "@tanstack/react-query";
import { Fragment, useEffect, useId, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";

import {
  getFile,
  getNeighbours,
  type FileDetail,
  type GraphNode,
  type Neighbour,
  type Site,
} from "../api";
import { GUESS_BELOW, languageLabel } from "../graphModel";
import type { LineRange } from "../links";
import { requestColours } from "../codeColours";
import { isTooLarge, langForPath, MAX_BYTES, ROLES, utf8Length, type ColouredLine } from "../codeRoles";
import { scrollToRange } from "../scroll";
import { CloseButton } from "./CloseButton";
import { useEscapeToClose } from "../escapeStack";
import { PanelTitle } from "./PanelTitle";
import { SeverityBadge } from "./Severity";
import { SiteChips } from "./SiteChips";

type Tab = "code" | "usedBy" | "uses" | "findings";

// Every query below is keyed by this node's ids and cancelled when the node changes, so a slow
// answer for one file can never be shown in another file's panel.
export function NodePanel({
  snapshotId,
  node,
  minConfidence,
  highlight,
  reveal = null,
  hidden = false,
  isInGraph,
  onSelectFile,
  onShowLines,
  onAsk,
  onShowFunctions,
  onClose,
}: {
  snapshotId: number;
  node: GraphNode;
  minConfidence: number;
  highlight: LineRange | null; // cited or flagged lines, from the URL
  /** Changes on each "open these lines" link (useRevealToken), so a click on the same chip again
   * shows the lines again. */
  reveal?: string | null;
  /** Behind the Ask tab (display: none): focus and scrolling wait until it is shown. */
  hidden?: boolean;
  isInGraph: (fileId: number) => boolean;
  onSelectFile: (fileId: number, lines?: LineRange) => void;
  onShowLines: (lines: LineRange) => void;
  onAsk: (fileId: number, path: string) => void;
  onShowFunctions?: (path: string) => void; // the map's symbol view of this file
  onClose: () => void;
}) {
  const [tab, setTab] = useState<Tab>("code");
  // New lines to show (a citation chip or a finding): open the code on them.
  const highlightKey = highlight ? `${highlight.start}-${highlight.end}` : null;
  useEffect(() => {
    if (highlightKey) setTab("code");
  }, [highlightKey, reveal]);
  const titleId = useId();
  const titleRef = useRef<HTMLHeadingElement>(null);

  // Keyboard focus (spec §11): opening moves focus to the panel heading; closing returns it to
  // whatever opened the panel (list row, graph node, a Used by / Uses link), if still on screen.
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    return () => {
      if (opener?.isConnected) opener.focus();
    };
  }, []);
  // A hidden heading cannot take focus: a file opened behind the Ask tab is focused when shown.
  const focusPending = useRef(true);
  useEffect(() => {
    focusPending.current = true;
  }, [node.id]);
  useEffect(() => {
    if (hidden || !focusPending.current) return;
    focusPending.current = false;
    titleRef.current?.focus();
  }, [node.id, hidden]);

  const panelRef = useRef<HTMLElement>(null);
  useEscapeToClose(panelRef, onClose);

  // A line chip in Used by / Uses: show that line in the code, in this file or in the other one.
  function openSite(fileId: number, line: number) {
    const lines = { start: line, end: line };
    setTab("code");
    if (fileId === node.id) onShowLines(lines);
    else onSelectFile(fileId, lines);
  }
  const canOpenSite = (fileId: number | null | undefined) =>
    fileId !== null && fileId !== undefined && (fileId === node.id || isInGraph(fileId));

  const file = useQuery({
    queryKey: ["file", snapshotId, node.id],
    queryFn: ({ signal }) => getFile(snapshotId, node.id, signal),
    staleTime: Infinity, // a snapshot never changes
  });
  const usedBy = useQuery({
    queryKey: ["neighbours", node.symbol_id, "dependents", minConfidence],
    queryFn: ({ signal }) => getNeighbours(node.symbol_id, "dependents", minConfidence, signal),
    staleTime: Infinity,
  });
  const uses = useQuery({
    queryKey: ["neighbours", node.symbol_id, "dependencies", minConfidence],
    queryFn: ({ signal }) => getNeighbours(node.symbol_id, "dependencies", minConfidence, signal),
    staleTime: Infinity,
  });
  // Under the line limit but over the byte limit: only known once the text is here.
  const coloursOff = useMemo(
    () => (file.data ? utf8Length(file.data.content) > MAX_BYTES : false),
    [file.data],
  );

  return (
    <aside className="panel" aria-labelledby={titleId} ref={panelRef}>
      <header className="panel-header">
        <div className="panel-heading">
          <PanelTitle id={titleId} path={node.path} titleRef={titleRef} />
          <p className="caption">
            {languageLabel(node.language)} · <span className="mono num">{node.loc}</span> lines
            {/* known from the line count before the text arrives, so it never shifts the panel */}
            {langForPath(node.path) && (isTooLarge(node.loc) || coloursOff) ? " · Colours off for large files" : null}
          </p>
        </div>
        {onShowFunctions ? (
          <button
            type="button"
            className="button button-secondary button-small"
            onClick={() => onShowFunctions(node.path)}
            title="Draw this file's classes and functions and what they connect to"
          >
            Functions
          </button>
        ) : null}
        <button
          type="button"
          className="button button-secondary button-small"
          onClick={() => onAsk(node.id, node.path)}
        >
          Ask about this
        </button>
        <CloseButton what="file panel" onClose={onClose} />
      </header>

      <dl className="panel-facts">
        <div>
          <dt>Used by</dt>
          <dd className="mono num">{usedBy.data ? files(usedBy.data.files) : "…"}</dd>
        </div>
        <div>
          <dt>Uses</dt>
          <dd className="mono num">{uses.data ? files(countFiles(uses.data.items)) : "…"}</dd>
        </div>
        <div>
          <dt>External imports</dt>
          <dd className="mono num">{node.external_imports}</dd>
        </div>
        <div>
          <dt>Unresolved imports</dt>
          <dd className="mono num">{node.unresolved_imports}</dd>
        </div>
      </dl>

      <div className="tabs" role="tablist" aria-label="File details">
        {(
          [
            ["code", "Code"],
            ["usedBy", "Used by"],
            ["uses", "Uses"],
            ["findings", `Findings (${node.findings})`],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            className="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="panel-body" role="tabpanel">
        {tab === "code" ? (
          file.data ? (
            <CodeView
              key={node.id}
              path={node.path}
              content={file.data.content}
              highlight={highlight}
              reveal={reveal}
              hidden={hidden}
            />
          ) : (
            <PanelState query={file} codeLines={node.loc} />
          )
        ) : tab === "usedBy" ? (
          usedBy.data ? (
            <NeighbourList
              items={usedBy.data.items}
              empty="No other file imports or calls this one."
              isInGraph={isInGraph}
              onSelectFile={onSelectFile}
              canOpenSite={canOpenSite}
              onOpenSite={openSite}
            />
          ) : (
            <PanelState query={usedBy} />
          )
        ) : tab === "findings" ? (
          file.data ? (
            <FileFindings findings={file.data.findings} onShowLines={onShowLines} />
          ) : (
            <PanelState query={file} />
          )
        ) : uses.data ? (
          <NeighbourList
            items={uses.data.items}
            empty="This file imports nothing and calls nothing outside itself."
            isInGraph={isInGraph}
            onSelectFile={onSelectFile}
            canOpenSite={canOpenSite}
            onOpenSite={openSite}
          />
        ) : (
          <PanelState query={uses} />
        )}
      </div>
    </aside>
  );
}

function files(n: number): string {
  return `${n} file${n === 1 ? "" : "s"}`;
}

function countFiles(items: Neighbour[]): number {
  return new Set(items.filter((i) => i.symbol.file_id !== null).map((i) => i.symbol.file_id)).size;
}

function PanelState({
  query,
  codeLines,
}: {
  query: { error: Error | null; refetch: () => unknown };
  /** Draw the code view's frame instead of rows: the file's real line count is known before its
   * text arrives, so the gutter has its final width and the lines fill the whole code area. */
  codeLines?: number;
}) {
  if (query.error) {
    return (
      <div className="panel-message" role="alert">
        <p>{query.error.message}</p>
        <button className="button button-secondary" onClick={() => query.refetch()}>
          Try again
        </button>
      </div>
    );
  }
  if (codeLines !== undefined) {
    // Enough lines to fill a tall panel (the area clips the rest); never more than the file has.
    const n = Math.max(1, Math.min(codeLines, CODE_SKELETON_MAX));
    const widths = Array.from({ length: n }, (_, i) => CODE_SKELETON[i % CODE_SKELETON.length]);
    return (
      <div className="code code-skeleton" aria-busy="true">
        <span className="visually-hidden">Loading the file…</span>
        <div className="code-gutter" aria-hidden="true">
          {widths.map((_, i) => (
            <div key={i}>{i + 1}</div>
          ))}
          {/* the widest number the file will show, so the gutter does not widen on arrival */}
          <div className="code-skeleton-width">{codeLines}</div>
        </div>
        <div className="code-text" aria-hidden="true">
          {widths.map((w, i) => (
            <div key={i} className="code-skeleton-line">
              {w ? <span className="skeleton" style={{ width: `${w}ch` }} /> : null}
            </div>
          ))}
        </div>
      </div>
    );
  }
  return (
    <div className="panel-message" aria-busy="true">
      {[70, 50, 62].map((w, i) => (
        <div key={i} className="skeleton" style={{ width: `${w}%`, marginTop: i ? 12 : 0 }} />
      ))}
    </div>
  );
}

// Line lengths (in characters) of the placeholder code; 0 is a blank line.
const CODE_SKELETON = [28, 0, 18, 22, 14, 0, 0, 34, 40, 26, 0, 30, 44, 20, 0, 36, 24, 0, 16, 38, 42, 30, 0];
// 1080px of panel at the code's 19.2px line height is about 50 lines; 80 covers taller screens.
const CODE_SKELETON_MAX = 80;

// Lines of context kept above a cited range that is too tall to centre (code line height 19.2px).
const SCROLL_CONTEXT_LINES = 3;

export function CodeView({
  path,
  content,
  highlight,
  reveal,
  hidden,
}: {
  path: string;
  content: string;
  highlight: LineRange | null;
  reveal: string | null;
  hidden: boolean;
}) {
  const lines = useMemo(() => {
    const all = content.split("\n");
    if (all.length > 1 && all[all.length - 1] === "") all.pop();
    return all;
  }, [content]);
  const colours = useCodeColours(path, content, lines);
  const gutter = useMemo(() => lines.map((_, i) => i + 1).join("\n"), [lines]);
  const markRef = useRef<HTMLDivElement>(null);
  const range =
    highlight && highlight.start <= lines.length
      ? { start: highlight.start, end: Math.min(highlight.end, lines.length) }
      : null;
  const rangeKey = range ? `${range.start}-${range.end}` : null;
  // Scroll to the lines once per request (new lines, or the same lines asked for again), and only
  // while the panel is on screen: behind the Ask tab it has no layout, so a scroll there does
  // nothing and the file would open on line 1. A request made while hidden waits for the tab.
  const requestKey = rangeKey === null ? null : `${rangeKey}|${reveal ?? ""}`;
  const doneKey = useRef<string | null>(null);
  const wasShown = useRef(false);
  useEffect(() => {
    const shownBefore = wasShown.current;
    wasShown.current = !hidden;
    if (hidden || !range || requestKey === null || doneKey.current === requestKey) return;
    const mark = markRef.current;
    const panel = mark?.closest<HTMLElement>(".panel-body");
    if (!mark || !panel) return;
    doneKey.current = requestKey;
    const lineHeight = mark.getBoundingClientRect().height / (range.end - range.start + 1);
    // Glide only within code that was already on screen; a file just opened or just brought to
    // the front lands on the lines at once. Never under reduced motion.
    const smooth = shownBefore && !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    scrollToRange(panel, mark, SCROLL_CONTEXT_LINES * lineHeight, smooth);
    // The chip that asked is now behind the panel, out of the tab order: keep focus in view.
    const active = document.activeElement;
    const code = mark.parentElement;
    if (code && (!active || active === document.body || active.closest("[inert]"))) {
      code.focus({ preventScroll: true });
    }
  }, [requestKey, hidden]); // range is part of requestKey
  return (
    <div
      className="code"
      data-colours={colours.state}
      tabIndex={0}
      aria-label={
        range ? `File contents, lines ${range.start} to ${range.end} highlighted` : "File contents"
      }
    >
      {range ? (
        <div
          ref={markRef}
          className="code-highlight"
          style={{ "--hl-start": range.start, "--hl-len": range.end - range.start + 1 } as CSSProperties}
          aria-hidden="true"
        />
      ) : null}
      <pre className="code-gutter" aria-hidden="true">
        {gutter}
      </pre>
      <pre className="code-text">{colours.lines ? renderColoured(colours.lines) : lines.join("\n")}</pre>
    </div>
  );
}

type ColourState = "pending" | "on" | "off" | "plain";

/** Plain text first; the coloured runs replace it in the same <pre> once the worker answers. Each
 * request has an id: an answer for an earlier request (another file, or this one opened again) is
 * never applied. Anything going wrong leaves the plain text, with a note in the console. */
function useCodeColours(
  path: string,
  content: string,
  lines: string[],
): { state: ColourState; lines: ColouredLine[] | null } {
  const lang = langForPath(path);
  const large = useMemo(() => isTooLarge(lines.length, utf8Length(content)), [lines, content]);
  const [result, setResult] = useState<{ id: number; lines: ColouredLine[] } | null>(null);
  const [failed, setFailed] = useState(false);
  const latest = useRef(0);
  useEffect(() => {
    setResult(null);
    setFailed(false);
    if (!lang || large) return;
    const req = requestColours(content, lang);
    latest.current = req.id;
    req.promise.then(
      (coloured) => {
        if (latest.current !== req.id || !coloured) return; // stale or cancelled
        if (sameText(coloured, lines)) setResult({ id: req.id, lines: coloured.slice(0, lines.length) });
        else {
          console.warn("Code colours do not match the file's text; showing plain text.");
          setFailed(true);
        }
      },
      (err: unknown) => {
        if (latest.current !== req.id) return;
        console.warn("Code colours unavailable; showing plain text.", err);
        setFailed(true);
      },
    );
    return () => {
      latest.current = 0;
      req.cancel();
    };
  }, [content, lang, large, lines]);
  const state: ColourState = !lang || failed ? "plain" : large ? "off" : result ? "on" : "pending";
  return { state, lines: result && result.id === latest.current ? result.lines : null };
}

/** The runs must give back the file exactly (the redacted text included), or they are not used. */
function sameText(coloured: ColouredLine[], lines: string[]): boolean {
  if (coloured.length < lines.length) return false;
  for (let i = coloured.length - 1; i >= lines.length; i--) if (coloured[i].length) return false;
  return lines.every((line, i) => coloured[i].map((run) => run[1]).join("") === line);
}

/** Runs as React text and spans with a fixed class per role: never HTML from the file. */
function renderColoured(coloured: ColouredLine[]): ReactNode[] {
  return coloured.map((line, i) => (
    <Fragment key={i}>
      {i ? "\n" : null}
      {line.map(([role, text], j) => {
        const name = ROLES[role];
        return name ? (
          <span key={j} className={`tk-${name}`}>
            {text}
          </span>
        ) : (
          text
        );
      })}
    </Fragment>
  ));
}

function FileFindings({
  findings,
  onShowLines,
}: {
  findings: FileDetail["findings"];
  onShowLines: (lines: LineRange) => void;
}) {
  if (findings.length === 0) {
    return (
      <p className="panel-message">
        No findings in this file from our current rules. This does not guarantee it is safe.
      </p>
    );
  }
  return (
    <ul className="neighbours">
      {findings.map((f) => (
        <li key={f.id} className="neighbour">
          <div className="neighbour-head">
            <SeverityBadge severity={f.severity} />
            <button
              type="button"
              className="row-button"
              onClick={() => onShowLines({ start: f.line, end: f.line })}
            >
              {f.message}
            </button>
          </div>
          <p className="neighbour-what caption">line {f.line}</p>
        </li>
      ))}
    </ul>
  );
}

interface FileGroup {
  key: string;
  fileId: number | null;
  path: string;
  kind: string; // module | external | unresolved
  imports: SiteRef | null;
  calls: (SiteRef & { name: string; guess: boolean })[];
}

// Where one import or call happens (the lines are in the file with id `fileId`).
interface SiteRef {
  fileId: number | null;
  path: string | null;
  sites: Site[];
  count: number | null;
}

function siteRef(item: Neighbour): SiteRef {
  return {
    fileId: item.site_file_id ?? null,
    path: item.site_path ?? null,
    sites: item.sites ?? [],
    count: item.site_count ?? null,
  };
}

function groupByFile(items: Neighbour[]): FileGroup[] {
  const groups = new Map<string, FileGroup>();
  for (const item of items) {
    const s = item.symbol;
    const key = s.file_id !== null ? `f${s.file_id}` : `${s.kind}:${s.qualified_name}`;
    let g = groups.get(key);
    if (!g) {
      g = {
        key,
        fileId: s.file_id,
        path: s.path ?? s.qualified_name,
        kind: s.file_id !== null ? "module" : s.kind,
        imports: null,
        calls: [],
      };
      groups.set(key, g);
    }
    if (item.type === "imports") g.imports = siteRef(item);
    else {
      g.calls.push({
        ...siteRef(item),
        name: s.kind === "module" ? "(top level)" : s.name,
        guess: item.confidence < GUESS_BELOW,
      });
    }
  }
  const order = { module: 0, unresolved: 1, external: 2 } as Record<string, number>;
  return [...groups.values()].sort(
    (a, b) => (order[a.kind] ?? 3) - (order[b.kind] ?? 3) || a.path.localeCompare(b.path),
  );
}

function NeighbourList({
  items,
  empty,
  isInGraph,
  onSelectFile,
  canOpenSite,
  onOpenSite,
}: {
  items: Neighbour[];
  empty: string;
  isInGraph: (fileId: number) => boolean;
  onSelectFile: (fileId: number) => void;
  canOpenSite: (fileId: number | null | undefined) => boolean;
  onOpenSite: (fileId: number, line: number) => void;
}) {
  const groups = useMemo(() => groupByFile(items), [items]);
  const chips = (ref: SiteRef) => (
    <SiteChips
      path={ref.path}
      sites={ref.sites}
      count={ref.count}
      onOpen={canOpenSite(ref.fileId) ? (line) => onOpenSite(ref.fileId!, line) : undefined}
    />
  );
  if (groups.length === 0) return <p className="panel-message">{empty}</p>;
  return (
    <ul className="neighbours">
      {groups.map((g) => (
        <li key={g.key} className="neighbour">
          <div className="neighbour-head">
            {g.fileId !== null && isInGraph(g.fileId) ? (
              <button type="button" className="row-button mono" onClick={() => onSelectFile(g.fileId!)}>
                {g.path}
              </button>
            ) : (
              <span className="mono neighbour-path">{g.path}</span>
            )}
            {g.kind !== "module" ? (
              <span className="tag" data-kind={g.kind}>
                {g.kind}
              </span>
            ) : null}
          </div>
          <p className="neighbour-what caption">
            {g.imports ? "imports" : null}
            {g.imports ? chips(g.imports) : null}
            {g.imports && g.calls.length ? " · " : null}
            {g.calls.length ? "calls " : null}
            {g.calls.length ? (
              <span className="neighbour-calls">
                {g.calls.map((c, i) => (
                  <span key={i} className="neighbour-call">
                    <span className="mono">{c.name}</span>
                    {c.guess ? (
                      <span className="guess-note" title="Best guess: matched by name only">
                        {" "}
                        (guess)
                      </span>
                    ) : null}
                    {chips(c)}
                  </span>
                ))}
              </span>
            ) : null}
            {g.kind === "unresolved" ? " · no matching file in this repository" : null}
          </p>
        </li>
      ))}
    </ul>
  );
}
