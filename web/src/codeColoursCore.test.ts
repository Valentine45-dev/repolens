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
