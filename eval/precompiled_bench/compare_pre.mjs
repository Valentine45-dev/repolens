// Character-level colour comparison: regex engine (current) vs precompiled grammars + raw engine.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
const [pkgDir, samplesDir] = process.argv.slice(2);
const mod = (p) => import(pathToFileURL(join(pkgDir, "node_modules", p)).href);
const { createHighlighterCore } = await mod("shiki/dist/core.mjs");
const { createJavaScriptRegexEngine, createJavaScriptRawEngine } = await mod("@shikijs/engine-javascript/dist/index.mjs");
const lp = (await mod("@shikijs/themes/dist/light-plus.mjs")).default;
const L = ["python", "javascript", "typescript", "tsx"];
const reg = await createHighlighterCore({ themes: [lp], langs: await Promise.all(L.map(async (l) => (await mod(`@shikijs/langs/dist/${l}.mjs`)).default)), engine: createJavaScriptRegexEngine() });
const pre = await createHighlighterCore({ themes: [lp], langs: await Promise.all(L.map(async (l) => (await mod(`@shikijs/langs-precompiled/dist/${l}.mjs`)).default)), engine: createJavaScriptRawEngine() });
const colours = (hl, code, lang) => {
  const out = [];
  for (const line of hl.codeToTokens(code, { lang, theme: "light-plus", tokenizeTimeLimit: 5000 }).tokens) {
    for (const t of line) for (const ch of t.content) out.push(ch.trim() ? (t.color ?? "").toLowerCase() : "");
    out.push("");
  }
  return out;
};
for (const f of readdirSync(samplesDir).sort()) {
  if (!/\.(py|js|ts|tsx)$/.test(f)) continue;
  const code = readFileSync(join(samplesDir, f), "utf8");
  const lang = f.endsWith(".py") ? "python" : f.endsWith(".tsx") ? "tsx" : f.endsWith(".ts") ? "typescript" : "javascript";
  const a = colours(reg, code, lang), b = colours(pre, code, lang);
  let diff = 0, total = 0, firstLine = null, line = 1;
  const pairs = new Map();
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    if (a[i] === "" && b[i] === "") { if (a[i] === "" && code[i - (0)] === undefined) {} }
    if (a[i]) total++;
    if (a[i] !== b[i]) { diff++; const k = `${a[i]}->${b[i]}`; pairs.set(k, (pairs.get(k) ?? 0) + 1); }
  }
  // the first line that differs
  const la = code.split("\n");
  let pos = 0;
  for (let n = 0; n < la.length; n++) { const len = la[n].length + 1; if (a.slice(pos, pos + len).join() !== b.slice(pos, pos + len).join()) { firstLine = n + 1; break; } pos += len; }
  console.log(`${f.padEnd(34)} ${lang.padEnd(10)} differing chars ${diff}/${total} (${(100 * diff / total).toFixed(2)}%) first differing line ${firstLine}  top: ${[...pairs].sort((x, y) => y[1] - x[1]).slice(0, 3).map(([k, v]) => `${k}:${v}`).join(" ")}`);
}
