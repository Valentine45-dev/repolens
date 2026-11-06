// The folder-first map, as pure functions: which view to ask for, what a click does, which edges
// are drawn, how an edge is described. No React, no layout library and no runtime imports, so
// the tests (and eval/graph_ui_readability.mjs) can load it on its own.

import type { Crumb, MapEdge, MapLevel, MapNode, MapView } from "./api";

/** At or under this many visible files a repo opens as files, not folders: its folder view would
 * be two nodes and no edges (itsdangerous, express). */
export const START_FILE_LIMIT = 30;
/** Edges drawn at rest. The server's 60-node limit does not limit edges (flask `src/flask` has
 * 20 nodes and 82 edges; a symbol view reaches 61 nodes and 202). */
export const EDGE_BUDGET = 40;
/** About three edges for every four nodes, between 12 and EDGE_BUDGET: a view of 20 nodes draws
 * at most 15 edges (it used to draw up to 40), a view of 60 still draws 40. What is left out is
 * one hover or "Show all edges" away. */
export function edgeBudgetFor(nodeCount: number): number {
  return Math.min(EDGE_BUDGET, Math.max(12, Math.round(nodeCount * 0.75)));
}
/** Up to this many drawn edges every one carries its count; above it only the strong ones do. */
export const LABEL_ALL_UP_TO = 12;

export type ViewLevel = "folder" | "file" | "symbol" | "flat";
export interface ViewRequest {
  level: ViewLevel;
  root: string;
}

/** A request the server answers; "flat" is the old graph, which has its own endpoint shape. */
export function isMapRequest(r: ViewRequest | null): r is { level: MapLevel; root: string } {
  return r !== null && r.level !== "flat";
}

const LEVELS: readonly string[] = ["folder", "file", "symbol", "flat"];

export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

export function parentDir(path: string): string {
  return path.slice(0, Math.max(path.lastIndexOf("/"), 0));
}

/** ?level=folder|file|symbol|flat&root=<path>. Anything else is "not set". */
export function parseViewParams(params: URLSearchParams): { level: ViewLevel | null; root: string } {
  const level = params.get("level");
  return {
    level: level !== null && LEVELS.includes(level) ? (level as ViewLevel) : null,
    root: (params.get("root") ?? "").replace(/^\/+|\/+$/g, ""),
  };
}

export function startLevel(visibleFiles: number): "file" | "folder" {
  return visibleFiles <= START_FILE_LIMIT ? "file" : "folder";
}

/** What to ask the server for. The URL wins. With no level and no root the start rule decides,
 * which needs the file count from the flat index; null means "not known yet". A link to a file
 * (`node=`, no root) opens that file's folder in a big repo, so the file is on the canvas. */
export function resolveView(
  url: { level: ViewLevel | null; root: string; nodeId: number | null },
  flat: { nodes: { id: number; path: string }[] } | null,
): ViewRequest | null {
  if (url.level === "flat") return { level: "flat", root: "" };
  if (url.level === "symbol" && url.root) return { level: "symbol", root: url.root };
  if (url.level === "folder" || url.level === "file") return { level: url.level, root: url.root };
  if (url.root) return { level: "folder", root: url.root };
  if (!flat) return null;
  if (flat.nodes.length > START_FILE_LIMIT && url.nodeId !== null) {
    const file = flat.nodes.find((n) => n.id === url.nodeId);
    if (file) return { level: "folder", root: parentDir(file.path) };
  }
  return { level: startLevel(flat.nodes.length), root: "" };
}

/** `?a=b` for the current address with these changes (null removes a key). */
export function paramsWith(search: string, changes: Record<string, string | null>): string {
  const next = new URLSearchParams(search);
  for (const [key, value] of Object.entries(changes)) {
    if (value === null) next.delete(key);
    else next.set(key, value);
  }
  const query = next.toString();
  return query ? `?${query}` : "";
}

/** Moving to another view closes the file panel: the file may not be on the new canvas. */
export function navigateChanges(level: ViewLevel, root: string): Record<string, string | null> {
  return {
    level,
    root: level === "flat" || root === "" ? null : root,
    node: null,
    lines: null,
  };
}

/** The folder a view is about; for a symbol view, the folder that holds its file. */
export function viewFolder(view: Pick<MapView, "level" | "root" | "breadcrumbs">): string {
  if (view.level !== "symbol") return view.root;
  return view.breadcrumbs[view.breadcrumbs.length - 2]?.path ?? "";
}

/** A breadcrumb opens as a folder, or as files when the view is a file view. The last crumb of
 * a symbol view is the file itself. */
export function crumbChanges(
  view: Pick<MapView, "level" | "breadcrumbs">,
  index: number,
): Record<string, string | null> {
  const crumb = view.breadcrumbs[index];
  if (view.level === "symbol" && index === view.breadcrumbs.length - 1) {
    return navigateChanges("symbol", crumb.path);
  }
  return navigateChanges(view.level === "file" ? "file" : "folder", crumb.path);
}

/** One level up, or null at the repo. */
export function upChanges(
  view: Pick<MapView, "level" | "breadcrumbs">,
): Record<string, string | null> | null {
  return view.breadcrumbs.length > 1 ? crumbChanges(view, view.breadcrumbs.length - 2) : null;
}

export function crumbLabel(crumb: Crumb, repo: string): string {
  return crumb.label === "" ? repo : crumb.label;
}

// --- clicks --------------------------------------------------------------------------------

export type NodeAction =
  | { type: "open"; level: "folder"; root: string }
  | { type: "select"; fileId: number; lines: { start: number; end: number } | null }
  | { type: "list"; root: string }
  | { type: "none" };

/** What a click on a node does: a folder opens, a file opens its panel, a symbol opens its file
 * on its lines, "N more" opens the List view for that folder (nothing in a symbol view, where
 * List has no symbols to show). */
export function nodeAction(level: "folder" | "file" | "symbol", node: MapNode): NodeAction {
  switch (node.kind) {
    case "folder":
      return { type: "open", level: "folder", root: node.path };
    case "file":
      return node.file_id === undefined
        ? { type: "none" }
        : { type: "select", fileId: node.file_id, lines: null };
    case "more":
      return level === "symbol" ? { type: "none" } : { type: "list", root: node.path };
    default: {
      if (node.file_id === undefined) return { type: "none" };
      const lines =
        node.kind !== "module" && node.start_line != null && node.end_line != null
          ? { start: node.start_line, end: node.end_line }
          : null;
      return { type: "select", fileId: node.file_id, lines };
    }
  }
}

// --- edges ---------------------------------------------------------------------------------

export function isCycleEdge(e: MapEdge): boolean {
  return (e.cycle_edges ?? 0) > 0;
}

/** Dashed when the link is mostly guesses. `guess` alone is not enough: it is true only when
 * every underlying edge is a guess, and an import (always solid) makes it false (express
 * `test` -> `lib` is 6 imports and 155 calls, 152 of them guesses). */
export function isDashed(e: MapEdge): boolean {
  if (e.type !== undefined) return e.guess; // symbol level: one call edge or one `defines`
  return e.guess || (e.guess_calls ?? 0) * 2 > e.count;
}

/** "6 imports · 155 calls (152 guesses)": a dashed edge never hides its solid imports. */
export function edgeSplit(e: MapEdge): string {
  if (e.type === "defines") return "defines (class to method)";
  if (e.type === "calls") return e.guess ? "calls (best guess)" : "calls";
  const parts: string[] = [];
  if (e.imports) parts.push(plural(e.imports, "import"));
  if (e.calls) {
    const guesses = e.guess_calls ?? 0;
    const note =
      guesses === 0 ? "" : ` (${guesses === 1 ? "1 guess" : `${guesses} guesses`})`;
    parts.push(`${plural(e.calls, "call")}${note}`);
  }
  return parts.join(" · ") || plural(e.count, "connection");
}

/** Count on a log scale: 1 -> 1.25px, 10 -> 2.7px, 160 -> 4.5px. */
export function edgeWidth(count: number): number {
  return Math.min(5, 1.25 + Math.log2(Math.max(count, 1)) * 0.45);
}

export function showEdgeLabel(count: number, drawn: number, active: boolean): boolean {
  return active || drawn <= LABEL_ALL_UP_TO || count >= 2;
}

export interface EdgeSelection {
  shown: MapEdge[];
  total: number;
  mode: "all" | "tier" | "sample";
  minCount: number | null; // tier mode: every drawn edge has at least this count
}

function sampleKey(e: MapEdge): (number | string)[] {
  return [e.type === "defines" ? 1 : 0, e.guess ? 1 : 0, -e.count, e.source, e.target];
}

function compareKeys(a: (number | string)[], b: (number | string)[]): number {
  for (let i = 0; i < a.length; i++) {
    if (a[i] === b[i]) continue;
    return a[i] < b[i] ? -1 : 1;
  }
  return 0;
}

/** The edges drawn at rest. At most `budget`, plus every edge of a circular import (those are
 * the point of the view). Whole tiers only: edges of equal count are never split, so nothing is
 * hidden by an arbitrary tie-break. If even the strongest tier is too big (a symbol view, where
 * every count is 1) a labelled sample is drawn instead: calls before `defines` (which only say a
 * class has a method), and within those solid before guesses. */
export function selectEdges(edges: MapEdge[], budget = EDGE_BUDGET): EdgeSelection {
  const total = edges.length;
  const forced = edges.filter(isCycleEdge);
  const rest = edges.filter((e) => !isCycleEdge(e));
  const room = Math.max(budget - forced.length, 0);
  if (total <= budget || rest.length <= room) {
    return { shown: edges, total, mode: "all", minCount: null };
  }

  const tiers = [...new Set(rest.map((e) => e.count))].sort((a, b) => b - a);
  const keep = new Set<MapEdge>(forced);
  let taken = 0;
  let minCount: number | null = null;
  for (const count of tiers) {
    const tier = rest.filter((e) => e.count === count);
    if (taken + tier.length > room) break;
    for (const e of tier) keep.add(e);
    taken += tier.length;
    minCount = count;
  }
  if (taken === 0) {
    const sample = [...rest].sort((a, b) => compareKeys(sampleKey(a), sampleKey(b))).slice(0, room);
    for (const e of sample) keep.add(e);
    return { shown: edges.filter((e) => keep.has(e)), total, mode: "sample", minCount: null };
  }
  return { shown: edges.filter((e) => keep.has(e)), total, mode: "tier", minCount };
}

/** The edges drawn at rest: the selection's, or every one when "Show all edges" is on. */
export function restingEdges(
  edges: MapEdge[],
  selection: EdgeSelection,
  showAll: boolean,
): Set<MapEdge> {
  return new Set(showAll || selection.mode === "all" ? edges : selection.shown);
}

/** Stable identity of an edge, whatever else changes. */
export function edgeKey(e: MapEdge): string {
  return `${e.source}>${e.target}${e.type ? `:${e.type}` : ""}`;
}

/** What hover, keyboard focus or selection does to one edge. Every edge of the focused node is
 * drawn (and active); at rest only the resting ones are; with a focus the rest are dimmed.
 * This is the only thing hover changes: nodes and edges keep their identity and their place. */
export function edgeRole(
  e: { source: string; target: string },
  rest: boolean,
  focusId: string | null,
): { active: boolean; visible: boolean; dimmed: boolean } {
  const active = focusId !== null && (e.source === focusId || e.target === focusId);
  return { active, visible: rest || active, dimmed: focusId !== null && !active };
}

/** The focused node and the nodes one edge away from it (every edge, drawn or not); null with
 * no focus. */
export function neighbourhood(edges: MapEdge[], focusId: string | null): Set<string> | null {
  if (focusId === null) return null;
  const ids = new Set([focusId]);
  for (const e of edges) {
    if (e.source === focusId) ids.add(e.target);
    if (e.target === focusId) ids.add(e.source);
  }
  return ids;
}

/** What the canvas says about the edges it leaves out; null when it leaves out none. */
export function densityCaption(selection: EdgeSelection, showAll: boolean): string | null {
  if (selection.mode === "all") return null;
  if (showAll) return `Showing all ${selection.total} connections.`;
  const of = `Showing ${selection.shown.length} of ${selection.total} connections`;
  const how =
    selection.mode === "tier"
      ? `the strongest (${selection.minCount} or more dependencies each)`
      : "a sample, as they are all equally strong";
  return `${of}, ${how}. Hover or select a node to see all of its connections.`;
}

// --- cycles --------------------------------------------------------------------------------

/** True only when something in this very view is part of a circular import. `view.cycles` lists
 * the whole repo, so it says nothing about what is on screen. Never true when cycles are not
 * known yet (the caption then says nothing at all). */
export function viewHasCycle(view: MapView): boolean {
  if (!view.cycles_available) return false;
  if (view.level === "symbol") return view.file?.in_cycle === true;
  return view.nodes.some((n) => n.in_cycle === true) || view.edges.some(isCycleEdge);
}

export const CYCLE_CAPTION = "Circular imports (top-level imports only)";

// --- node text -----------------------------------------------------------------------------

/** "12 files · 5 findings". A count of findings is a number, never a verdict, so none is shown
 * when there are none. */
export function nodeSummary(n: MapNode): string {
  const parts: string[] = [];
  if (n.kind === "folder" || n.kind === "more") parts.push(plural(n.file_count ?? 0, "file"));
  if (n.finding_count > 0) parts.push(plural(n.finding_count, "finding"));
  return parts.join(" · ");
}

/** "↑ 4 in · 2 out": edges that cross the view's boundary at this node. Null when none do. */
export function boundaryText(n: MapNode): string | null {
  const inside = n.outside_in ?? 0;
  const out = n.outside_out ?? 0;
  return inside + out > 0 ? `↑ ${inside} in · ${out} out` : null;
}

export function boundaryTitle(n: MapNode): string {
  return (
    `${plural(n.outside_in ?? 0, "dependency")} from outside this view into it · ` +
    `${plural(n.outside_out ?? 0, "dependency")} from it to outside this view`
  );
}

/** Hover text for a node: what it is and what it holds, not its name again. */
export function nodeTooltip(n: MapNode, level: "folder" | "file" | "symbol"): string {
  const lines: string[] = [];
  if (n.kind === "more") {
    return level === "symbol"
      ? `${plural(n.hidden_count ?? 0, "more symbol")} are not drawn: this view shows the 60 best connected.`
      : `${plural(n.hidden_count ?? 0, "item")} not drawn, ${plural(n.file_count ?? 0, "file")} in all.\nClick to open them in List view.`;
  }
  if (n.kind === "folder") {
    lines.push(`${n.path}/`);
    const parts = [plural(n.file_count ?? 0, "file")];
    if (n.test_file_count) parts.push(`${n.test_file_count} of them tests or examples`);
    if (n.finding_count) parts.push(plural(n.finding_count, "finding"));
    lines.push(parts.join(" · "));
  } else if (n.kind === "file") {
    lines.push(n.path);
    const parts = [languageName(n.language), n.loc != null ? plural(n.loc, "line") : ""].filter(Boolean);
    if (n.finding_count) parts.push(plural(n.finding_count, "finding"));
    if (n.external_imports) parts.push(`${plural(n.external_imports, "external import")}`);
    lines.push(parts.join(" · "));
  } else {
    lines.push(n.qualified_name ?? n.label);
    const where = n.start_line != null ? `${n.path}:${n.start_line}-${n.end_line}` : n.path;
    lines.push(`${n.kind} · ${where}`);
    if (n.finding_count) lines.push(plural(n.finding_count, "finding"));
  }
  if (level !== "symbol") {
    const crossing = boundaryText(n);
    if (crossing) lines.push(`${crossing}: ${boundaryTitle(n)}`);
  }
  if (n.in_cycle === true) lines.push("Part of a circular import (top-level imports only).");
  return lines.join("\n");
}

function languageName(language: string | undefined): string {
  if (language === "python") return "Python";
  if (language === "typescript") return "TypeScript";
  if (language === "javascript") return "JavaScript";
  return language ?? "";
}

/** The note beside the toolbar: what is on the canvas and what is hidden. */
export function viewNote(view: MapView): string {
  const parts: string[] = [];
  if (view.level === "symbol") {
    const own = view.nodes.filter((n) => n.own).length;
    const others = view.nodes.filter((n) => n.kind !== "more" && !n.own).length;
    parts.push(plural(own, "symbol") + " here");
    if (others) parts.push(`${plural(others, "neighbour")} in other files`);
    if (view.hidden_symbols) {
      parts.push(`${plural(view.hidden_symbols, "neighbour")} in test or example files hidden`);
    }
    return parts.join(" · ");
  }
  if (view.level === "folder") {
    const folders = view.nodes.filter((n) => n.kind === "folder").length;
    const files = view.nodes.filter((n) => n.kind === "file").length;
    if (folders) parts.push(plural(folders, "folder"));
    if (files) parts.push(plural(files, "file"));
    if (view.hidden_count) parts.push(`${view.hidden_count} more not drawn`);
  } else {
    const total = view.nodes.reduce((sum, n) => sum + (n.kind === "more" ? (n.file_count ?? 0) : 1), 0);
    parts.push(plural(total, "file"));
    if (view.hidden_count) parts.push(`${view.hidden_count} not drawn`);
  }
  const hidden = view.hidden_files_under_root ?? 0;
  if (hidden) parts.push(`${plural(hidden, "test or example file")} hidden here`);
  return parts.join(" · ");
}

/** Shown on a canvas with no nodes: why, and what to do. */
export function emptyViewMessage(view: MapView): { text: string; hiddenFiles: number } {
  const hidden = view.hidden_files_under_root ?? 0;
  return hidden > 0
    ? {
        text: `${plural(hidden, "test or example file")} hidden here. Turn on “Show tests & examples” to see ${hidden === 1 ? "it" : "them"}.`,
        hiddenFiles: hidden,
      }
    : { text: "No Python or JavaScript/TypeScript files here.", hiddenFiles: 0 };
}

/** Is this file one of the view's own nodes? A file inside a folder node is not drawn itself. */
export function isDrawn(view: MapView, path: string): boolean {
  return view.nodes.some((n) =>
    view.level === "symbol" ? n.path === path : n.kind !== "more" && n.path === path,
  );
}
