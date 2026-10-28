import "@xyflow/react/dist/style.css";

import {
  BaseEdge,
  type Edge,
  type EdgeProps,
  type FitViewOptions,
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

import type { GraphEdge, GraphNode } from "../api";
import {
  isGuess,
  languageLabel,
  NODE_HEIGHT,
  NODE_WIDTH,
  type Positioned,
  splitPath,
} from "../graphModel";

type FileNodeData = {
  path: string;
  language: string;
  selected: boolean;
  dimmed: boolean;
};
type FileFlowNode = Node<FileNodeData, "file">;

type DepEdgeData = { guess: boolean; label: string; active: boolean; dimmed: boolean };
type DepFlowEdge = Edge<DepEdgeData, "dep">;

const LANG_MARK: Record<string, string> = { python: "py", javascript: "js", typescript: "ts" };

const FileNode = memo(function FileNode({ data }: NodeProps<FileFlowNode>) {
  const [dir, name] = splitPath(data.path);
  return (
    <div
      className="graph-node"
      data-lang={data.language}
      data-selected={data.selected || undefined}
      data-dimmed={data.dimmed || undefined}
      title={`${data.path} · ${languageLabel(data.language)}`}
    >
      <Handle type="target" position={Position.Left} isConnectable={false} className="graph-handle" />
      <span className="graph-node-lang" aria-hidden="true">
        {LANG_MARK[data.language] ?? "··"}
      </span>
      <span className="graph-node-text">
        <span className="graph-node-name">{name}</span>
        {dir ? (
          // rtl so a long path is cut at the start; <bdi> keeps the text itself in order
          <span className="graph-node-dir" dir="rtl">
            <bdi>{dir.replace(/\/$/, "")}</bdi>
          </span>
        ) : null}
      </span>
      <Handle type="source" position={Position.Right} isConnectable={false} className="graph-handle" />
    </div>
  );
});

function DepEdge(props: EdgeProps<DepFlowEdge>) {
  const { sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, markerEnd, data } =
    props;
  const [path] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
  return (
    <g className="graph-edge" data-active={data?.active || undefined} data-dimmed={data?.dimmed || undefined}>
      <title>{data?.label}</title>
      <BaseEdge
        path={path}
        markerEnd={markerEnd}
        style={{
          strokeDasharray: data?.guess ? "5 4" : undefined,
          strokeWidth: data?.active ? 1.75 : 1.25,
        }}
      />
    </g>
  );
}

// The Fit button: the whole graph.
export const FIT_OPTIONS: FitViewOptions = {
  padding: "24px",
  maxZoom: 1.1,
};

// Zoom used when centring a selected file: 12px names at 0.8 stay ~10px.
const READABLE_ZOOM = 0.8;
// First view: the whole graph when it fits at this zoom or closer (names still readable, ~7px
// at worst); a small repo like itsdangerous (~0.67) then opens whole instead of cropped. A
// bigger graph opens on its most connected file and that file's neighbours instead.
const WHOLE_GRAPH_ZOOM = 0.6;

function hubOf(edges: GraphEdge[]): number | null {
  const degree = new Map<number, number>();
  for (const e of edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }
  let hub: number | null = null;
  for (const [id, d] of degree) if (hub === null || d > degree.get(hub)!) hub = id;
  return hub;
}

function hubNeighbourhood(hub: number, edges: GraphEdge[]): { id: string }[] {
  const ids = new Set([hub]);
  for (const e of edges) {
    if (e.source === hub) ids.add(e.target);
    if (e.target === hub) ids.add(e.source);
  }
  return [...ids].map((id) => ({ id: String(id) }));
}

/** The file the first view opens on, or null when the whole graph is shown. Explore uses it to
 * say which file the view is centred on. */
export function firstViewHub(positions: Map<number, Positioned>, edges: GraphEdge[]): number | null {
  if (positions.size === 0) return null;
  const xs = [...positions.values()].map((p) => p.x);
  const ys = [...positions.values()].map((p) => p.y);
  const width = Math.max(...xs) - Math.min(...xs) + NODE_WIDTH + 48;
  const height = Math.max(...ys) - Math.min(...ys) + NODE_HEIGHT + 136;
  // The canvas fills the viewport below the header and toolbar (~150px).
  const wholeZoom = Math.min(window.innerWidth / width, (window.innerHeight - 150) / height);
  return wholeZoom >= WHOLE_GRAPH_ZOOM ? null : hubOf(edges);
}

const nodeTypes = { file: FileNode };
const edgeTypes = { dep: DepEdge };

function edgeLabel(e: GraphEdge): string {
  const parts = [];
  if (e.import) parts.push("imports");
  if (e.calls) parts.push(`${e.calls} call${e.calls === 1 ? "" : "s"}`);
  const text = parts.join(" + ");
  return isGuess(e)
    ? `${text} (best guess: dynamic code makes some calls hard to resolve)`
    : text;
}

export function GraphView({
  nodes,
  edges,
  positions,
  selectedId,
  panelOverlay,
  onSelect,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  positions: Map<number, Positioned>;
  selectedId: number | null;
  panelOverlay: boolean; // the node panel covers the canvas instead of docking beside it
  onSelect: (fileId: number | null) => void;
}) {
  const { getViewport, setCenter } = useReactFlow();
  const initialFit = useMemo<FitViewOptions>(() => {
    // Fit the whole graph when that keeps names readable; otherwise open on the hub.
    const hub = firstViewHub(positions, edges);
    if (hub === null) return FIT_OPTIONS;
    return { ...FIT_OPTIONS, minZoom: READABLE_ZOOM, nodes: hubNeighbourhood(hub, edges) };
  }, [positions, edges]);

  // Keep the selected file in view: centre it in the part of the canvas the panel leaves free
  // (below 900px, or beside the Ask drawer below 1600px, the panel overlays the canvas).
  // Opened with ?node= in the URL: skip React Flow's first fit (it would run after, and undo,
  // the centring below) and open on the selected file instead.
  const [fitOnMount] = useState(selectedId === null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false); // set by onInit: the viewport can be moved
  // The canvas narrows when the docked panel opens; centring must use the final size, so it
  // re-runs whenever the canvas is resized.
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
    if (selectedId === null || !ready || !canvasSize) return;
    const p = positions.get(selectedId);
    const canvas = canvasRef.current;
    if (!p || !canvas) return;
    const frame = requestAnimationFrame(() => {
      const zoom = Math.max(getViewport().zoom, READABLE_ZOOM);
      const covered = panelOverlay ? Math.min(480, canvas.clientWidth) : 0;
      const visibleWidth = canvas.clientWidth - covered;
      const shift = covered > 0 && visibleWidth > NODE_WIDTH * zoom ? covered / 2 / zoom : 0;
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      void setCenter(p.x + NODE_WIDTH / 2 + shift, p.y + NODE_HEIGHT / 2, {
        zoom,
        duration: reduced ? 0 : 200,
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [selectedId, positions, ready, canvasSize, panelOverlay, getViewport, setCenter]);

  // Focus mode: with a file selected, everything outside its 1-hop neighbourhood is dimmed.
  const neighbourhood = useMemo(() => {
    if (selectedId === null) return null;
    const ids = new Set([selectedId]);
    for (const e of edges) {
      if (e.source === selectedId) ids.add(e.target);
      if (e.target === selectedId) ids.add(e.source);
    }
    return ids;
  }, [edges, selectedId]);

  const flowNodes = useMemo<FileFlowNode[]>(
    () =>
      nodes.map((n) => {
        const p = positions.get(n.id);
        return {
          id: String(n.id),
          type: "file",
          position: { x: p?.x ?? 0, y: p?.y ?? 0 },
          data: {
            path: n.path,
            language: n.language,
            selected: n.id === selectedId,
            dimmed: neighbourhood !== null && !neighbourhood.has(n.id),
          },
          draggable: false,
          connectable: false,
          ariaLabel: n.path,
        };
      }),
    [nodes, positions, selectedId, neighbourhood],
  );

  const flowEdges = useMemo<DepFlowEdge[]>(
    () =>
      edges.map((e) => {
        const active = selectedId !== null && (e.source === selectedId || e.target === selectedId);
        return {
          id: `${e.source}-${e.target}`,
          source: String(e.source),
          target: String(e.target),
          type: "dep",
          markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: active ? "var(--text)" : "var(--edge)" },
          data: { guess: isGuess(e), label: edgeLabel(e), active, dimmed: selectedId !== null && !active },
          focusable: false,
        };
      }),
    [edges, selectedId],
  );

  return (
    // Nodes are focusable but not selectable (selection is the URL's ?node=), so React Flow does
    // not act on Enter or Space: open the focused file here, like a click.
    <div
      ref={canvasRef}
      className="canvas-flow"
      onKeyDown={(e) => {
        if (e.key !== "Enter" && e.key !== " ") return;
        const node = (e.target as HTMLElement).closest<HTMLElement>(".react-flow__node");
        if (!node?.dataset.id) return;
        e.preventDefault();
        onSelect(Number(node.dataset.id));
      }}
    >
      <ReactFlow<FileFlowNode, DepFlowEdge>
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeClick={(_, node) => onSelect(Number(node.id))}
        onPaneClick={() => onSelect(null)}
        fitView={fitOnMount}
        fitViewOptions={initialFit}
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
