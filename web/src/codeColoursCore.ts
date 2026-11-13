// Runs inside the code-colouring worker (and in tests): Shiki, fine-grained, with the JavaScript
// regex engine (no WASM). One highlighter for the worker's life; grammars load on first use.
import { createHighlighterCore, type HighlighterCore, type ThemeRegistration } from "shiki/core";
import { createJavaScriptRegexEngine } from "shiki/engine/javascript";
import lightPlus from "shiki/themes/light-plus.mjs";

import { MAX_LINE_CHARS, ROLES, type CodeLang, type ColouredLine } from "./codeRoles";

const GRAMMARS = {
  python: () => import("shiki/langs/python.mjs"),
  javascript: () => import("shiki/langs/javascript.mjs"),
  typescript: () => import("shiki/langs/typescript.mjs"),
  tsx: () => import("shiki/langs/tsx.mjs"),
} satisfies Record<CodeLang, () => Promise<unknown>>;

// light-plus colour -> role. light-plus and dark-plus colour the same scopes alike for Python and
// JS/TS, so one pass gives the role and styles.css gives each theme's colour for it.
const ROLE_OF: Record<string, (typeof ROLES)[number]> = {
  "#0000ff": "keyword",
  "#af00db": "control",
  "#001080": "variable",
  "#0451a5": "property",
  "#0070c1": "constant",
  "#795e26": "function",
  "#267f99": "type",
  "#a31515": "string",
  "#ee0000": "escape",
  "#811f3f": "regex",
  "#d16969": "regex",
  "#098658": "number",
  "#008000": "comment",
  "#800000": "tag",
  "#e50000": "attribute",
};

const THEME = "repolens-roles";
const LINE_TIME_LIMIT_MS = 5000;
const MARK = /^var\(--r(\d+)\)$/;

/** light-plus's scope rules with each colour replaced by a role marker (no font styles). */
function roleTheme(): ThemeRegistration {
  const base = lightPlus as ThemeRegistration;
  return {
    name: THEME,
    type: "light",
    fg: "var(--r0)",
    bg: "var(--r0)",
    colors: { "editor.foreground": "var(--r0)", "editor.background": "var(--r0)" },
    settings: (base.tokenColors ?? base.settings ?? []).map((rule) => {
      const fg = rule.settings?.foreground?.toLowerCase().slice(0, 7);
      const role = fg ? ROLES.indexOf(ROLE_OF[fg] ?? "") : 0;
      return { scope: rule.scope, settings: { foreground: `var(--r${Math.max(role, 0)})` } };
    }),
  };
}

let highlighter: Promise<HighlighterCore> | null = null;
const loaded = new Map<CodeLang, Promise<void>>();

function getHighlighter(): Promise<HighlighterCore> {
  highlighter ??= createHighlighterCore({
    themes: [roleTheme()],
    langs: [],
    engine: createJavaScriptRegexEngine(),
  });
  return highlighter;
}

async function ensureLang(hl: HighlighterCore, lang: CodeLang): Promise<void> {
  let p = loaded.get(lang);
  if (!p) {
    p = hl.loadLanguage(GRAMMARS[lang]() as never);
    loaded.set(lang, p);
    p.catch(() => loaded.delete(lang));
  }
  await p;
}

/** The code as coloured runs per line. Joined back, the runs give exactly the input text. */
export async function colourLines(code: string, lang: CodeLang): Promise<ColouredLine[]> {
  const hl = await getHighlighter();
  await ensureLang(hl, lang);
  const { tokens } = hl.codeToTokens(code, {
    lang,
    theme: THEME,
    tokenizeMaxLineLength: MAX_LINE_CHARS,
    // Shiki's default (500 ms a line) is hit on the eval PC while a grammar's patterns are first
    // compiled, and the rest of that line then gets the wrong colours. This runs in the worker,
    // which the page stops after TIMEOUT_MS anyway.
    tokenizeTimeLimit: LINE_TIME_LIMIT_MS,
  });
  return tokens.map((row) => {
    const out: ColouredLine = [];
    for (const t of row) {
      const role = Number(MARK.exec(t.color ?? "")?.[1] ?? 0);
      const last = out[out.length - 1];
      if (last && last[0] === role) last[1] += t.content;
      else out.push([role, t.content]);
    }
    return out;
  });
}
