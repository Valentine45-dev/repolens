// Syntax colours in the code view (feat/code-highlight): screenshots and measurements.
// Headless Edge (throwaway profile, never a window on screen) at a real 1366x768 over the DevTools
// protocol. Needs Node 22+ (global WebSocket). No dependencies. No /ask calls: $0 API spend.
//
//   node eval/code_highlight_evidence.mjs --base http://127.0.0.1:5173 --out DIR --label after --mode shots
//   node eval/code_highlight_evidence.mjs --base http://127.0.0.1:5173 --out DIR --label after --mode measure
//
// shots:   DIR/<label>-1366-<light|dark>-<py|js>.png, a Python and a JS file with a cited-line band
//          (PyGoat, snapshot 2), each theme set before the page loads.
// measure: DIR/measure.json —
//   lazy:    requests made on Home and on Findings (must include no worker, grammar or Shiki chunk),
//            then the Explorer with a file open (must load the worker: the positive control);
//   timing:  time from plain text on screen to colours, for the 1st file (worker + Shiki + Python),
//            2nd (first JS: grammar compile), 3rd (Python again, warm) and 4th (JS again, warm),
//            all in one page, files opened in-app (history.pushState + popstate, as a link does);
//   swap:    the main-thread long task that applies the colours (and, for scale, the one that
//            first shows the plain text), layout shift with its sources, and the code's, band's and
//            scroller's positions before vs after, for the biggest files still coloured, each with
//            a cited band;
//   theme:   a real click on the theme toggle with a coloured file open: token colours before and
//            after, and whether the <pre> was re-rendered (it must not be: CSS only);
//   large:   black tests/test_black.py (4,591 lines) and profiling/list_huge.py (22,431) stay
//            plain with the caption note.

import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
);
const BASE = args.base ?? "http://127.0.0.1:5173";
const OUT = args.out ?? ".";
const LABEL = args.label ?? "probe";
const MODE = args.mode ?? "shots";
const W = 1366;
const H = 768;
const PORT = 9345;

const BROWSERS = [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
];
const exe = BROWSERS.find(existsSync);
if (!exe) throw new Error("no Edge found");

// Real files of the dev database (PyGoat = snapshot 2, express = 3, black = 7).
const PY = { snap: 2, id: 1767, path: "introduction/views.py", lines: "21-28" };
const JS = { snap: 2, id: 1794, path: "introduction/static/js/lab_manager.js", lines: "10-16" };
const PY2 = { snap: 2, id: 1642, path: "challenge/labs/security_headers_lab/app.py", lines: "1-3" };
const JS2 = { snap: 3, id: 327, path: "lib/response.js", lines: "1-3" };
// The biggest files still coloured under the 3,000-line limit, plus typical big ones.
const BIG = [
  { snap: 7, id: 971, path: "src/black/trans.py", lines: "1400-1404" },
  { snap: 6, id: 789, path: "src/flask/app.py", lines: "800-804" },
  { snap: 3, id: 344, path: "test/app.router.js", lines: "600-604", tests: true },
];
// Over the limit: must stay plain with the caption note.
const LARGE = [
  { snap: 7, id: 997, path: "tests/test_black.py", lines: "2200-2204", tests: true },
  { snap: 7, id: 937, path: "profiling/list_huge.py", lines: "1-1" },
];
const href = (f) => `/a/${f.snap}/explore?node=${f.id}&lines=${f.lines}${f.tests ? "&tests=1" : ""}`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function launch() {
  const dir = mkdtempSync(join(tmpdir(), "repolens-cdp-"));
  const flags = [`--remote-debugging-port=${PORT}`, `--user-data-dir=${dir}`, "--headless=new", "--no-first-run", "--disable-gpu", `--window-size=${W},${H}`, "about:blank"];
  const proc = spawn(exe, flags, { stdio: "ignore" });
  for (let i = 0; i < 60; i++) {
    try {
      if ((await fetch(`http://127.0.0.1:${PORT}/json/version`)).ok) return { proc, dir };
    } catch { /* not up yet */ }
    await sleep(500);
  }
  proc.kill();
  throw new Error("browser did not start");
}

async function connect() {
  const target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: "PUT" })).json();
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0;
  const pending = new Map();
  const listeners = [];
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
    else if (msg.method) for (const fn of listeners) fn(msg);
  };
  const send = (method, params = {}) => new Promise((res, rej) => {
    const i = ++id;
    pending.set(i, (msg) => (msg.error ? rej(new Error(`${method}: ${msg.error.message}`)) : res(msg.result)));
    ws.send(JSON.stringify({ id: i, method, params }));
  });
  return { send, on: (fn) => listeners.push(fn), close: () => ws.close() };
}

let cdp;
const evaluate = async (expression) => {
  const r = await cdp.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + " " + (r.exceptionDetails.exception?.description ?? ""));
  return r.result.value;
};
async function waitFor(expr, ms = 60000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (await evaluate(`!!(${expr})`)) return true;
    await sleep(100);
  }
  return false;
}
async function shot(name) {
  const r = await cdp.send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, `${LABEL}-${W}-${name}.png`), Buffer.from(r.data, "base64"));
}

// Before any page script: the theme and the map hint, and a recorder of the code view's states,
// long tasks and layout shifts (all times are performance.now() in the page).
const RECORDER = (theme) => `
  try { localStorage.setItem("repolens.theme", ${JSON.stringify(theme)}); localStorage.setItem("repolens.mapHintSeen", "1"); } catch {}
  window.__cv = { states: [], long: [], shifts: [] };
  new PerformanceObserver((l) => { for (const e of l.getEntries()) __cv.long.push({ start: e.startTime, duration: e.duration }); }).observe({ type: "longtask", buffered: true });
  new PerformanceObserver((l) => { for (const e of l.getEntries()) __cv.shifts.push({ t: e.startTime, value: e.value, sources: (e.sources || []).map((x) => x.node ? (x.node.className || x.node.nodeName) + "" : "?") }); }).observe({ type: "layout-shift", buffered: true });
  let lastEl = null, lastState = null;
  const look = () => {
    const el = document.querySelector(".panel .code[data-colours]");
    const state = el ? el.dataset.colours : null;
    if (el === lastEl && state === lastState) return;
    lastEl = el; lastState = state;
    if (!el) return;
    const body = el.closest(".panel-body"), pre = el.querySelector(".code-text"), band = el.querySelector(".code-highlight");
    __cv.states.push({ t: performance.now(), state, label: el.getAttribute("aria-label"),
      scrollTop: body?.scrollTop, preTop: pre?.getBoundingClientRect().top, preHeight: pre?.getBoundingClientRect().height,
      bandTop: band?.getBoundingClientRect().top, spans: pre?.querySelectorAll("span").length,
      headerHeight: el.closest(".panel")?.querySelector(".panel-header")?.getBoundingClientRect().height,
      bodyTop: body?.getBoundingClientRect().top });
  };
  new MutationObserver(look).observe(document, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-colours"] });
`;

async function newPage(theme) {
  cdp = await connect();
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await cdp.send("Page.addScriptToEvaluateOnNewDocument", { source: RECORDER(theme) });
}
async function open(path) {
  await cdp.send("Page.navigate", { url: BASE + path });
}
/** In-app navigation, as a link does (React Router listens to popstate). */
async function pushTo(path) {
  await evaluate(`(history.pushState({}, "", ${JSON.stringify(path)}), dispatchEvent(new PopStateEvent("popstate")), 1)`);
}
const codeFor = (f) => `document.querySelector(".panel .code[data-colours]") && document.title.includes(${JSON.stringify(f.path.split("/").pop())})`;
const stateIs = (s) => `document.querySelector(".panel .code")?.dataset.colours === ${JSON.stringify(s)}`;

async function shots() {
  for (const theme of ["light", "dark"]) {
    for (const [name, f] of [["py", PY], ["js", JS]]) {
      await newPage(theme);
      await open(href(f));
      await waitFor(`document.querySelector(".panel .code-text") && document.querySelector(".panel .code-highlight")`);
      // after: wait for the colours (the before build has no data-colours: give it the same settle)
      await waitFor(`!document.querySelector(".panel .code[data-colours]") || ${stateIs("on")}`, 30000);
      await sleep(1200);
      await shot(`${theme}-${name}`);
      cdp.close();
    }
  }
}

/** Times for one file opened in the current page: plain text shown -> colours on. */
async function timeFile(f, how) {
  const from = await evaluate(`window.__cv ? __cv.states.length : 0`);
  if (how === "navigate") await open(href(f));
  else await pushTo(href(f));
  await waitFor(codeFor(f));
  const ok = await waitFor(`${codeFor(f)} && ${stateIs("on")}`, 60000);
  await sleep(300);
  const states = (await evaluate(`__cv.states`)).slice(how === "navigate" ? 0 : from);
  const pending = states.find((s) => s.state === "pending");
  const on = states.find((s) => s.state === "on");
  return { file: f.path, coloured: ok, ms_plain_to_colours: pending && on ? Math.round(on.t - pending.t) : null, lines: f.lines, pending, on };
}

async function measure() {
  const out = { base: BASE, when: new Date().toISOString(), viewport: `${W}x${H}` };
  const only = args.only ? args.only.split(",") : null;
  const want = (k) => !only || only.includes(k);
  if (want("lazy")) {
  // 1. Lazy loading: Home and Findings must not fetch the worker, a grammar or Shiki.
  await newPage("light");
  await cdp.send("Network.enable");
  const requests = [];
  cdp.on((m) => { if (m.method === "Network.requestWillBeSent") requests.push(m.params.request.url.replace(BASE, "")); });
  const heavy = (u) => /codeColours\.worker|\/(python|javascript|typescript|tsx|jsx)-[\w-]+\.js|shiki|\.wasm/i.test(u);
  const page = async (name, path, ready) => {
    const from = requests.length;
    await open(path);
    await waitFor(ready);
    await sleep(7000); // longer than the warm-up's 5 s idle timeout: it would have started by now
    const urls = requests.slice(from).filter((u) => !u.startsWith("data:"));
    const resources = await evaluate(`performance.getEntriesByType("resource").map((e) => e.name.replace(location.origin, ""))`);
    return { page: name, path, requests: urls, heavy_requests: urls.filter(heavy), heavy_resources: resources.filter(heavy) };
  };
  out.lazy = [
    await page("Home", "/", `document.querySelector("input")`),
    await page("Findings", "/a/2/findings", `document.querySelector("table, .findings-list, [role=table]")`),
    await page("Explorer with a file open (control)", href(PY), `document.querySelector(".panel .code[data-colours=on]")`),
    await page("Explorer map, no file open (warm-up control)", "/a/2/explore", `document.querySelector(".react-flow__node")`),
  ];
  cdp.close();

  }
  if (want("timing")) {
  // 2. Time to colours, first to fourth file, one page (one worker, one highlighter).
  await newPage("light");
  out.timing = [];
  out.timing.push({ order: 1, note: "first file: worker start, Shiki core + engine, Python grammar", ...(await timeFile(PY, "navigate")) });
  out.timing.push({ order: 2, note: "second file, first JS: JavaScript grammar loads and compiles", ...(await timeFile(JS, "push")) });
  out.timing.push({ order: 3, note: "third file, Python again (warm)", ...(await timeFile(PY2, "push")) });
  out.timing.push({ order: 4, note: "fourth file, JS again (warm)", ...(await timeFile(JS2, "push")) });
  for (const t of out.timing) { delete t.pending; delete t.on; }
  cdp.close();

  }
  if (want("swap")) {
  // 3. The swap on big files: the long task that applies the colours, layout shift, positions.
  out.swap = [];
  for (const f of BIG) {
    await newPage("light");
    const r = await timeFile(f, "navigate");
    const cv = await evaluate(`__cv`);
    const on = r.on, pending = r.pending;
    const swapTask = cv.long.find((l) => l.start <= on.t && on.t <= l.start + l.duration + 1);
    const plainTask = cv.long.find((l) => l.start <= pending.t && pending.t <= l.start + l.duration + 1);
    const during = cv.long.filter((l) => l.start >= pending.t - 1 && l.start < on.t - 1);
    out.swap.push({
      file: f.path,
      ms_plain_to_colours: r.ms_plain_to_colours,
      spans: on.spans,
      swap_long_task_ms: swapTask ? Math.round(swapTask.duration) : 0,
      plain_render_long_task_ms: plainTask ? Math.round(plainTask.duration) : 0,
      shifts: cv.shifts.filter((s) => s.t >= pending.t - 1),
      header_height: [pending.headerHeight, on.headerHeight],
      body_top: [pending.bodyTop, on.bodyTop],
      longest_task_while_colouring_ms: Math.round(Math.max(0, ...during.map((l) => l.duration))),
      layout_shift_during: cv.shifts.filter((s) => s.t >= pending.t - 1).reduce((a, s) => a + s.value, 0),
      scrollTop: [pending.scrollTop, on.scrollTop],
      pre_top: [pending.preTop, on.preTop],
      pre_height: [pending.preHeight, on.preHeight],
      band_top: [pending.bandTop, on.bandTop],
      label: on.label,
    });
    await shot(`swap-${f.path.split("/").pop().replace(".py", "")}`);
    cdp.close();
  }

  }
  if (want("theme")) {
  // 4. Theme switch with colours on: a real click on the toggle; CSS only, no re-render.
  await newPage("light");
  await open(href(PY));
  await waitFor(`${codeFor(PY)} && ${stateIs("on")}`);
  await sleep(500);
  const colours = `(() => { const pick = (c) => getComputedStyle(document.querySelector(".panel .code-text ." + c)).color; return { keyword: pick("tk-keyword"), string: pick("tk-string"), function: pick("tk-function"), plain: getComputedStyle(document.querySelector(".panel .code-text")).color, band: getComputedStyle(document.querySelector(".panel .code-highlight")).backgroundColor, theme: document.documentElement.dataset.theme }; })()`;
  const before = await evaluate(colours);
  await evaluate(`(window.__pre = document.querySelector(".panel .code-text"), window.__first = __pre.firstChild, 1)`);
  const box = await evaluate(`(() => { const r = document.querySelector(".theme-toggle").getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
  for (const type of ["mouseMoved", "mousePressed", "mouseReleased"]) {
    await cdp.send("Input.dispatchMouseEvent", { type, x: box.x, y: box.y, button: "left", clickCount: type === "mouseMoved" ? 0 : 1 });
  }
  await sleep(1200);
  const after = await evaluate(colours);
  out.theme = {
    before, after,
    same_pre_element: await evaluate(`document.querySelector(".panel .code-text") === __pre`),
    same_first_token_node: await evaluate(`document.querySelector(".panel .code-text").firstChild === __first`),
    still_coloured: await evaluate(stateIs("on")),
  };
  cdp.close();

  }
  if (want("ligatures")) {
  // 6. Ligatures off wherever JetBrains Mono is drawn (code view, paths, chips, tags), JS file open.
  await newPage("light");
  await open(href(JS));
  await waitFor(`${codeFor(JS)} && ${stateIs("on")}`);
  await sleep(800);
  out.ligatures = await evaluate(`(() => {
    const mono = [...document.querySelectorAll("body *")].filter((el) => el.childNodes.length && [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()) && getComputedStyle(el).fontFamily.includes("JetBrains Mono"));
    const on = mono.filter((el) => getComputedStyle(el).fontVariantLigatures !== "none");
    return { mono_text_elements: mono.length, with_ligatures: on.length, examples_with: on.slice(0, 5).map((el) => el.className || el.tagName), code_text: getComputedStyle(document.querySelector(".panel .code-text")).fontVariantLigatures, has_neq: document.querySelector(".panel .code-text").textContent.includes("!==") };
  })()`);
  // a close-up of line 10 of lab_manager.js ("document.cookie !== ''"), at 3x
  const box = await evaluate(`(() => { const r = document.querySelector(".panel .code-highlight").getBoundingClientRect(); return { x: r.x, y: r.y, width: Math.min(r.width, 460), height: 20 }; })()`);
  const r = await cdp.send("Page.captureScreenshot", { format: "png", clip: { ...box, scale: 3 } });
  writeFileSync(join(OUT, `${LABEL}-${W}-ligatures-closeup.png`), Buffer.from(r.data, "base64"));
  cdp.close();
  }
  if (want("large")) {
  // 5. Files over the limit stay plain, with the caption note.
  out.large = [];
  for (const f of LARGE) {
    await newPage("light");
    await open(href(f));
    await waitFor(codeFor(f));
    await sleep(1500);
    out.large.push({
      file: f.path,
      state: await evaluate(`document.querySelector(".panel .code").dataset.colours`),
      caption: await evaluate(`document.querySelector(".panel .panel-heading .caption").textContent`),
      spans: await evaluate(`document.querySelectorAll(".panel .code-text span").length`),
    });
    await shot(`large-${f.path.split("/").pop().replace(".py", "")}`);
    cdp.close();
  }
  }
  writeFileSync(join(OUT, args.json ?? "measure.json"), JSON.stringify(out, null, 2));
  console.log(JSON.stringify(out, null, 2));
}

mkdirSync(OUT, { recursive: true });
const { proc, dir } = await launch();
try {
  if (MODE === "measure") await measure();
  else await shots();
} finally {
  proc.kill();
  await sleep(800);
  try { rmSync(dir, { recursive: true, force: true }); } catch { /* Edge may still hold a file */ }
}
