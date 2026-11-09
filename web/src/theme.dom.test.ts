// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  applyTheme,
  chooseTheme,
  followSystem,
  INSTANT_CLASS,
  readStored,
  resolveTheme,
  REVEAL_CLASS,
  REVEAL_MS,
  THEME_KEY,
} from "./theme";

// @ts-expect-error node:fs has no type declarations here; the tests run in Node
const { readFileSync } = await import("node:fs");
// jsdom's URL is not Node's, so read by path; vitest runs from web/.
// @ts-expect-error process has no type declarations here; the tests run in Node
const html: string = readFileSync(`${process.cwd()}/index.html`, "utf8");
// The boot script is the first inline <script> in <head>.
const head = html.slice(0, html.indexOf("</head>"));
const bootScript = head.slice(head.indexOf("<script>") + 8, head.indexOf("</script>"));

type MQ = { matches: boolean; listeners: Set<() => void> };
const queries = new Map<string, MQ>();
function setMedia(query: string, matches: boolean) {
  const q = queries.get(query) ?? { matches, listeners: new Set() };
  q.matches = matches;
  queries.set(query, q);
  q.listeners.forEach((l) => l());
}

beforeEach(() => {
  queries.clear();
  setMedia("(prefers-color-scheme: dark)", false);
  setMedia("(prefers-reduced-motion: reduce)", false);
  window.matchMedia = ((query: string) => {
    const q = queries.get(query) ?? { matches: false, listeners: new Set<() => void>() };
    queries.set(query, q);
    return {
      get matches() {
        return q.matches;
      },
      addEventListener: (_: string, l: () => void) => q.listeners.add(l),
      removeEventListener: (_: string, l: () => void) => q.listeners.delete(l),
    };
  }) as unknown as typeof window.matchMedia;
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.className = "";
});
afterEach(() => vi.useRealTimers());

const runBoot = () => new Function(bootScript)();
const theme = () => document.documentElement.dataset.theme;

describe("theme rule", () => {
  it("a stored pick wins; otherwise the system setting decides", () => {
    expect(resolveTheme("dark", false)).toBe("dark");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme(null, true)).toBe("dark");
    expect(resolveTheme("purple", false)).toBe("light");
  });
});

describe("index.html boot script (runs before first paint)", () => {
  it("follows the system when nothing is stored", () => {
    setMedia("(prefers-color-scheme: dark)", true);
    runBoot();
    expect(theme()).toBe("dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  it("uses the stored pick over the system", () => {
    setMedia("(prefers-color-scheme: dark)", true);
    localStorage.setItem(THEME_KEY, "light");
    runBoot();
    expect(theme()).toBe("light");
  });

  it("agrees with theme.ts on every case", () => {
    for (const stored of [null, "light", "dark", "junk"]) {
      for (const system of [false, true]) {
        localStorage.clear();
        if (stored) localStorage.setItem(THEME_KEY, stored);
        setMedia("(prefers-color-scheme: dark)", system);
        runBoot();
        expect(theme()).toBe(resolveTheme(stored, system));
      }
    }
  });

  it("survives storage that throws (private windows, blocked site data)", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    setMedia("(prefers-color-scheme: dark)", true);
    expect(() => runBoot()).not.toThrow();
    expect(theme()).toBe("dark");
    expect(readStored()).toBeNull();
    spy.mockRestore();
  });
});

describe("choosing a theme", () => {
  it("is remembered and applied instantly, with transitions off only during the swap", () => {
    const seen: boolean[] = [];
    const spy = vi.spyOn(window, "getComputedStyle").mockImplementation(() => {
      seen.push(document.documentElement.classList.contains(INSTANT_CLASS));
      return { color: "" } as CSSStyleDeclaration;
    });
    chooseTheme("dark"); // no origin and no View Transitions in jsdom: the instant switch
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(theme()).toBe("dark");
    expect(seen).toEqual([true]); // one style read, while every transition was off
    expect(document.documentElement.className).toBe(""); // nothing left behind
    spy.mockRestore();
  });

  it("still applies when storage throws on write", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => chooseTheme("dark")).not.toThrow();
    expect(theme()).toBe("dark");
    spy.mockRestore();
  });

  it("the system setting changes the theme only until the user picks one", () => {
    applyTheme("light");
    const stop = followSystem();
    setMedia("(prefers-color-scheme: dark)", true);
    expect(theme()).toBe("dark");
    localStorage.setItem(THEME_KEY, "light");
    setMedia("(prefers-color-scheme: dark)", false);
    setMedia("(prefers-color-scheme: dark)", true);
    expect(theme()).toBe("light");
    stop();
  });
});

// A stand-in for document.startViewTransition: records each call and lets the test run the update
// callback and settle `ready` and `finished` by hand, as a browser does over a few frames.
type Settle = { promise: Promise<void>; resolve: () => void; reject: () => void };
function settle(): Settle {
  let resolve!: () => void;
  let reject!: () => void;
  const promise = new Promise<void>((res, rej) => {
    resolve = res;
    reject = () => rej(new Error("skipped"));
  });
  return { promise, resolve, reject };
}
type FakeTransition = { update: () => void; ready: Settle; finished: Settle };
function fakeViewTransitions() {
  const calls: FakeTransition[] = [];
  const start = vi.fn((update: () => void) => {
    const call = { update, ready: settle(), finished: settle() };
    calls.push(call);
    return { ready: call.ready.promise, finished: call.finished.promise };
  });
  const animate = vi.fn();
  Object.assign(document, { startViewTransition: start });
  Object.assign(document.documentElement, { animate });
  return { calls, start, animate };
}
const flushPromises = () => new Promise((r) => setTimeout(r, 0));

function toggleAt(left: number, top: number): HTMLButtonElement {
  const button = document.createElement("button");
  vi.spyOn(button, "getBoundingClientRect").mockReturnValue({ left, top, width: 32, height: 32 } as DOMRect);
  return button;
}

describe("the circular reveal (View Transitions)", () => {
  afterEach(() => {
    delete (document as unknown as Record<string, unknown>).startViewTransition;
    delete (document.documentElement as unknown as Record<string, unknown>).animate;
  });

  it("grows a circle from the toggle's centre to the farthest window corner", async () => {
    const { calls, start, animate } = fakeViewTransitions();
    chooseTheme("dark", toggleAt(1300, 10));
    expect(start).toHaveBeenCalledTimes(1);
    expect(document.documentElement.classList.contains(REVEAL_CLASS)).toBe(true);
    expect(theme()).toBeUndefined(); // the page changes inside the update callback, not before

    calls[0].update();
    expect(theme()).toBe("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");

    calls[0].ready.resolve();
    await flushPromises();
    const [x, y] = [1316, 26];
    const r = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
    expect(animate).toHaveBeenCalledWith(
      { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${r}px at ${x}px ${y}px)`] },
      { duration: REVEAL_MS, easing: "ease-in-out", pseudoElement: "::view-transition-new(root)" },
    );

    calls[0].finished.resolve();
    await flushPromises();
    expect(document.documentElement.className).toBe("");
  });

  it("swaps the variables with transitions off inside the update, so the new snapshot is settled", async () => {
    const { calls } = fakeViewTransitions();
    const seen: boolean[] = [];
    const spy = vi.spyOn(window, "getComputedStyle").mockImplementation(() => {
      seen.push(document.documentElement.classList.contains(INSTANT_CLASS));
      return { color: "" } as CSSStyleDeclaration;
    });
    chooseTheme("dark", toggleAt(0, 0));
    expect(seen).toEqual([]);
    calls[0].update();
    expect(seen).toEqual([true]);
    expect(document.documentElement.classList.contains(INSTANT_CLASS)).toBe(false);
    spy.mockRestore();
    calls[0].finished.resolve();
    await flushPromises();
  });

  it("runs the same reveal in both directions", async () => {
    const { calls, start } = fakeViewTransitions();
    applyTheme("dark");
    chooseTheme("light", toggleAt(0, 0));
    calls[0].update();
    expect(theme()).toBe("light");
    calls[0].finished.resolve();
    await flushPromises();
    chooseTheme("dark", toggleAt(0, 0));
    expect(start).toHaveBeenCalledTimes(2);
    calls[1].update();
    expect(theme()).toBe("dark");
    calls[1].finished.resolve();
    await flushPromises();
  });

  it("ignores a second click while a reveal runs (no stacking), and works again once it ends", async () => {
    const { calls, start } = fakeViewTransitions();
    const button = toggleAt(0, 0);
    chooseTheme("dark", button);
    calls[0].update();
    chooseTheme("light", button); // double click
    expect(start).toHaveBeenCalledTimes(1);
    expect(theme()).toBe("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    calls[0].ready.resolve();
    calls[0].finished.resolve();
    await flushPromises();
    chooseTheme("light", button);
    expect(start).toHaveBeenCalledTimes(2);
    calls[1].update();
    calls[1].finished.resolve();
    await flushPromises();
    expect(theme()).toBe("light");
  });

  it("leaves no class and no guard behind when the transition is skipped or fails", async () => {
    const { calls, start, animate } = fakeViewTransitions();
    chooseTheme("dark", toggleAt(0, 0));
    calls[0].update();
    calls[0].ready.reject();
    calls[0].finished.reject();
    await flushPromises();
    expect(animate).not.toHaveBeenCalled();
    expect(document.documentElement.className).toBe("");
    expect(theme()).toBe("dark");
    chooseTheme("light", toggleAt(0, 0));
    expect(start).toHaveBeenCalledTimes(2);
    calls[1].update();
    calls[1].finished.resolve();
    await flushPromises();
  });

  it("switches instantly if starting the transition throws", () => {
    Object.assign(document, {
      startViewTransition: () => {
        throw new Error("InvalidStateError");
      },
    });
    chooseTheme("dark", toggleAt(0, 0));
    expect(theme()).toBe("dark");
    expect(document.documentElement.className).toBe("");
  });

  it("is never used under reduced motion: the switch is instant", () => {
    const { start } = fakeViewTransitions();
    setMedia("(prefers-reduced-motion: reduce)", true);
    chooseTheme("dark", toggleAt(0, 0));
    expect(start).not.toHaveBeenCalled();
    expect(theme()).toBe("dark");
    expect(document.documentElement.className).toBe("");
  });

  it("falls back to the instant switch where the browser has no View Transitions", () => {
    expect("startViewTransition" in document).toBe(false);
    chooseTheme("dark", toggleAt(0, 0));
    expect(theme()).toBe("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(document.documentElement.className).toBe("");
  });
});
