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
import { ALL_EDGES_SHOWN_TITLE, ExploreLegend, SHOW_ALL_EDGES_TITLE, ShowGroup } from "../components/ExploreLegend";
import { MapHint } from "../components/MapHint";
import { MapView } from "../components/MapView";
import { NodePanel } from "../components/NodePanel";
import { applyCap, degrees, layoutGraph, RENDER_CAP } from "../graphModel";
import { densityText, statusText } from "../legendText";
import { useDocumentTitle } from "../documentTitle";
import { parseLines, useSetParams, type LineRange } from "../links";
import { layoutMap } from "../mapLayout";
import {
  edgeBudgetFor,
  restingEdges,
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
import { useDelayedFlag } from "../useDelayedFlag";
import { useMediaQuery } from "../useMediaQuery";
import { Icon } from "../components/Icon";

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
  // Matches the CSS: the node panel overlays the canvas below 901px. Between 901 and 1599px with
  // Ask open it shares Ask's column as a tab (AnalysisShell), so the canvas keeps its width.
  const panelOverlay = useMediaQuery("(max-width: 900px)");
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
  const [zoomedIn, setZoomedIn] = useState(false);
  const showHubNote = hub !== null && selectedId === null && fittedAt !== graph.dataUpdatedAt;

  // --- the map ---
  const selection = useMemo(
    () => (view ? selectEdges(view.edges, edgeBudgetFor(view.nodes.length)) : null),
    [view],
  );
  // Arranged for the edges that are drawn at rest, so what is on screen is what is untangled;
  // hovering a node draws more on top of that arrangement without moving anything.
  const mapPositions = useMemo(
    () =>
      view && selection
        ? layoutMap(view.level, view.nodes, [...restingEdges(view.edges, selection, showAllEdges)])
        : new Map(),
    [view, selection, showAllEdges],
  );

  const reconnecting = isReconnecting(graph) || (!listView && !flatMode && isReconnecting(map));
  const hardError = listView || flatMode ? graph.error : (map.error ?? graph.error);
  const hasData = listView || flatMode ? Boolean(graph.data) : Boolean(view);
  const updating = graph.isPlaceholderData || (!listView && !flatMode && map.isPlaceholderData);
  const repo = status ? (repoName(status.url).split("/").pop() ?? "") : "";
  // Where you are: the file of a function view, the folder of a map view, the selected file.
  const place = listView ? "List" : request?.level === "flat" ? "Flat" : request?.root || null;
  useDocumentTitle([selected?.path ?? place, "Explorer", status ? repoName(status.url) : null]);
  const mapMode = !listView && !flatMode;
  // The old picture stays while the next one loads (keepPreviousData). Say so on the canvas itself
  // after 200ms (a fast load shows nothing), dim it and stop clicks on it, and show where you are
  // going in the breadcrumbs at once.
  const pendingRoot = mapMode && view && request && map.isPlaceholderData && request.root !== view.root
    ? request.root
    : null;
  const pending = useDelayedFlag(updating);
  const legendStatus = statusText(selection ? densityText(selection, showAllEdges) : null, zoomedIn);
  const canShowAll = showAllEdges || (selection !== null && selection.mode !== "all");

  return (
    <div className="explore">
      {mapMode && !phone ? (
        view && pendingRoot === null ? (
          <div className="crumb-row">
            <Breadcrumbs view={view} repo={repo} search={location.search} />
            <p className="crumb-facts caption" aria-live="polite">
              {updating ? "Updating…" : mapNote(view)}
            </p>
          </div>
        ) : (
          <CrumbSkeleton root={pendingRoot ?? urlView.root} repo={view ? repo : undefined} />
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
        <ShowGroup>
          <label className="check" title="Tests, and example code under examples/">
            <input
              type="checkbox"
              checked={showTests}
              onChange={(e) => setParam("tests", e.target.checked ? "1" : null)}
            />
            Tests &amp; examples
          </label>
          <label className="check" title="Calls matched by name only">
            <input
              type="checkbox"
              checked={showGuesses}
              onChange={(e) => setParam("guesses", e.target.checked ? "1" : null)}
            />
            Guessed calls
          </label>
          {mapMode ? (
            // Always there, so the toolbar never changes shape when the view arrives; it is only
            // available when the map leaves edges out, and says so when it is not.
            <label
              className="check"
              title={canShowAll ? SHOW_ALL_EDGES_TITLE : ALL_EDGES_SHOWN_TITLE}
              data-disabled={!canShowAll || undefined}
            >
              <input
                type="checkbox"
                checked={showAllEdges}
                disabled={!canShowAll}
                aria-describedby={canShowAll ? undefined : "all-edges-hint"}
                onChange={(e) => setParam("edges", e.target.checked ? "all" : null)}
              />
              All edges
              {canShowAll ? null : (
                <span id="all-edges-hint" className="visually-hidden">
                  {ALL_EDGES_SHOWN_TITLE}
                </span>
              )}
            </label>
          ) : null}
        </ShowGroup>
        {listView ? (
          <p className="toolbar-note caption" aria-live="polite">
            {updating ? (
              "Updating…"
            ) : graph.data ? (
              graphNote(graph.data, capped, listView)
            ) : (
              <span className="skeleton toolbar-note-skeleton" aria-hidden="true" />
            )}
          </p>
        ) : null}
      </div>

      {mapMode && (!view || view.nodes.length > 0) ? (
        <ExploreLegend
          kind="map"
          showGuesses={showGuesses}
          cycle={view ? viewHasCycle(view) : false}
          status={view ? legendStatus : null}
        />
      ) : flatMode && (!graph.data || graph.data.nodes.length > 0) ? (
        <ExploreLegend
          kind="flat"
          showGuesses={showGuesses}
          facts={
            updating ? "Updating…" : graph.data ? graphNote(graph.data, capped, false) : <FactsSkeleton />
          }
        />
      ) : null}

      <div className="explore-body">
        <div className="canvas" data-pending={pending || undefined}>
          {pending && hasData ? (
            <p className="canvas-pending" role="status">
              <Icon name="spinner" size={14} />
              {pendingRoot !== null ? (
                <span>
                  Opening <span className="mono">{pendingRoot || repo}</span>…
                </span>
              ) : (
                <span>Updating…</span>
              )}
            </p>
          ) : null}
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
                  onZoomedIn={setZoomedIn}
                />
                <MapHint />
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

function FactsSkeleton() {
  return <span className="skeleton toolbar-note-skeleton" aria-hidden="true" />;
}
