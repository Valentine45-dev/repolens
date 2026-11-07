import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useRef, useState, type CSSProperties } from "react";

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
import { scrollToCenter } from "../scroll";
import { Icon } from "./Icon";
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
  }, [highlightKey]);
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
  useEffect(() => {
    titleRef.current?.focus();
  }, [node.id]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      // Esc inside the Ask drawer closes only the drawer (it has its own handler).
      if (e.key === "Escape" && !document.activeElement?.closest("#ask-drawer")) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

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

  return (
    <aside className="panel" aria-labelledby={titleId}>
      <header className="panel-header">
        <div className="panel-heading">
          <PanelTitle id={titleId} path={node.path} titleRef={titleRef} />
          <p className="caption">
            {languageLabel(node.language)} · <span className="mono num">{node.loc}</span> lines
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
        <button
          type="button"
          className="icon-button"
          onClick={onClose}
          aria-label="Close panel (Esc)"
          title="Close (Esc)"
        >
          <Icon name="x" />
        </button>
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
            <CodeView key={node.id} content={file.data.content} highlight={highlight} />
          ) : (
            <PanelState query={file} />
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

function PanelState({ query }: { query: { error: Error | null; refetch: () => unknown } }) {
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
  return (
    <div className="panel-message" aria-busy="true">
      <div className="skeleton" style={{ width: "70%" }} />
      <div className="skeleton" style={{ width: "50%", marginTop: 8 }} />
    </div>
  );
}

function CodeView({ content, highlight }: { content: string; highlight: LineRange | null }) {
  const lines = useMemo(() => {
    const all = content.split("\n");
    if (all.length > 1 && all[all.length - 1] === "") all.pop();
    return all;
  }, [content]);
  const gutter = useMemo(() => lines.map((_, i) => i + 1).join("\n"), [lines]);
  const markRef = useRef<HTMLDivElement>(null);
  const range =
    highlight && highlight.start <= lines.length
      ? { start: highlight.start, end: Math.min(highlight.end, lines.length) }
      : null;
  const rangeKey = range ? `${range.start}-${range.end}` : null;
  useEffect(() => {
    const mark = markRef.current;
    const panel = mark?.closest<HTMLElement>(".panel-body");
    if (mark && panel) scrollToCenter(panel, mark);
  }, [rangeKey]);
  return (
    <div
      className="code"
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
      <pre className="code-text">{lines.join("\n")}</pre>
    </div>
  );
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
