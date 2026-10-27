import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { getFile, getNeighbours, type GraphNode, type Neighbour } from "../api";
import { GUESS_BELOW, languageLabel } from "../graphModel";
import { Icon } from "./Icon";

type Tab = "code" | "usedBy" | "uses";

// Every query below is keyed by this node's ids and cancelled when the node changes, so a slow
// answer for one file can never be shown in another file's panel.
export function NodePanel({
  snapshotId,
  node,
  minConfidence,
  isInGraph,
  onSelectFile,
  onClose,
}: {
  snapshotId: number;
  node: GraphNode;
  minConfidence: number;
  isInGraph: (fileId: number) => boolean;
  onSelectFile: (fileId: number) => void;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<Tab>("code");
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

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
          <h2 id={titleId} className="panel-title mono">
            {node.path}
          </h2>
          <p className="caption">
            {languageLabel(node.language)} · <span className="mono num">{node.loc}</span> lines
          </p>
        </div>
        <button
          ref={closeRef}
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
            <CodeView key={node.id} content={file.data.content} />
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
            />
          ) : (
            <PanelState query={usedBy} />
          )
        ) : uses.data ? (
          <NeighbourList
            items={uses.data.items}
            empty="This file imports nothing and calls nothing outside itself."
            isInGraph={isInGraph}
            onSelectFile={onSelectFile}
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

function CodeView({ content }: { content: string }) {
  const lines = useMemo(() => {
    const all = content.split("\n");
    if (all.length > 1 && all[all.length - 1] === "") all.pop();
    return all;
  }, [content]);
  const gutter = useMemo(() => lines.map((_, i) => i + 1).join("\n"), [lines]);
  return (
    <div className="code" tabIndex={0} aria-label="File contents">
      <pre className="code-gutter" aria-hidden="true">
        {gutter}
      </pre>
      <pre className="code-text">{lines.join("\n")}</pre>
    </div>
  );
}

interface FileGroup {
  key: string;
  fileId: number | null;
  path: string;
  kind: string; // module | external | unresolved
  imports: boolean;
  calls: { name: string; guess: boolean }[];
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
        imports: false,
        calls: [],
      };
      groups.set(key, g);
    }
    if (item.type === "imports") g.imports = true;
    else g.calls.push({ name: s.kind === "module" ? "(top level)" : s.name, guess: item.confidence < GUESS_BELOW });
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
}: {
  items: Neighbour[];
  empty: string;
  isInGraph: (fileId: number) => boolean;
  onSelectFile: (fileId: number) => void;
}) {
  const groups = useMemo(() => groupByFile(items), [items]);
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
            {g.imports && g.calls.length ? " · " : null}
            {g.calls.length ? "calls " : null}
            {g.calls.map((c, i) => (
              <span key={i}>
                {i ? ", " : null}
                <span className="mono">{c.name}</span>
                {c.guess ? (
                  <span className="guess-note" title="Best guess: matched by name only">
                    {" "}
                    (guess)
                  </span>
                ) : null}
              </span>
            ))}
            {g.kind === "unresolved" ? " · no matching file in this repository" : null}
          </p>
        </li>
      ))}
    </ul>
  );
}
