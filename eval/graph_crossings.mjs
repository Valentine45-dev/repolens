// Edge crossings of the folder-map UI, before and after a layout or budget change. Loads the
// layout and edge-density code of two checkouts (--old and --new, each a web/src folder), lays out
// every view in the dump from eval/graph_crossings.py with each, and counts crossings with the
// same yardstick (edgeMetrics in web/src/mapLayout.ts of --new). Needs Node 22.6+ (type stripping).
//
//   node --experimental-strip-types eval/graph_crossings.mjs views.json --old DIR --new DIR
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const argv = process.argv.slice(2);
const flag = (name) => argv[argv.indexOf(`--${name}`) + 1];
const views = JSON.parse(readFileSync(argv[0], "utf8"));
const load = async (dir) => ({
  layout: await import(pathToFileURL(resolve(dir, "mapLayout.ts")).href),
  model: await import(pathToFileURL(resolve(dir, "mapModel.ts")).href),
});
const OLD = await load(flag("old"));
const NEW = await load(flag("new"));
const { edgeMetrics } = NEW.layout;
const FIXED_BUDGET = argv.includes("--budget") ? Number(flag("budget")) : null; // sweeps: one budget for every view

function measure(code, view, mode) {
  const level = view.level;
  const size = { width: code.layout.mapNodeWidth ? code.layout.mapNodeWidth(level) : code.layout.MAP_NODE_WIDTH, height: code.layout.mapNodeHeight(level) };
  const budget = code === OLD ? undefined : (FIXED_BUDGET ?? (code.model.edgeBudgetFor ? code.model.edgeBudgetFor(view.nodes.length) : undefined));
  const selection = budget === undefined ? code.model.selectEdges(view.edges) : code.model.selectEdges(view.edges, budget);
  const drawn = selection.shown;
  // "old" lays out with every edge; "new" lays out with the edges drawn at rest
  const positions = code.layout.layoutMap(level, view.nodes, mode === "all" ? view.edges : drawn);
  return { budget: budget ?? 40, mode: selection.mode, ...edgeMetrics(positions, drawn, size) };
}

const out = views.map((v) => ({ id: v.id, label: v.label, level: v.level, nodes: v.nodes.length, edgesTotal: v.edges.length, before: measure(OLD, v, "all"), after: measure(NEW, v, "resting") }));
console.log(JSON.stringify(out));
