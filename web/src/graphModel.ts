// Pure graph preparation: degrees, the render cap, and dagre layout. React Flow does not
// position nodes, so every node gets x/y from here.

import { Graph as DagreGraph, layout } from "@dagrejs/dagre";

import type { Graph, GraphEdge, GraphNode } from "./api";

export const RENDER_CAP = 300;
export const GUESS_BELOW = 0.9; // edges under this confidence are best guesses, drawn dashed
export const NODE_WIDTH = 200;
export const NODE_HEIGHT = 44;

export interface Degrees {
  uses: number; // files this file depends on
  usedBy: number; // files that depend on this file
}

export function degrees(graph: Graph): Map<number, Degrees> {
  const result = new Map<number, Degrees>(graph.nodes.map((n) => [n.id, { uses: 0, usedBy: 0 }]));
  for (const e of graph.edges) {
    const source = result.get(e.source);
    const target = result.get(e.target);
    if (source) source.uses += 1;
    if (target) target.usedBy += 1;
  }
  return result;
}

export interface CappedGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total: number;
  capped: boolean;
}

/** Keep the `cap` most connected files (ties by path) and the edges among them. */
export function applyCap(graph: Graph, deg: Map<number, Degrees>, cap = RENDER_CAP): CappedGraph {
  const total = graph.nodes.length;
  if (total <= cap) return { nodes: graph.nodes, edges: graph.edges, total, capped: false };
  const score = (n: GraphNode) => {
    const d = deg.get(n.id);
    return d ? d.uses + d.usedBy : 0;
  };
  const kept = [...graph.nodes]
    .sort((a, b) => score(b) - score(a) || a.path.localeCompare(b.path))
    .slice(0, cap);
  const ids = new Set(kept.map((n) => n.id));
  return {
    nodes: kept,
    edges: graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target)),
    total,
    capped: true,
  };
}

export interface Positioned {
  id: number;
  x: number; // top-left, as React Flow expects
  y: number;
}

const COLUMN_MAX = 24; // a layer taller than this wraps into extra columns
const NODE_GAP = 14;
const LAYER_GAP = 72;

/** Left-to-right layered layout: importers left, what they import to the right. A layer with
 * many files (e.g. a hundred tests that all import the package root) wraps into several
 * columns, so the fitted view stays readable instead of becoming a thin strip. */
export function layoutGraph(nodes: GraphNode[], edges: GraphEdge[]): Map<number, Positioned> {
  const g = new DagreGraph();
  g.setGraph({ rankdir: "LR", nodesep: NODE_GAP, ranksep: LAYER_GAP, marginx: 16, marginy: 16 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of nodes) g.setNode(String(n.id), { width: NODE_WIDTH, height: NODE_HEIGHT });
  for (const e of edges) g.setEdge(String(e.source), String(e.target));
  layout(g);

  // Group nodes into dagre's layers (same x), keeping dagre's top-to-bottom order.
  const layers = new Map<number, { id: number; y: number }[]>();
  for (const n of nodes) {
    const p = g.node(String(n.id));
    const x = Math.round(p.x);
    if (!layers.has(x)) layers.set(x, []);
    layers.get(x)!.push({ id: n.id, y: p.y });
  }
  const columns = [...layers.entries()].sort((a, b) => a[0] - b[0]).map(([, l]) => l);
  const tallest = Math.min(COLUMN_MAX, Math.max(...columns.map((l) => l.length)));
  const centre = (tallest * (NODE_HEIGHT + NODE_GAP)) / 2;

  const result = new Map<number, Positioned>();
  let x = 0;
  for (const layer of columns) {
    layer.sort((a, b) => a.y - b.y);
    const wraps = Math.ceil(layer.length / COLUMN_MAX);
    const perColumn = Math.ceil(layer.length / wraps);
    layer.forEach((n, i) => {
      const col = Math.floor(i / perColumn);
      const row = i % perColumn;
      const rows = Math.min(perColumn, layer.length - col * perColumn);
      const top = centre - (rows * (NODE_HEIGHT + NODE_GAP)) / 2;
      result.set(n.id, {
        id: n.id,
        x: x + col * (NODE_WIDTH + NODE_GAP * 2),
        y: top + row * (NODE_HEIGHT + NODE_GAP),
      });
    });
    x += wraps * (NODE_WIDTH + NODE_GAP * 2) - NODE_GAP * 2 + LAYER_GAP;
  }
  return result;
}

export function isGuess(edge: GraphEdge): boolean {
  return edge.confidence < GUESS_BELOW;
}

/** 'web/src/lib/math.ts' -> ['web/src/lib/', 'math.ts'] */
export function splitPath(path: string): [string, string] {
  const i = path.lastIndexOf("/");
  return i === -1 ? ["", path] : [path.slice(0, i + 1), path.slice(i + 1)];
}

export function languageLabel(language: string): string {
  if (language === "python") return "Python";
  if (language === "typescript") return "TypeScript";
  if (language === "javascript") return "JavaScript";
  return language;
}
