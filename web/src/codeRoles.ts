// Shared by the code-colouring worker and the page: what a coloured line looks like and the limits.
// Kept free of imports so the page never pulls Shiki in through it.

/** Languages the code view colours. Everything else stays plain text. */
export type CodeLang = "python" | "javascript" | "typescript" | "tsx";

/** Colour roles, VS Code light-plus based. Index 0 is plain text (no class). styles.css has a
 * `--code-<role>` token (light and dark) and a `.tk-<role>` rule for every other entry. */
export const ROLES = [
  "",
  "keyword",
  "control",
  "variable",
  "property",
  "constant",
  "function",
  "type",
  "string",
  "escape",
  "regex",
  "number",
  "comment",
  "tag",
  "attribute",
] as const;
export type Role = (typeof ROLES)[number];

/** One line as runs of [role index, text]; the texts join back to the line exactly. */
export type ColouredLine = [number, string][];

/** Above either limit the file stays plain ("Colours off for large files"). Measured on the eval
 * PC (N5030): tokenising ~4,600 lines of Python takes ~0.9 s in the worker. */
export const MAX_LINES = 5000;
export const MAX_BYTES = 256 * 1024;
/** Longer lines are left uncoloured by the tokenizer (a minified or data line). */
export const MAX_LINE_CHARS = 1000;

const EXT: Record<string, CodeLang> = {
  py: "python",
  pyi: "python",
  js: "javascript",
  jsx: "javascript", // VS Code's JavaScript grammar covers JSX
  mjs: "javascript",
  cjs: "javascript",
  ts: "typescript",
  mts: "typescript",
  cts: "typescript",
  tsx: "tsx",
};

export function langForPath(path: string): CodeLang | null {
  const name = path.slice(path.lastIndexOf("/") + 1);
  const dot = name.lastIndexOf(".");
  if (dot <= 0) return null;
  return EXT[name.slice(dot + 1).toLowerCase()] ?? null;
}

export function utf8Length(text: string): number {
  return new TextEncoder().encode(text).length;
}

export function isTooLarge(lines: number, bytes = 0): boolean {
  return lines > MAX_LINES || bytes > MAX_BYTES;
}
