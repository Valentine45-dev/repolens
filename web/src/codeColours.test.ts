import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { requestColours, resetForTests, TIMEOUT_MS } from "./codeColours";
import { isTooLarge, langForPath, MAX_BYTES, MAX_LINES, utf8Length, type ColouredLine } from "./codeRoles";

/** A worker we answer by hand: records what was sent, and how many workers were made. */
class FakeWorker {
  static made: FakeWorker[] = [];
  sent: { id: number; code: string; lang: string }[] = [];
  terminated = false;
  listeners: Record<string, ((e: Event) => void)[]> = {};
  constructor() {
    FakeWorker.made.push(this);
  }
  postMessage(m: { id: number; code: string; lang: string }) {
    this.sent.push(m);
  }
  terminate() {
    this.terminated = true;
  }
  addEventListener(type: string, fn: (e: Event) => void) {
    (this.listeners[type] ??= []).push(fn);
  }
  reply(id: number, lines: ColouredLine[]) {
    for (const fn of this.listeners.message ?? []) fn({ data: { id, lines } } as unknown as Event);
  }
  crash() {
    for (const fn of this.listeners.error ?? []) fn({} as Event);
  }
}
const last = () => FakeWorker.made[FakeWorker.made.length - 1];
const LINES: ColouredLine[] = [[[1, "def"], [0, " f(): pass"]]];

beforeEach(() => {
  FakeWorker.made = [];
  resetForTests(() => new FakeWorker());
});
afterEach(() => {
  vi.useRealTimers();
});

describe("language and size", () => {
  it("colours Python and JS/TS by extension, nothing else", () => {
    expect(langForPath("src/app.py")).toBe("python");
    expect(langForPath("lib/router/index.js")).toBe("javascript");
    expect(langForPath("a/b.mjs")).toBe("javascript");
    expect(langForPath("view.jsx")).toBe("javascript");
    expect(langForPath("x/y.ts")).toBe("typescript");
    expect(langForPath("x/y.tsx")).toBe("tsx");
    expect(langForPath("package.json")).toBeNull();
    expect(langForPath("README.md")).toBeNull();
    expect(langForPath("Makefile")).toBeNull();
    expect(langForPath(".py")).toBeNull();
  });

  it("turns colours off above 3,000 lines or 256 KB", () => {
    expect(isTooLarge(MAX_LINES)).toBe(false);
    expect(isTooLarge(MAX_LINES + 1)).toBe(true);
    expect(isTooLarge(10, MAX_BYTES)).toBe(false);
    expect(isTooLarge(10, MAX_BYTES + 1)).toBe(true);
    expect(utf8Length("é")).toBe(2);
  });
});

describe("requestColours", () => {
  it("keeps one worker for many files and sends one request at a time", async () => {
    const a = requestColours("a = 1", "python");
    const b = requestColours("b = 2", "python");
    expect(FakeWorker.made).toHaveLength(1);
    expect(last().sent.map((m) => m.id)).toEqual([a.id]); // b waits
    last().reply(a.id, LINES);
    expect(await a.promise).toEqual(LINES);
    expect(last().sent.map((m) => m.id)).toEqual([a.id, b.id]);
    last().reply(b.id, LINES);
    expect(await b.promise).toEqual(LINES);
    expect(FakeWorker.made).toHaveLength(1);
  });

  it("drops a cancelled request: never sent if queued, answer discarded if sent", async () => {
    const a = requestColours("a = 1", "python");
    const b = requestColours("b = 2", "python");
    const c = requestColours("c = 3", "python");
    a.cancel(); // sent already
    b.cancel(); // still queued
    expect(await a.promise).toBeNull();
    expect(await b.promise).toBeNull();
    last().reply(a.id, LINES); // the late answer for a
    expect(last().sent.map((m) => m.id)).toEqual([a.id, c.id]); // b was never sent
    last().reply(a.id, [[[2, "late"]]]); // a stray second answer for a is ignored too
    last().reply(c.id, LINES);
    expect(await c.promise).toEqual(LINES);
  });

  it("answers again from memory for the same code (tab switch, file reopened)", async () => {
    const a = requestColours("same", "python");
    last().reply(a.id, LINES);
    await a.promise;
    const again = requestColours("same", "python");
    expect(again.id).not.toBe(a.id);
    expect(await again.promise).toEqual(LINES);
    expect(last().sent).toHaveLength(1);
    expect(requestColours("same", "javascript").id).toBeGreaterThan(again.id); // other language: asked
    expect(last().sent).toHaveLength(2);
  });

  it("stops a worker that takes too long and uses a new one for the next file", async () => {
    vi.useFakeTimers();
    const slow = requestColours("slow", "python");
    const next = requestColours("next", "python");
    const first = last();
    vi.advanceTimersByTime(TIMEOUT_MS);
    await expect(slow.promise).rejects.toThrow(/longer than/);
    expect(first.terminated).toBe(true);
    expect(FakeWorker.made).toHaveLength(2);
    expect(last().sent.map((m) => m.id)).toEqual([next.id]);
    first.reply(slow.id, LINES); // a dead worker's answer changes nothing
    last().reply(next.id, LINES);
    expect(await next.promise).toEqual(LINES);
  });

  it("replaces a worker that crashed", async () => {
    const a = requestColours("a", "python");
    last().crash();
    await expect(a.promise).rejects.toThrow(/stopped/);
    const b = requestColours("b", "python");
    expect(FakeWorker.made).toHaveLength(2);
    last().reply(b.id, LINES);
    expect(await b.promise).toEqual(LINES);
  });

  it("rejects (so the view stays plain) when workers are unavailable", async () => {
    resetForTests(() => {
      throw new Error("Web Workers are not available");
    });
    await expect(requestColours("a", "python").promise).rejects.toThrow(/not available/);
  });
});
