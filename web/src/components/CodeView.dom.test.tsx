// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { scrollToRange } from "../scroll";
import { CodeView } from "./NodePanel";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const CONTENT = Array.from({ length: 400 }, (_, i) => `line ${i + 1}`).join("\n");

let host: HTMLDivElement;
let root: Root;
let calls: { top: number; behavior: ScrollBehavior | undefined; hiddenAtCall: string | undefined }[];
let reduced = false;
beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  calls = [];
  reduced = false;
  window.matchMedia = ((query: string) => ({
    matches: query === "(prefers-reduced-motion: reduce)" && reduced,
    addEventListener() {},
    removeEventListener() {},
  })) as unknown as typeof window.matchMedia;
  // jsdom has no layout and no Element.scrollTo: record each call and whether the panel was shown.
  HTMLElement.prototype.scrollTo = function (this: HTMLElement, opts?: ScrollToOptions | number) {
    const o = opts as ScrollToOptions;
    calls.push({ top: o.top ?? 0, behavior: o.behavior, hiddenAtCall: this.dataset.hidden });
  } as typeof HTMLElement.prototype.scrollTo;
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

function show(props: { start: number; end: number; hidden: boolean; reveal?: string | null }) {
  act(() =>
    root.render(
      <div className="panel-body" data-hidden={String(props.hidden)}>
        <CodeView
          content={CONTENT}
          highlight={{ start: props.start, end: props.end }}
          reveal={props.reveal ?? null}
          hidden={props.hidden}
        />
      </div>,
    ),
  );
}

describe("scrolling to cited lines", () => {
  it("waits while the panel is behind the Ask tab, then scrolls once it is shown", () => {
    show({ start: 380, end: 390, hidden: true });
    expect(host.querySelector(".code")?.getAttribute("aria-label")).toBe(
      "File contents, lines 380 to 390 highlighted",
    );
    expect(calls).toHaveLength(0); // a hidden panel has no layout: scrolling now would do nothing
    show({ start: 380, end: 390, hidden: false }); // the File tab comes to the front (or is opened by hand)
    expect(calls).toHaveLength(1);
    expect(calls[0].hiddenAtCall).toBe("false");
    expect(calls[0].behavior).toBe("auto"); // just shown: land on the lines, no glide
  });

  it("scrolls once per request: not again on an unrelated re-render, again for the same lines asked again", () => {
    show({ start: 53, end: 56, hidden: false, reveal: "k1" });
    show({ start: 53, end: 56, hidden: false, reveal: "k1" });
    expect(calls).toHaveLength(1);
    show({ start: 53, end: 56, hidden: true, reveal: "k1" }); // the user went to Ask and back
    show({ start: 53, end: 56, hidden: false, reveal: "k1" });
    expect(calls).toHaveLength(1); // their own scroll position is kept
    show({ start: 53, end: 56, hidden: false, reveal: "k2" }); // the same chip clicked again
    expect(calls).toHaveLength(2);
  });

  it("glides between lines of code already on screen, but never under reduced motion", () => {
    show({ start: 53, end: 56, hidden: false });
    show({ start: 212, end: 212, hidden: false });
    expect(calls.map((c) => c.behavior)).toEqual(["auto", "smooth"]);
    reduced = true;
    show({ start: 300, end: 305, hidden: false });
    expect(calls[2].behavior).toBe("auto");
  });
});

describe("scrollToRange", () => {
  // A 400px code area scrolled to the top; the range's top `at` px into the content, `height` tall.
  function box(at: number, height: number) {
    const container = document.createElement("div");
    const el = document.createElement("div");
    Object.defineProperty(container, "clientHeight", { value: 400 });
    container.getBoundingClientRect = () => ({ top: 100 }) as DOMRect;
    el.getBoundingClientRect = () => ({ top: 100 + at, height }) as DOMRect;
    const scrollTo = vi.fn();
    container.scrollTo = scrollTo;
    return { container, el, scrollTo };
  }

  it("centres a range that fits, with context to spare", () => {
    const { container, el, scrollTo } = box(2000, 40);
    scrollToRange(container, el, 57);
    expect(scrollTo).toHaveBeenCalledWith({ top: 2000 - 180, behavior: "auto" });
  });

  it("puts a tall range's first line a few lines below the top, never flush", () => {
    const { container, el, scrollTo } = box(2000, 2400);
    scrollToRange(container, el, 57, true);
    expect(scrollTo).toHaveBeenCalledWith({ top: 2000 - 57, behavior: "smooth" });
  });

  it("never asks for a negative position near the top of the file", () => {
    const { container, el, scrollTo } = box(20, 19);
    scrollToRange(container, el, 57);
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "auto" });
  });
});
