// Hover, keyboard focus and selection of the map, kept outside React state. Nodes and edges
// subscribe to a small number about themselves (`nodeFlags`, `edgeFlags`), so a hover re-renders
// only the nodes and edges it changes, not the whole canvas; the dimming of everything else is
// one attribute on the container (CSS). Nothing here touches a node or edge object, which is what
// keeps React Flow from hiding and re-measuring nodes.

import type { MapEdge } from "./api";
import { edgeRole, neighbourhood } from "./mapModel";

export const NODE_SELECTED = 1;
export const NODE_NEAR = 2; // the focused node or one edge away from it
export const EDGE_ACTIVE = 1;
export const EDGE_VISIBLE = 2;

export interface FocusStore {
  subscribe(listener: () => void): () => void;
  /** The view's edges and the node of the file open in the panel. */
  configure(edges: MapEdge[], selectedId: string | null): void;
  setHover(id: string | null): void;
  setFocused(id: string | null): void;
  /** True while a node is hovered, keyboard-focused or selected. */
  focusing(): boolean;
  nodeFlags(id: string): number;
  edgeFlags(source: string, target: string, rest: boolean): number;
}

export function createFocusStore(): FocusStore {
  let edges: MapEdge[] = [];
  let hover: string | null = null;
  let focused: string | null = null;
  let selected: string | null = null;
  let focusId: string | null = null;
  let near: Set<string> | null = null;
  const listeners = new Set<() => void>();

  function recompute() {
    const next = hover ?? focused ?? selected;
    if (next === focusId) return;
    focusId = next;
    near = neighbourhood(edges, focusId);
    for (const l of listeners) l();
  }

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    configure(nextEdges, selectedId) {
      const changed = nextEdges !== edges || selectedId !== selected;
      edges = nextEdges;
      selected = selectedId;
      if (!changed) return;
      focusId = null; // recompute even when the id is the same: the neighbours may differ
      near = null;
      recompute();
      for (const l of listeners) l();
    },
    setHover(id) {
      hover = id;
      recompute();
    },
    setFocused(id) {
      focused = id;
      recompute();
    },
    focusing: () => focusId !== null,
    nodeFlags: (id) => (selected === id ? NODE_SELECTED : 0) | (near?.has(id) ? NODE_NEAR : 0),
    edgeFlags(source, target, rest) {
      const role = edgeRole({ source, target }, rest, focusId);
      return (role.active ? EDGE_ACTIVE : 0) | (role.visible ? EDGE_VISIBLE : 0);
    },
  };
}
