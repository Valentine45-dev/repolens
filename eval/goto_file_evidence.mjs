// "Go to file" (feat/goto-file): screenshots and checks in headless Edge (throwaway profile, never
// a window on screen) at a real 1366x768, over the DevTools protocol. Keys are real key events
// (Input.dispatchKeyEvent); text is typed with Input.insertText. No dependencies, no API spend
// (graph and file endpoints only; nothing is asked).
//
//   node eval/goto_file_evidence.mjs --base http://127.0.0.1:5173 --out DIR [--theme light|dark] [--width 1366]
//
// Writes DIR/<theme>-<width>-<step>.png and DIR/<theme>-<width>.json.

import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
);
const BASE = args.base ?? "http://127.0.0.1:5173";
const OUT = args.out ?? ".";
const THEME = args.theme ?? "light";
const W = Number(args.width ?? 1366);
const H = W >= 1600 ? 1080 : 768;
const PORT = 9353;
const BLACK = 7; // psf/black: 55 files with tests off, 371 test files hidden
const REDASH = 13; // the largest analysis here: 970 openable files

const exe = [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
].find(existsSync);
if (!exe) throw new Error("no Edge found");
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function launch() {
  const dir = mkdtempSync(join(tmpdir(), "repolens-cdp-"));
  const flags = [`--remote-debugging-port=${PORT}`, `--user-data-dir=${dir}`, "--headless=new", "--no-first-run",
    "--disable-gpu", `--window-size=${W},${H}`, "about:blank"];
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
  writeFileSync(join(OUT, `${THEME}-${W}-${step}.png`), Buffer.from(r.data, "base64"));
}
async function waitFor(expr, ms = 60000, what = expr) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (await evaluate(`!!(${expr})`)) { await sleep(300); return true; }
    await sleep(100);
  }
  await shot("timeout");
  throw new Error(`timed out (${ms} ms) waiting for: ${what}`);
}
async function go(path) {
  await cdp.send("Page.navigate", { url: BASE + path });
  await sleep(500);
}

const KEYS = {
  k: { key: "k", code: "KeyK", windowsVirtualKeyCode: 75 },
  "/": { key: "/", code: "Slash", windowsVirtualKeyCode: 191, text: "/" },
  Enter: { key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, text: "\r" },
  Escape: { key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 },
  ArrowDown: { key: "ArrowDown", code: "ArrowDown", windowsVirtualKeyCode: 40 },
  a: { key: "a", code: "KeyA", windowsVirtualKeyCode: 65 },
};
/** A real key press; modifiers: 2 = Ctrl. */
async function press(name, modifiers = 0) {
  const k = KEYS[name];
  const text = modifiers ? undefined : k.text;
  await cdp.send("Input.dispatchKeyEvent", { type: text ? "keyDown" : "rawKeyDown", modifiers, ...k, text });
  await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", modifiers, ...k, text: undefined });
}
async function typeText(text) {
  await press("a", 2); // select what is there, so the new text replaces it
  await cdp.send("Input.insertText", { text });
}

const MAP_READY = `document.querySelector('.react-flow__node') && !document.querySelector('.analysis-search:disabled')`;
const DIALOG_OPEN = `document.querySelector('dialog.goto[open]')`;
const LIST_READY = `document.querySelector('dialog.goto[open]') && !document.querySelector('.goto-results[aria-busy]')`;
const STATE = `(() => {
  const d = document.querySelector('dialog.goto[open]');
  const params = new URLSearchParams(location.search);
  const panel = document.querySelector('.panel-title');
  return {
    dialog: !!d,
    focus: document.activeElement?.className || document.activeElement?.tagName,
    options: [...document.querySelectorAll('[role=option]')].slice(0, 6).map((o) => ({
      path: o.title, selected: o.getAttribute('aria-selected') === 'true',
      hits: [...o.querySelectorAll('mark')].map((m) => m.textContent), tag: o.querySelector('.goto-tag')?.textContent ?? null,
    })),
    optionCount: document.querySelectorAll('[role=option]').length,
    message: document.querySelector('.goto-message')?.textContent ?? null,
    note: document.querySelector('.goto-note')?.textContent ?? null,
    url: location.pathname + location.search,
    node: params.get('node'), tests: params.get('tests'),
    panel: panel ? panel.textContent : null,
    codeTab: document.querySelector('.panel [role=tab][aria-selected=true]')?.textContent ?? null,
    code: !!document.querySelector('.panel .code[aria-label]'),
    testsChecked: [...document.querySelectorAll('.toolbar label.check')].find((l) => l.textContent.includes('Tests'))?.querySelector('input').checked ?? null,
  };
})()`;
// Nothing sticks out of the dialog sideways: the field, every row and every tag end inside it; a
// list taller than the dialog scrolls (a vertical scrollbar), never sideways.
const OVERFLOW = `(() => {
  const d = document.querySelector('dialog.goto[open]');
  if (!d) return null;
  const box = d.getBoundingClientRect();
  const results = d.querySelector('.goto-results');
  const inner = d.querySelector('.goto-inner');
  const outside = (el) => el.getBoundingClientRect().right > box.right + 0.5;
  return {
    dialogWidth: Math.round(box.width),
    innerSideways: inner.scrollWidth > inner.clientWidth,
    resultsSideways: results.scrollWidth > results.clientWidth,
    fieldOutside: outside(d.querySelector('.goto-input')),
    rowsOutside: [...d.querySelectorAll('[role=option]')].filter(outside).length,
    tagsOutside: [...d.querySelectorAll('.goto-tag')].filter(outside).length,
    rows: d.querySelectorAll('[role=option]').length,
    scrollsDown: results.scrollHeight > results.clientHeight,
    scrollbarShown: results.offsetWidth - results.clientWidth > 0,
  };
})()`;
const fits = (o) => o && !o.innerSideways && !o.resultsSideways && !o.fieldOutside && o.rowsOutside === 0 && o.tagsOutside === 0
  && (!o.scrollsDown || o.scrollbarShown);
// The file-list request as the network saw it (Resource Timing): server time vs. the page's own.
const LIST_REQUEST = `(() => {
  const e = performance.getEntriesByType('resource').filter((r) => /exclude_tests=false/.test(r.name)).pop();
  return e ? { totalMs: Math.round(e.duration), waitingForServerMs: Math.round(e.responseStart - e.requestStart),
    downloadMs: Math.round(e.responseEnd - e.responseStart), startedAfterNavigationMs: Math.round(e.startTime) } : null;
})()`;
const LOADED = (pattern) => `performance.getEntriesByType('resource').filter((e) => ${pattern}.test(e.name)).length`;

const { proc, dir } = await launch();
const report = { theme: THEME, width: W, base: BASE, steps: {}, checks: {} };
try {
  cdp = await connect();
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await cdp.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: THEME }] });

  // 1. Home: no search code and no file list.
  await go("/");
  await waitFor(`document.querySelector('h1')`);
  await sleep(1500);
  report.checks.home = { goToFileChunk: await evaluate(LOADED("/GoToFile-/")), graphRequests: await evaluate(LOADED("/\\/graph/")) };

  // 2. The Explorer on black (tests off): the button in the header; nothing loaded for search yet.
  await go(`/a/${BLACK}/explore`);
  await waitFor(MAP_READY, 90000, "the map");
  await shot("1-header");
  report.checks.explorerBeforeOpen = {
    goToFileChunk: await evaluate(LOADED("/GoToFile-/")),
    listWithTests: await evaluate(LOADED("/exclude_tests=false/")),
    button: await evaluate(`document.querySelector('.analysis-search').textContent`),
  };

  // 3. Ctrl+K opens it; time to the open dialog and to the loaded list (first time: chunk + list).
  let t0 = Date.now();
  await press("k", 2);
  await waitFor(DIALOG_OPEN, 20000, "the dialog");
  const openMs = Date.now() - t0;
  await waitFor(LIST_READY, 30000, "the file list");
  report.checks.firstOpen = { dialogMs: openMs, listMs: Date.now() - t0, note: "polled every 100 ms; includes 300 ms settle",
    listRequest: await evaluate(LIST_REQUEST) };
  await shot("2-empty-query");
  report.steps.emptyQuery = await evaluate(STATE);

  await typeText("trans");
  await waitFor(`document.querySelectorAll('[role=option]').length > 0`);
  await shot("3-results-trans");
  report.steps.trans = await evaluate(STATE);
  report.checks.overflowTrans = await evaluate(OVERFLOW);

  await typeText("test_black");
  await waitFor(`document.querySelector('[role=option] .goto-tag')`);
  await shot("4-hidden-test-file");
  report.steps.testBlack = await evaluate(STATE);

  await typeText("zzqx");
  await waitFor(`document.querySelector('.goto-message')?.textContent.startsWith('No files')`);
  await shot("5-empty-state");
  report.steps.empty = await evaluate(STATE);

  // 4. Open the hidden test file: tests turn on, the file panel shows its code.
  await typeText("test_black");
  await waitFor(`document.querySelector('[role=option] .goto-tag')`);
  await press("Enter");
  await waitFor(`document.querySelector('.panel .code[aria-label]') && document.querySelector('.react-flow__node')`, 60000);
  await sleep(1500);
  await shot("6-opened-test-file");
  report.steps.opened = await evaluate(STATE);

  // 5. Esc with the panel open: one press closes only the dialog; focus back on the opener.
  await evaluate(`document.querySelector('.analysis-search').focus()`);
  await press("/");
  await waitFor(LIST_READY);
  await press("Escape");
  await sleep(300);
  report.checks.escapeWithPanel = await evaluate(STATE)
    .then((s) => ({ dialog: s.dialog, panelStillOpen: s.panel !== null, node: s.node, focus: s.focus }));

  // 6. "/" typed in a text field does not open it (Findings' path filter).
  await go(`/a/${BLACK}/findings`);
  const PATH_FIELD = `[...document.querySelectorAll('.filter')].find((f) => f.textContent.includes('Path starts with'))?.querySelector('input')`;
  await waitFor(`${PATH_FIELD} && document.querySelector('.findings-table table.table:not([aria-hidden])') && !document.querySelector('.findings-table[aria-busy]') && !document.querySelector('.analysis-search:disabled')`, 90000, "the Findings list");
  await evaluate(`${PATH_FIELD}.focus()`);
  report.checks.slashFieldFocused = await evaluate(`document.activeElement === ${PATH_FIELD}`);
  await press("/");
  await sleep(500);
  report.checks.slashInField = { dialogOpened: await evaluate(`!!(${DIALOG_OPEN})`), fieldValue: await evaluate(`document.activeElement.value`) };

  // 7. From Findings: opens the file in the Explorer.
  // Clear the "/" again (the field applies on blur), then leave the field.
  await press("a", 2);
  await cdp.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: "Backspace", code: "Backspace", windowsVirtualKeyCode: 8 });
  await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Backspace", code: "Backspace", windowsVirtualKeyCode: 8 });
  await evaluate(`document.activeElement.blur()`);
  await sleep(500);
  await press("k", 2);
  await waitFor(LIST_READY, 30000, "the dialog on Findings");
  await typeText("src/black/trans.py");
  await waitFor(`document.querySelectorAll('[role=option]').length > 0`);
  await press("Enter");
  await waitFor(`document.querySelector('.panel .code[aria-label]')`, 60000);
  report.checks.fromFindings = await evaluate(STATE).then((s) => ({ url: s.url, panel: s.panel, codeTab: s.codeTab }));

  // 8. Keystroke cost on the largest list (redash, tests on: 970 files + 165 folders): input event to
  //    the field's echo (synchronous) and to the list's DOM update (a deferred render of up to 50 rows).
  await go(`/a/${REDASH}/explore?view=list`);
  await waitFor(`document.querySelector('table') && !document.querySelector('.analysis-search:disabled')`, 90000);
  await press("k", 2);
  await waitFor(LIST_READY, 30000);
  report.checks.redashKeystrokes = await evaluate(`(async () => {
    const input = document.querySelector('.goto-input');
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    const out = [];
    for (const round of [0, 1, 2]) {
      for (const q of ['t', 'tr', 'tra', 'tran', 'trans', 'transf', 'zzq', 'src/', 'components/']) {
        const results = document.querySelector('.goto-results');
        let listAt = null;
        const seen = new MutationObserver(() => { listAt ??= performance.now(); });
        seen.observe(results, { childList: true, subtree: true, characterData: true });
        const t0 = performance.now();
        setter.call(input, q);
        input.dispatchEvent(new Event('input', { bubbles: true }));
        const echo = performance.now() - t0; // the field's own update (sync)
        for (let i = 0; i < 100 && listAt === null; i++) await new Promise((r) => setTimeout(r, 5));
        seen.disconnect();
        if (round === 2) out.push({ q, echoMs: +echo.toFixed(1), listMs: listAt === null ? null : +(listAt - t0).toFixed(1),
          options: document.querySelectorAll('[role=option]').length,
          message: document.querySelector('.goto-message')?.textContent ?? null });
        await new Promise((r) => setTimeout(r, 30));
      }
    }
    return out;
  })()`);
  // Long rows: redash's deepest paths, 50 rows.
  await typeText("index");
  await waitFor(`document.querySelectorAll('[role=option]').length >= 20`, 30000, "redash rows");
  report.checks.overflowRedash = await evaluate(OVERFLOW);
  await shot("7-redash-list");
  report.checks.noSidewaysOverflow = fits(report.checks.overflowTrans) && fits(report.checks.overflowRedash);
  writeFileSync(join(OUT, `${THEME}-${W}.json`), JSON.stringify(report, null, 1));
  console.log(JSON.stringify(report, null, 1));
} finally {
  cdp?.close();
  proc.kill();
  await sleep(800);
  try { rmSync(dir, { recursive: true, force: true }); } catch { /* still locked */ }
}
