// What the Explorer draws at rest in each map view, computed by the web app's own code: the same
// call Explore.tsx makes, selectEdges(view.edges, edgeBudgetFor(view.nodes.length)), imported from
// web/src/mapModel.ts by Node's type stripping (no re-implementation). Run by ui_drawn_counts.py:
//   node --experimental-strip-types --no-warnings eval/ui_drawn_counts.mjs views.json
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { edgeBudgetFor, edgeKey, isDashed, selectEdges } from "../web/src/mapModel.ts";

const views = JSON.parse(readFileSync(process.argv[2], "utf8"));
const out = views.map((v) => {
  const budget = edgeBudgetFor(v.node_count);
  const s = selectEdges(v.edges, budget);
  const keys = s.shown.map((e) => edgeKey(e)).sort();
  return {
    id: v.id,
    nodes: v.node_count,
    budget,
    edges_total: s.total,
    edges_drawn: s.shown.length,
    dashed_drawn: s.shown.filter(isDashed).length,
    mode: s.mode,
    min_count: s.minCount,
    drawn_sha1: createHash("sha1").update(keys.join("\n")).digest("hex"),
  };
});
console.log(JSON.stringify({ views: out }));
