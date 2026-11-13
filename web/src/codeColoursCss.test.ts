// Every colour role has a light and a dark token and a class, and every token holds 4.5:1 on the
// code background and on the cited-line band, in both themes (read from styles.css itself).
import { describe, expect, it } from "vitest";

import { ROLES } from "./codeRoles";

// @ts-expect-error node:fs has no type declarations here; the tests run in Node
const { readFileSync } = await import("node:fs");
const css: string = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

function block(selector: string): string {
  const start = css.indexOf(`${selector} {`);
  return css.slice(start, css.indexOf("\n}", start));
}
const LIGHT = block(":root");
const DARK = block(':root[data-theme="dark"]');
const token = (b: string, name: string) => b.match(new RegExp(`${name}:\\s*(#[0-9a-f]{6})`, "i"))?.[1];

function contrast(a: string, b: string): number {
  const lum = (hex: string) => {
    const [r, g, bl] = [1, 3, 5]
      .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

const roles = ROLES.filter((r) => r !== "");

describe("code colour tokens", () => {
  it("has a class per role that sets only the colour", () => {
    for (const r of roles) {
      const m = css.match(new RegExp(`\\n\\.tk-${r} \\{([^}]*)\\}`));
      expect(m, r).not.toBeNull();
      expect(m![1].trim()).toBe(`color: var(--code-${r});`);
    }
  });

  for (const [theme, b] of [
    ["light", LIGHT],
    ["dark", DARK],
  ] as const) {
    it(`${theme}: every role holds 4.5:1 on the code background and on the highlight band`, () => {
      const bg = token(b, "--bg")!;
      const band = token(b, "--highlight")!;
      for (const r of roles) {
        const c = token(b, `--code-${r}`);
        expect(c, `${theme} --code-${r}`).toBeDefined();
        expect(contrast(c!, bg), `${r} on bg`).toBeGreaterThanOrEqual(4.5);
        expect(contrast(c!, band), `${r} on band`).toBeGreaterThanOrEqual(4.5);
      }
    });
  }
});
