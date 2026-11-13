// Real Shiki (as inside the worker), in Node: roles come out right and the text never changes.
import { describe, expect, it } from "vitest";

import { colourLines } from "./codeColoursCore";
import { ROLES, type ColouredLine } from "./codeRoles";

const text = (lines: ColouredLine[]) => lines.map((l) => l.map((r) => r[1]).join("")).join("\n");
const roleOf = (lines: ColouredLine[], piece: string) => {
  for (const l of lines) for (const [r, t] of l) if (t.includes(piece)) return ROLES[r];
  return undefined;
};

describe("colourLines", () => {
  it("colours Python by role and gives back the exact text", async () => {
    const code = [
      "import os",
      "",
      "def load(path: str) -> int:",
      '    """Read it."""',
      "    # a comment",
      '    key = "[REDACTED]"',
      "    if path:",
      "        return 42",
      "    return len(os.listdir(path))",
    ].join("\n");
    const lines = await colourLines(code, "python");
    expect(text(lines)).toBe(code);
    expect(lines).toHaveLength(9);
    expect(roleOf(lines, "def")).toBe("keyword");
    expect(roleOf(lines, "load")).toBe("function");
    expect(roleOf(lines, "# a comment")).toBe("comment");
    expect(roleOf(lines, "[REDACTED]")).toBe("string"); // redacted value: same text, string colour
    expect(roleOf(lines, "42")).toBe("number");
    expect(roleOf(lines, "return")).toBe("control");
  });

  it("treats HTML-like repo text as text, in JS and in Python", async () => {
    const js = [
      "// <script>alert('x')</script>",
      'const html = "<img src=x onerror=alert(1)>";',
      "el.innerHTML = `<b>${name}</b>`;",
    ].join("\n");
    const out = await colourLines(js, "javascript");
    expect(text(out)).toBe(js);
    expect(roleOf(out, "<script>")).toBe("comment");
    expect(roleOf(out, "<img")).toBe("string");
    const py = 'PAGE = "</pre><script>x()</script>"  # <!-- -->';
    expect(text(await colourLines(py, "python"))).toBe(py);
  });

  it("colours JSX in a .jsx file with the JavaScript grammar, and TSX", async () => {
    const jsx = "export const A = () => <div className=\"a\">hi</div>;";
    const a = await colourLines(jsx, "javascript");
    expect(text(a)).toBe(jsx);
    expect(roleOf(a, "div")).toBe("tag");
    expect(roleOf(a, "className")).toBe("attribute");
    const tsx = "export function B(p: { n: number }) { return <span>{p.n}</span>; }";
    const b = await colourLines(tsx, "tsx");
    expect(text(b)).toBe(tsx);
    expect(roleOf(b, "span")).toBe("tag");
    expect(roleOf(b, "number")).toBe("type");
  });

  it("keeps a trailing newline as an empty last line and CRLF-free text intact", async () => {
    const code = "x = 1\n\ty = 2\n";
    expect(text(await colourLines(code, "python"))).toBe(code);
  });
});

// JS, TS and TSX are coloured with Shiki's precompiled grammars (faster first file); that is only
// sound while their colours equal the regex engine's. Checked on real files, character by character.
describe("precompiled JS/TS/TSX grammars", () => {
  it("colour exactly like the regex engine on real files", async () => {
    // @ts-expect-error node:fs has no type declarations here; the tests run in Node
    const { readFileSync } = await import("node:fs");
    const { createHighlighterCore } = await import("shiki/core");
    const { createJavaScriptRawEngine, createJavaScriptRegexEngine } = await import("shiki/engine/javascript");
    const lightPlus = (await import("shiki/themes/light-plus.mjs")).default;
    const langs = ["javascript", "typescript", "tsx"] as const;
    const regex = await createHighlighterCore({
      themes: [lightPlus],
      langs: [import("shiki/langs/javascript.mjs"), import("shiki/langs/typescript.mjs"), import("shiki/langs/tsx.mjs")],
      engine: createJavaScriptRegexEngine(),
    });
    const raw = await createHighlighterCore({
      themes: [lightPlus],
      langs: [
        import("@shikijs/langs-precompiled/javascript"),
        import("@shikijs/langs-precompiled/typescript"),
        import("@shikijs/langs-precompiled/tsx"),
      ],
      engine: createJavaScriptRawEngine(),
    });
    const files: [string, (typeof langs)[number]][] = [
      ["../../backend/tests/fixtures/detectors/js_positive.js", "javascript"],
      ["../../backend/tests/fixtures/sample_repo/web/src/server.js", "javascript"],
      ["./api.ts", "typescript"],
      ["./codeColours.ts", "typescript"],
      ["./components/NodePanel.tsx", "tsx"],
    ];
    const perChar = (hl: typeof regex, code: string, lang: string) =>
      hl
        .codeToTokens(code, { lang, theme: "light-plus", tokenizeTimeLimit: 5000 })
        .tokens.flatMap((line) => line.flatMap((t) => [...t.content].map((ch) => (ch.trim() ? t.color : ""))));
    for (const [path, lang] of files) {
      const code: string = readFileSync(new URL(path, import.meta.url), "utf8");
      expect(code.length, path).toBeGreaterThan(200);
      expect(perChar(raw, code, lang), path).toEqual(perChar(regex, code, lang));
    }
  }, 120_000);
});
