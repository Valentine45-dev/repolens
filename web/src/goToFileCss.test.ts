// The Go to file highlighter, read from styles.css: its text holds 4.5:1 on it, and it stands out
// at 3:1 from a result row (Paper) and from the active row (Sunk Grey), in both themes.
import { describe, expect, it } from "vitest";

// @ts-expect-error node:fs has no type declarations here; the tests run in Node
const { readFileSync } = await import("node:fs");
const css: string = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

function block(selector: string): string {
  const start = css.indexOf(`${selector} {`);
  return css.slice(start, css.indexOf("\n}", start));
}
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

describe("Go to file highlighter", () => {
  it("is a background with its own text colour, no underline and no extra weight", () => {
    const rule = css.match(/\n\.goto-hit \{([^}]*)\}/)![1];
    expect(rule).toContain("background: var(--match);");
    expect(rule).toContain("color: var(--match-text);");
    expect(rule).not.toMatch(/text-decoration|font-weight/);
  });

  for (const [theme, b] of [
    ["light", block(":root")],
    ["dark", block(':root[data-theme="dark"]')],
  ] as const) {
    it(`${theme}: 4.5:1 text, 3:1 against a row and the active row`, () => {
      const match = token(b, "--match")!;
      expect(contrast(token(b, "--match-text")!, match)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(match, token(b, "--bg")!)).toBeGreaterThanOrEqual(3);
      expect(contrast(match, token(b, "--surface-2")!)).toBeGreaterThanOrEqual(3);
    });
  }
});
