import { describe, expect, it } from "vitest";

import type { MapEdge } from "./api";
import { dashedText, densityText, FIT_TEXT, statusText, ZOOMED_TEXT } from "./legendText";
import { edgeBudgetFor, selectEdges } from "./mapModel";

function edge(i: number, count: number, over: Partial<MapEdge> = {}): MapEdge {
  return { source: `dir:a${i}`, target: `dir:b${i}`, count, confidence: 1, guess: false, ...over };
}

describe("legend text from the real edge selection", () => {
  it("says nothing when every connection is drawn", () => {
    const sel = selectEdges([edge(1, 3), edge(2, 1)], edgeBudgetFor(4));
    expect(sel.mode).toBe("all");
    expect(densityText(sel, false)).toBeNull();
    expect(statusText(densityText(sel, false), false)).toBeNull();
  });

  it("names the strongest tier with its real counts (flask's root: 8 of 95, 3 or more)", () => {
    // 8 edges of count 3 or more, then 87 of count 1: budget for 25 nodes is 19, so tiers 5 and 3 fit.
    const edges = [
      ...[1, 2, 3].map((i) => edge(i, 5)),
      ...[4, 5, 6, 7, 8].map((i) => edge(i, 3)),
      ...Array.from({ length: 87 }, (_, i) => edge(100 + i, 1)),
    ];
    const sel = selectEdges(edges, edgeBudgetFor(25));
    expect(sel.mode).toBe("tier");
    expect(densityText(sel, false)).toBe(
      "Showing the 8 strongest of 95 connections (3 or more each). Hover or select a node to see all of its connections.",
    );
    expect(densityText(sel, true)).toBe("Showing all 95 connections.");
  });

  it("says when circular-import edges are drawn below the strongest tier", () => {
    const edges = [
      ...Array.from({ length: 10 }, (_, i) => edge(i, 4)),
      edge(50, 1, { cycle_edges: 1 }),
      ...Array.from({ length: 20 }, (_, i) => edge(100 + i, 1)),
    ];
    const sel = selectEdges(edges, 12);
    expect(sel.mode).toBe("tier");
    expect(densityText(sel, false)).toContain("Showing 11 of 31 connections: the strongest (4 or more each) and every circular import.");
  });

  it("calls a sample a sample, and says why: the strongest group alone is too big", () => {
    // 30 edges all of count 2 plus 10 of count 1; the strongest tier (30) does not fit in 12.
    const edges = [...Array.from({ length: 30 }, (_, i) => edge(i, 2)), ...Array.from({ length: 10 }, (_, i) => edge(100 + i, 1))];
    const sel = selectEdges(edges, 12);
    expect(sel.mode).toBe("sample");
    expect(densityText(sel, false)).toBe(
      "Showing 12 of 40 connections, a sample: more of them tie for strongest than fit. Hover or select a node to see all of its connections.",
    );
  });

  it("the dashed sample says guess whether guesses are shown or hidden", () => {
    for (const level of ["map", "flat"] as const) {
      for (const shown of [true, false]) expect(dashedText(level, shown).toLowerCase()).toContain("guess");
    }
    expect(dashedText("map", false)).toBe("Mostly guesses (hidden; turn on “Guessed calls”)");
  });

  it("the status line ends with the Fit hint, and only exists when there is something to say", () => {
    expect(statusText(null, false)).toBeNull();
    expect(statusText(null, true)).toBe(`${ZOOMED_TEXT} ${FIT_TEXT}`);
    expect(statusText("Showing all 9 connections.", true)).toBe(`Showing all 9 connections. ${ZOOMED_TEXT} ${FIT_TEXT}`);
  });
});
