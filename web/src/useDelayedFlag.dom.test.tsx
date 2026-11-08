// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useDelayedFlag } from "./useDelayedFlag";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root;
let shown = false;
function Probe({ on }: { on: boolean }) {
  shown = useDelayedFlag(on, 200, 400);
  return null;
}
const render = (on: boolean) => act(() => root.render(<Probe on={on} />));
const wait = (ms: number) => act(() => vi.advanceTimersByTime(ms));

beforeEach(() => {
  vi.useFakeTimers();
  root = createRoot(document.createElement("div"));
});
afterEach(() => {
  act(() => root.unmount());
  vi.useRealTimers();
});

describe("useDelayedFlag", () => {
  it("shows nothing for a load faster than the delay", () => {
    render(true);
    wait(150);
    render(false);
    wait(1000);
    expect(shown).toBe(false);
  });

  it("turns on after the delay and stays at least the minimum time", () => {
    render(true);
    wait(199);
    expect(shown).toBe(false);
    wait(1);
    expect(shown).toBe(true);
    wait(50);
    render(false); // the data arrived 50 ms after the loader appeared
    wait(300);
    expect(shown).toBe(true);
    wait(50);
    expect(shown).toBe(false);
  });

  it("goes off at once when it has already been shown long enough", () => {
    render(true);
    wait(200 + 600);
    render(false);
    wait(0);
    expect(shown).toBe(false);
  });
});
