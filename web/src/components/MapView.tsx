import "@xyflow/react/dist/style.css";

import {
  BaseEdge,
  type Edge,
  type EdgeMouseHandler,
  type EdgeProps,
  EdgeLabelRenderer,
  getBezierPath,
  Handle,
  type Node,
  type NodeMouseHandler,
  type NodeProps,
  Position,
  ReactFlow,
  useReactFlow,
} from "@xyflow/react";
import {
  createContext,
  memo,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { Link } from "react-router-dom";

import type { MapNode, MapView as MapViewData } from "../api";
import { splitPath } from "../graphModel";
import {
  createFocusStore,
  EDGE_ACTIVE,
  EDGE_VISIBLE,
  type FocusStore,
  NODE_NEAR,
  NODE_SELECTED,
} from "../focusStore";
import { scheduleWarmUp } from "../codeColours";
import { findingsHref } from "../links";
import { createHoverIntent } from "../hoverIntent";
import {
  edgeHandles,
  initialViewport,
  mapNodeHeight,
  mapNodeWidth,
  type MapPosition,
  READABLE_MIN_ZOOM,
} from "../mapLayout";
import {
  boundaryText,
  boundaryTitle,
  edgeKey,
  edgeSites,
  edgeSplit,
  edgeWidth,
  type EdgeSelection,
  isCycleEdge,
  isDashed,
  type NodeAction,
  nodeAction,
  nodeTooltip,
  plural,
  restingEdges,
  showEdgeLabel,
} from "../mapModel";
import { Icon } from "./Icon";

// Hover, keyboard focus and selection live in a store, not in the node and edge objects: React
// Flow treats a new node object as a new node and hides it until it is measured again, which
// blanked the whole canvas on every hover. The objects below never change with focus; each node
// and edge subscribes to a number about itself (so a hover re-renders a handful of them, not the
// canvas) and the dimming of everything else is one attribute on the container.
const StoreContext = createContext<FocusStore>(createFocusStore());

// The edge tooltip is ours (a native <title> shows late, and only over the thin line): it follows
// the pointer over an edge, its wide invisible hit zone, and its count label.
interface Tip {
  show(clientX: number, clientY: number, text: string): void;
  hide(): void;
}
const TipContext = createContext<Tip>({ show: () => undefined, hide: () => undefined });

type MapNodeData = {
  node: MapNode;
  level: MapViewData["level"];
  snapshotId: number;
  hideTests: boolean;
  /** Connections of this node that are not drawn at rest (hover shows them). */
  hiddenEdges: number;
};
type MapFlowNode = Node<MapNodeData, "map">;

type MapEdgeData = {
  source: string;
  target: string;
  rest: boolean; // drawn when nothing is focused
  dashed: boolean;
  cycle: boolean;
  width: number;
  title: string;
  restLabel: string | null; // the count, when labels are on at rest
  activeLabel: string; // shown when one end is focused
  markerId: string;
  lane: number; // a two-way pair runs as two parallel lines, this far from the centre
  vertical: boolean; // the lane then shifts x, not y
};
type MapFlowEdge = Edge<MapEdgeData, "dep">;

const LANG_MARK: Record<string, string> = { python: "py", javascript: "js", typescript: "ts" };
const SYMBOL_MARK: Record<string, string> = { class: "cls", function: "fn", method: "fn", module: "mod" };

function Findings({
  node,
  data,
}: {
  node: MapNode;
  data: Pick<MapNodeData, "snapshotId" | "hideTests">;
}) {
  if (node.finding_count <= 0) return null;
  const text = plural(node.finding_count, "finding");
  // Symbols have no page of their own: their file's findings are one click away in the panel.
  if (node.kind === "more" || !node.path) return <span>{text}</span>;
  const isFolder = node.kind === "folder";
  return (
    <Link
      className="map-findings-link"
      to={findingsHref(data.snapshotId, { path: node.path, folder: isFolder, hideTests: data.hideTests })}
      onClick={(e) => e.stopPropagation()}
      title={`Open the ${text} under ${node.path} in Findings`}
    >
      {text}
    </Link>
  );
}

function Summary({ node, data }: { node: MapNode; data: MapNodeData }) {
  const files =
    node.kind === "folder" || node.kind === "more" ? plural(node.file_count ?? 0, "file") : null;
  const hasFindings = node.finding_count > 0;
  if (!files && !hasFindings) return null;
  return (
    <div className="map-node-sub">
      {files}
      {files && hasFindings ? " · " : null}
      <Findings node={node} data={data} />
    </div>
  );
}

function CycleTag({ node }: { node: MapNode }) {
  if (node.in_cycle !== true) return null;
  const inside =
    node.kind === "folder" && node.cycle_files
      ? `${plural(node.cycle_files, "file")} here take part in a circular import. Open the folder to see which.`
      : "Part of a circular import (top-level imports only).";
  return (
    <span className="map-cycle-tag" title={inside}>
      <Icon name="cycle" size={12} />
      circular
    </span>
  );
}

const MapNodeView = memo(function MapNodeView({ data }: NodeProps<MapFlowNode>) {
  const { node, level } = data;
  const store = useContext(StoreContext);
  const flags = useSyncExternalStore(store.subscribe, () => store.nodeFlags(node.id));
  const selected = (flags & NODE_SELECTED) !== 0;
  const near = (flags & NODE_NEAR) !== 0;
  const boundary = boundaryText(node);
  const common = {
    "data-kind": node.kind,
    "data-selected": selected || undefined,
    "data-near": near || undefined,
    "data-cycle": node.in_cycle === true || undefined,
    "data-level": level,
    style: { width: mapNodeWidth(level), height: mapNodeHeight(level) },
  };
  let head;
  const title = nodeTooltip(node, level);
  if (node.kind === "folder") {
    head = (
      <>
        <span className="map-node-icon" aria-hidden="true">
          <Icon name="folder" size={16} />
        </span>
        <span className="map-node-name">{node.label}</span>
      </>
    );
  } else if (node.kind === "file") {
    const [dir, name] = splitPath(node.label);
    head = (
      <>
        <span className="graph-node-lang" data-lang={node.language} aria-hidden="true">
          {LANG_MARK[node.language ?? ""] ?? "··"}
        </span>
        <span className="map-node-text">
          <span className="map-node-name">{name}</span>
          {dir ? (
            <span className="graph-node-dir" dir="rtl">
              <bdi>{dir.replace(/\/$/, "")}</bdi>
            </span>
          ) : null}
        </span>
      </>
    );
  } else if (node.kind === "more") {
    const opens = level !== "symbol";
    head = (
      <span className="map-node-text">
        <span className="map-node-name">+ {node.label}</span>
        <span className="map-node-hint">{opens ? "open in List view →" : "not drawn"}</span>
      </span>
    );
  } else {
    const own = node.own !== false;
    head = (
      <>
        <span className="graph-node-lang" data-symbol aria-hidden="true">
          {SYMBOL_MARK[node.kind] ?? "··"}
        </span>
        <span className="map-node-text">
          <span className="map-node-name">{node.label}</span>
          {!own ? (
            <span className="graph-node-dir" dir="rtl">
              <bdi>{node.path}</bdi>
            </span>
          ) : node.start_line != null ? (
            <span className="graph-node-dir">
              lines {node.start_line}–{node.end_line}
            </span>
          ) : null}
        </span>
      </>
    );
  }
  return (
    <div className="map-node" title={title} {...common}>
      {/* Edges leave from the right and arrive on the left; one that points back (to a node to
          its left) uses the other two, so it does not loop around the node. */}
      <Handle id="in-l" type="target" position={Position.Left} isConnectable={false} className="graph-handle" />
      <Handle id="out-l" type="source" position={Position.Left} isConnectable={false} className="graph-handle" />
      <div className="map-node-head">
        {head}
        <CycleTag node={node} />
      </div>
      {level === "symbol" ? (
        node.finding_count > 0 ? (
          <div className="map-node-sub">{plural(node.finding_count, "finding")}</div>
        ) : null
      ) : (
        <Summary node={node} data={data} />
      )}
      {data.hiddenEdges > 0 ? (
        <div
          className="map-node-hidden"
          title="These connections are not drawn until you hover this node, or turn on “All edges”."
        >
          {plural(data.hiddenEdges, "connection")} not drawn
        </div>
      ) : null}
      {boundary && level !== "symbol" ? (
        <div className="map-node-boundary" title={boundaryTitle(node)}>
          {boundary}
        </div>
      ) : null}
      <Handle id="in-t" type="target" position={Position.Top} isConnectable={false} className="graph-handle" />
      <Handle id="out-t" type="source" position={Position.Top} isConnectable={false} className="graph-handle" />
      <Handle id="in-b" type="target" position={Position.Bottom} isConnectable={false} className="graph-handle" />
      <Handle id="out-b" type="source" position={Position.Bottom} isConnectable={false} className="graph-handle" />
      <Handle id="out-r" type="source" position={Position.Right} isConnectable={false} className="graph-handle" />
      <Handle id="in-r" type="target" position={Position.Right} isConnectable={false} className="graph-handle" />
    </div>
  );
});

function DepEdge({
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<MapFlowEdge>) {
  const store = useContext(StoreContext);
  const tip = useContext(TipContext);
  const flags = useSyncExternalStore(store.subscribe, () =>
    data ? store.edgeFlags(data.source, data.target, data.rest) : 0,
  );
  if (!data || (flags & EDGE_VISIBLE) === 0) return null;
  const active = (flags & EDGE_ACTIVE) !== 0;
  const [path, labelX, labelY] = getBezierPath({
    sourceX: sourceX + (data.vertical ? data.lane : 0),
    sourceY: sourceY + (data.vertical ? 0 : data.lane),
    targetX: targetX + (data.vertical ? data.lane : 0),
    targetY: targetY + (data.vertical ? 0 : data.lane),
    sourcePosition,
    targetPosition,
  });
  const label = active ? data.activeLabel : data.rest ? data.restLabel : null;
  return (
    <>
      <g
        className="graph-edge"
        data-active={active || undefined}
        data-cycle={data.cycle || undefined}
      >
        {/* The arrowhead takes the edge's colour (currentColor), so focus never swaps markers. */}
        <defs>
          <marker
            id={data.markerId}
            viewBox="-10 -10 20 20"
            markerWidth={20}
            markerHeight={20}
            markerUnits="userSpaceOnUse" /* a fixed size: on a thick edge a scaled arrowhead was huge */
            orient="auto-start-reverse"
            refX={0}
            refY={0}
          >
            <polyline
              points="-5,-4 0,0 -5,4 -5,-4"
              fill="currentColor"
              stroke="currentColor"
              strokeWidth={1}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </marker>
        </defs>
        <title>{data.title}</title>
        <BaseEdge
          path={path}
          interactionWidth={EDGE_HIT_WIDTH}
          markerEnd={`url(#${data.markerId})`}
          style={{
            strokeDasharray: data.dashed ? "5 4" : undefined,
            strokeWidth: data.width + (active ? 0.5 : 0),
          }}
        />
      </g>
      {label ? (
        <EdgeLabelRenderer>
          <div
            className="edge-label mono num"
            data-active={active || undefined}
            data-cycle={data.cycle || undefined}
            onMouseEnter={(e) => tip.show(e.clientX, e.clientY, data.title)}
            onMouseMove={(e) => tip.show(e.clientX, e.clientY, data.title)}
            onMouseLeave={tip.hide}
            style={{
              transform: `translate(-50%, -50%) translate(${labelX + (data.vertical ? data.lane : 0)}px, ${labelY + (data.vertical ? 0 : data.lane)}px)`,
            }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

// A wide invisible zone around each edge line, so a 1-px line can be hit with a real mouse.
const EDGE_HIT_WIDTH = 18;

const nodeTypes = { map: MapNodeView };
const edgeTypes = { dep: DepEdge };

// Zoom used when centring a selected node: 12px names at 0.8 stay ~10px.
const READABLE_ZOOM = 0.8;

export function MapView({
  view,
  positions,
  selection,
  showAll,
  snapshotId,
  hideTests,
  selectedFileId,
  panelOverlay,
  onAction,
  onClear,
  onZoomedIn,
}: {
  view: MapViewData;
  positions: Map<string, MapPosition>;
  selection: EdgeSelection;
  showAll: boolean;
  snapshotId: number;
  hideTests: boolean;
  selectedFileId: number | null;
  panelOverlay: boolean; // the node panel covers the canvas instead of docking beside it
  onAction: (action: NodeAction) => void;
  onClear: () => void;
  /** True while the first view is zoomed in (not everything is on screen); the legend says so. */
  onZoomedIn: (zoomedIn: boolean) => void;
}) {
  const { getViewport, setCenter } = useReactFlow();
  const height = mapNodeHeight(view.level);
  const width = mapNodeWidth(view.level);
  const nodesById = useMemo(() => new Map(view.nodes.map((n) => [n.id, n])), [view.nodes]);
  const selectedNodeId = useMemo(
    () =>
      selectedFileId === null
        ? null
        : (view.nodes.find((n) => n.kind === "file" && n.file_id === selectedFileId)?.id ?? null),
    [view.nodes, selectedFileId],
  );

  // Hover and keyboard focus show every edge of a node, like a selection does. Hover waits a
  // moment, so sweeping across the map does not restyle it for every node it crosses.
  const store = useMemo(createFocusStore, []);
  const [tipState, setTipState] = useState<{ x: number; y: number; text: string } | null>(null);
  const tip = useMemo<Tip>(
    () => ({
      show(clientX, clientY, text) {
        const box = canvasRef.current?.getBoundingClientRect();
        if (!box) return;
        const x = Math.round(clientX - box.left);
        const y = Math.round(clientY - box.top);
        setTipState((old) =>
          old && old.text === text && Math.abs(old.x - x) < 4 && Math.abs(old.y - y) < 4
            ? old
            : { x, y, text },
        );
      },
      hide: () => setTipState(null),
    }),
    [],
  );
  useLayoutEffect(() => store.configure(view.edges, selectedNodeId), [store, view.edges, selectedNodeId]);
  const intent = useMemo(() => createHoverIntent(store.setHover), [store]);
  useEffect(() => () => intent.cancel(), [intent]);
  const onNodeMouseEnter = useCallback<NodeMouseHandler>((_, node) => intent.enter(node.id), [intent]);
  const onNodeMouseLeave = useCallback<NodeMouseHandler>(() => intent.leave(), [intent]);
  const focusing = useSyncExternalStore(store.subscribe, store.focusing);
  const onEdgeMouseMove = useCallback<EdgeMouseHandler<MapFlowEdge>>(
    (event, edge) => tip.show(event.clientX, event.clientY, edge.data?.title ?? ""),
    [tip],
  );

  // Centre a selected file in the part of the canvas the panel leaves free.
  // First view: everything when names stay readable, else the top left at a readable zoom.
  const [fitOnMount] = useState(selectedNodeId === null);
  const setZoomedIn = onZoomedIn;
  useEffect(() => () => onZoomedIn(false), [onZoomedIn]);
  const canvasRef = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  // Once the map has drawn, warm up code colours (Python) while the browser is idle (codeColours.ts).
  useEffect(() => (ready ? scheduleWarmUp() : undefined), [ready]);
  const [canvasSize, setCanvasSize] = useState("");
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const observer = new ResizeObserver(() =>
      setCanvasSize(`${canvas.clientWidth}x${canvas.clientHeight}`),
    );
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (selectedNodeId === null || !ready || !canvasSize) return;
    const p = positions.get(selectedNodeId);
    const canvas = canvasRef.current;
    if (!p || !canvas) return;
    const frame = requestAnimationFrame(() => {
      const zoom = Math.max(getViewport().zoom, READABLE_ZOOM);
      const covered = panelOverlay ? Math.min(480, canvas.clientWidth) : 0;
      const visibleWidth = canvas.clientWidth - covered;
      const shift = covered > 0 && visibleWidth > width * zoom ? covered / 2 / zoom : 0;
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      void setCenter(p.x + width / 2 + shift, p.y + height / 2, {
        zoom,
        duration: reduced ? 0 : 200,
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [selectedNodeId, positions, ready, canvasSize, panelOverlay, height, width, getViewport, setCenter]);

  // Built from the view only (and the "Show all edges" setting for edges): never from hover,
  // focus or selection, so React Flow keeps every node it has measured.
  const hiddenByNode = useMemo(() => {
    const rest = restingEdges(view.edges, selection, showAll);
    const counts = new Map<string, number>();
    for (const e of view.edges) {
      if (rest.has(e)) continue;
      counts.set(e.source, (counts.get(e.source) ?? 0) + 1);
      counts.set(e.target, (counts.get(e.target) ?? 0) + 1);
    }
    return counts;
  }, [view.edges, selection, showAll]);

  const flowNodes = useMemo<MapFlowNode[]>(
    () =>
      view.nodes.map((n) => {
        const p = positions.get(n.id);
        return {
          id: n.id,
          type: "map",
          position: { x: p?.x ?? 0, y: p?.y ?? 0 },
          data: { node: n, level: view.level, snapshotId, hideTests, hiddenEdges: hiddenByNode.get(n.id) ?? 0 },
          draggable: false,
          connectable: false,
          ariaLabel: n.kind === "more" ? n.label : n.path || n.label,
        };
      }),
    [view.nodes, view.level, positions, snapshotId, hideTests, hiddenByNode],
  );

  const flowEdges = useMemo<MapFlowEdge[]>(() => {
    const handles = (e: { source: string; target: string }) => {
      const h = edgeHandles(positions.get(e.source), positions.get(e.target), width);
      return { sourceHandle: h.sourceHandle, targetHandle: h.targetHandle };
    };
    const rest = restingEdges(view.edges, selection, showAll);
    const reverse = new Set(view.edges.map((e) => `${e.target}>${e.source}`));
    return view.edges.map((e, i) => {
      const cycle = isCycleEdge(e);
      const dashed = isDashed(e);
      const symbolEdge = e.type !== undefined;
      const split = edgeSplit(e);
      const notes = [
        `${labelOf(nodesById, e.source)} → ${labelOf(nodesById, e.target)}: ${split}`,
        edgeSites(e),
        cycle ? "Part of a circular import (top-level imports only)." : null,
        dashed && !symbolEdge
          ? "Drawn dashed: mostly best guesses, because dynamic code makes some calls hard to resolve."
          : null,
      ].filter(Boolean);
      const isRest = rest.has(e);
      return {
        id: edgeKey(e),
        source: e.source,
        target: e.target,
        type: "dep",
        data: {
          source: e.source,
          target: e.target,
          rest: isRest,
          dashed,
          cycle,
          width: symbolEdge ? 1.25 : edgeWidth(e.count),
          title: notes.join("\n"),
          restLabel: !symbolEdge && showEdgeLabel(e.count, rest.size, false) ? String(e.count) : null,
          activeLabel: symbolEdge ? split : String(e.count),
          markerId: `mk-${i}`,
          lane: reverse.has(`${e.source}>${e.target}`) ? (e.source < e.target ? -10 : 10) : 0,
          vertical: edgeHandles(positions.get(e.source), positions.get(e.target), width).vertical,
        },
        ...handles(e),
        focusable: false,
      };
    });
  }, [view.edges, selection, showAll, nodesById, positions, width]);

  return (
    // Nodes are focusable but not selectable (selection is the URL's ?node=), so React Flow does
    // not act on Enter or Space: do it here, like a click. A link inside a node keeps its own keys.
    <div
      ref={canvasRef}
      className="canvas-flow"
      onKeyDown={(e) => {
        if (e.key !== "Enter" && e.key !== " ") return;
        if ((e.target as HTMLElement).closest("a")) return;
        const el = (e.target as HTMLElement).closest<HTMLElement>(".react-flow__node");
        const node = el?.dataset.id ? nodesById.get(el.dataset.id) : undefined;
        if (!node) return;
        e.preventDefault();
        onAction(nodeAction(view.level, node));
      }}
      data-focus={focusing || undefined}
      onFocus={(e) => {
        const el = (e.target as HTMLElement).closest<HTMLElement>(".react-flow__node");
        store.setFocused(el?.dataset.id ?? null);
      }}
      onBlur={() => store.setFocused(null)}
    >
      <StoreContext.Provider value={store}>
      <TipContext.Provider value={tip}>
      <ReactFlow<MapFlowNode, MapFlowEdge>
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeClick={(_, node) => {
          const n = nodesById.get(node.id);
          if (n) onAction(nodeAction(view.level, n));
        }}
        onNodeMouseEnter={onNodeMouseEnter}
        onNodeMouseLeave={onNodeMouseLeave}
        // Edges ignore the pointer unless the canvas has an edge handler; these also drive the tooltip.
        onEdgeMouseEnter={onEdgeMouseMove}
        onEdgeMouseMove={onEdgeMouseMove}
        onEdgeMouseLeave={tip.hide}
        onPaneClick={onClear}
        onInit={(instance) => {
          const canvas = canvasRef.current;
          if (fitOnMount && canvas) {
            const vp = initialViewport(view.level, positions, {
              width: canvas.clientWidth,
              height: canvas.clientHeight,
            });
            void instance.setViewport({ x: vp.x, y: vp.y, zoom: vp.zoom }, { duration: 0 });
            setZoomedIn(vp.zoomedIn);
          }
          setReady(true);
        }}
        // A move the user made (a drag or the wheel) ends the "zoomed in" note; so does Fit,
        // which ends below the readable zoom.
        onMoveStart={(event) => event && setZoomedIn(false)}
        onMoveEnd={(_, viewport) => viewport.zoom < READABLE_MIN_ZOOM - 0.01 && setZoomedIn(false)}
        minZoom={0.08}
        maxZoom={2}
        nodesConnectable={false}
        nodesDraggable={false}
        elementsSelectable={false}
        onlyRenderVisibleElements
      />
      {tipState ? (
        <div
          className="map-tip"
          role="tooltip"
          style={{
            left: tipState.x + 14,
            top: tipState.y + 14,
            transform:
              canvasRef.current && tipState.x > canvasRef.current.clientWidth - 340
                ? "translateX(calc(-100% - 28px))"
                : undefined,
          }}
        >
          {tipState.text}
        </div>
      ) : null}
      </TipContext.Provider>
      </StoreContext.Provider>
    </div>
  );
}

function labelOf(nodes: Map<string, MapNode>, id: string): string {
  const n = nodes.get(id);
  return n ? (n.kind === "more" ? n.label : n.label || n.path) : id;
}
