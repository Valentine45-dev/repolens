// The Explorer's legend and status words, built from the real edge selection. Only wording lives
// here: which edges are drawn is mapModel.ts selectEdges, unchanged and only read.
import { type EdgeSelection, isCycleEdge } from "./mapModel";

/** Line 1 of the map legend: what a solid line, its number and its width mean. */
export const MAP_SOLID = "Import or call, arrow to the one used · number = how many · thicker = more";
/** Line 1 of the flat graph's legend (one edge per import or call, no counts). */
export const FLAT_SOLID = "Import or call, arrow to the file used";

/** The dashed sample. A map edge is dashed when most of its connections are guesses; a flat edge
 * when it is one guess. Says "guess" whether guesses are shown or hidden. */
export function dashedText(level: "map" | "flat", showGuesses: boolean): string {
  const what = level === "map" ? "Mostly guesses" : "Guess";
  return showGuesses ? `${what} (calls matched by name only)` : `${what} (hidden; turn on “Guessed calls”)`;
}

/** What the canvas leaves out, or null when every connection is drawn. */
export function densityText(selection: EdgeSelection, showAll: boolean): string | null {
  if (selection.mode === "all") return null;
  if (showAll) return `Showing all ${selection.total} connections.`;
  const shown = selection.shown.length;
  const of = `of ${selection.total} connections`;
  let what: string;
  if (selection.mode === "tier") {
    // Circular-import edges are always drawn, even when weaker than the tiers that fit.
    const minCount = selection.minCount ?? 0;
    const extraCycles = selection.shown.some((e) => isCycleEdge(e) && e.count < minCount);
    what = extraCycles
      ? `Showing ${shown} ${of}: the strongest (${minCount} or more each) and every circular import.`
      : `Showing the ${shown} strongest ${of} (${minCount} or more each).`;
  } else {
    // Sample mode: even the strongest group (equal count) has more edges than the budget.
    what = `Showing ${shown} ${of}, a sample: more of them tie for strongest than fit.`;
  }
  return `${what} Hover or select a node to see all of its connections.`;
}

export const ZOOMED_TEXT = "Zoomed in so names stay readable; drag to move.";
export const FIT_TEXT = "Fit shows the whole map.";

/** Line 2 under the legend, or null when it has nothing to say (then it is not drawn at all). */
export function statusText(density: string | null, zoomedIn: boolean): string | null {
  const parts = [density, zoomedIn ? ZOOMED_TEXT : null].filter(Boolean);
  return parts.length ? `${parts.join(" ")} ${FIT_TEXT}` : null;
}
