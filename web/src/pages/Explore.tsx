import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ReactFlowProvider, useReactFlow } from "@xyflow/react";
import { useCallback, useMemo, useState } from "react";
import { useOutletContext, useSearchParams } from "react-router-dom";

import { getGraph } from "../api";
import type { AnalysisContext } from "../components/AnalysisShell";
import { ConnectionNotice, isReconnecting } from "../components/ConnectionNotice";
import { FileList } from "../components/FileList";
import { GraphSkeleton } from "../components/GraphSkeleton";
import { FIT_OPTIONS, firstViewHub, GraphView } from "../components/GraphView";
import { NodePanel } from "../components/NodePanel";
import { applyCap, degrees, layoutGraph, RENDER_CAP } from "../graphModel";
import { parseLines, useSetParams, type LineRange } from "../links";
import { useMediaQuery } from "../useMediaQuery";

// State lives in the URL (spec §3.6): ?tests=1&guesses=1&view=list&node=<file id>&lines=12-15.
// The analysis header, tabs and Ask drawer come from AnalysisShell.
export function Explore() {
  return (
    <ReactFlowProvider>
      <ExploreInner />
    </ReactFlowProvider>
  );
}

function ExploreInner() {
  const { snapshotId } = useOutletContext<AnalysisContext>();
  const [params] = useSearchParams();
  const showTests = params.get("tests") === "1";
  const showGuesses = params.get("guesses") === "1";
  // Spec §10: under 768px the graph is not readable, so phones get the list only.
  const phone = useMediaQuery("(max-width: 767px)");
  const listView = phone || params.get("view") === "list";
  // Matches the CSS: the node panel overlays the canvas below 900px, and below 1600px while the
  // Ask drawer is open (three docked columns leave the canvas too narrow).
  const narrow = useMediaQuery("(max-width: 900px)");
  const askSqueeze = useMediaQuery("(max-width: 1599px)") && params.get("ask") === "1";
  const panelOverlay = narrow || askSqueeze;
  const selectedId = params.get("node") ? Number(params.get("node")) : null;
  const linesParam = params.get("lines");
  const highlight = useMemo(() => parseLines(linesParam), [linesParam]);
  const { fitView } = useReactFlow();

  const setParams = useSetParams();
  const setParam = useCallback(
    (key: string, value: string | null, replace = true) => setParams({ [key]: value }, replace),
    [setParams],
  );
  // Selecting a node is a navigation step (Back undoes it); toggles replace the entry. Lines
  // belong to the file they were cited in, so a new selection drops them.
  const select = useCallback(
    (fileId: number | null) =>
      setParams({ node: fileId === null ? null : String(fileId), lines: null }, false),
    [setParams],
  );
  const closePanel = useCallback(() => select(null), [select]);
  const showLines = useCallback(
    (lines: LineRange) => setParams({ lines: `${lines.start}-${lines.end}` }, false),
    [setParams],
  );
  const askAbout = useCallback(
    (path: string) => setParams({ ask: "1", askq: `About ${path}: ` }),
    [setParams],
  );

  const graph = useQuery({
    queryKey: ["graph", snapshotId, showTests, showGuesses],
    queryFn: ({ signal }) => getGraph(snapshotId, { showTests, showGuesses }, signal),
    placeholderData: keepPreviousData, // keep the old picture while a toggle refetches
    staleTime: Infinity,
  });

  const deg = useMemo(() => (graph.data ? degrees(graph.data) : new Map()), [graph.data]);
  const capped = useMemo(() => (graph.data ? applyCap(graph.data, deg) : null), [graph.data, deg]);
  // The layout is the slow part (dagre, main thread) and only the graph needs it.
  const positions = useMemo(
    () => (capped && !listView ? layoutGraph(capped.nodes, capped.edges) : new Map()),
    [capped, listView],
  );
  const shownIds = useMemo(() => new Set(capped?.nodes.map((n) => n.id) ?? []), [capped]);
  const allIds = useMemo(() => new Set(graph.data?.nodes.map((n) => n.id) ?? []), [graph.data]);
  const selected = graph.data?.nodes.find((n) => n.id === selectedId) ?? null;
  const isInGraph = useCallback((fileId: number) => allIds.has(fileId), [allIds]);
  // A big graph opens on its most connected file; say which one until the user picks a file
  // or presses Fit. A new picture (a toggle) opens fresh, so the note comes back with it.
  const hubId = useMemo(
    () => (capped ? firstViewHub(positions, capped.edges) : null),
    [capped, positions],
  );
  const hub = hubId === null ? null : (graph.data?.nodes.find((n) => n.id === hubId) ?? null);
  const [fittedAt, setFittedAt] = useState<number | null>(null);
  const showHubNote = hub !== null && selectedId === null && fittedAt !== graph.dataUpdatedAt;

  const reconnecting = isReconnecting(graph);
  const hardError = graph.error;

  return (
    <div className="explore">
      <div className="toolbar" role="toolbar" aria-label="Graph options">
        {reconnecting ? <ConnectionNotice /> : null}
        {phone ? (
          <p className="caption">The graph view needs a larger screen.</p>
        ) : (
          <div className="segmented" role="group" aria-label="View">
            <button type="button" aria-pressed={!listView} onClick={() => setParam("view", null)}>
              Graph
            </button>
            <button type="button" aria-pressed={listView} onClick={() => setParam("view", "list")}>
              List
            </button>
          </div>
        )}
        <label className="check">
          <input
            type="checkbox"
            checked={showTests}
            onChange={(e) => setParam("tests", e.target.checked ? "1" : null)}
          />
          Show test files
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={showGuesses}
            onChange={(e) => setParam("guesses", e.target.checked ? "1" : null)}
          />
          Show guessed calls
        </label>
        {!listView ? (
          <button
            type="button"
            className="button button-secondary button-small"
            onClick={() => {
              setFittedAt(graph.dataUpdatedAt);
              void fitView({ ...FIT_OPTIONS, duration: 200 });
            }}
          >
            Fit
          </button>
        ) : null}
        <p className="toolbar-note caption" aria-live="polite">
          {graph.isPlaceholderData ? "Updating…" : graphNote(graph.data, capped, listView)}
        </p>
      </div>

      {!listView && graph.data && graph.data.nodes.length > 0 ? (
        <Legend showGuesses={showGuesses} />
      ) : null}

      <div className="explore-body">
        <div className="canvas">
          {hardError && !graph.data ? (
            <div className="canvas-message" role="alert">
              <p>{hardError.message}</p>
              <button className="button button-secondary" onClick={() => graph.refetch()}>
                Try again
              </button>
            </div>
          ) : !graph.data || !capped ? (
            listView ? (
              <div className="canvas-message" aria-busy="true">
                <p className="caption">Loading files…</p>
              </div>
            ) : (
              <GraphSkeleton />
            )
          ) : graph.data.nodes.length === 0 ? (
            <div className="canvas-message">
              <p>No Python or JavaScript/TypeScript files to show.</p>
              {graph.data.hidden_files ? (
                <p className="caption">
                  {graph.data.hidden_files} test files are hidden. Turn on “Show test files” to
                  see them.
                </p>
              ) : null}
            </div>
          ) : listView ? (
            <FileList nodes={graph.data.nodes} deg={deg} selectedId={selectedId} onSelect={select} />
          ) : (
            <>
              <GraphView
                key={graph.dataUpdatedAt} // new data (a toggle) remounts, so it opens fitted
                nodes={capped.nodes}
                edges={capped.edges}
                positions={positions}
                selectedId={selectedId}
                panelOverlay={panelOverlay}
                onSelect={select}
              />
              {selectedId !== null && selected && !shownIds.has(selectedId) ? (
                <p className="canvas-hint caption">
                  {selected.path} is outside the {RENDER_CAP} files drawn. It is in List view.
                </p>
              ) : showHubNote ? (
                <p className="canvas-hint caption">
                  Opened on <span className="mono">{hub.path}</span>, the most connected file, and
                  its neighbours. Fit shows all files.
                </p>
              ) : null}
            </>
          )}
        </div>

        {selected ? (
          <NodePanel
            snapshotId={snapshotId}
            node={selected}
            minConfidence={showGuesses ? 0.5 : 0.9}
            highlight={highlight}
            isInGraph={isInGraph}
            onSelectFile={select}
            onShowLines={showLines}
            onAsk={askAbout}
            onClose={closePanel}
          />
        ) : null}
      </div>
    </div>
  );
}

function graphNote(
  data: { nodes: unknown[]; hidden_files: number } | undefined,
  capped: { total: number; capped: boolean; nodes: unknown[] } | null,
  listView: boolean,
): string {
  if (!data || !capped) return "";
  const parts = [];
  if (!listView && capped.capped) {
    parts.push(
      `Showing ${capped.nodes.length} of ${capped.total} files, the most connected. List view shows all.`,
    );
  } else {
    parts.push(`${data.nodes.length} files`);
  }
  if (data.hidden_files) parts.push(`${data.hidden_files} test files hidden`);
  return parts.join(" · ");
}

function Legend({ showGuesses }: { showGuesses: boolean }) {
  return (
    <div className="legend" aria-label="Legend">
      <div className="legend-row">
        <svg width="28" height="8" aria-hidden="true">
          <line x1="0" y1="4" x2="28" y2="4" className="legend-line" />
        </svg>
        Import or call (arrow points to the file used)
      </div>
      <div className="legend-row" data-muted={!showGuesses || undefined}>
        <svg width="28" height="8" aria-hidden="true">
          <line x1="0" y1="4" x2="28" y2="4" className="legend-line" strokeDasharray="5 4" />
        </svg>
        <span>
          Dashed: a best guess. Dynamic code makes some calls hard to resolve.
          {showGuesses ? null : " Hidden; turn on “Show guessed calls”."}
        </span>
      </div>
    </div>
  );
}
