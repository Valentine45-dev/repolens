// Cold start of colouring, per page load: ?engine=regex|pre &lang=python|javascript &warm=0|1
const q = new URLSearchParams(location.search);
const engine = q.get("engine"), lang = q.get("lang"), warm = q.get("warm") === "1";
const file = lang === "python" ? "views.py.txt" : "lab_manager.js.txt";
const SAMPLE = {
  python: 'import os\nfrom x import y as z\n\n@dec(1)\nclass A(B):\n    """Doc."""\n    def f(self, a: int = 1, *b, **c) -> str:\n        # c\n        if a and not b or c is None:\n            return f"{a!r} {b}" + \'s\' % (1, 2.5, 0x1f)\n        for i in range(3):\n            yield [i for i in b if i]\n        try:\n            with open(p) as fh:\n                pass\n        except (E, F) as e:\n            raise X from e\n        lambda x: {k: v for k, v in d.items()}\n',
  javascript: 'import a, { b as c } from "x";\nconst re = /a+[b-c]/g;\nexport default class A extends B {\n  #p = 1;\n  static async *m(x = 1, ...r) {\n    // c\n    /* d */\n    if (x === 2 && !y || z !== null) return `t ${x}`;\n    for (const [k, v] of Object.entries(o)) await f?.(k, v);\n    try { new C(); } catch (e) { throw e; }\n    const fn = (a, b) => ({ a, b: [1, 2.5, 0x1f, "s", \'q\'] });\n    el.innerHTML = <div className="a">{x}</div>;\n  }\n}\nmodule.exports = function (req, res) { res.send(require("y")); };\n',
};
async function run() {
  const t0 = performance.now();
  const code = await (await fetch(file)).text();
  const tFetch = performance.now();
  let hl;
  const lp = (await import("shiki/themes/light-plus.mjs")).default;
  const { createHighlighterCore } = await import("shiki/core");
  if (engine === "pre") {
    const { createJavaScriptRawEngine } = await import("shiki/engine/javascript");
    const langMod = lang === "python" ? import("@shikijs/langs-precompiled/python") : import("@shikijs/langs-precompiled/javascript");
    hl = await createHighlighterCore({ themes: [lp], langs: [langMod], engine: createJavaScriptRawEngine() });
  } else {
    const { createJavaScriptRegexEngine } = await import("shiki/engine/javascript");
    const langMod = lang === "python" ? import("shiki/langs/python.mjs") : import("shiki/langs/javascript.mjs");
    hl = await createHighlighterCore({ themes: [lp], langs: [langMod], engine: createJavaScriptRegexEngine() });
  }
  const tInit = performance.now();
  let tWarm = tInit;
  const opts = { lang, theme: "light-plus", tokenizeTimeLimit: 5000 };
  if (warm) { hl.codeToTokens(SAMPLE[lang], opts); tWarm = performance.now(); }
  const r1 = hl.codeToTokens(code, opts);
  const tFirst = performance.now();
  hl.codeToTokens(code, opts);
  const tSecond = performance.now();
  const back = r1.tokens.map((l) => l.map((t) => t.content).join("")).join("\n");
  const ok = back === code || back === code.replace(/\n$/, "");
  const res = { tag: location.search, engine, lang, warm, ua: navigator.userAgent.match(/(Firefox|Edg)\/[\d.]+/)?.[0], load_and_init_ms: Math.round(tInit - tFetch), warm_sample_ms: Math.round(tWarm - tInit), first_file_ms: Math.round(tFirst - tWarm), total_to_colours_ms: Math.round(tFirst - tFetch), second_same_file_ms: Math.round(tSecond - tFirst), lines: r1.tokens.length, roundtrip: ok, tokens: r1.tokens.reduce((a, l) => a + l.length, 0) };
  document.getElementById("out").textContent = JSON.stringify(res);
  await fetch("/result", { method: "POST", body: JSON.stringify(res) });
}
run().catch((e) => fetch("/result", { method: "POST", body: JSON.stringify({ tag: location.search, engine, lang, error: String(e) }) }));
