// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { applyTheme, chooseTheme, followSystem, readStored, resolveTheme, THEME_KEY, TRANSITION_MS } from "./theme";

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
  it("is remembered and applied, and eases colours for 200ms only", () => {
    vi.useFakeTimers();
    chooseTheme("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(theme()).toBe("dark");
    expect(document.documentElement.classList.contains("theme-switching")).toBe(true);
    vi.advanceTimersByTime(TRANSITION_MS);
    expect(document.documentElement.classList.contains("theme-switching")).toBe(false);
  });

  it("is instant under reduced motion (no transition class at all)", () => {
    setMedia("(prefers-reduced-motion: reduce)", true);
    chooseTheme("dark");
    expect(theme()).toBe("dark");
    expect(document.documentElement.classList.contains("theme-switching")).toBe(false);
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
