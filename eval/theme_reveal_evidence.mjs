// Evidence for the theme reveal (fix/theme-transition). Needs a production build served on :4180
// (`npx vite preview --outDir <build> --port 4180` in web/) and the API on :8000 with redash
// (snapshot 13). Windows only (Edge and Firefox paths, window sizing).
//
//   node eval/theme_reveal_evidence.mjs edge|firefox [reduced]
//
// Real windows at this PC's screen size; the real toggle is clicked with real input (DevTools
// protocol for Edge, WebDriver BiDi for Firefox; Node's own WebSocket, no packages). A test-only hook
// injected through that protocol (not in the app) counts View Transitions and can hold the reveal
// animation at a set time. Edge: page screenshots of the held frame. Firefox: its screenshot command
// draws the page without the View Transition layer and a screen capture would catch other windows,
// so the held frame is recorded as the computed clip-path of ::view-transition-new(root).
// "reduced": Edge emulates prefers-reduced-motion; Firefox gets ui.prefersReducedMotion=1.
import { spawn, execFileSync } from "node:child_process";
import { writeFileSync, mkdirSync, rmSync } from "node:fs";
import { join, dirname } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "results", "screenshots-theme-reveal");
const BASE = "http://127.0.0.1:4180";
const PAGES = { explorer: "/a/13/explore?node=3658&ask=1", findings: "/a/13/findings?category=all" };
const which = process.argv[2];
const reduced = process.argv[3] === "reduced";
const REVEAL_MS = 450;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const EXE = {
  edge: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  firefox: "C:/Program Files/Mozilla Firefox/firefox.exe",
};

function wsClient(url) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    let id = 0;
    const waiting = new Map();
    ws.onmessage = (m) => {
      const msg = JSON.parse(m.data);
      if (msg.id !== undefined && waiting.has(msg.id)) {
        const { res, rej } = waiting.get(msg.id);
        waiting.delete(msg.id);
        if (msg.error || msg.type === "error") rej(new Error(JSON.stringify(msg.error ?? msg.message)));
        else res(msg.result);
      }
    };
    ws.onerror = reject;
    ws.onopen = () => resolve({
      send(method, params = {}) {
        const i = ++id;
        ws.send(JSON.stringify({ id: i, method, params }));
        return new Promise((res, rej) => waiting.set(i, { res, rej }));
      },
    });
  });
}
async function retry(fn) {
  for (let i = 0; i < 60; i++) { try { return await fn(); } catch { await sleep(500); } }
  throw new Error("retry failed");
}

async function edge() {
  const port = 9634;
  const prof = join(tmpdir(), "repolens-reveal-edge");
  rmSync(prof, { recursive: true, force: true });
  spawn(EXE.edge, [`--remote-debugging-port=${port}`, `--user-data-dir=${prof}`, "--no-first-run", "--no-default-browser-check",
    "--start-maximized", "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding", "about:blank"], { stdio: "ignore" });
  const list = await retry(async () => (await fetch(`http://127.0.0.1:${port}/json/list`)).json());
  const c = await wsClient(list.find((t) => t.type === "page").webSocketDebuggerUrl);
  await c.send("Page.enable");
  const version = (await c.send("Browser.getVersion")).product;
  if (reduced) await c.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  return {
    version,
    async navigate(url) { await c.send("Page.navigate", { url }); await sleep(500); },
    async evaluate(expr) {
      const r = await c.send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 400));
      return r.result.value;
    },
    async click(x, y) {
      await c.send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
      await c.send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
      await c.send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
    },
    async enter() {
      const k = { key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 };
      await c.send("Input.dispatchKeyEvent", { type: "rawKeyDown", ...k });
      await c.send("Input.dispatchKeyEvent", { type: "char", ...k, text: "\r" });
      await c.send("Input.dispatchKeyEvent", { type: "keyUp", ...k });
    },
    async shot(file) { const r = await c.send("Page.captureScreenshot", { format: "jpeg", quality: 72 }); writeFileSync(file, Buffer.from(r.data, "base64")); },
    async front() { await c.send("Page.bringToFront"); },
    async quit() { try { await c.send("Browser.close"); } catch {} },
  };
}

async function firefox() {
  const port = 9644;
  const prof = join(tmpdir(), "repolens-reveal-firefox");
  rmSync(prof, { recursive: true, force: true });
  mkdirSync(prof, { recursive: true });
  writeFileSync(join(prof, "user.js"), [
    'user_pref("browser.shell.checkDefaultBrowser", false);',
    'user_pref("browser.aboutwelcome.enabled", false);',
    'user_pref("datareporting.policy.dataSubmissionEnabled", false);',
    'user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);',
    'user_pref("browser.startup.homepage_override.mstone", "ignore");',
    'user_pref("browser.startup.page", 0);',
    // The OS-level "reduce motion" setting, as Firefox reads it (1 = reduce).
    reduced ? 'user_pref("ui.prefersReducedMotion", 1);' : "",
  ].join("\n"));
  const proc = spawn(EXE.firefox, ["-no-remote", "-profile", prof, "--remote-debugging-port", String(port), "about:blank"], { stdio: "ignore" });
  const win = (action, out = "") =>
    execFileSync("powershell", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", join(HERE, "theme_reveal_window.ps1"), "-ProcId", String(proc.pid), "-Action", action, "-Out", out]);
  const c = await retry(() => wsClient(`ws://127.0.0.1:${port}/session`));
  const s = await c.send("session.new", { capabilities: {} });
  const context = (await c.send("browsingContext.getTree", {})).contexts[0].context;
  const act = (actions) => c.send("input.performActions", { context, actions });
  return {
    version: `Firefox ${s.capabilities.browserVersion}`,
    async navigate(url) { await c.send("browsingContext.navigate", { context, url, wait: "complete" }); },
    async evaluate(expr) {
      const r = await c.send("script.evaluate", { expression: `(async () => JSON.stringify(await (${expr.trim().replace(/;\s*$/, "")})))()`, target: { context }, awaitPromise: true });
      if (r.type === "exception") throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 400));
      return r.result.value === undefined ? undefined : JSON.parse(r.result.value);
    },
    async click(x, y) {
      await act([{ type: "pointer", id: "mouse", parameters: { pointerType: "mouse" }, actions: [
        { type: "pointerMove", x: Math.round(x), y: Math.round(y) }, { type: "pointerDown", button: 0 }, { type: "pointerUp", button: 0 }] }]);
    },
    async enter() { await act([{ type: "key", id: "kb", actions: [{ type: "keyDown", value: "\uE007" }, { type: "keyUp", value: "\uE007" }] }]); },
    // Firefox's own screenshot command draws the document without the View Transition layer, so
    // capture the test window itself (only this process's window, even if others cover it).
    // Firefox paints the View Transition layer only to the screen (its screenshot command and
    // PrintWindow draw the page without it), so the test window is brought to the front and the
    // screen inside its box is captured.
    // ...and a screen capture would catch whatever window the owner has in front, so Firefox gets
    // no pictures: the held frame is recorded as the pseudo-element's computed clip-path instead.
    async shot() {},
    noPictures: true,
    maximize() { win("size"); },
    async front() { await c.send("browsingContext.activate", { context }); },
    async quit() { try { await c.send("browser.close", {}); } catch {} },
  };
}

const HOOK = `(() => {
  if (window.__h) return 1;
  const H = (window.__h = { vt: [], anims: [], pauseAt: null, paused: null });
  const orig = document.startViewTransition;
  if (typeof orig === "function")
    document.startViewTransition = function (cb) {
      const rec = { t0: performance.now(), before: document.documentElement.dataset.theme };
      H.vt.push(rec);
      const t = orig.call(document, cb);
      t.ready.then(() => (rec.ready = performance.now() - rec.t0), () => (rec.readyErr = true));
      t.finished.then(
        () => { rec.finished = performance.now() - rec.t0; rec.classAfter = document.documentElement.className; rec.after = document.documentElement.dataset.theme; },
        () => (rec.finErr = true));
      return t;
    };
  // The reveal is a CSS animation on ::view-transition-new(root): once the transition is ready,
  // note it and, for a screenshot, hold it at H.pauseAt ms.
  const origStart = document.startViewTransition;
  if (typeof origStart === "function")
    document.startViewTransition = function (cb) {
      const t = origStart.call(document, cb);
      t.ready.then(() => {
        const a = document.getAnimations().find((x) => x.effect && x.effect.pseudoElement === "::view-transition-new(root)");
        if (!a) return;
        const timing = a.effect.getTiming();
        H.anims.push({ pseudo: a.effect.pseudoElement, name: a.animationName, duration: timing.duration, easing: timing.easing,
          x: getComputedStyle(document.documentElement).getPropertyValue("--theme-reveal-x"),
          y: getComputedStyle(document.documentElement).getPropertyValue("--theme-reveal-y"),
          r: getComputedStyle(document.documentElement).getPropertyValue("--theme-reveal-r") });
        if (H.pauseAt !== null) { a.pause(); a.currentTime = H.pauseAt; H.paused = a; }
      }, () => {});
      return t;
    };
  return 1;
})()`;

const b = which === "firefox" ? await firefox() : await edge();
console.log(b.version, reduced ? "(reduced motion)" : "");
await sleep(2000);
if (which === "firefox") b.maximize(); // only the test browser's own window
await b.front();
await b.navigate(BASE + "/");
await b.evaluate("(localStorage.setItem('repolens.theme', 'light'), localStorage.setItem('repolens.mapHintSeen', '1'), 1)");

const dir = join(OUT, reduced ? `${which}-reduced-motion` : which);
mkdirSync(dir, { recursive: true });
const log = { browser: b.version, reducedMotion: reduced, when: new Date().toISOString(), pages: {} };

async function open(key) {
  await b.evaluate("(localStorage.setItem('repolens.theme', 'light'), 1)");
  await b.navigate(BASE + PAGES[key]);
  for (let i = 0; i < 120; i++) {
    const ok = await b.evaluate(key === "explorer"
      ? "document.querySelectorAll('.react-flow__node').length > 0 && document.querySelectorAll('.code-line, pre, code').length > 0"
      : "document.querySelectorAll('*').length > 600");
    if (ok) break;
    await sleep(500);
  }
  await sleep(2500);
  await b.evaluate(HOOK);
  const info = await b.evaluate("({ w: innerWidth, h: innerHeight, dpr: devicePixelRatio, vt: typeof document.startViewTransition === 'function', reduced: matchMedia('(prefers-reduced-motion: reduce)').matches, theme: document.documentElement.dataset.theme })");
  const tog = await b.evaluate("(() => { const r = document.querySelector('.theme-toggle').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()");
  return { info, tog };
}
const state = () => b.evaluate("({ theme: document.documentElement.dataset.theme, cls: document.documentElement.className, vt: __h.vt.length, stored: localStorage.getItem('repolens.theme'), pressed: document.querySelector('.theme-toggle').getAttribute('aria-pressed') })");
async function waitSettled() {
  for (let i = 0; i < 40; i++) {
    const s = await b.evaluate("(() => { const r = __h.vt[__h.vt.length - 1]; return !r || r.finished !== undefined || r.finErr; })()");
    if (s) break;
    await sleep(100);
  }
  await sleep(400);
}

// One switch by a real click; with `pauseAt`, the reveal is held at that time for the screenshot.
async function switchAndShoot(tog, name, pauseAt) {
  const before = await state();
  const dirName = before.theme === "dark" ? "dark-to-light" : "light-to-dark";
  name = name.replace("DIR", dirName);
  await b.evaluate(`(__h.pauseAt = ${pauseAt ?? "null"}, 1)`);
  await b.click(tog.x, tog.y);
  let shot = null;
  let held = null;
  if (pauseAt !== null && pauseAt !== undefined) {
    for (let i = 0; i < 50; i++) { if (await b.evaluate("!!__h.paused")) break; await sleep(50); }
    await sleep(400); // let the held frame paint
    held = await b.evaluate(`(() => {
      const s = (p) => getComputedStyle(document.documentElement, p);
      const a = __h.paused;
      return { progress: a && a.effect.getComputedTiming().progress, newClipPath: s("::view-transition-new(root)").clipPath,
        oldClipPath: s("::view-transition-old(root)").clipPath, oldAnimation: s("::view-transition-old(root)").animationName,
        newAnimation: s("::view-transition-new(root)").animationName };
    })()`);
    if (!b.noPictures) { shot = `${name}.jpg`; await b.shot(join(dir, shot)); }
    await b.evaluate("(__h.paused && __h.paused.play(), __h.paused = null, __h.pauseAt = null, 1)");
  } else {
    await sleep(120);
    if (!b.noPictures) { shot = `${name}.jpg`; await b.shot(join(dir, shot)); }
  }
  await waitSettled();
  const after = await state();
  const vt = await b.evaluate("__h.vt[__h.vt.length - 1] || null");
  return { name, shot, pauseAtMs: pauseAt ?? null, held, before, after, transition: after.vt > before.vt ? vt : null };
}

for (const key of Object.keys(PAGES)) {
  const { info, tog } = await open(key);
  const page = (log.pages[key] = { info, toggleCentre: tog, steps: [] });
  console.log(key, JSON.stringify(info));
  await b.shot(join(dir, `${key}-rest-light.jpg`));
  if (reduced) {
    // Reduced motion: both directions, each switch shot ~120 ms after the click.
    page.steps.push(await switchAndShoot(tog, `${key}-DIR-instant`, null));
    page.steps.push(await switchAndShoot(tog, `${key}-DIR-instant`, null));
  } else {
    const fracs = key === "explorer" ? [0.25, 0.5, 0.75] : [0.5];
    for (const f of fracs) {
      const pct = Math.round(f * 100);
      page.steps.push(await switchAndShoot(tog, `${key}-DIR-${pct}pct`, f * REVEAL_MS));
      page.steps.push(await switchAndShoot(tog, `${key}-DIR-${pct}pct`, f * REVEAL_MS));
    }
    page.steps.push(await switchAndShoot(tog, `${key}-after-reveal-dark`, null));
    await b.shot(join(dir, `${key}-rest-dark.jpg`));
    page.steps.push(await switchAndShoot(tog, `${key}-after-reveal-light`, null));
  }
  if (key === "explorer" && !reduced) {
    // No stacking: two real clicks 80 ms apart, then Enter twice 80 ms apart on the focused toggle.
    const s0 = await state();
    await b.click(tog.x, tog.y);
    await sleep(80);
    await b.click(tog.x, tog.y);
    await waitSettled();
    const s1 = await state();
    await b.evaluate("(document.querySelector('.theme-toggle').focus(), 1)");
    page.keyFocus = await b.evaluate("({ active: document.activeElement && document.activeElement.className, hasFocus: document.hasFocus() })");
    await b.enter();
    await sleep(80);
    await b.enter();
    await waitSettled();
    const s2 = await state();
    page.doubleClick = { before: s0, afterTwoClicks: s1, afterTwoEnters: s2 };
  }
  page.anims = await b.evaluate("__h.anims");
  writeFileSync(join(dir, "run.json"), JSON.stringify(log, null, 2));
}
await b.quit();
console.log("saved", dir);
process.exit(0);
