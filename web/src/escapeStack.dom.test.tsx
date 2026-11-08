// @vitest-environment jsdom
import { act, useRef } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useEscapeToClose } from "./escapeStack";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function Panel({ name, onClose, behind = false }: { name: string; onClose: () => void; behind?: boolean }) {
  const ref = useRef<HTMLElement>(null);
  useEscapeToClose(ref, onClose);
  return (
    <aside ref={ref} data-name={name} style={behind ? { visibility: "hidden" } : undefined}>
      <button type="button">{name}</button>
    </aside>
  );
}

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

const esc = () => act(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", cancelable: true })));

describe("Esc closes the top-most side panel, one per press", () => {
  it("closes the most recently opened when focus is elsewhere", () => {
    const file = vi.fn();
    const ask = vi.fn();
    act(() => root.render(<><Panel name="file" onClose={file} /><Panel name="ask" onClose={ask} /></>));
    esc();
    expect(ask).toHaveBeenCalledOnce();
    expect(file).not.toHaveBeenCalled();
  });

  it("closes the panel that holds focus, even if it is not the newest", () => {
    const file = vi.fn();
    const ask = vi.fn();
    act(() => root.render(<><Panel name="file" onClose={file} /><Panel name="ask" onClose={ask} /></>));
    act(() => host.querySelector<HTMLButtonElement>('[data-name="file"] button')!.focus());
    esc();
    expect(file).toHaveBeenCalledOnce();
    expect(ask).not.toHaveBeenCalled();
  });

  it("skips a panel that is behind a tab", () => {
    const file = vi.fn();
    const ask = vi.fn();
    act(() => root.render(<><Panel name="file" onClose={file} /><Panel name="ask" onClose={ask} behind /></>));
    esc();
    expect(file).toHaveBeenCalledOnce();
    expect(ask).not.toHaveBeenCalled();
  });

  it("does nothing once every panel is closed", () => {
    act(() => root.render(<></>));
    expect(() => esc()).not.toThrow();
  });
});
