// @vitest-environment jsdom
import { act, useRef } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { type Edges, edgesOf, useScrollEdges } from "./scrollEdges";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// @ts-expect-error node:fs has no type declarations here; the tests run in Node
const { readFileSync } = await import("node:fs");
// @ts-expect-error process has no type declarations here; the tests run in Node
const css: string = readFileSync(`${process.cwd()}/src/styles.css`, "utf8");

describe("scroll edges", () => {
  it("say where there is more content", () => {
    expect(edgesOf(0, 300, 300)).toEqual({ top: false, bottom: false }); // all in view: no fades
    expect(edgesOf(0, 300, 442)).toEqual({ top: false, bottom: true }); // at the top
    expect(edgesOf(70, 300, 442)).toEqual({ top: true, bottom: true }); // in the middle
    expect(edgesOf(142, 300, 442)).toEqual({ top: true, bottom: false }); // at the end
    expect(edgesOf(141.5, 300, 442)).toEqual({ top: true, bottom: false }); // fractional positions
  });

  it("the fades come from the panel's own ground token and never take the pointer", () => {
    expect(css).toMatch(/\.scroll-fade-top \{[^}]*linear-gradient\(to bottom, var\(--bg\), transparent\)/);
    expect(css).toMatch(/\.scroll-fade-bottom \{[^}]*linear-gradient\(to top, var\(--bg\), transparent\)/);
    expect(css).toMatch(/\.scroll-fade \{[^}]*pointer-events: none/);
    // Their only motion is an opacity transition, which the reduced-motion rule makes instant.
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\) \{\s*\*,\s*\*::before,\s*\*::after \{\s*transition-duration: 0\.01ms !important;/);
  });
});

let host: HTMLDivElement;
let root: Root;
let edges: Edges = { top: false, bottom: false };
let el: HTMLDivElement | null = null;
function Probe() {
  const ref = useRef<HTMLDivElement>(null);
  edges = useScrollEdges(ref);
  return (
    <div
      ref={(node) => {
        ref.current = node;
        el = node;
      }}
    />
  );
}
beforeEach(() => {
  host = document.createElement("div");
  root = createRoot(host);
});
afterEach(() => act(() => root.unmount()));

describe("useScrollEdges", () => {
  it("follows scrolling", () => {
    act(() => root.render(<Probe />));
    const node = el!;
    Object.defineProperty(node, "clientHeight", { value: 300, configurable: true });
    Object.defineProperty(node, "scrollHeight", { value: 442, configurable: true });
    node.scrollTop = 0;
    act(() => node.dispatchEvent(new Event("scroll")));
    expect(edges).toEqual({ top: false, bottom: true });
    node.scrollTop = 142;
    act(() => node.dispatchEvent(new Event("scroll")));
    expect(edges).toEqual({ top: true, bottom: false });
  });
});
