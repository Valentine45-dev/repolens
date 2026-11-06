// First-paint fidelity of the web app, measured in headless Chromium (Edge or Chrome) at a fixed
// 1440x900 over the DevTools protocol. For each route it records
//   - the layout shifts of a normal load (Layout Instability API) and what moved,
//   - the position and size of landmark elements in the skeleton (app scripts blocked, so only the
//     page shipped in index.html is on screen) and in the loaded page, and
//   - a screenshot of each state.
// Needs Node 22+ (global WebSocket). No dependencies.
//
//   node eval/layout_shift.mjs --base http://localhost:5173 --out DIR [--label NAME] [--wait 7000]
//
// Writes DIR/<label>.json and DIR/<label>-<route>-{skeleton,loaded}.png. eval/layout_overlay.py
// turns the pairs into overlay and difference images.

import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
);
const BASE = args.base ?? "http://localhost:5173";
const OUT = args.out ?? ".";
const LABEL = args.label ?? "layout";
const WAIT = Number(args.wait ?? 7000);
const PORT = 9333;
const W = 1440;
const H = 900;

const BROWSERS = [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
];
const exe = BROWSERS.find(existsSync);
if (!exe) throw new Error("no Edge or Chrome found");

// Known analyses in the dev database (see PROGRESS.md): 2 PyGoat, 6 flask.
const RECENT = [
  { snapshotId: 6, url: "https://github.com/pallets/flask", commitSha: "49943b5aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", submittedAt: Date.now() - 864e5 },
  { snapshotId: 2, url: "https://github.com/adeyosemanputra/pygoat", commitSha: "46fef968f3f44d1191363baf936aaa3335dc5c6d", submittedAt: Date.now() - 36e5 },
];
const ROUTES = {
  home: { path: "/", landmarks: [".topbar", ".page-title", ".lede", "form", ".submit-row", "#repo-url", ".submit-row .button", ".field-message", ".examples", ".examples .chip", ".section", ".list-row"] },
  explore: {
    path: "/a/6/explore?level=folder&root=src%2Fflask",
    landmarks: [".topbar", ".analysis-header", ".analysis-heading", ".analysis-tabs", ".analysis-tab", ".analysis-ask", ".crumb-row", ".breadcrumbs-up", ".toolbar", ".segmented", ".check", ".toolbar .button", ".legend", ".explore-body"],
  },
  findings: {
    path: "/a/2/findings",
    landmarks: [".analysis-header", ".analysis-heading", ".analysis-tabs", ".analysis-ask", ".findings-head", ".section-title", ".findings-filters", ".filter", ".select-rule", ".input-small", ".findings-filters .check"],
  },
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function launch() {
  const dir = mkdtempSync(join(tmpdir(), "repolens-cdp-"));
  const proc = spawn(exe, [`--remote-debugging-port=${PORT}`, `--user-data-dir=${dir}`, "--headless=new", "--no-first-run", "--disable-gpu", `--window-size=${W},${H}`, "about:blank"], { stdio: "ignore" });
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/version`);
      if (r.ok) return proc;
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

const evaluate = async (cdp, expression) => {
  const r = await cdp.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + " " + (r.exceptionDetails.exception?.description ?? ""));
  return r.result.value;
};

async function shot(cdp, file) {
  const r = await cdp.send("Page.captureScreenshot", { format: "png" });
  writeFileSync(file, Buffer.from(r.data, "base64"));
}

const RECTS = (landmarks) => `(() => { const out = {}; for (const sel of ${JSON.stringify(landmarks)}) { const els = [...document.querySelectorAll(sel)].slice(0, 4); out[sel] = els.map((e) => { const r = e.getBoundingClientRect(); return [Math.round(r.x * 10) / 10, Math.round(r.y * 10) / 10, Math.round(r.width * 10) / 10, Math.round(r.height * 10) / 10]; }); } return out; })()`;

const SHIFTS = `new Promise((res) => { const out = []; let total = 0; const po = new PerformanceObserver((l) => { for (const e of l.getEntries()) { if (e.hadRecentInput) continue; total += e.value; out.push({ value: +e.value.toFixed(5), at: Math.round(e.startTime), moved: (e.sources || []).map((s) => ({ node: s.node && s.node.nodeType === 1 ? s.node.tagName.toLowerCase() + '.' + String(typeof s.node.className === 'string' ? s.node.className : '').split(' ')[0] : '?', from: [s.previousRect.x, s.previousRect.y, s.previousRect.width, s.previousRect.height].map(Math.round), to: [s.currentRect.x, s.currentRect.y, s.currentRect.width, s.currentRect.height].map(Math.round) })) }); } }); po.observe({ type: 'layout-shift', buffered: true }); setTimeout(() => { po.disconnect(); res({ cls: +total.toFixed(5), shifts: out }); }, 400); })`;

mkdirSync(OUT, { recursive: true });
const proc = await launch();
const result = { base: BASE, viewport: [W, H], browser: exe.split("/").pop(), routes: {} };
try {
  const cdp = await connect();
  await cdp.send("Page.enable");
  await cdp.send("Network.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  // The recent list lives in localStorage of this origin: set it once so names are known.
  await cdp.send("Page.navigate", { url: `${BASE}/404-placeholder` });
  await sleep(1500);
  await evaluate(cdp, `localStorage.setItem('repolens.recent', ${JSON.stringify(JSON.stringify(RECENT))}); 1`);

  for (const [name, route] of Object.entries(ROUTES)) {
    // 1. the skeleton alone: block every script, so only what index.html ships is on screen
    await cdp.send("Network.setBlockedURLs", { urls: ["*/assets/*.js", "*/src/*.tsx", "*/src/*.ts", "*/@vite/*"] });
    await cdp.send("Page.navigate", { url: BASE + route.path });
    await sleep(2500);
    const skeleton = await evaluate(cdp, RECTS(route.landmarks));
    await shot(cdp, join(OUT, `${LABEL}-${name}-skeleton.png`));

    // 2. a normal load: layout shifts and the loaded layout
    await cdp.send("Network.setBlockedURLs", { urls: [] });
    await cdp.send("Page.navigate", { url: BASE + route.path });
    await sleep(WAIT);
    const shifts = await evaluate(cdp, SHIFTS);
    const loaded = await evaluate(cdp, RECTS(route.landmarks));
    await shot(cdp, join(OUT, `${LABEL}-${name}-loaded.png`));

    // 3. landmark by landmark: how far did the skeleton's element sit from the real one?
    const compare = {};
    for (const sel of route.landmarks) {
      const a = skeleton[sel] ?? [];
      const b = loaded[sel] ?? [];
      compare[sel] = { skeleton: a, loaded: b, maxDelta: a.length && b.length ? Math.max(...a.slice(0, b.length).flatMap((r, i) => r.map((v, k) => Math.abs(v - b[i][k])))) : null };
    }
    result.routes[name] = { path: route.path, ...shifts, landmarks: compare };
    console.log(`${name.padEnd(9)} CLS ${shifts.cls}  (${shifts.shifts.length} shifts)  skeleton vs loaded, largest landmark delta: ${Math.max(0, ...Object.values(compare).map((c) => c.maxDelta ?? 0))}px`);
  }
  cdp.close();
} finally {
  proc.kill();
}
writeFileSync(join(OUT, `${LABEL}.json`), JSON.stringify(result, null, 2));
console.log(`wrote ${join(OUT, LABEL + ".json")}`);
