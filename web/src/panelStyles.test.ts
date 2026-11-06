// The side panel's layout rules, read from the stylesheet: a regression here is only visible in a
// real browser (the code ran over the line numbers in Firefox), so pin the declarations.
import { describe, expect, it } from "vitest";

// Vitest returns an empty string for `styles.css?raw`, and there are no Node types in this project,
// so read the file with Node directly.
// @ts-expect-error node:fs has no type declarations here; the tests run in Node
const { readFileSync } = await import("node:fs");
const css: string = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

/** The declarations of the first rule whose selector is exactly `selector`. */
function rule(selector: string): string {
  const start = css.indexOf(`\n${selector} {`);
  if (start === -1) throw new Error(`no rule for ${selector}`);
  const open = css.indexOf("{", start);
  return css.slice(open + 1, css.indexOf("}", open));
}

describe("code viewer", () => {
  it("keeps the line numbers fixed on the left, opaque and above the code", () => {
    const gutter = rule(".code-gutter");
    expect(gutter).toMatch(/position:\s*sticky/);
    expect(gutter).toMatch(/left:\s*0/);
    expect(gutter).toMatch(/background:\s*var\(--surface\)/);
    const z = Number(gutter.match(/z-index:\s*(\d+)/)?.[1]);
    expect(z).toBeGreaterThanOrEqual(1);
  });

  it("the code and the highlight sit below the gutter", () => {
    expect(css).toMatch(/\.code-text \{\s*position:\s*relative/);
    expect(rule(".code-highlight")).not.toMatch(/z-index/);
  });
});

describe("panel height", () => {
  it("fits the canvas area and scrolls the code inside, both ways", () => {
    expect(rule(".panel")).toMatch(/max-height:\s*100%/);
    expect(rule(".panel")).toMatch(/overflow:\s*hidden/);
    const body = rule(".panel-body");
    expect(body).toMatch(/flex:\s*1/);
    expect(body).toMatch(/min-height:\s*0/);
    expect(body).toMatch(/overflow:\s*auto/);
  });
});

describe("panel title", () => {
  it("is cut with an ellipsis on one line per part, never broken in a name", () => {
    expect(rule(".panel-title-path")).toMatch(/overflow-wrap:\s*normal/);
    for (const part of [".panel-title-dir", ".panel-title-name"]) {
      const r = rule(part);
      expect(r).toMatch(/text-overflow:\s*ellipsis/);
      expect(r).toMatch(/white-space:\s*nowrap/);
    }
  });
});

describe("map tooltips", () => {
  it("edge count labels take the pointer, so hovering one shows the tooltip", () => {
    expect(rule(".edge-label")).toMatch(/pointer-events:\s*all/);
  });

  it("edges take the pointer although React Flow marks them inactive", () => {
    expect(rule(".canvas-flow .react-flow__edge.inactive")).toMatch(/pointer-events:\s*visibleStroke/);
  });

  it("the tooltip itself never takes the pointer", () => {
    expect(rule(".map-tip")).toMatch(/pointer-events:\s*none/);
  });
});
