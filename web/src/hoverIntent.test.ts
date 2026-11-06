import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createHoverIntent } from "./hoverIntent";

describe("hover intent", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("reports a hover only after the delay", () => {
    const seen: (string | null)[] = [];
    const h = createHoverIntent((id) => seen.push(id), 100, 60);
    h.enter("a");
    vi.advanceTimersByTime(99);
    expect(seen).toEqual([]);
    vi.advanceTimersByTime(1);
    expect(seen).toEqual(["a"]);
  });

  it("a mouse sweeping across nodes changes nothing", () => {
    const seen: (string | null)[] = [];
    const h = createHoverIntent((id) => seen.push(id), 100, 60);
    for (const id of ["a", "b", "c", "d"]) {
      h.enter(id);
      vi.advanceTimersByTime(30); // gone before the delay
      h.leave();
      vi.advanceTimersByTime(10);
    }
    vi.advanceTimersByTime(500);
    expect(seen).toEqual([]);
  });

  it("moving straight from one node to the next never passes through nothing", () => {
    const seen: (string | null)[] = [];
    const h = createHoverIntent((id) => seen.push(id), 100, 60);
    h.enter("a");
    vi.advanceTimersByTime(150);
    h.leave();
    vi.advanceTimersByTime(5);
    h.enter("b");
    vi.advanceTimersByTime(500);
    expect(seen).toEqual(["a", "b"]);
  });

  it("clears after the leave delay, and cancel stops a pending change", () => {
    const seen: (string | null)[] = [];
    const h = createHoverIntent((id) => seen.push(id), 100, 60);
    h.enter("a");
    vi.advanceTimersByTime(100);
    h.leave();
    vi.advanceTimersByTime(60);
    expect(seen).toEqual(["a", null]);
    h.enter("b");
    h.cancel();
    vi.advanceTimersByTime(500);
    expect(seen).toEqual(["a", null]);
  });
});
