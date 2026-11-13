// Runs inside the code-colouring worker (and in tests): Shiki, fine-grained, no WASM. Grammars load
// on first use; the highlighters live as long as the worker.
//
// Two engines. JavaScript, TypeScript and TSX use Shiki's precompiled grammars with the raw
// JavaScript engine: their output is identical to the regex engine's (checked character by
// character on real files; codeColoursCore.test.ts keeps checking it) and the first JS file colours
// much sooner in Firefox (headless, eval PC: median 14.3 s -> 8.6 s). Python stays on the regex
// engine: the precompiled Python grammar colours most of a file wrongly (shikijs/shiki#918, open).
import { createHighlighterCore, type HighlighterCore, type ThemeRegistration } from "shiki/core";
import { createJavaScriptRawEngine, createJavaScriptRegexEngine } from "shiki/engine/javascript";
import lightPlus from "shiki/themes/light-plus.mjs";

import { MAX_LINE_CHARS, ROLES, type CodeLang, type ColouredLine } from "./codeRoles";

type Engine = "regex" | "raw";
const ENGINE_OF: Record<CodeLang, Engine> = {
  python: "regex",
  javascript: "raw",
  typescript: "raw",
  tsx: "raw",
};

const GRAMMARS = {
  python: () => import("shiki/langs/python.mjs"),
  javascript: () => import("@shikijs/langs-precompiled/javascript"),
  typescript: () => import("@shikijs/langs-precompiled/typescript"),
  tsx: () => import("@shikijs/langs-precompiled/tsx"),
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

const highlighters = new Map<Engine, Promise<HighlighterCore>>();
const loaded = new Map<CodeLang, Promise<void>>();

function getHighlighter(engine: Engine): Promise<HighlighterCore> {
  let hl = highlighters.get(engine);
  if (!hl) {
    hl = createHighlighterCore({
      themes: [roleTheme()],
      langs: [],
      engine: engine === "raw" ? createJavaScriptRawEngine() : createJavaScriptRegexEngine(),
    });
    highlighters.set(engine, hl);
  }
  return hl;
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

// Short samples that touch the common rules of each grammar, so a warm-up compiles their patterns
// before the first real file (our own text, never repo code). The page warms Python only (see
// warmUpColours); the JavaScript sample is kept for a caller that asks for it.
const WARM_SAMPLES: Partial<Record<CodeLang, string>> = {
  python: [
    "import os",
    "from pkg.mod import name as alias",
    "",
    "@decorator(1)",
    "class Model(Base):",
    '    """Docstring."""',
    "    def method(self, a: int = 1, *args, **kwargs) -> str:",
    "        # comment",
    "        if a and not args or kwargs is None:",
    "            return f\"{a!r} {args}\" + 's' % (1, 2.5, 0x1F)",
    "        for i in range(3):",
    "            yield [x for x in args if x]",
    "        try:",
    "            with open(path) as fh:",
    "                pass",
    "        except (ValueError, KeyError) as e:",
    "            raise RuntimeError('x') from e",
    "        return lambda x: {k: v for k, v in self.items.items()}",
    "",
  ].join("\n"),
  javascript: [
    'import def, { a as b } from "pkg";',
    "const re = /a+[b-c]\\d/gi;",
    "export default class Thing extends Base {",
    "  #field = 1;",
    "  static async *method(x = 1, ...rest) {",
    "    // comment",
    "    /* block */",
    "    if (x === 2 && !y || z !== null) return `t ${x}`;",
    "    for (const [k, v] of Object.entries(obj)) await fn?.(k, v);",
    "    try { new Other(); } catch (err) { throw err; }",
    '    const f = (a, b) => ({ a, b: [1, 2.5, 0x1f, "s", \'q\'] });',
    '    return <div className="a" onClick={() => f(1)}>{x}</div>;',
    "  }",
    "}",
    "module.exports = function handler(req, res) { res.send(require(\"y\")); };",
    "",
  ].join("\n"),
};

/** Start the highlighter, load the grammar and run a sample through it (warm-up, no result). */
export async function warmUp(lang: CodeLang): Promise<void> {
  await colourLines(WARM_SAMPLES[lang] ?? "", lang);
}

/** The code as coloured runs per line. Joined back, the runs give exactly the input text. */
export async function colourLines(code: string, lang: CodeLang): Promise<ColouredLine[]> {
  const hl = await getHighlighter(ENGINE_OF[lang]);
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
