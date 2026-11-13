// "Open these lines" while another right-column tab is in front (fix/citation-opens-file).
// Headless Edge (throwaway profile, never a window on screen) at a real 1366x768 or 1920x1080
// over the DevTools protocol. Clicks are real mouse events at the element's centre.
// Needs Node 22+ (global WebSocket). No dependencies.
//
//   node eval/citation_tab_evidence.mjs --base http://127.0.0.1:5173 --out DIR --label after [--width 1366]
//
// The Ask conversation is seeded into this tab's sessionStorage (where the app keeps it):
//   - a real graph answer, fetched from the running API ("What calls updateLabStatus?", no LLM);
//   - one AI-shaped turn whose text says it is a seeded test turn (no model was called), with
//     citations to real line ranges of PyGoat (snapshot 2). $0 API spend.
// Writes DIR/<label>-<width>.json and DIR/<label>-<width>-<step>.png.

import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
);
const BASE = args.base ?? "http://127.0.0.1:5173";
const API = args.api ?? "http://127.0.0.1:8000";
const OUT = args.out ?? ".";
const LABEL = args.label ?? "probe";
const W = Number(args.width ?? 1366);
const H = W >= 1600 ? 1080 : 768;
const PORT = 9344;
const REDUCED = args.reduced === "1";

const BROWSERS = [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
];
const exe = BROWSERS.find(existsSync);
if (!exe) throw new Error("no Edge found");

const SNAP = 2; // PyGoat
const LAB = { path: "introduction/static/js/lab_manager.js", file_id: 1794, module: 9108 };
const VIEWS = { path: "introduction/views.py", file_id: 1767 };

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function launch() {
  const dir = mkdtempSync(join(tmpdir(), "repolens-cdp-"));
  const flags = [`--remote-debugging-port=${PORT}`, `--user-data-dir=${dir}`, "--headless=new", "--no-first-run", "--disable-gpu", `--window-size=${W},${H}`, "about:blank"];
  if (REDUCED) flags.unshift("--force-prefers-reduced-motion");
  const proc = spawn(exe, flags, { stdio: "ignore" });
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/version`);
      if (r.ok) return { proc, dir };
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
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  };
  const send = (method, params = {}) => new Promise((res, rej) => {
    const i = ++id;
    pending.set(i, (msg) => (msg.error ? rej(new Error(`${method}: ${msg.error.message}`)) : res(msg.result)));
    ws.send(JSON.stringify({ id: i, method, params }));
  });
  return { send, close: () => ws.close() };
}

let cdp;
const evaluate = async (expression) => {
  const r = await cdp.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + " " + (r.exceptionDetails.exception?.description ?? ""));
  return r.result.value;
};
async function shot(step) {
  const r = await cdp.send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, `${LABEL}-${W}-${step}.png`), Buffer.from(r.data, "base64"));
}
async function go(path, wait = 4000) {
  await cdp.send("Page.navigate", { url: BASE + path });
  await sleep(wait);
}
/** Real mouse click at the centre of the first element matching `selector` whose text includes `text`. */
async function click(selector, text = "") {
  const box = await evaluate(`(() => {
    const el = [...document.querySelectorAll(${JSON.stringify(selector)})].find((e) => e.textContent.includes(${JSON.stringify(text)}) && e.getClientRects().length);
    if (!el) return null;
    let r = el.getBoundingClientRect();
    // Off screen (below a panel's fold): scroll it into view first, as a user would.
    if (r.bottom > innerHeight || r.top < 0) { el.scrollIntoView({ block: "center" }); r = el.getBoundingClientRect(); }
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  })()`);
  if (!box) throw new Error(`nothing to click: ${selector} ${text}`);
  for (const type of ["mouseMoved", "mousePressed", "mouseReleased"]) {
    await cdp.send("Input.dispatchMouseEvent", { type, x: box.x, y: box.y, button: "left", clickCount: type === "mouseMoved" ? 0 : 1 });
  }
}
/** Wait until `expr` (a page expression) is truthy, up to `ms`; then a short settle. */
async function waitFor(expr, ms = 30000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (await evaluate(`!!(${expr})`)) { await sleep(400); return true; }
    await sleep(150);
  }
  return false;
}
// The cited code is on screen in the visible panel (not the loading placeholder).
const CODE_SHOWN = `(() => { const c = document.querySelector('.panel .code[aria-label]'); return c && c.getClientRects().length && document.querySelector('.analysis-body')?.dataset.rightTab !== 'ask'; })()`;

/** Scroll the Ask list so the element is on screen (as a user would with the wheel). */
async function revealInAsk(selector, text) {
  await evaluate(`(() => {
    const list = document.querySelector('#ask-drawer .drawer-body');
    const el = [...document.querySelectorAll(${JSON.stringify(selector)})].find((e) => e.textContent.includes(${JSON.stringify(text)}));
    if (list && el) list.scrollTop += el.getBoundingClientRect().top - list.getBoundingClientRect().top - 120;
    return 1;
  })()`);
  await sleep(300);
}

// What the right column shows, and where the highlighted lines are inside the visible code area.
const STATE = `(() => {
  const body = document.querySelector('.analysis-body');
  const tabs = [...document.querySelectorAll('.right-tabs [role=tab]')].map((t) => t.textContent + (t.getAttribute('aria-selected') === 'true' ? '*' : ''));
  const drawer = document.querySelector('#ask-drawer');
  const panel = document.querySelector('.panel-body');
  const mark = document.querySelector('.code-highlight');
  const visible = (el) => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  const askList = drawer?.querySelector('.drawer-body');
  let markInView = null;
  if (panel && mark && visible(panel)) {
    const p = panel.getBoundingClientRect();
    const m = mark.getBoundingClientRect();
    markInView = { panelTop: Math.round(p.top), panelBottom: Math.round(p.bottom), markTop: Math.round(m.top), markBottom: Math.round(m.bottom), above: Math.round(m.top - p.top), below: Math.round(p.bottom - m.bottom), fullyInside: m.top >= p.top && m.bottom <= p.bottom };
  }
  return {
    url: location.pathname + location.search,
    rightTab: body?.dataset.rightTab ?? null,
    tabs,
    askVisible: visible(drawer) && drawer?.dataset.behind === undefined,
    panelVisible: visible(panel),
    panelScrollTop: panel ? Math.round(panel.scrollTop) : null,
    highlightAria: document.querySelector('.code[aria-label]')?.getAttribute('aria-label') ?? null,
    markInView,
    askScrollTop: askList ? Math.round(askList.scrollTop) : null,
    askTurns: drawer ? drawer.querySelectorAll('.turn, li.ask-turn, [data-turn]').length : null,
    draft: drawer?.querySelector('textarea')?.value ?? null,
  };
})()`;

async function seed() {
  const graph = await (await fetch(`${API}/snapshots/${SNAP}/ask`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question: "What calls updateLabStatus?" }),
  })).json();
  if (graph.kind !== "graph") throw new Error("expected a graph-routed answer (no LLM)");
  const cite = (f, s, e, symbol) => ({ path: f.path, start_line: s, end_line: e, file_id: f.file_id, symbol_id: symbol, in_test: false });
  const ai = {
    kind: "ai", status: "answered", dropped: 0, results: [], prompt_version: "seeded-test",
    retrieval: { sent: 2, used_test_code: false, from_graph: 0 },
    answer: "Seeded test turn for the citation check: no model was called. The lab status code is in lab_manager.js [introduction/static/js/lab_manager.js:53-56], the views in views.py [introduction/views.py:300-310].",
    citations: [cite(LAB, 53, 56, LAB.module), cite(LAB, 380, 390, LAB.module), cite(VIEWS, 300, 310, null)],
  };
  const turns = [
    { id: "seed-1", question: "What calls updateLabStatus?", answer: graph },
    { id: "seed-2", question: "Where is the lab status updated?", answer: ai },
  ];
  await go(`/a/${SNAP}/no-such-page`, 1500);
  await evaluate(`sessionStorage.setItem('repolens.ask.${SNAP}', ${JSON.stringify(JSON.stringify(turns))}); localStorage.setItem('repolens.recent', ${JSON.stringify(JSON.stringify([{ snapshotId: SNAP, url: "https://github.com/adeyosemanputra/pygoat", commitSha: "46fef968f3f44d1191363baf936aaa3335dc5c6d", submittedAt: Date.now() }]))}); localStorage.setItem('repolens.mapHintSeen', '1'); 1`);
}

const DRAFT = "half-typed question";
async function typeDraft() {
  await evaluate(`(() => { const t = document.querySelector('#ask-drawer textarea'); t.focus(); return 1; })()`);
  await cdp.send("Input.insertText", { text: DRAFT });
  await sleep(200);
}

mkdirSync(OUT, { recursive: true });
const { proc, dir } = await launch();
const out = { base: BASE, viewport: [W, H], reducedMotion: REDUCED, browser: exe.split("/").pop(), steps: {} };
const record = async (step, extra = {}) => {
  const s = await evaluate(STATE);
  out.steps[step] = { ...s, ...extra };
  await shot(step);
  console.log(step, JSON.stringify(out.steps[step]));
};
try {
  cdp = await connect();
  await cdp.send("Page.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await seed();

  const tabbed = async () => (await evaluate(STATE)).tabs.length > 0;
  // Put Ask in front, as the user would, where Ask shares the column with the panel.
  const toAsk = async () => {
    if (await tabbed()) { await click(".right-tabs [role=tab]", "Ask"); await sleep(500); }
  };

  // A. Ask open, no file yet: click the AI answer's citation chip lab_manager.js:53-56.
  await go(`/a/${SNAP}/explore?ask=1`, 12000);
  await revealInAsk(".citation", "lab_manager.js:53");
  await typeDraft();
  const askBefore = await evaluate(STATE);
  out.steps["a0-ask"] = askBefore;
  await shot("a0-ask");
  await click(".citation", "lab_manager.js:53");
  await waitFor(CODE_SHOWN);
  await record("a1-after-chip");
  // A2. Back to Ask: the conversation, draft and scroll position as they were.
  await toAsk();
  await record("a2-back-to-ask", { askScrollBefore: askBefore.askScrollTop, draftBefore: askBefore.draft, askTurnsBefore: askBefore.askTurns });
  // B. The same file already open behind Ask: a chip for other lines in it (380-390).
  await click(".citation", "lab_manager.js:380");
  // 60 ms in: an instant scroll is already there, a smooth one is still on its way.
  await sleep(60);
  const immediate = await evaluate(`Math.round(document.querySelector('.panel-body')?.scrollTop ?? -1)`);
  await sleep(1500);
  await record("b1-same-file-chip", { scrollTopAt60ms: immediate });
  // B2. The same chip again after scrolling the code away (the address does not change).
  const code = await evaluate(`(() => { const r = document.querySelector('.panel-body').getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
  await cdp.send("Input.dispatchMouseEvent", { type: "mouseWheel", x: code.x, y: code.y, deltaX: 0, deltaY: -100000 });
  await sleep(600);
  await record("b2-scrolled-away");
  await toAsk();
  await click(".citation", "lab_manager.js:380");
  await sleep(1500);
  await record("b3-same-chip-again");
  // C. Another file (views.py:300-310), not loaded before.
  await toAsk();
  await click(".citation", "views.py:300");
  await waitFor(CODE_SHOWN);
  await record("c1-other-file-chip");
  if (out.steps["c1-other-file-chip"].rightTab === "ask") {
    await click(".right-tabs [role=tab]", "File");
    await sleep(1500);
    await record("c2-file-tab-by-hand");
  }
  // D. Graph answer: a "called at" line chip (lab_manager.js line 212; the file is cached now).
  await toAsk();
  await revealInAsk(".site-chips a", "212");
  await click(".site-chips a", "212");
  await sleep(2000);
  await record("d1-graph-site-chip");
  // E. Graph answer: a result row (launchLab, lines 103-230: taller than the panel).
  await toAsk();
  await revealInAsk(".result-row", "launchLab");
  await click("a.result-row", "launchLab");
  await sleep(2000);
  await record("e1-graph-result-row");
  // F. Uses: a line chip inside the file panel (views.py, Uses tab), opening another file.
  await go(`/a/${SNAP}/explore?node=${VIEWS.file_id}&ask=1`, 2000);
  await waitFor(CODE_SHOWN);
  await click(".panel .tabs [role=tab]", "Uses");
  await waitFor(`document.querySelector('.panel .site-chip')`);
  const siteText = await evaluate(`[...document.querySelectorAll('.panel .site-chip')].filter((e) => e.tagName === 'BUTTON' || e.tagName === 'A').map((e) => e.textContent)[0] ?? null`);
  if (siteText) {
    await click(".panel .site-chip", siteText);
    await waitFor(CODE_SHOWN);
    await record("f1-uses-site-chip", { clicked: siteText });
  }
  // G. Findings: a finding open beside Ask (Finding | Ask), then "Open in Explorer".
  await go(`/a/${SNAP}/findings?category=all&ask=1&finding=5429`, 3000);
  await waitFor(`[...document.querySelectorAll('.panel a')].some((a) => a.textContent.includes('Open in Explorer'))`);
  await record("g0-finding-open");
  await waitFor(`document.querySelector('.panel a.site-chip')`, 15000);
  const reachChip = await evaluate(`[...document.querySelectorAll('.panel a.site-chip')].map((e) => e.textContent)[0] ?? null`);
  await click(".panel a", "Open in Explorer");
  await waitFor(CODE_SHOWN);
  await record("g1-open-in-explorer");
  // H. Findings: a reachability path chip in the finding panel.
  if (reachChip) {
    await go(`/a/${SNAP}/findings?category=all&ask=1&finding=5429`, 3000);
    await waitFor(`document.querySelector('.panel a.site-chip')`);
    await click(".panel a.site-chip", reachChip);
    await waitFor(CODE_SHOWN);
    await record("h1-reach-chip", { clicked: reachChip });
  } else out.steps["h1-reach-chip"] = { skipped: "no reachability chip on finding 5429" };
  // I. Deep link with lines= and Ask open.
  await go(`/a/${SNAP}/explore?node=${LAB.file_id}&lines=300-305&ask=1`, 2000);
  await waitFor(CODE_SHOWN);
  await record("i1-deep-link");
} finally {
  writeFileSync(join(OUT, `${LABEL}-${W}.json`), JSON.stringify(out, null, 2));
  cdp?.close();
  // The whole tree: killing only msedge's parent process leaves its renderers running.
  spawnSync("taskkill", ["/PID", String(proc.pid), "/T", "/F"], { stdio: "ignore" });
  // Renderers can outlive that tree: stop every msedge started with this run's own profile, only.
  const mine = `Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" | Where-Object { $_.CommandLine -like '*${basename(dir)}*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }`;
  spawnSync("powershell", ["-NoProfile", "-Command", mine], { stdio: "ignore" });
  await sleep(500);
  try { rmSync(dir, { recursive: true, force: true }); } catch { /* profile still locked */ }
}
