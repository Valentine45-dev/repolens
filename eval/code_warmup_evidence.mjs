// Code-colour warm-up (feat/code-highlight): does warming the worker after the map draws make the
// first file colour sooner, without slowing the map? A/B on the same flow, two builds:
//   --with    a build that has the warm-up   (this branch)
//   --without a build without it            (the commit before it)
// Flow per run, each run in a fresh headless browser with a throwaway profile (never a window):
//   open PyGoat's Explorer (the map, no file) -> map drawn -> wait --wait ms -> open a Python file
//   in-app (history.pushState + popstate, as a link does) -> colours -> open a JS file -> colours.
// Edge over the DevTools protocol, Firefox over WebDriver BiDi. Node 22+, no dependencies, no /ask.
//
//   node eval/code_warmup_evidence.mjs --with http://127.0.0.1:5173 --without http://127.0.0.1:5175 \
//        --browsers edge,firefox --runs 3 --wait 20000 --out eval/results/screenshots-code-highlight/warmup.json

import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
);
const BUILDS = { with: args.with ?? "http://127.0.0.1:5173", without: args.without ?? "http://127.0.0.1:5175" };
const BROWSERS = (args.browsers ?? "edge,firefox").split(",");
const RUNS = Number(args.runs ?? 3);
const WAIT = Number(args.wait ?? 20000);
const OUT = args.out ?? "warmup.json";
const W = 1366, H = 768;

const MAP = "/a/2/explore";
const PY = { path: "introduction/views.py", url: "/a/2/explore?node=1767&lines=21-28" };
const JS = { path: "introduction/static/js/lab_manager.js", url: "/a/2/explore?node=1794&lines=10-16" };

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// In the page before any script: when the map first drew, each code view state change, long tasks.
const RECORDER = `
  try { localStorage.setItem("repolens.theme", "light"); localStorage.setItem("repolens.mapHintSeen", "1"); } catch {}
  window.__w = { mapAt: null, states: [], long: [] };
  try { new PerformanceObserver((l) => { for (const e of l.getEntries()) __w.long.push({ start: e.startTime, duration: e.duration }); }).observe({ type: "longtask", buffered: true }); } catch {}
  let lastEl = null, lastState = null;
  new MutationObserver(() => {
    if (__w.mapAt === null && document.querySelector(".react-flow__node")) __w.mapAt = performance.now();
    const el = document.querySelector(".panel .code[data-colours]");
    const state = el ? el.dataset.colours : null;
    if (el === lastEl && state === lastState) return;
    lastEl = el; lastState = state;
    if (el) __w.states.push({ t: performance.now(), state, title: document.title });
  }).observe(document, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-colours"] });
`;

function launch(browser, port) {
  const dir = mkdtempSync(join(tmpdir(), `repolens-warm-${browser}-`));
  const exe = browser === "edge"
    ? ["C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", "C:/Program Files/Microsoft/Edge/Application/msedge.exe"].find(existsSync)
    : "C:/Program Files/Mozilla Firefox/firefox.exe";
  const flags = browser === "edge"
    ? [`--remote-debugging-port=${port}`, `--user-data-dir=${dir}`, "--headless=new", "--no-first-run", "--disable-gpu", `--window-size=${W},${H}`, "about:blank"]
    : ["--headless", "-no-remote", "-profile", dir, `--remote-debugging-port=${port}`, `--width=${W}`, `--height=${H}`, "about:blank"];
  const proc = spawn(exe, flags, { stdio: "ignore" });
  return { proc, dir };
}
function killTree(proc) {
  spawn("taskkill", ["/T", "/F", "/PID", String(proc.pid)], { stdio: "ignore" });
}

function socket(url) {
  return new Promise((res, rej) => {
    const ws = new WebSocket(url);
    let id = 0;
    const pending = new Map();
    ws.onmessage = (m) => {
      const msg = JSON.parse(m.data);
      if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
    };
    ws.onopen = () => res({
      send: (method, params = {}) => new Promise((ok, bad) => {
        const i = ++id;
        pending.set(i, (msg) => (msg.error ? bad(new Error(`${method}: ${msg.message ?? msg.error.message ?? msg.error}`)) : ok(msg.result)));
        ws.send(JSON.stringify({ id: i, method, params }));
      }),
      close: () => ws.close(),
    });
    ws.onerror = rej;
  });
}

/** A page driver with the same four calls for Edge (CDP) and Firefox (BiDi). */
let nextPort = 9350; // a new port per run, so a browser still shutting down never collides
async function driver(browser) {
  const port = nextPort++;
  const { proc, dir } = launch(browser, port);
  const end = Date.now() + 60000;
  let api;
  while (!api && Date.now() < end) {
    try {
      if (browser === "edge") {
        const t = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: "PUT" })).json();
        const s = await socket(t.webSocketDebuggerUrl);
        await s.send("Page.enable");
        await s.send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
        await s.send("Page.addScriptToEvaluateOnNewDocument", { source: RECORDER });
        api = {
          navigate: (url) => s.send("Page.navigate", { url }),
          evaluate: async (expr) => {
            const r = await s.send("Runtime.evaluate", { expression: `JSON.stringify(${expr})`, awaitPromise: true, returnByValue: true });
            return r.result.value === undefined ? undefined : JSON.parse(r.result.value);
          },
          close: s.close,
        };
      } else {
        const s = await socket(`ws://127.0.0.1:${port}/session`);
        await s.send("session.new", { capabilities: {} });
        const tree = await s.send("browsingContext.getTree", {});
        const context = tree.contexts[0].context;
        await s.send("browsingContext.setViewport", { context, viewport: { width: W, height: H } });
        await s.send("script.addPreloadScript", { functionDeclaration: `() => { ${RECORDER} }` });
        api = {
          navigate: (url) => s.send("browsingContext.navigate", { context, url, wait: "none" }),
          evaluate: async (expr) => {
            const r = await s.send("script.evaluate", { expression: `JSON.stringify(${expr})`, target: { context }, awaitPromise: true });
            return r.result?.value === undefined ? undefined : JSON.parse(r.result.value);
          },
          close: s.close,
        };
      }
    } catch { await sleep(500); }
  }
  if (!api) { killTree(proc); throw new Error(`${browser} did not start`); }
  return {
    ...api,
    async quit() {
      try { api.close(); } catch {}
      killTree(proc);
      await sleep(1500);
      try { rmSync(dir, { recursive: true, force: true }); } catch {}
    },
  };
}

async function waitFor(d, expr, ms = 90000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try { if (await d.evaluate(`!!(${expr})`)) return true; } catch {}
    await sleep(100);
  }
  return false;
}

async function openFile(d, base, f) {
  const from = (await d.evaluate("__w.states.length")) ?? 0;
  const t0 = await d.evaluate("performance.now()");
  await d.evaluate(`(history.pushState({}, "", ${JSON.stringify(f.url)}), dispatchEvent(new PopStateEvent("popstate")), 1)`);
  const name = f.path.split("/").pop();
  const ok = await waitFor(d, `__w.states.slice(${from}).some((s) => s.state === "on" && s.title.includes(${JSON.stringify(name)}))`, 90000);
  const states = (await d.evaluate("__w.states")).slice(from);
  const pending = states.find((s) => s.state === "pending");
  const on = states.find((s) => s.state === "on");
  return {
    file: f.path,
    coloured: ok,
    ms_plain_to_colours: pending && on ? Math.round(on.t - pending.t) : null,
    ms_click_to_colours: on ? Math.round(on.t - t0) : null,
  };
}

async function one(browser, build) {
  const base = BUILDS[build];
  let d;
  try {
    d = await driver(browser);
  } catch (err) {
    return { browser, build, error: String(err) };
  }
  try {
    await d.navigate(base + MAP);
    const drawn = await waitFor(d, "__w && __w.mapAt !== null", 180000);
    const mapAt = await d.evaluate("__w.mapAt");
    await sleep(WAIT);
    const long = await d.evaluate("__w.long");
    const py = await openFile(d, base, PY);
    const js = await openFile(d, base, JS);
    const longDuringWait = long.filter((l) => l.start >= mapAt);
    return {
      browser, build, map_drawn: drawn, ms_nav_to_map_drawn: mapAt === null ? null : Math.round(mapAt),
      long_tasks_before_map_ms: long.filter((l) => l.start < mapAt).map((l) => Math.round(l.duration)),
      long_tasks_after_map_while_waiting_ms: browser === "edge" ? longDuringWait.map((l) => Math.round(l.duration)) : "not supported in Firefox",
      python: py, javascript: js,
    };
  } catch (err) {
    return { browser, build, error: String(err) };
  } finally {
    await d.quit();
  }
}

const out = { when: new Date().toISOString(), builds: BUILDS, wait_after_map_ms: WAIT, note: args.note ?? "", runs: [] };
for (const browser of BROWSERS) {
  for (let run = 1; run <= RUNS; run++) {
    for (const build of run % 2 ? ["with", "without"] : ["without", "with"]) {
      const r = await one(browser, build);
      out.runs.push({ run, ...r });
      console.log(JSON.stringify({ run, ...r }));
    }
  }
}
writeFileSync(OUT, JSON.stringify(out, null, 2));
