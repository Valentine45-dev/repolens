import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ReactFlowProvider, useReactFlow } from "@xyflow/react";
import { useCallback, useMemo, useState } from "react";
import { useLocation, useOutletContext, useSearchParams } from "react-router-dom";

import { ApiError, getGraph, getMapView, type MapView as MapViewData, repoName } from "../api";
import type { AnalysisContext } from "../components/AnalysisShell";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { ConnectionNotice, isReconnecting } from "../components/ConnectionNotice";
import { FileList } from "../components/FileList";
import { CrumbSkeleton, GraphSkeleton, ListSkeleton } from "../components/GraphSkeleton";
import { FIT_OPTIONS, firstViewHub, GraphView } from "../components/GraphView";
import { Icon } from "../components/Icon";
import { MapView } from "../components/MapView";
import { NodePanel } from "../components/NodePanel";
import { applyCap, degrees, layoutGraph, RENDER_CAP } from "../graphModel";
import { parseLines, useSetParams, type LineRange } from "../links";
import { layoutMap } from "../mapLayout";
import {
  CYCLE_CAPTION,
  densityCaption,
  emptyViewMessage,
  isDrawn,
  isMapRequest,
  navigateChanges,
  type NodeAction,
  parentDir,
  parseViewParams,
  plural,
  resolveView,
  selectEdges,
  viewFolder,
  viewHasCycle,
  type ViewLevel,
  viewNote,
} from "../mapModel";
import { useMediaQuery } from "../useMediaQuery";

// State lives in the URL (spec §3.6): ?level=folder|file|symbol|flat&root=<path>&tests=1&guesses=1
// &edges=all&view=list&node=<file id>&lines=12-15. The analysis header, tabs and Ask drawer come
// from AnalysisShell.
export function Explore() {
  return (
    <ReactFlowProvider>
      <ExploreInner />
    </ReactFlowProvider>
  );
}

function ExploreInner() {
  const { snapshotId, status } = useOutletContext<AnalysisContext>();
  const ready = status !== undefined; // no data is asked for before the analysis is known to be done
  const [params] = useSearchParams();
  const location = useLocation();
  const showTests = params.get("tests") === "1";
  const showGuesses = params.get("guesses") === "1";
  const showAllEdges = params.get("edges") === "all";
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
  const urlView = useMemo(() => parseViewParams(params), [params]);
  const { fitView } = useReactFlow();

  const setParams = useSetParams();
  const setParam = useCallback(
    (key: string, value: string | null, replace = true) => setParams({ [key]: value }, replace),
    [setParams],
  );

  // The flat file graph stays the index of every file: the node panel, the List view, citation
  // chips and the start rule all read it. (A folder view only has the files it draws.)
  const graph = useQuery({
    queryKey: ["graph", snapshotId, showTests, showGuesses],
    queryFn: ({ signal }) => getGraph(snapshotId, { showTests, showGuesses }, signal),
    enabled: ready,
    placeholderData: keepPreviousData, // keep the old picture while a toggle refetches
    staleTime: Infinity,
  });
  const deg = useMemo(() => (graph.data ? degrees(graph.data) : new Map()), [graph.data]);
  const allIds = useMemo(() => new Set(graph.data?.nodes.map((n) => n.id) ?? []), [graph.data]);
  const selected = graph.data?.nodes.find((n) => n.id === selectedId) ?? null;
  const isInGraph = useCallback((fileId: number) => allIds.has(fileId), [allIds]);

  // Which view: the URL wins; with no level and no root the start rule picks files for a small
  // repo and folders for a big one; a link to a file opens that file's folder.
  const request = useMemo(
    () => resolveView({ ...urlView, nodeId: selectedId }, graph.data ?? null),
    [urlView, selectedId, graph.data],
  );
  const flatMode = request?.level === "flat";
  const mapRequest = isMapRequest(request) ? request : null;
  const map = useQuery({
    queryKey: ["map", snapshotId, mapRequest, showTests, showGuesses],
    queryFn: ({ signal }) =>
      getMapView(snapshotId, { ...mapRequest!, showTests, showGuesses }, signal),
    enabled: ready && mapRequest !== null && !listView,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  });
  const view = !listView && !flatMode ? (map.data ?? null) : null;

  // Selecting is a navigation step (Back undoes it); toggles replace the entry. It pins the view
  // in the URL, so a link shared from here opens the same picture. Lines belong to the file
  // they were cited in, so a new selection drops them.
  const pin = useMemo<Record<string, string | null>>(
    () =>
      request
        ? { level: request.level as string, root: request.root || null }
        : ({} as Record<string, string | null>),
    [request],
  );
  const select = useCallback(
    (fileId: number | null, lines: LineRange | null = null) =>
      setParams(
        fileId === null
          ? { node: null, lines: null }
          : {
              node: String(fileId),
              lines: lines ? `${lines.start}-${lines.end}` : null,
              ...pin,
            },
        false,
      ),
    [setParams, pin],
  );
  const closePanel = useCallback(() => select(null), [select]);
  const showLines = useCallback(
    (lines: LineRange) => setParams({ lines: `${lines.start}-${lines.end}` }, false),
    [setParams],
  );
  const askAbout = useCallback(
    (fileId: number, path: string) =>
      setParams({ ask: "1", askq: `About ${path}: `, askfile: String(fileId), askpath: path }),
    [setParams],
  );
  const onAction = useCallback(
    (action: NodeAction) => {
      if (action.type === "open") setParams(navigateChanges(action.level, action.root), false);
      else if (action.type === "select") select(action.fileId, action.lines);
      else if (action.type === "list") {
        setParams({ view: "list", root: action.root, level: null, node: null, lines: null }, false);
      }
    },
    [setParams, select],
  );
  const showFunctions = useCallback(
    (path: string) => setParams({ level: "symbol", root: path }, false),
    [setParams],
  );
  // Folders / Files / Flat keep the selected file; they only change what is drawn.
  const setLevel = useCallback(
    (level: ViewLevel) => {
      const root = view ? viewFolder(view) : urlView.root;
      setParams({ level, root: level === "flat" || !root ? null : root }, false);
    },
    [setParams, view, urlView.root],
  );

  // --- the old flat picture (level=flat) ---
  const capped = useMemo(
    () => (flatMode && graph.data ? applyCap(graph.data, deg) : null),
    [flatMode, graph.data, deg],
  );
  const positions = useMemo(
    () => (capped && !listView ? layoutGraph(capped.nodes, capped.edges) : new Map()),
    [capped, listView],
  );
  const shownIds = useMemo(() => new Set(capped?.nodes.map((n) => n.id) ?? []), [capped]);
  // A big graph opens on its most connected file; say which one until the user picks a file or
  // presses Fit. A new picture (a toggle) opens fresh, so the note comes back with it.
  const hubId = useMemo(
    () => (capped ? firstViewHub(positions, capped.edges) : null),
    [capped, positions],
  );
  const hub = hubId === null ? null : (graph.data?.nodes.find((n) => n.id === hubId) ?? null);
  const [fittedAt, setFittedAt] = useState<number | null>(null);
  const showHubNote = hub !== null && selectedId === null && fittedAt !== graph.dataUpdatedAt;

  // --- the map ---
  const selection = useMemo(() => (view ? selectEdges(view.edges) : null), [view]);
  const mapPositions = useMemo(
    () => (view ? layoutMap(view.level, view.nodes, view.edges) : new Map()),
    [view],
  );

  const reconnecting = isReconnecting(graph) || (!listView && !flatMode && isReconnecting(map));
  const hardError = listView || flatMode ? graph.error : (map.error ?? graph.error);
  const hasData = listView || flatMode ? Boolean(graph.data) : Boolean(view);
  const updating = graph.isPlaceholderData || (!listView && !flatMode && map.isPlaceholderData);
  const repo = status ? (repoName(status.url).split("/").pop() ?? "") : "";
  const mapMode = !listView && !flatMode;
  const caption = selection ? densityCaption(selection, showAllEdges) : null;
  const canShowAll = showAllEdges || (selection !== null && selection.mode !== "all");

  return (
    <div className="explore">
      {mapMode && !phone ? (
        view ? (
          <div className="crumb-row">
            <Breadcrumbs view={view} repo={repo} search={location.search} />
          </div>
        ) : (
          <CrumbSkeleton root={urlView.root} />
        )
      ) : null}
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
        {!listView && !phone ? (
          <div className="segmented" role="group" aria-label="Level of detail">
            {(
              [
                ["folder", "Folders"],
                ["file", "Files"],
                ["flat", "Flat"],
              ] as const
            ).map(([level, label]) => (
              <button
                key={level}
                type="button"
                aria-pressed={request?.level === level}
                onClick={() => setLevel(level)}
                title={
                  level === "flat"
                    ? "Every file at once, the original graph"
                    : level === "folder"
                      ? "Folders first; click one to open it"
                      : "Every file under this folder"
                }
              >
                {label}
              </button>
            ))}
          </div>
        ) : null}
        <label className="check" title="Tests, and example code under examples/">
          <input
            type="checkbox"
            checked={showTests}
            onChange={(e) => setParam("tests", e.target.checked ? "1" : null)}
          />
          Show tests &amp; examples
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={showGuesses}
            onChange={(e) => setParam("guesses", e.target.checked ? "1" : null)}
          />
          Show guessed calls
        </label>
        {mapMode ? (
          // Always there, so the toolbar never changes shape when the view arrives; it is only
          // available when the map leaves edges out.
          <label className="check" title="Draw every connection, not only the strongest" data-disabled={!canShowAll || undefined}>
            <input
              type="checkbox"
              checked={showAllEdges}
              disabled={!canShowAll}
              onChange={(e) => setParam("edges", e.target.checked ? "all" : null)}
            />
            Show all edges
          </label>
        ) : null}
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
          {updating ? (
            "Updating…"
          ) : listView || flatMode ? (
            graph.data ? (
              graphNote(graph.data, capped, listView)
            ) : (
              <span className="skeleton toolbar-note-skeleton" aria-hidden="true" />
            )
          ) : view ? (
            mapNote(view)
          ) : (
            <span className="skeleton toolbar-note-skeleton" aria-hidden="true" />
          )}
        </p>
      </div>

      {mapMode && (!view || view.nodes.length > 0) ? (
        <MapLegend
          showGuesses={showGuesses}
          cycle={view ? viewHasCycle(view) : false}
          caption={caption}
        />
      ) : flatMode && (!graph.data || graph.data.nodes.length > 0) ? (
        <Legend showGuesses={showGuesses} />
      ) : null}

      <div className="explore-body">
        <div className="canvas">
          {hardError && !hasData ? (
            <div className="canvas-message" role="alert">
              <p>{hardError.message}</p>
              {hardError instanceof ApiError && hardError.status === 404 ? (
                // A shared link to a folder that is not in this analysis.
                <button
                  className="button button-secondary"
                  onClick={() => setParams({ level: null, root: null, node: null, lines: null })}
                >
                  Open the repo root
                </button>
              ) : (
                <button
                  className="button button-secondary"
                  onClick={() => (listView || flatMode ? graph.refetch() : map.refetch())}
                >
                  Try again
                </button>
              )}
            </div>
          ) : !hasData ? (
            listView ? (
              <ListSkeleton />
            ) : (
              <GraphSkeleton />
            )
          ) : listView ? (
            graph.data && graph.data.nodes.length > 0 ? (
              <FileList
                nodes={graph.data.nodes}
                deg={deg}
                selectedId={selectedId}
                onSelect={select}
                root={urlView.root}
                onClearRoot={() => setParam("root", null)}
              />
            ) : (
              <EmptyFiles hidden={graph.data?.hidden_files ?? 0} />
            )
          ) : flatMode && graph.data && capped ? (
            graph.data.nodes.length === 0 ? (
              <EmptyFiles hidden={graph.data.hidden_files} />
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
                ) : showHubNote && hub ? (
                  <p className="canvas-hint caption">
                    Opened on <span className="mono">{hub.path}</span>, the most connected file, and
                    its neighbours. Fit shows all files.
                  </p>
                ) : null}
              </>
            )
          ) : view && selection ? (
            view.nodes.length === 0 ? (
              <EmptyView
                message={emptyViewMessage(view)}
                onShowTests={() => setParam("tests", "1")}
              />
            ) : (
              <>
                <MapView
                  key={`${view.level}:${view.root}:${showTests}:${showGuesses}`}
                  view={view}
                  positions={mapPositions}
                  selection={selection}
                  showAll={showAllEdges}
                  snapshotId={snapshotId}
                  hideTests={!showTests}
                  selectedFileId={selectedId}
                  panelOverlay={panelOverlay}
                  onAction={onAction}
                  onClear={closePanel}
                />
                {selected && !isDrawn(view, selected.path) ? (
                  <p className="canvas-hint caption">
                    <span className="mono">{selected.path}</span> is not drawn in this view.{" "}
                    <button
                      type="button"
                      className="link-button"
                      onClick={() =>
                        setParams({ level: "folder", root: parentDir(selected.path) || null }, false)
                      }
                    >
                      Show its folder
                    </button>
                  </p>
                ) : null}
              </>
            )
          ) : null}
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
            onShowFunctions={
              request?.level === "symbol" && request.root === selected.path ? undefined : showFunctions
            }
            onClose={closePanel}
          />
        ) : null}
      </div>
    </div>
  );
}

function mapNote(view: MapViewData): string {
  const parts = [viewNote(view)];
  if (view.other_findings) {
    parts.push(`${plural(view.other_findings, "finding")} in files that are not code`);
  }
  return parts.filter(Boolean).join(" · ");
}

function graphNote(
  data: { nodes: unknown[]; hidden_files: number } | undefined,
  capped: { total: number; capped: boolean; nodes: unknown[] } | null,
  listView: boolean,
): string {
  if (!data) return "";
  const parts = [];
  if (!listView && capped?.capped) {
    parts.push(
      `Showing ${capped.nodes.length} of ${capped.total} files, the most connected. List view shows all.`,
    );
  } else {
    parts.push(`${data.nodes.length} files`);
  }
  if (data.hidden_files) parts.push(`${data.hidden_files} test or example files hidden`);
  return parts.join(" · ");
}

function EmptyFiles({ hidden }: { hidden: number }) {
  return (
    <div className="canvas-message">
      <p>No Python or JavaScript/TypeScript files to show.</p>
      {hidden ? (
        <p className="caption">
          {hidden} test or example files are hidden. Turn on “Show tests &amp; examples” to see them.
        </p>
      ) : null}
    </div>
  );
}

function EmptyView({
  message,
  onShowTests,
}: {
  message: { text: string; hiddenFiles: number };
  onShowTests: () => void;
}) {
  return (
    <div className="canvas-message">
      <p>{message.text}</p>
      {message.hiddenFiles > 0 ? (
        <button type="button" className="button button-secondary" onClick={onShowTests}>
          Show tests &amp; examples
        </button>
      ) : null}
    </div>
  );
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

function MapLegend({
  showGuesses,
  cycle,
  caption,
}: {
  showGuesses: boolean;
  cycle: boolean;
  caption: string | null;
}) {
  return (
    <div className="legend" aria-label="Legend">
      <div className="legend-row">
        <svg width="28" height="8" aria-hidden="true">
          <line x1="0" y1="4" x2="28" y2="4" className="legend-line" />
        </svg>
        Import or call. The number counts connections; thicker means more.
      </div>
      <div className="legend-row" data-muted={!showGuesses || undefined}>
        <svg width="28" height="8" aria-hidden="true">
          <line x1="0" y1="4" x2="28" y2="4" className="legend-line" strokeDasharray="5 4" />
        </svg>
        <span>
          Dashed: mostly best guesses. Dynamic code makes some calls hard to resolve.
          {showGuesses ? null : " Hidden; turn on “Show guessed calls”."}
        </span>
      </div>
      {/* One row that is always there (it holds nothing for a small graph), so a caption arriving
          with the data never pushes the map down. */}
      <p className="legend-note">
        {cycle ? (
          <span className="legend-cycle">
            <Icon name="cycle" size={14} />
            {CYCLE_CAPTION}
          </span>
        ) : null}
        {cycle && caption ? " · " : null}
        {caption}
      </p>
    </div>
  );
}
