// Layout for the folder-first map. React Flow does not position nodes, so every node gets x/y
// here. Nodes with a connection go through dagre (importers left, what they import to the right);
// nodes with none (a folder of tests that only import code outside the view) form a grid below,
// so a view of 60 loose files is a block and not a tall strip.

import { Graph as DagreGraph, layout } from "@dagrejs/dagre";

import type { MapEdge, MapLevel, MapNode } from "./api";

export const MAP_NODE_WIDTH = 208;
const NODE_GAP = 14;
const LAYER_GAP = 72;
const GRID_GAP = 56;
const BAND_GAP = 48;
const COLUMN_HEIGHT = 720; // a layer taller than this wraps into extra columns
const ROW_WIDTH = 1800; // a chain of layers longer than this continues on a new row

export interface MapPosition {
  x: number; // top-left, as React Flow expects
  y: number;
  rank: number; // dagre's layer, in dependency order; wraps to a new row keep it
}

export function mapNodeHeight(level: MapLevel): number {
  return level === "symbol" ? 48 : 76;
}

export function layoutMap(
  level: MapLevel,
  nodes: MapNode[],
  edges: MapEdge[],
): Map<string, MapPosition> {
  const height = mapNodeHeight(level);
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
    g.setGraph({ rankdir: "LR", nodesep: NODE_GAP, ranksep: LAYER_GAP, marginx: 0, marginy: 0 });
    g.setDefaultEdgeLabel(() => ({}));
    for (const n of connected) g.setNode(n.id, { width: MAP_NODE_WIDTH, height });
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
          width: wraps * (MAP_NODE_WIDTH + NODE_GAP * 2) - NODE_GAP * 2,
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
          result.set(n.id, { x: x + col * (MAP_NODE_WIDTH + NODE_GAP * 2), y, rank: layer.rank });
          bottom = Math.max(bottom, y + height);
        });
        x += layer.width + LAYER_GAP;
      }
      top += tall + BAND_GAP;
    }
  }

  if (loose.length > 0) {
    // Wide rather than tall: a screen is wider than it is high (58 loose files -> 8 x 8).
    const columns = Math.max(1, Math.min(Math.ceil(Math.sqrt(loose.length * 2)), 8));
    const top = connected.length > 0 ? bottom + GRID_GAP : 0;
    loose.forEach((n, i) => {
      result.set(n.id, {
        x: (i % columns) * (MAP_NODE_WIDTH + NODE_GAP),
        y: top + Math.floor(i / columns) * (height + NODE_GAP),
        rank: -1,
      });
    });
  }
  return result;
}
