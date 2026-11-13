// Ligatures are off wherever the mono font is used (code view, paths, chips, inputs), so "!=="
// shows as three characters. font-variant-ligatures is inherited, so setting it on every rule that
// sets the font covers the text inside.
import { describe, expect, it } from "vitest";

// @ts-expect-error node:fs has no type declarations here; the tests run in Node
const { readFileSync } = await import("node:fs");
const css: string = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

describe("mono font", () => {
  it("turns ligatures off in every rule that sets it", () => {
    const rules = [...css.matchAll(/([^{}]*)\{([^{}]*)\}/g)].filter((m) => /font-family:\s*var\(--font-mono\)/.test(m[2]));
    expect(rules.length).toBeGreaterThan(10);
    for (const [, selector, body] of rules) {
      expect(body, selector.trim()).toMatch(/font-variant-ligatures:\s*none/);
    }
  });

  it("the code view and its text are among them", () => {
    const code = css.match(/\n\.code \{([^}]*)\}/)?.[1] ?? "";
    expect(code).toMatch(/font-family:\s*var\(--font-mono\)/);
    expect(code).toMatch(/font-variant-ligatures:\s*none/);
  });
});
