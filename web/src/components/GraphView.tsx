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
} from "@xyflow/react";
import { memo, useMemo } from "react";

import type { GraphEdge, GraphNode } from "../api";
import { isGuess, languageLabel, type Positioned, splitPath } from "../graphModel";

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

// Room at the bottom for the legend, so the fitted graph never sits under it.
export const FIT_OPTIONS: FitViewOptions = {
  padding: { top: "24px", right: "24px", bottom: "112px", left: "24px" },
  maxZoom: 1.1,
};

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
  onSelect,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  positions: Map<number, Positioned>;
  selectedId: number | null;
  onSelect: (fileId: number | null) => void;
}) {
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
    <ReactFlow<FileFlowNode, DepFlowEdge>
      nodes={flowNodes}
      edges={flowEdges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodeClick={(_, node) => onSelect(Number(node.id))}
      onPaneClick={() => onSelect(null)}
      fitView
      fitViewOptions={FIT_OPTIONS}
      minZoom={0.08}
      maxZoom={2}
      nodesConnectable={false}
      nodesDraggable={false}
      elementsSelectable={false}
      onlyRenderVisibleElements
    />
  );
}
