// The skeleton shimmer: one shared sweep, moved by transform (cheap), in step across bars, themed
// from tokens, and off under reduced motion. Read from the stylesheet and index.html.
import { describe, expect, it } from "vitest";

// @ts-expect-error node:fs has no type declarations here; the tests run in Node
const { readFileSync } = await import("node:fs");
const read = (rel: string): string => readFileSync(new URL(rel, import.meta.url), "utf8");
const css = read("./styles.css");
const html = read("../index.html");

function block(start: string): string {
  const i = css.indexOf(start);
  if (i === -1) throw new Error(`no ${start}`);
  let depth = 0;
  for (let j = css.indexOf("{", i); j < css.length; j++) {
    if (css[j] === "{") depth++;
    if (css[j] === "}" && --depth === 0) return css.slice(i, j + 1);
  }
  throw new Error("unclosed");
}

describe("skeleton shimmer", () => {
  it("is one pseudo-element band moved by transform, 1.5s per sweep", () => {
    const after = block(".skeleton::after {");
    expect(after).toMatch(/animation:\s*skeleton-shimmer 1\.5s linear infinite/);
    expect(after).toMatch(/var\(--shimmer\)/);
    const keys = block("@keyframes skeleton-shimmer");
    expect(keys).toMatch(/transform:\s*translateX\(100%\)/);
    // No keyframes anywhere move a background (each @keyframes block on its own, so a rule after
    // one, such as the theme reveal's, is not read as part of it).
    const names = [...css.matchAll(/@keyframes\s+([\w-]+)/g)].map((m) => m[1]);
    expect(names).toContain("skeleton-shimmer");
    for (const name of names) expect(block(`@keyframes ${name}`)).not.toMatch(/background-position/);
  });

  it("has a light and a dark band from tokens", () => {
    expect(block(":root {")).toMatch(/--shimmer:\s*color-mix\(in srgb, var\(--bg\)/);
    expect(block(':root[data-theme="dark"] {')).toMatch(/--shimmer:\s*color-mix\(in srgb, var\(--text\) 7%/);
  });

  it("stops under reduced motion", () => {
    const reduced = block("@media (prefers-reduced-motion: reduce)");
    expect(reduced).toMatch(/\.skeleton::after \{\s*display: none;\s*animation: none;/);
  });

  it("every bar is put on the same start time, so they sweep together", () => {
    expect(html).toContain('e.animationName !== "skeleton-shimmer"');
    expect(html).toContain("a.startTime = 0");
  });
});
