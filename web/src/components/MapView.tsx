import "@xyflow/react/dist/style.css";

import {
  BaseEdge,
  type Edge,
  type EdgeProps,
  EdgeLabelRenderer,
  getBezierPath,
  Handle,
  MarkerType,
  type Node,
  type NodeProps,
  Position,
  ReactFlow,
  useReactFlow,
} from "@xyflow/react";
import { memo, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import type { MapNode, MapView as MapViewData } from "../api";
import { languageLabel, splitPath } from "../graphModel";
import { findingsHref } from "../links";
import { MAP_NODE_WIDTH, mapNodeHeight, type MapPosition } from "../mapLayout";
import {
  boundaryText,
  boundaryTitle,
  drawnEdges,
  edgeSplit,
  edgeWidth,
  type EdgeSelection,
  isCycleEdge,
  isDashed,
  type NodeAction,
  nodeAction,
  plural,
  showEdgeLabel,
} from "../mapModel";
import { FIT_OPTIONS } from "./GraphView";
import { Icon } from "./Icon";

type MapNodeData = {
  node: MapNode;
  level: MapViewData["level"];
  snapshotId: number;
  hideTests: boolean;
  selected: boolean;
  dimmed: boolean;
};
type MapFlowNode = Node<MapNodeData, "map">;

type MapEdgeData = {
  dashed: boolean;
  cycle: boolean;
  width: number;
  title: string;
  label: string | null;
  active: boolean;
  dimmed: boolean;
  lane: number; // a two-way pair runs as two parallel lines, this far from the centre
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
  const { node, level, selected, dimmed } = data;
  const boundary = boundaryText(node);
  const common = {
    "data-kind": node.kind,
    "data-selected": selected || undefined,
    "data-dimmed": dimmed || undefined,
    "data-cycle": node.in_cycle === true || undefined,
    style: { width: MAP_NODE_WIDTH, height: mapNodeHeight(level) },
  };
  let head;
  let title = node.path;
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
    title = `${node.path} · ${languageLabel(node.language ?? "")}`;
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
    title = opens ? `${node.label}: open them in List view` : `${node.label}: not drawn`;
    head = (
      <span className="map-node-text">
        <span className="map-node-name">+ {node.label}</span>
        <span className="map-node-hint">{opens ? "open in List view →" : "not drawn"}</span>
      </span>
    );
  } else {
    const own = node.own !== false;
    title = `${node.qualified_name ?? node.label} · ${node.path}`;
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
      {boundary && level !== "symbol" ? (
        <div className="map-node-boundary" title={boundaryTitle(node)}>
          {boundary}
        </div>
      ) : null}
      <Handle id="out-r" type="source" position={Position.Right} isConnectable={false} className="graph-handle" />
      <Handle id="in-r" type="target" position={Position.Right} isConnectable={false} className="graph-handle" />
    </div>
  );
});

function DepEdge(props: EdgeProps<MapFlowEdge>) {
  const { sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, markerEnd, data } = props;
  const lane = data?.lane ?? 0;
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY: sourceY + lane,
    targetX,
    targetY: targetY + lane,
    sourcePosition,
    targetPosition,
  });
  return (
    <>
      <g
        className="graph-edge"
        data-active={data?.active || undefined}
        data-dimmed={data?.dimmed || undefined}
        data-cycle={data?.cycle || undefined}
      >
        <title>{data?.title}</title>
        <BaseEdge
          path={path}
          markerEnd={markerEnd}
          style={{
            strokeDasharray: data?.dashed ? "5 4" : undefined,
            strokeWidth: (data?.width ?? 1.25) + (data?.active ? 0.5 : 0),
          }}
        />
      </g>
      {data?.label ? (
        <EdgeLabelRenderer>
          <div
            className="edge-label mono num"
            data-active={data.active || undefined}
            data-dimmed={data.dimmed || undefined}
            data-cycle={data.cycle || undefined}
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY + lane}px)`,
            }}
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

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
}) {
  const { getViewport, setCenter } = useReactFlow();
  const height = mapNodeHeight(view.level);
  const nodesById = useMemo(() => new Map(view.nodes.map((n) => [n.id, n])), [view.nodes]);
  const selectedNodeId = useMemo(
    () =>
      selectedFileId === null
        ? null
        : (view.nodes.find((n) => n.kind === "file" && n.file_id === selectedFileId)?.id ?? null),
    [view.nodes, selectedFileId],
  );

  // Hover and keyboard focus show every edge of a node, like a selection does.
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const focusId = hoverId ?? focusedId ?? selectedNodeId;

  const drawn = useMemo(
    () => drawnEdges(view.edges, selection, focusId, showAll),
    [view.edges, selection, focusId, showAll],
  );
  // The picture is dimmed around the focused node using every edge, drawn or not.
  const neighbourhood = useMemo(() => {
    if (focusId === null) return null;
    const ids = new Set([focusId]);
    for (const e of view.edges) {
      if (e.source === focusId) ids.add(e.target);
      if (e.target === focusId) ids.add(e.source);
    }
    return ids;
  }, [view.edges, focusId]);

  // Centre a selected file in the part of the canvas the panel leaves free.
  const [fitOnMount] = useState(selectedNodeId === null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
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
      const shift = covered > 0 && visibleWidth > MAP_NODE_WIDTH * zoom ? covered / 2 / zoom : 0;
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      void setCenter(p.x + MAP_NODE_WIDTH / 2 + shift, p.y + height / 2, {
        zoom,
        duration: reduced ? 0 : 200,
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [selectedNodeId, positions, ready, canvasSize, panelOverlay, height, getViewport, setCenter]);

  const flowNodes = useMemo<MapFlowNode[]>(
    () =>
      view.nodes.map((n) => {
        const p = positions.get(n.id);
        return {
          id: n.id,
          type: "map",
          position: { x: p?.x ?? 0, y: p?.y ?? 0 },
          data: {
            node: n,
            level: view.level,
            snapshotId,
            hideTests,
            selected: n.id === selectedNodeId,
            dimmed: neighbourhood !== null && !neighbourhood.has(n.id),
          },
          draggable: false,
          connectable: false,
          ariaLabel: n.kind === "more" ? n.label : n.path || n.label,
        };
      }),
    [view.nodes, view.level, positions, snapshotId, hideTests, selectedNodeId, neighbourhood],
  );

  const flowEdges = useMemo<MapFlowEdge[]>(() => {
    const reverse = new Set(drawn.map((e) => `${e.target}>${e.source}`));
    return drawn.map((e) => {
      const active = focusId !== null && (e.source === focusId || e.target === focusId);
      const cycle = isCycleEdge(e);
      const dashed = isDashed(e);
      const symbolEdge = e.type !== undefined;
      const split = edgeSplit(e);
      const notes = [
        `${labelOf(nodesById, e.source)} → ${labelOf(nodesById, e.target)}: ${split}`,
        cycle ? "Part of a circular import (top-level imports only)." : null,
        dashed && !symbolEdge
          ? "Drawn dashed: mostly best guesses, because dynamic code makes some calls hard to resolve."
          : null,
      ].filter(Boolean);
      const color = active || cycle ? "var(--text)" : "var(--edge)";
      return {
        id: `${e.source}>${e.target}${e.type ? `:${e.type}` : ""}`,
        source: e.source,
        target: e.target,
        type: "dep",
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color },
        data: {
          dashed,
          cycle,
          width: symbolEdge ? 1.25 : edgeWidth(e.count),
          title: notes.join("\n"),
          label: showEdgeLabel(e.count, drawn.length, active)
            ? symbolEdge
              ? active
                ? split
                : null
              : String(e.count)
            : null,
          active,
          dimmed: focusId !== null && !active,
          lane: reverse.has(`${e.source}>${e.target}`) ? (e.source < e.target ? -10 : 10) : 0,
        },
        ...handlesFor(positions.get(e.source), positions.get(e.target)),
        focusable: false,
      };
    });
  }, [drawn, focusId, nodesById, positions]);

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
      onFocus={(e) => {
        const el = (e.target as HTMLElement).closest<HTMLElement>(".react-flow__node");
        setFocusedId(el?.dataset.id ?? null);
      }}
      onBlur={() => setFocusedId(null)}
    >
      <ReactFlow<MapFlowNode, MapFlowEdge>
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeClick={(_, node) => {
          const n = nodesById.get(node.id);
          if (n) onAction(nodeAction(view.level, n));
        }}
        onNodeMouseEnter={(_, node) => setHoverId(node.id)}
        onNodeMouseLeave={() => setHoverId(null)}
        onPaneClick={onClear}
        fitView={fitOnMount}
        fitViewOptions={FIT_OPTIONS}
        onInit={() => setReady(true)}
        minZoom={0.08}
        maxZoom={2}
        nodesConnectable={false}
        nodesDraggable={false}
        elementsSelectable={false}
        onlyRenderVisibleElements
      />
    </div>
  );
}

/** Forward edges go right side -> left side; edges that point back (to an earlier layer) go
 * left side -> right side; two nodes in one layer, or not in the chain at all, connect on their
 * right sides. */
function handlesFor(
  from: MapPosition | undefined,
  to: MapPosition | undefined,
): { sourceHandle: string; targetHandle: string } {
  if (!from || !to) return { sourceHandle: "out-r", targetHandle: "in-l" };
  if (from.rank === to.rank) return { sourceHandle: "out-r", targetHandle: "in-r" };
  return from.rank < to.rank
    ? { sourceHandle: "out-r", targetHandle: "in-l" }
    : { sourceHandle: "out-l", targetHandle: "in-r" };
}

function labelOf(nodes: Map<string, MapNode>, id: string): string {
  const n = nodes.get(id);
  return n ? (n.kind === "more" ? n.label : n.label || n.path) : id;
}
