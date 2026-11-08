// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MAP_HINT_KEY, MapHint } from "./MapHint";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  localStorage.clear();
  host = document.createElement("div");
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  vi.restoreAllMocks();
});
const mount = () => act(() => root.render(<MapHint />));
const gotIt = () =>
  act(() => [...host.querySelectorAll("button")].find((b) => b.textContent === "Got it")!.click());

describe("first-visit map help", () => {
  it("shows once, and stays closed in this browser after it is closed", () => {
    mount();
    expect(host.textContent).toContain("How to read this map");
    gotIt();
    expect(host.textContent).toBe("");
    expect(localStorage.getItem(MAP_HINT_KEY)).toBe("1");
    act(() => root.unmount());
    root = createRoot(host);
    mount();
    expect(host.textContent).toBe("");
  });

  it("works without storage: shown, and closable for this page", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    mount();
    expect(host.textContent).toContain("How to read this map");
    gotIt();
    expect(host.textContent).toBe("");
  });
});
