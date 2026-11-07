// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SiteChips, visibleSites } from "./SiteChips";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const mk = (n: number, confidence: number | null = null) =>
  Array.from({ length: n }, (_, i) => ({ line: (i + 1) * 10, confidence }));

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const chips = () => [...host.querySelectorAll<HTMLElement>(".site-chip:not(.site-chip-more)")];
const button = (text: RegExp) =>
  [...host.querySelectorAll<HTMLButtonElement>("button")].find((b) => text.test(b.textContent ?? ""));

describe("visibleSites", () => {
  it("lists 3 collapsed, all sent expanded, and counts lines beyond what was sent", () => {
    const sites = mk(20);
    expect(visibleSites(sites, 45, false)).toMatchObject({ hidden: 17, unlisted: 25 });
    expect(visibleSites(sites, 45, false).shown).toHaveLength(3);
    expect(visibleSites(sites, 45, true)).toMatchObject({ hidden: 0, unlisted: 25 });
    expect(visibleSites(mk(5), 5, true).shown).toHaveLength(5);
    expect(visibleSites(mk(5), null, false)).toMatchObject({ hidden: 2, unlisted: 0 });
  });
});

describe("SiteChips expand and collapse", () => {
  it("+N more lists every line, Show fewer folds back, and the opener keeps working", () => {
    const open = vi.fn();
    act(() => root.render(<SiteChips path="test/a.js" sites={mk(8)} count={8} onOpen={open} />));
    expect(chips()).toHaveLength(3);
    const more = button(/\+5 more/)!;
    expect(more.getAttribute("aria-expanded")).toBe("false");

    act(() => more.click());
    expect(chips()).toHaveLength(8);
    expect(button(/\+5 more/)).toBeUndefined();
    const fewer = button(/Show fewer/)!;
    expect(fewer.getAttribute("aria-expanded")).toBe("true");

    act(() => chips()[7].click()); // a line that was hidden is now reachable
    expect(open).toHaveBeenCalledWith(80);

    act(() => fewer.click());
    expect(chips()).toHaveLength(3);
    expect(button(/\+5 more/)).toBeDefined();
  });

  it("says how many lines the server did not send (edges keep at most 20)", () => {
    act(() => root.render(<SiteChips path="t.js" sites={mk(20)} count={45} onOpen={() => {}} />));
    expect(button(/\+42 more/)).toBeDefined();
    act(() => button(/\+42 more/)!.click());
    expect(chips()).toHaveLength(20);
    expect(host.textContent).toContain("25 more not listed");
  });

  it("has no toggle when every line already fits", () => {
    act(() => root.render(<SiteChips path="t.js" sites={mk(3)} count={3} onOpen={() => {}} />));
    expect(button(/more|fewer/)).toBeUndefined();
  });

  it("is reachable by keyboard: the toggle is a real button in the tab order", () => {
    act(() => root.render(<SiteChips path="t.js" sites={mk(6)} count={6} onOpen={() => {}} />));
    const more = button(/\+3 more/)!;
    expect(more.tagName).toBe("BUTTON");
    expect(more.getAttribute("type")).toBe("button");
    expect(more.tabIndex).toBe(0);
    more.focus();
    expect(document.activeElement).toBe(more);
  });

  it("keeps guesses dimmed: a site under 0.9 is marked, a sure one is not", () => {
    const sites = [
      { line: 1, confidence: 1 },
      { line: 2, confidence: 0.5 },
      { line: 3, confidence: 0.9 },
      { line: 4, confidence: null },
    ];
    act(() => root.render(<SiteChips path="t.js" sites={sites} count={4} onOpen={() => {}} />));
    act(() => button(/\+1 more/)!.click());
    expect(chips().map((c) => c.hasAttribute("data-guess"))).toEqual([false, true, false, false]);
    expect(chips()[1].title).toContain("best guess");
  });
});
