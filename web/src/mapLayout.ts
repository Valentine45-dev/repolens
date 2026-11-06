// Layout for the folder-first map. React Flow does not position nodes, so every node gets x/y
// here. Nodes with a connection go through dagre (importers left, what they import to the right);
// nodes with none (a folder of tests that only import code outside the view) form a grid below,
// so a view of 60 loose files is a block and not a tall strip.

import { Graph as DagreGraph, layout } from "@dagrejs/dagre";

import type { MapEdge, MapLevel, MapNode } from "./api";

export const MAP_NODE_WIDTH = 208; // folder and file nodes
export const SYMBOL_NODE_WIDTH = 248; // longer names, and they are what is read in a symbol view

/** Zoom below which names stop being readable: the first view never goes under it. */
export const READABLE_MIN_ZOOM = 0.75;
export const FIT_MAX_ZOOM = 1.1;
const FIT_PAD = 24;
const NODE_GAP = 14;
const LAYER_GAP = 72;
const GRID_GAP = 56;
const BAND_GAP = 48;
const COLUMN_HEIGHT = 720; // a layer taller than this wraps into extra columns
const LOOSE_ROW_UNITS = 1800; // the width of a screen at the readable zoom
const ROW_WIDTH = 1800; // a chain of layers longer than this continues on a new row

export interface MapPosition {
  x: number; // top-left, as React Flow expects
  y: number;
  rank: number; // dagre's layer, in dependency order; wraps to a new row keep it
}

export function mapNodeHeight(level: MapLevel): number {
  return level === "symbol" ? 56 : 76;
}

export function mapNodeWidth(level: MapLevel): number {
  return level === "symbol" ? SYMBOL_NODE_WIDTH : MAP_NODE_WIDTH;
}

export interface Viewport {
  x: number;
  y: number;
  zoom: number;
}

/** Where the first view of a map sits. Everything fits when that keeps names readable (zoom of
 * READABLE_MIN_ZOOM or more); otherwise the view opens at that zoom on the top left of the map,
 * and the rest is a scroll away (`zoomedIn`: the canvas says so, and Fit shows everything). */
export function initialViewport(
  level: MapLevel,
  positions: Map<string, MapPosition>,
  canvas: { width: number; height: number },
): Viewport & { zoomedIn: boolean } {
  const w = mapNodeWidth(level);
  const h = mapNodeHeight(level);
  if (positions.size === 0) return { x: FIT_PAD, y: FIT_PAD, zoom: 1, zoomedIn: false };
  const xs = [...positions.values()].map((p) => p.x);
  const ys = [...positions.values()].map((p) => p.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const width = Math.max(...xs) + w - minX;
  const height = Math.max(...ys) + h - minY;
  const fit = Math.min((canvas.width - 2 * FIT_PAD) / width, (canvas.height - 2 * FIT_PAD) / height);
  if (fit >= READABLE_MIN_ZOOM) {
    const zoom = Math.min(fit, FIT_MAX_ZOOM);
    return {
      x: (canvas.width - width * zoom) / 2 - minX * zoom,
      y: (canvas.height - height * zoom) / 2 - minY * zoom,
      zoom,
      zoomedIn: false,
    };
  }
  return { x: FIT_PAD - minX * READABLE_MIN_ZOOM, y: FIT_PAD - minY * READABLE_MIN_ZOOM, zoom: READABLE_MIN_ZOOM, zoomedIn: true };
}

/** dagre settings tried for each map; the one with the fewest crossings wins. */
interface DagreVariant {
  ranker: "network-simplex" | "tight-tree" | "longest-path";
  acyclicer?: "greedy";
}
const VARIANTS: DagreVariant[] = [
  { ranker: "network-simplex" },
  { ranker: "tight-tree" },
  { ranker: "longest-path" },
  { ranker: "network-simplex", acyclicer: "greedy" },
  { ranker: "tight-tree", acyclicer: "greedy" },
  { ranker: "longest-path", acyclicer: "greedy" },
];

/** Lay a map out: nodes with a connection through dagre (importers left, what they import to the
 * right), the rest in a grid below. `edges` should be the edges that are drawn, so the picture
 * is arranged for what is on screen; hover shows more on top of it. Several dagre settings are
 * tried (a map has at most 61 nodes, so this is a few milliseconds) and the arrangement with the
 * fewest crossings, then the fewest edges through other nodes, then the smallest area, is kept. */
export function layoutMap(
  level: MapLevel,
  nodes: MapNode[],
  edges: MapEdge[],
): Map<string, MapPosition> {
  const size = { width: mapNodeWidth(level), height: mapNodeHeight(level) };
  let best: { positions: Map<string, MapPosition>; score: number[] } | null = null;
  for (const variant of VARIANTS) {
    const positions = layoutWith(level, nodes, edges, variant);
    const m = edgeMetrics(positions, edges, size);
    const xs = [...positions.values()].map((p) => p.x);
    const ys = [...positions.values()].map((p) => p.y);
    const area = xs.length ? (Math.max(...xs) - Math.min(...xs) + 1) * (Math.max(...ys) - Math.min(...ys) + 1) : 0;
    const score = [m.crossings, m.throughNodes, m.backward + m.sameColumn, area];
    if (best === null || compareScores(score, best.score) < 0) best = { positions, score };
  }
  return best?.positions ?? new Map();
}

function compareScores(a: number[], b: number[]): number {
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] - b[i];
  return 0;
}

function layoutWith(
  level: MapLevel,
  nodes: MapNode[],
  edges: MapEdge[],
  variant: DagreVariant,
): Map<string, MapPosition> {
  const height = mapNodeHeight(level);
  const width = mapNodeWidth(level);
  const ids = new Set(nodes.map((n) => n.id));
  const linked = new Set<string>();
  for (const e of edges) {
    if (e.source !== e.target && ids.has(e.source) && ids.has(e.target)) {
      linked.add(e.source);
      linked.add(e.target);
    }
  }
  const connected = nodes.filter((n) => linked.has(n.id));
  const loose = nodes.filter((n) => !linked.has(n.id));
  const result = new Map<string, MapPosition>();
  let bottom = 0;

  if (connected.length > 0) {
    const g = new DagreGraph();
    g.setGraph({
      rankdir: "LR",
      nodesep: NODE_GAP,
      ranksep: LAYER_GAP,
      marginx: 0,
      marginy: 0,
      ranker: variant.ranker,
      ...(variant.acyclicer ? { acyclicer: variant.acyclicer } : {}),
    });
    g.setDefaultEdgeLabel(() => ({}));
    for (const n of connected) g.setNode(n.id, { width, height });
    for (const e of edges) {
      if (e.source !== e.target && linked.has(e.source) && linked.has(e.target)) {
        g.setEdge(e.source, e.target);
      }
    }
    layout(g);

    // dagre's layers share an x; keep its top-to-bottom order inside each.
    const byX = new Map<number, { id: string; y: number }[]>();
    for (const n of connected) {
      const p = g.node(n.id);
      const x = Math.round(p.x);
      if (!byX.has(x)) byX.set(x, []);
      byX.get(x)!.push({ id: n.id, y: p.y });
    }
    const rowsMax = Math.max(1, Math.floor(COLUMN_HEIGHT / (height + NODE_GAP)));
    const layers = [...byX.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([, members], rank) => {
        members.sort((a, b) => a.y - b.y);
        const wraps = Math.ceil(members.length / rowsMax);
        const perColumn = Math.ceil(members.length / wraps);
        return {
          rank,
          members,
          wraps,
          perColumn,
          width: wraps * (width + NODE_GAP * 2) - NODE_GAP * 2,
        };
      });

    // Bands: a long chain of layers continues on a new row instead of one thin strip.
    const bands: (typeof layers)[] = [[]];
    let used = 0;
    for (const layer of layers) {
      if (used > 0 && used + layer.width > ROW_WIDTH) {
        bands.push([]);
        used = 0;
      }
      bands[bands.length - 1].push(layer);
      used += layer.width + LAYER_GAP;
    }
    let top = 0;
    for (const band of bands) {
      const tall = Math.max(...band.map((l) => l.perColumn)) * (height + NODE_GAP);
      let x = 0;
      for (const layer of band) {
        layer.members.forEach((n, i) => {
          const col = Math.floor(i / layer.perColumn);
          const row = i % layer.perColumn;
          const rows = Math.min(layer.perColumn, layer.members.length - col * layer.perColumn);
          const y = top + (tall - rows * (height + NODE_GAP)) / 2 + row * (height + NODE_GAP);
          result.set(n.id, { x: x + col * (width + NODE_GAP * 2), y, rank: layer.rank });
          bottom = Math.max(bottom, y + height);
        });
        x += layer.width + LAYER_GAP;
      }
      top += tall + BAND_GAP;
    }
  }

  if (loose.length > 0) {
    // Wide rather than tall: a screen is wider than it is high (58 loose files -> 8 x 8).
    // As many columns as fit a screen at the readable zoom (~1800 units), or a squarish block.
    const fits = Math.max(1, Math.floor(LOOSE_ROW_UNITS / (width + NODE_GAP)));
    const columns = Math.max(1, Math.min(Math.ceil(Math.sqrt(loose.length * 2)), fits));
    const top = connected.length > 0 ? bottom + GRID_GAP : 0;
    loose.forEach((n, i) => {
      result.set(n.id, {
        x: (i % columns) * (width + NODE_GAP),
        y: top + Math.floor(i / columns) * (height + NODE_GAP),
        rank: -1,
      });
    });
  }
  return result;
}

// --- How tangled a drawn map is --------------------------------------------------------------
// From where the nodes are and which edges are drawn. Each edge is judged as a straight line
// between node centres (the curves we draw stay close to it): a fair yardstick for comparing
// layouts, not a pixel-exact count.

export interface Placed {
  x: number; // top-left
  y: number;
}

export interface EdgeMetrics {
  edges: number;
  /** Pairs of drawn edges that cross, not counting two edges that share a node. */
  crossings: number;
  /** Drawn edges that pass through the box of a node that is neither end of them. */
  throughNodes: number;
  /** Edges that point back (their target sits left of their source by more than a node). */
  backward: number;
  /** Edges between two nodes in the same column (their boxes overlap in x). */
  sameColumn: number;
}

type Pt = [number, number];

function ccw(a: Pt, b: Pt, c: Pt): number {
  return (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0]);
}

/** Proper intersection of segments ab and cd (touching at an end does not count). */
function segmentsCross(a: Pt, b: Pt, c: Pt, d: Pt): boolean {
  const d1 = ccw(a, b, c);
  const d2 = ccw(a, b, d);
  const d3 = ccw(c, d, a);
  const d4 = ccw(c, d, b);
  return d1 * d2 < 0 && d3 * d4 < 0;
}

/** Does segment ab pass through the open rectangle (x, y, w, h)? Liang-Barsky clipping. */
function segmentHitsBox(a: Pt, b: Pt, x: number, y: number, w: number, h: number): boolean {
  let t0 = 0;
  let t1 = 1;
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const checks: [number, number][] = [
    [-dx, a[0] - x],
    [dx, x + w - a[0]],
    [-dy, a[1] - y],
    [dy, y + h - a[1]],
  ];
  for (const [p, q] of checks) {
    if (p === 0) {
      if (q <= 0) return false;
    } else {
      const r = q / p;
      if (p < 0) {
        if (r > t1) return false;
        if (r > t0) t0 = r;
      } else {
        if (r < t0) return false;
        if (r < t1) t1 = r;
      }
    }
  }
  // Ignore a graze that is only a sliver of the box.
  return t1 - t0 > 1e-6;
}

export function edgeMetrics(
  positions: Map<string, Placed>,
  edges: { source: string; target: string }[],
  size: { width: number; height: number },
): EdgeMetrics {
  const centre = (id: string): Pt | null => {
    const p = positions.get(id);
    return p ? [p.x + size.width / 2, p.y + size.height / 2] : null;
  };
  const lines = edges
    .map((e) => ({ e, a: centre(e.source), b: centre(e.target) }))
    .filter((l): l is { e: { source: string; target: string }; a: Pt; b: Pt } => l.a !== null && l.b !== null && l.e.source !== l.e.target);

  let crossings = 0;
  for (let i = 0; i < lines.length; i++) {
    for (let j = i + 1; j < lines.length; j++) {
      const p = lines[i];
      const q = lines[j];
      if (p.e.source === q.e.source || p.e.source === q.e.target || p.e.target === q.e.source || p.e.target === q.e.target) continue;
      if (segmentsCross(p.a, p.b, q.a, q.b)) crossings++;
    }
  }

  let throughNodes = 0;
  for (const l of lines) {
    for (const [id, p] of positions) {
      if (id === l.e.source || id === l.e.target) continue;
      if (segmentHitsBox(l.a, l.b, p.x, p.y, size.width, size.height)) throughNodes++;
    }
  }

  let backward = 0;
  let sameColumn = 0;
  for (const l of lines) {
    const from = positions.get(l.e.source)!;
    const to = positions.get(l.e.target)!;
    if (Math.abs(from.x - to.x) < size.width / 2) sameColumn++;
    else if (to.x < from.x) backward++;
  }
  return { edges: lines.length, crossings, throughNodes, backward, sameColumn };
}

export interface EdgeHandles {
  sourceHandle: "out-r" | "out-l" | "out-b" | "out-t";
  targetHandle: "in-l" | "in-r" | "in-t" | "in-b";
  vertical: boolean; // leaves and arrives through the top or bottom
}

/** Which sides an edge uses. Nodes side by side: right side to left side, or, when it points back,
 * left side to right side. Nodes in one column: bottom to top (or top to bottom), a short straight
 * line, instead of the loop out to the side and back that two right sides make. */
export function edgeHandles(
  from: MapPosition | undefined,
  to: MapPosition | undefined,
  width: number,
): EdgeHandles {
  if (!from || !to) return { sourceHandle: "out-r", targetHandle: "in-l", vertical: false };
  if (Math.abs(to.x - from.x) < width / 2) {
    return to.y >= from.y
      ? { sourceHandle: "out-b", targetHandle: "in-t", vertical: true }
      : { sourceHandle: "out-t", targetHandle: "in-b", vertical: true };
  }
  return to.x > from.x
    ? { sourceHandle: "out-r", targetHandle: "in-l", vertical: false }
    : { sourceHandle: "out-l", targetHandle: "in-r", vertical: false };
}
