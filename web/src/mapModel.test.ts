import { describe, expect, it } from "vitest";

import type { MapEdge, MapNode, MapView } from "./api";
import { exploreHref, findingsHref } from "./links";
import { layoutMap, MAP_NODE_WIDTH, mapNodeHeight } from "./mapLayout";
import {
  boundaryText,
  crumbChanges,
  CYCLE_CAPTION,
  densityCaption,
  edgeKey,
  edgeRole,
  edgeSplit,
  edgeWidth,
  EDGE_BUDGET,
  emptyViewMessage,
  neighbourhood,
  restingEdges,
  isDashed,
  isDrawn,
  nodeAction,
  nodeTooltip,
  nodeSummary,
  navigateChanges,
  paramsWith,
  parseViewParams,
  resolveView,
  selectEdges,
  showEdgeLabel,
  START_FILE_LIMIT,
  startLevel,
  upChanges,
  viewFolder,
  viewHasCycle,
  viewNote,
} from "./mapModel";

function edge(source: string, target: string, over: Partial<MapEdge> = {}): MapEdge {
  return {
    source,
    target,
    count: 1,
    imports: 1,
    calls: 0,
    guess_calls: 0,
    confidence: 1,
    guess: false,
    cycle_edges: 0,
    ...over,
  };
}

function node(id: string, over: Partial<MapNode> = {}): MapNode {
  return { id, kind: "folder", path: id, label: id, finding_count: 0, file_count: 1, ...over };
}

function view(over: Partial<MapView> = {}): MapView {
  return {
    snapshot_id: 1,
    level: "folder",
    root: "",
    breadcrumbs: [{ path: "", label: "" }],
    view_limit: 60,
    total_files: 100,
    hidden_files: 0,
    hidden_files_under_root: 0,
    hidden_count: 0,
    cycle_scope: "top_level_imports",
    cycles_available: true,
    cycles: [],
    nodes: [],
    edges: [],
    ...over,
  };
}

describe("aggregated edge display", () => {
  it("shows the split, so a dashed edge does not hide its solid imports", () => {
    // express test -> lib at 0.5: 161 = 6 imports + 155 calls, 152 of them guesses
    const e = edge("dir:test", "dir:lib", { count: 161, imports: 6, calls: 155, guess_calls: 152 });
    expect(edgeSplit(e)).toBe("6 imports · 155 calls (152 guesses)");
  });

  it("says 1 import / 1 call / 1 guess in the singular", () => {
    expect(edgeSplit(edge("a", "b"))).toBe("1 import");
    expect(edgeSplit(edge("a", "b", { count: 1, imports: 0, calls: 1, guess_calls: 1 }))).toBe(
      "1 call (1 guess)",
    );
  });

  it("leaves the guess note off when no call is a guess", () => {
    const e = edge("a", "b", { count: 7, imports: 2, calls: 5 });
    expect(edgeSplit(e)).toBe("2 imports · 5 calls");
  });

  it("describes symbol edges by type", () => {
    expect(edgeSplit(edge("s1", "s2", { type: "defines" }))).toBe("defines (class to method)");
    expect(edgeSplit(edge("s1", "s2", { type: "calls", guess: true }))).toBe("calls (best guess)");
    expect(edgeSplit(edge("s1", "s2", { type: "calls" }))).toBe("calls");
  });

  it("thickens with the count on a log scale, capped", () => {
    expect(edgeWidth(1)).toBeCloseTo(1.25);
    expect(edgeWidth(10)).toBeGreaterThan(edgeWidth(2));
    expect(edgeWidth(161)).toBeLessThanOrEqual(5);
    expect(edgeWidth(1_000_000)).toBe(5);
  });
});

describe("guess styling", () => {
  it("is dashed when most of the connections are guesses, even though the API's guess is false", () => {
    const e = edge("a", "b", { count: 161, imports: 6, calls: 155, guess_calls: 152, guess: false });
    expect(isDashed(e)).toBe(true);
  });

  it("is dashed when every underlying edge is a guess", () => {
    expect(isDashed(edge("a", "b", { guess: true, count: 3, imports: 0, calls: 3, guess_calls: 3 }))).toBe(true);
  });

  it("stays solid when guesses are a minority", () => {
    expect(isDashed(edge("a", "b", { count: 10, imports: 2, calls: 8, guess_calls: 3 }))).toBe(false);
    expect(isDashed(edge("a", "b", { count: 10, imports: 5, calls: 5, guess_calls: 5 }))).toBe(false);
  });

  it("follows `guess` for symbol edges", () => {
    expect(isDashed(edge("s1", "s2", { type: "calls", guess: true }))).toBe(true);
    expect(isDashed(edge("s1", "s2", { type: "calls", guess: false }))).toBe(false);
  });
});

describe("edge density", () => {
  const many = (n: number, count: (i: number) => number): MapEdge[] =>
    Array.from({ length: n }, (_, i) => edge(`n${i}`, `m${i}`, { count: count(i) }));

  it("draws everything up to the budget", () => {
    const edges = many(EDGE_BUDGET, () => 1);
    const s = selectEdges(edges);
    expect(s.mode).toBe("all");
    expect(s.shown).toHaveLength(EDGE_BUDGET);
    expect(densityCaption(s, false)).toBeNull();
  });

  it("keeps whole tiers: edges of equal count are never split", () => {
    // flask src/flask shape: a few strong edges, a long tail of count-1 edges
    const counts = [6, 6, 5, 5, ...Array(16).fill(2), ...Array(60).fill(1)];
    const edges = counts.map((c, i) => edge(`n${i}`, `m${i}`, { count: c }));
    const s = selectEdges(edges);
    expect(s.mode).toBe("tier");
    expect(s.minCount).toBe(2);
    expect(s.shown).toHaveLength(20); // 4 + 16; adding the 60 count-1 edges would pass 40
    expect(s.shown.every((e) => e.count >= 2)).toBe(true);
    expect(s.total).toBe(80);
  });

  it("a tier that would pass the budget is left out entirely, not cut in half", () => {
    const edges = [...many(30, () => 3), ...many(30, () => 2)];
    const s = selectEdges(edges);
    expect(s.shown).toHaveLength(30);
    expect(s.shown.every((e) => e.count === 3)).toBe(true);
  });

  it("falls back to a labelled sample when even the first tier is too big", () => {
    // a symbol view: every connection counts 1
    const edges = [
      ...Array.from({ length: 60 }, (_, i) =>
        edge(`s${i}`, `t${i}`, { type: "defines", count: 1, guess: false }),
      ),
      ...Array.from({ length: 60 }, (_, i) =>
        edge(`u${i}`, `v${i}`, { type: "calls", count: 1, guess: i % 2 === 0 }),
      ),
    ];
    const s = selectEdges(edges);
    expect(s.mode).toBe("sample");
    expect(s.shown).toHaveLength(EDGE_BUDGET);
    // calls before defines, solid before guesses: 30 solid calls, then 10 of the 30 guesses
    expect(s.shown.every((e) => e.type === "calls")).toBe(true);
    expect(s.shown.filter((e) => !e.guess)).toHaveLength(30);
    expect(s.shown.filter((e) => e.guess)).toHaveLength(10);
    expect(densityCaption(s, false)).toBe(
      "Showing 40 of 120 connections, a sample, as they are all equally strong. Hover or select a node to see all of its connections.",
    );
  });

  it("always draws circular-import edges on top of the budget", () => {
    const cycle = edge("a", "b", { count: 1, cycle_edges: 1 });
    const edges = [...many(80, () => 5), cycle];
    const s = selectEdges(edges);
    expect(s.shown).toContain(cycle);
    expect(s.shown.length).toBeLessThanOrEqual(EDGE_BUDGET + 1);
  });

  it("says what it draws, in words", () => {
    const edges = [...many(10, () => 4), ...many(60, () => 1)];
    const s = selectEdges(edges);
    expect(densityCaption(s, false)).toBe(
      "Showing 10 of 70 connections, the strongest (4 or more dependencies each). Hover or select a node to see all of its connections.",
    );
    expect(densityCaption(s, true)).toBe("Showing all 70 connections.");
  });

  it("draws every edge of the focused node on top of the resting set, and all edges on request", () => {
    const edges = [...many(10, () => 4), ...many(60, () => 1)];
    const s = selectEdges(edges);
    const rest = restingEdges(edges, s, false);
    expect(rest.size).toBe(10);
    expect(restingEdges(edges, s, true).size).toBe(70);
    const hidden = edges.filter((e) => e.count === 1)[30]; // n30: not an end of a resting edge
    // nothing focused: only the resting edges are visible
    expect(edges.filter((e) => edgeRole(e, rest.has(e), null).visible)).toHaveLength(10);
    // focus a node whose edge is not at rest: that edge appears, active, and the rest dim
    const visible = edges.filter((e) => edgeRole(e, rest.has(e), hidden.source).visible);
    expect(visible).toHaveLength(11);
    expect(edgeRole(hidden, false, hidden.source)).toEqual({ active: true, visible: true, dimmed: false });
    expect(edgeRole(edges[0], true, hidden.source)).toEqual({ active: false, visible: true, dimmed: true });
    expect(edgeRole(edges[0], true, null)).toEqual({ active: false, visible: true, dimmed: false });
  });

  it("an edge's identity does not depend on focus, so hover never replaces it", () => {
    const e = edge("a", "b", { type: "calls" });
    expect(edgeKey(e)).toBe("a>b:calls");
    expect(edgeKey(edge("a", "b"))).toBe("a>b");
  });

  it("the neighbourhood is the focused node and what is one edge away, from every edge", () => {
    const edges = [edge("a", "b"), edge("c", "a"), edge("d", "e")];
    expect(neighbourhood(edges, null)).toBeNull();
    expect([...neighbourhood(edges, "a")!].sort()).toEqual(["a", "b", "c"]);
  });

  it("labels every edge when few are drawn, only the strong ones when many are", () => {
    expect(showEdgeLabel(1, 12, false)).toBe(true);
    expect(showEdgeLabel(1, 13, false)).toBe(false);
    expect(showEdgeLabel(2, 40, false)).toBe(true);
    expect(showEdgeLabel(1, 40, true)).toBe(true);
  });
});

describe("start rule", () => {
  const files = (n: number) => ({
    nodes: Array.from({ length: n }, (_, i) => ({ id: i + 1, path: `src/pkg/f${i}.py` })),
  });

  it("opens files at 30 or fewer visible files, folders above", () => {
    expect(startLevel(START_FILE_LIMIT)).toBe("file");
    expect(startLevel(START_FILE_LIMIT + 1)).toBe("folder");
    expect(resolveView({ level: null, root: "", nodeId: null }, files(9))).toEqual({ level: "file", root: "" });
    expect(resolveView({ level: null, root: "", nodeId: null }, files(114))).toEqual({ level: "folder", root: "" });
  });

  it("waits for the file count when the URL says nothing", () => {
    expect(resolveView({ level: null, root: "", nodeId: null }, null)).toBeNull();
  });

  it("lets the URL win over the rule, without waiting for the count", () => {
    expect(resolveView({ level: "folder", root: "", nodeId: null }, null)).toEqual({ level: "folder", root: "" });
    expect(resolveView({ level: "file", root: "src", nodeId: null }, files(114))).toEqual({ level: "file", root: "src" });
    expect(resolveView({ level: "flat", root: "ignored", nodeId: null }, null)).toEqual({ level: "flat", root: "" });
    expect(resolveView({ level: null, root: "src/flask", nodeId: null }, null)).toEqual({ level: "folder", root: "src/flask" });
  });

  it("ignores level=symbol without a file", () => {
    expect(resolveView({ level: "symbol", root: "", nodeId: null }, files(114))).toEqual({ level: "folder", root: "" });
    expect(resolveView({ level: "symbol", root: "a/b.py", nodeId: null }, null)).toEqual({ level: "symbol", root: "a/b.py" });
  });
});

describe("deep links", () => {
  const flat = {
    nodes: [
      ...Array.from({ length: 40 }, (_, i) => ({ id: i + 1, path: `src/pkg/f${i}.py` })),
      { id: 99, path: "scoring/admin.py" },
    ],
  };

  it("a link to a file in a big repo opens that file's folder", () => {
    expect(resolveView({ level: null, root: "", nodeId: 99 }, flat)).toEqual({ level: "folder", root: "scoring" });
  });

  it("a file in the repo root opens the root", () => {
    const top = { nodes: [...flat.nodes, { id: 100, path: "manage.py" }] };
    expect(resolveView({ level: null, root: "", nodeId: 100 }, top)).toEqual({ level: "folder", root: "" });
  });

  it("an unknown file id (tests hidden) falls back to the start rule", () => {
    expect(resolveView({ level: null, root: "", nodeId: 12345 }, flat)).toEqual({ level: "folder", root: "" });
  });

  it("a small repo already shows the file at the root", () => {
    const small = { nodes: [{ id: 1, path: "a/b.py" }] };
    expect(resolveView({ level: null, root: "", nodeId: 1 }, small)).toEqual({ level: "file", root: "" });
  });

  it("citation chips and findings link with node= and no view, which this rule then resolves", () => {
    expect(exploreHref(7, { fileId: 99, lines: { start: 3, end: 9 }, tests: true, ask: true })).toBe(
      "/a/7/explore?node=99&lines=3-9&tests=1&ask=1",
    );
  });

  it("links to the findings under a folder, matching what the map counts", () => {
    expect(findingsHref(7, { path: "src/flask", folder: true, hideTests: true })).toBe(
      "/a/7/findings?path=src%2Fflask%2F&tests=hide",
    );
    expect(findingsHref(7, { path: "a/b.py", folder: false, hideTests: false })).toBe(
      "/a/7/findings?path=a%2Fb.py",
    );
    expect(findingsHref(7, { path: "", folder: true, hideTests: false })).toBe("/a/7/findings");
  });
});

describe("URL state", () => {
  it("round-trips level and root, dropping what a new view makes stale", () => {
    const search = "?tests=1&guesses=1&node=5&lines=3-4&ask=1";
    const next = paramsWith(search, navigateChanges("folder", "src/flask"));
    const parsed = new URLSearchParams(next);
    expect(parseViewParams(parsed)).toEqual({ level: "folder", root: "src/flask" });
    expect(parsed.get("tests")).toBe("1");
    expect(parsed.get("guesses")).toBe("1");
    expect(parsed.get("ask")).toBe("1");
    expect(parsed.has("node")).toBe(false);
    expect(parsed.has("lines")).toBe(false);
  });

  it("the repo root and the flat level carry no root", () => {
    expect(new URLSearchParams(paramsWith("?root=src", navigateChanges("folder", ""))).has("root")).toBe(false);
    expect(new URLSearchParams(paramsWith("?root=src", navigateChanges("flat", "src"))).has("root")).toBe(false);
  });

  it("reads only known levels and trims slashes", () => {
    expect(parseViewParams(new URLSearchParams("level=bogus&root=/src/"))).toEqual({ level: null, root: "src" });
    expect(parseViewParams(new URLSearchParams(""))).toEqual({ level: null, root: "" });
  });

  it("an empty query string stays empty", () => {
    expect(paramsWith("?level=folder", { level: null })).toBe("");
  });
});

describe("breadcrumbs and Up", () => {
  const crumbs = [
    { path: "", label: "" },
    { path: "src/itsdangerous", label: "src/itsdangerous" },
  ];

  it("a crumb opens as a folder, or as files in a file view", () => {
    expect(crumbChanges({ level: "folder", breadcrumbs: crumbs }, 0)).toEqual({
      level: "folder", root: null, node: null, lines: null,
    });
    expect(crumbChanges({ level: "file", breadcrumbs: crumbs }, 1)).toEqual({
      level: "file", root: "src/itsdangerous", node: null, lines: null,
    });
  });

  it("Up goes to the previous crumb, and is null at the repo", () => {
    expect(upChanges({ level: "folder", breadcrumbs: crumbs })).toEqual(
      crumbChanges({ level: "folder", breadcrumbs: crumbs }, 0),
    );
    expect(upChanges({ level: "folder", breadcrumbs: [crumbs[0]] })).toBeNull();
  });

  it("in a symbol view Up leaves the file for its folder, and the last crumb is the file", () => {
    const symbol = {
      level: "symbol" as const,
      root: "src/itsdangerous/signer.py",
      breadcrumbs: [...crumbs, { path: "src/itsdangerous/signer.py", label: "signer.py" }],
    };
    expect(upChanges(symbol)).toMatchObject({ level: "folder", root: "src/itsdangerous" });
    expect(crumbChanges(symbol, 2)).toMatchObject({ level: "symbol", root: "src/itsdangerous/signer.py" });
    expect(viewFolder(symbol)).toBe("src/itsdangerous");
    expect(viewFolder({ level: "folder", root: "src", breadcrumbs: crumbs })).toBe("src");
  });
});

describe("clicks", () => {
  it("a folder opens", () => {
    expect(nodeAction("folder", node("dir:src/flask", { path: "src/flask" }))).toEqual({
      type: "open", level: "folder", root: "src/flask",
    });
  });

  it("a file opens its panel", () => {
    expect(nodeAction("folder", node("file:a.py", { kind: "file", file_id: 4 }))).toEqual({
      type: "select", fileId: 4, lines: null,
    });
  });

  it("a symbol opens its file on its lines", () => {
    const sym = node("sym:1", { kind: "function", file_id: 4, start_line: 10, end_line: 22 });
    expect(nodeAction("symbol", sym)).toEqual({ type: "select", fileId: 4, lines: { start: 10, end: 22 } });
    expect(nodeAction("symbol", node("sym:2", { kind: "module", file_id: 4, start_line: 1, end_line: 99 }))).toEqual({
      type: "select", fileId: 4, lines: null,
    });
  });

  it("'N more' opens List view for its folder, and does nothing in a symbol view", () => {
    const more = node("more:test", { kind: "more", path: "test", label: "13 more" });
    expect(nodeAction("folder", more)).toEqual({ type: "list", root: "test" });
    expect(nodeAction("file", more)).toEqual({ type: "list", root: "test" });
    expect(nodeAction("symbol", more)).toEqual({ type: "none" });
  });
});

describe("cycle highlighting comes from the view's own data", () => {
  const cycles = [{ id: 1, size: 2, files: ["a.py", "b.py"] }];

  it("is true for a node in a cycle", () => {
    expect(viewHasCycle(view({ nodes: [node("file:a.py", { in_cycle: true })], cycles }))).toBe(true);
  });

  it("is true for an edge that is part of a cycle", () => {
    expect(viewHasCycle(view({ nodes: [node("a")], edges: [edge("a", "b", { cycle_edges: 2 })] }))).toBe(true);
  });

  it("two folders that use each other are not a cycle", () => {
    // PyGoat: challenge -> scoring (10) and scoring -> challenge (2)
    const v = view({
      nodes: [node("dir:challenge", { in_cycle: false }), node("dir:scoring", { in_cycle: false })],
      edges: [edge("dir:challenge", "dir:scoring", { count: 10 }), edge("dir:scoring", "dir:challenge", { count: 2 })],
    });
    expect(viewHasCycle(v)).toBe(false);
  });

  it("the repo-wide `cycles` list alone says nothing about this view", () => {
    // flask src/flask with everything shown: one cycle in the repo, none on screen
    expect(viewHasCycle(view({ nodes: [node("dir:json", { in_cycle: false })], cycles }))).toBe(false);
  });

  it("says nothing when cycles are not known yet (never 'no cycles')", () => {
    const v = view({
      cycles_available: false,
      nodes: [node("a", { in_cycle: null })],
      edges: [edge("a", "b", { cycle_edges: null })],
    });
    expect(viewHasCycle(v)).toBe(false);
  });

  it("a symbol view follows its file", () => {
    const base = { level: "symbol" as const, nodes: [] };
    const file = { file_id: 1, path: "a.py", finding_count: 0 };
    expect(viewHasCycle(view({ ...base, file: { ...file, in_cycle: true } }))).toBe(true);
    expect(viewHasCycle(view({ ...base, file: { ...file, in_cycle: false } }))).toBe(false);
    expect(viewHasCycle(view({ ...base, file: { ...file, in_cycle: null } }))).toBe(false);
  });

  it("the caption is the agreed words", () => {
    expect(CYCLE_CAPTION).toBe("Circular imports (top-level imports only)");
  });
});

describe("node text", () => {
  it("counts files and findings as plain numbers, and says nothing about zero findings", () => {
    expect(nodeSummary(node("dir:a", { file_count: 12, finding_count: 5 }))).toBe("12 files · 5 findings");
    expect(nodeSummary(node("dir:a", { file_count: 1, finding_count: 1 }))).toBe("1 file · 1 finding");
    expect(nodeSummary(node("dir:a", { file_count: 8, finding_count: 0 }))).toBe("8 files");
    expect(nodeSummary(node("file:a.py", { kind: "file", finding_count: 0 }))).toBe("");
  });

  it("shows boundary counts only when something crosses the view", () => {
    expect(boundaryText(node("a", { outside_in: 4, outside_out: 2 }))).toBe("↑ 4 in · 2 out");
    expect(boundaryText(node("a", { outside_in: 0, outside_out: 0 }))).toBeNull();
  });
});

describe("notes", () => {
  it("says how many test or example files are hidden here", () => {
    const v = view({
      nodes: [node("dir:a"), node("dir:b"), node("file:c.py", { kind: "file" })],
      hidden_files_under_root: 6,
    });
    expect(viewNote(v)).toBe("2 folders · 1 file · 6 test or example files hidden here");
  });

  it("an empty folder explains itself and offers the hidden files", () => {
    expect(emptyViewMessage(view({ hidden_files_under_root: 3 }))).toEqual({
      text: "3 test or example files hidden here. Turn on “Show tests & examples” to see them.",
      hiddenFiles: 3,
    });
    expect(emptyViewMessage(view()).hiddenFiles).toBe(0);
  });

  it("knows whether a file is one of the view's own nodes", () => {
    const v = view({ nodes: [node("dir:src", { path: "src" }), node("file:a.py", { kind: "file", path: "a.py" })] });
    expect(isDrawn(v, "a.py")).toBe(true);
    expect(isDrawn(v, "src/b.py")).toBe(false);
  });
});

describe("layout", () => {
  it("gives every node a place and keeps nodes apart", () => {
    const nodes = Array.from({ length: 58 }, (_, i) => node(`file:t${i}`, { kind: "file" }));
    nodes.push(node("dir:acceptance"), node("dir:support"));
    const edges = [edge("dir:acceptance", "dir:support")];
    const pos = layoutMap("folder", nodes, edges);
    expect(pos.size).toBe(nodes.length);
    const h = mapNodeHeight("folder");
    const list = [...pos.values()];
    for (let i = 0; i < list.length; i++) {
      for (let j = i + 1; j < list.length; j++) {
        const apart =
          Math.abs(list[i].x - list[j].x) >= MAP_NODE_WIDTH || Math.abs(list[i].y - list[j].y) >= h;
        expect(apart).toBe(true);
      }
    }
  });

  it("puts nodes with no connection in a block, not a tall strip", () => {
    const nodes = Array.from({ length: 58 }, (_, i) => node(`file:t${i}`, { kind: "file" }));
    const pos = layoutMap("folder", nodes, []);
    const xs = new Set([...pos.values()].map((p) => p.x));
    const ys = new Set([...pos.values()].map((p) => p.y));
    expect(xs.size).toBeGreaterThanOrEqual(4);
    expect(xs.size).toBeLessThanOrEqual(8);
    expect(ys.size).toBeLessThanOrEqual(15);
  });

  it("ignores edges to nodes that are not in the view", () => {
    const pos = layoutMap("folder", [node("a")], [edge("a", "missing")]);
    expect(pos.size).toBe(1);
  });
});

describe("node tooltips say something the label does not", () => {
  it("a folder: path, files, tests, findings and what crosses its edge", () => {
    const t = nodeTooltip(
      node("dir:challenge", {
        path: "challenge", file_count: 22, test_file_count: 3, finding_count: 8,
        outside_in: 4, outside_out: 2, in_cycle: false,
      }),
      "folder",
    );
    expect(t).toContain("challenge/");
    expect(t).toContain("22 files · 3 of them tests or examples · 8 findings");
    expect(t).toContain("↑ 4 in · 2 out");
    expect(t).not.toContain("circular");
  });

  it("a file: path, language, lines, findings and external imports", () => {
    const t = nodeTooltip(
      node("file:a.py", {
        kind: "file", path: "src/a.py", language: "python", loc: 120, finding_count: 1,
        external_imports: 3, outside_in: 0, outside_out: 0,
      }),
      "file",
    );
    expect(t).toBe("src/a.py\nPython · 120 lines · 1 finding · 3 external imports");
  });

  it("a symbol: qualified name, kind and where it is", () => {
    const t = nodeTooltip(
      node("sym:1", {
        kind: "method", label: "sign", qualified_name: "Signer.sign", path: "src/signer.py",
        start_line: 10, end_line: 22,
      }),
      "symbol",
    );
    expect(t).toBe("Signer.sign\nmethod · src/signer.py:10-22");
  });

  it("marks circular members and explains '+ N more'", () => {
    expect(nodeTooltip(node("file:a.py", { kind: "file", path: "a.py", in_cycle: true }), "file")).toContain(
      "circular import",
    );
    const more = node("more:test", { kind: "more", label: "13 more", hidden_count: 13, file_count: 13 });
    expect(nodeTooltip(more, "folder")).toContain("13 items not drawn, 13 files in all.");
    expect(nodeTooltip(more, "folder")).toContain("List view");
  });
});
