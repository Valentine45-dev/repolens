// Applies the web app's edge-density rule (web/src/mapModel.ts, selectEdges) to map views dumped
// by eval/graph_ui_readability.py. Run by that script; needs Node 22.6+ (type stripping):
//   node --experimental-strip-types eval/graph_ui_readability.mjs views.json
import { readFileSync } from "node:fs";
import { EDGE_BUDGET, selectEdges } from "../web/src/mapModel.ts";

const views = JSON.parse(readFileSync(process.argv[2], "utf8"));
const out = views.map((v) => {
  const s = selectEdges(v.edges);
  return { id: v.id, total_edges: s.total, drawn_edges: s.shown.length, mode: s.mode, min_count: s.minCount };
});
console.log(JSON.stringify({ budget: EDGE_BUDGET, views: out }));
