// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { isGoToFileShortcut, isTypingTarget, shortcutLabel } from "./goToFileShortcut";

function press(key: string, init: KeyboardEventInit = {}, target: HTMLElement = document.body): KeyboardEvent {
  const e = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...init });
  Object.defineProperty(e, "target", { value: target });
  return e;
}

const el = <K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Record<string, string> = {}) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
};

describe("Go to file shortcut", () => {
  it("is Ctrl+K, Cmd+K or /", () => {
    expect(isGoToFileShortcut(press("k", { ctrlKey: true }))).toBe(true);
    expect(isGoToFileShortcut(press("K", { ctrlKey: true }))).toBe(true); // caps lock
    expect(isGoToFileShortcut(press("k", { metaKey: true }))).toBe(true);
    expect(isGoToFileShortcut(press("/"))).toBe(true);
  });

  it("is not K alone, other modifiers, or a repeat", () => {
    expect(isGoToFileShortcut(press("k"))).toBe(false);
    expect(isGoToFileShortcut(press("k", { ctrlKey: true, shiftKey: true }))).toBe(false);
    expect(isGoToFileShortcut(press("k", { ctrlKey: true, altKey: true }))).toBe(false);
    expect(isGoToFileShortcut(press("/", { ctrlKey: true }))).toBe(false);
    expect(isGoToFileShortcut(press("/", { repeat: true }))).toBe(false);
  });

  it("never fires while typing in a field", () => {
    for (const target of [el("input"), el("input", { type: "search" }), el("textarea"), el("select")]) {
      expect(isTypingTarget(target)).toBe(true);
      expect(isGoToFileShortcut(press("/", {}, target))).toBe(false);
      expect(isGoToFileShortcut(press("k", { ctrlKey: true }, target))).toBe(false);
    }
    const editable = el("div", { contenteditable: "true" });
    Object.defineProperty(editable, "isContentEditable", { value: true });
    expect(isGoToFileShortcut(press("/", {}, editable))).toBe(false);
  });

  it("fires from a checkbox or a button (nothing is being typed there)", () => {
    expect(isGoToFileShortcut(press("/", {}, el("input", { type: "checkbox" })))).toBe(true);
    expect(isGoToFileShortcut(press("k", { ctrlKey: true }, el("button")))).toBe(true);
  });

  it("does not fire during IME composition or when already handled", () => {
    expect(isGoToFileShortcut(press("/", { isComposing: true }))).toBe(false);
    const handled = press("/");
    handled.preventDefault();
    expect(isGoToFileShortcut(handled)).toBe(false);
  });

  it("is written as this computer writes it", () => {
    expect(shortcutLabel("Win32")).toBe("Ctrl K");
    expect(shortcutLabel("MacIntel")).toBe("⌘ K");
  });
});
