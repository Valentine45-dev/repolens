// @vitest-environment jsdom
// The code view's colours: plain text first, coloured runs after, in the same elements; never HTML
// from the file; stale answers dropped; plain text whenever anything goes wrong.
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetForTests } from "../codeColours";
import { colourLines } from "../codeColoursCore";
import { MAX_LINES, type CodeLang, type ColouredLine } from "../codeRoles";
import { CodeView } from "./NodePanel";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

type Msg = { id: number; code: string; lang: CodeLang };

/** A worker answered by the test (`reply`), or by real Shiki (`auto`). */
class TestWorker {
  static made: TestWorker[] = [];
  static auto = false;
  sent: Msg[] = [];
  onMessage: ((e: Event) => void)[] = [];
  onError: ((e: Event) => void)[] = [];
  constructor() {
    TestWorker.made.push(this);
  }
  postMessage(m: Msg) {
    this.sent.push(m);
    if (TestWorker.auto) void colourLines(m.code, m.lang).then((lines) => this.reply(m.id, lines));
  }
  terminate() {}
  addEventListener(type: string, fn: (e: Event) => void) {
    (type === "message" ? this.onMessage : this.onError).push(fn);
  }
  reply(id: number, lines: ColouredLine[]) {
    for (const fn of this.onMessage) fn({ data: { id, lines } } as unknown as Event);
  }
  crash() {
    for (const fn of this.onError) fn({} as Event);
  }
}
const worker = () => TestWorker.made[TestWorker.made.length - 1];

let host: HTMLDivElement;
let root: Root;
let warn: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  TestWorker.made = [];
  TestWorker.auto = false;
  resetForTests(() => new TestWorker());
  warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  window.matchMedia = (() => ({ matches: false })) as unknown as typeof window.matchMedia;
  HTMLElement.prototype.scrollTo = vi.fn() as typeof HTMLElement.prototype.scrollTo;
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  warn.mockRestore();
});

function show(path: string, content: string, key = path, highlight: { start: number; end: number } | null = null) {
  act(() =>
    root.render(
      <div className="panel-body">
        <CodeView key={key} path={path} content={content} highlight={highlight} reveal={null} hidden={false} />
      </div>,
    ),
  );
}
const code = () => host.querySelector<HTMLElement>(".code")!;
const pre = () => host.querySelector<HTMLElement>(".code-text")!;
async function settle() {
  for (let i = 0; i < 50 && TestWorker.auto && code()?.dataset.colours === "pending"; i++) {
    await act(() => new Promise((r) => setTimeout(r, 20)));
  }
  await act(async () => {});
}

const PY = 'def f(x):\n    return "a"  # done\n';

describe("code colours in the code view", () => {
  it("shows plain text at once, then colours in the same elements with the same text", async () => {
    show("src/a.py", PY);
    const [codeEl, preEl] = [code(), pre()];
    expect(codeEl.dataset.colours).toBe("pending");
    expect(preEl.querySelector("span")).toBeNull();
    expect(preEl.textContent).toBe('def f(x):\n    return "a"  # done');
    const lines: ColouredLine[] = [
      [[1, "def"], [0, " "], [6, "f"], [0, "(x):"]],
      [[0, "    "], [2, "return"], [0, " "], [8, '"a"'], [0, "  "], [12, "# done"]],
    ];
    await act(async () => worker().reply(worker().sent[0].id, lines));
    expect(code()).toBe(codeEl); // no remount: scroll position, focus and the band stay put
    expect(pre()).toBe(preEl);
    expect(codeEl.dataset.colours).toBe("on");
    expect(preEl.textContent).toBe('def f(x):\n    return "a"  # done');
    expect([...preEl.querySelectorAll("span")].map((s) => `${s.className}:${s.textContent}`)).toEqual([
      "tk-keyword:def",
      "tk-function:f",
      "tk-control:return",
      'tk-string:"a"',
      "tk-comment:# done",
    ]);
  });

  it("renders HTML-like repo text as text, never as elements (real Shiki)", async () => {
    TestWorker.auto = true;
    const js = [
      "// </pre><script>alert(1)</script>",
      'const s = "<img src=x onerror=alert(2)>";',
      "el.innerHTML = `<b onclick=\"x()\">${name}</b>`;",
      "export const V = () => <div dangerouslySetInnerHTML={{ __html: s }} />;",
    ].join("\n");
    show("web/view.jsx", js);
    await settle();
    expect(code().dataset.colours).toBe("on");
    expect(pre().textContent).toBe(js);
    expect(host.querySelector("script, img")).toBeNull();
    for (const tag of ["script", "img", "b", "div"]) expect(pre().querySelector(tag)).toBeNull();
    expect([...pre().querySelectorAll("*")].every((el) => el.tagName === "SPAN" && /^tk-[a-z]+$/.test(el.className))).toBe(true);
    expect([...pre().querySelectorAll("*")].every((el) => el.attributes.length === 1)).toBe(true); // class only
  });

  it("keeps redacted values exactly as stored (real Shiki)", async () => {
    TestWorker.auto = true;
    const py = 'API_KEY = "[REDACTED]"\npassword = [REDACTED]\n\nprint(API_KEY)\n';
    show("settings.py", py);
    await settle();
    expect(code().dataset.colours).toBe("on");
    expect(pre().textContent).toBe(py.slice(0, -1));
    expect(pre().textContent).toContain('"[REDACTED]"');
  });

  it("never applies an answer meant for another file, or for this file opened again", async () => {
    show("a.py", "a = 1\n", "file-a");
    const first = worker().sent[0].id;
    show("b.py", "b = 2\n", "file-b"); // another file before the colours came
    // the old answer, even one that would fit the new file's text, is dropped
    await act(async () => worker().reply(first, [[[1, "b = 2"]]]));
    expect(code().dataset.colours).toBe("pending");
    expect(pre().querySelector("span")).toBeNull();
    const second = worker().sent[1].id;
    expect(second).not.toBe(first);
    await act(async () => worker().reply(second, [[[0, "b = "], [11, "2"]]]));
    expect(pre().querySelector(".tk-number")?.textContent).toBe("2");

    // the same file opened again (a new code view) while its first request is still out
    show("c.py", "c = 3\n", "c-1");
    const old = worker().sent[2].id;
    show("c.py", "c = 3\n", "c-2");
    await act(async () => worker().reply(old, [[[1, "c = 3"]]]));
    expect(pre().querySelector("span")).toBeNull(); // the first view's answer is not this view's
    const mine = worker().sent[3].id;
    await act(async () => worker().reply(mine, [[[0, "c = "], [11, "3"]]]));
    expect(pre().querySelector(".tk-number")?.textContent).toBe("3");
    expect(TestWorker.made).toHaveLength(1); // one worker for every file
  });

  it("leaves large files plain and never asks the worker", () => {
    const big = Array.from({ length: MAX_LINES + 1 }, (_, i) => `x${i} = ${i}`).join("\n");
    show("big.py", big);
    expect(code().dataset.colours).toBe("off");
    expect(TestWorker.made).toHaveLength(0);
  });

  it("leaves other languages plain", () => {
    show("README.md", "# Title\n<b>x</b>\n");
    expect(code().dataset.colours).toBe("plain");
    expect(pre().textContent).toBe("# Title\n<b>x</b>");
    expect(TestWorker.made).toHaveLength(0);
  });

  it("stays plain (and says so in the console) when the worker fails or answers with other text", async () => {
    show("a.py", PY);
    await act(async () => worker().crash());
    expect(code().dataset.colours).toBe("plain");
    expect(pre().textContent).toBe('def f(x):\n    return "a"  # done');
    expect(warn).toHaveBeenCalled();

    show("b.py", "b = 2\n");
    await act(async () => worker().reply(worker().sent[0].id, [[[1, "something else"]]]));
    expect(code().dataset.colours).toBe("plain");
    expect(pre().textContent).toBe("b = 2");
  });

  it("does not scroll again or move the band when the colours arrive", async () => {
    const content = Array.from({ length: 200 }, (_, i) => `v${i} = ${i}`).join("\n");
    show("a.py", content, "a", { start: 150, end: 152 });
    const scrolls = (HTMLElement.prototype.scrollTo as ReturnType<typeof vi.fn>).mock.calls.length;
    const band = host.querySelector<HTMLElement>(".code-highlight")!;
    const style = band.getAttribute("style");
    const lines: ColouredLine[] = content.split("\n").map((l) => [[0, l.split(" = ")[0] + " = "], [11, l.split(" = ")[1]]]);
    await act(async () => worker().reply(worker().sent[0].id, lines));
    expect(code().dataset.colours).toBe("on");
    expect((HTMLElement.prototype.scrollTo as ReturnType<typeof vi.fn>).mock.calls.length).toBe(scrolls);
    expect(host.querySelector(".code-highlight")).toBe(band);
    expect(band.getAttribute("style")).toBe(style);
    expect(code().getAttribute("aria-label")).toBe("File contents, lines 150 to 152 highlighted");
  });
});
