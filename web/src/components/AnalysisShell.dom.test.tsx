// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes, useOutletContext, useSearchParams } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Answer, SnapshotStatus } from "../api";
import { parseLines, useRevealToken } from "../links";
import { AnalysisShell, type AnalysisContext } from "./AnalysisShell";
import { CodeView } from "./NodePanel";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const STATUS: SnapshotStatus = {
  snapshot_id: 2, url: "https://github.com/example/app", commit_sha: "46fef968f3f44d1191363baf936aaa3335dc5c6d",
  job_id: 1, status: "done", stage: "done", percent: 100, error: null, progress: null, receipt: null,
  features: { ask: true, ask_reason: null, ai: true, search: "ready", search_progress: null, search_error: null, retry_search: false },
};

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  getStatus: vi.fn(async () => STATUS),
  getFindings: vi.fn(async () => ({ total: 0, limit: 1, offset: 0, items: [], notes: [], counts: { total: 0 } })),
  getGraph: vi.fn(async () => ({ nodes: [], edges: [] })),
}));

const cite = (start: number, end: number) => ({
  path: "static/js/lab_manager.js", start_line: start, end_line: end, file_id: 1794, symbol_id: 9108, in_test: false,
});
const ANSWER: Answer = {
  kind: "ai", status: "answered", answer: "Test answer.", dropped: 0, results: [], prompt_version: "test",
  retrieval: { sent: 1, used_test_code: false, from_graph: 0 },
  citations: [cite(53, 56), cite(380, 390)],
};
const CONTENT = Array.from({ length: 600 }, (_, i) => `line ${i + 1}`).join("\n");

// Stands in for the Explorer: the real code view inside a file panel, hidden as the shell says.
function FilePage() {
  const { panelHidden } = useOutletContext<AnalysisContext>();
  const [params] = useSearchParams();
  const reveal = useRevealToken();
  if (!params.get("node")) return null;
  return (
    <aside className="panel">
      <div className="panel-body">
        <CodeView content={CONTENT} highlight={parseLines(params.get("lines"))} reveal={reveal} hidden={panelHidden} />
      </div>
    </aside>
  );
}

let host: HTMLDivElement;
let root: Root;
let midWidth = true;
let scrolls: { top: number; rightTab: string | undefined }[];
beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  scrolls = [];
  sessionStorage.setItem("repolens.ask.2", JSON.stringify([{ id: "t1", question: "Where is the lab status?", answer: ANSWER }]));
  window.matchMedia = ((query: string) => ({
    matches: query === "(min-width: 901px) and (max-width: 1599px)" ? midWidth : false,
    addEventListener() {},
    removeEventListener() {},
  })) as unknown as typeof window.matchMedia;
  HTMLElement.prototype.scrollTo = function (this: HTMLElement, opts?: ScrollToOptions | number) {
    if (!this.classList.contains("panel-body")) return; // the Ask list's own scrolling is not under test
    scrolls.push({
      top: (opts as ScrollToOptions).top ?? 0,
      rightTab: document.querySelector<HTMLElement>(".analysis-body")?.dataset.rightTab,
    });
  } as typeof HTMLElement.prototype.scrollTo;
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  sessionStorage.clear();
});

async function open(url: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () =>
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[url]}>
          <Routes>
            <Route path="/a/:id" element={<AnalysisShell />}>
              <Route path="explore" element={<FilePage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  );
  // The status query answers on a later tick; Ask (and its chips) draws after it.
  for (let i = 0; i < 50 && !host.querySelector("#ask-drawer a.citation"); i++) {
    await act(async () => new Promise((r) => setTimeout(r, 10)));
  }
}
const $ = <T extends Element = HTMLElement>(sel: string) => host.querySelector<T>(sel);
const tabs = () => [...host.querySelectorAll(".right-tabs [role=tab]")].map((t) => `${t.textContent}${t.getAttribute("aria-selected") === "true" ? "*" : ""}`);
const chip = (text: string) => [...host.querySelectorAll<HTMLAnchorElement>("a.citation")].find((a) => a.textContent?.includes(text))!;
const clickAsync = (el: HTMLElement) => act(async () => el.click());
function typeDraft(text: string) {
  const area = $<HTMLTextAreaElement>("#ask-drawer textarea")!;
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
  act(() => {
    setter.call(area, text);
    area.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

describe("a citation chip below 1600px (File | Ask tabs)", () => {
  it("brings the File tab to the front with the cited lines highlighted and scrolled to once shown", async () => {
    await open("/a/2/explore?ask=1");
    expect(tabs()).toEqual([]); // no file yet: Ask has the column to itself
    await clickAsync(chip(":53-56"));
    expect(tabs()).toEqual(["File*", "Ask"]);
    expect($(".code")?.getAttribute("aria-label")).toBe("File contents, lines 53 to 56 highlighted");
    expect(scrolls).toEqual([{ top: expect.any(Number), rightTab: "panel" }]); // after the panel is shown
  });

  it("also when that file is already open behind Ask, and for the same chip clicked again", async () => {
    await open("/a/2/explore?ask=1&node=1794&lines=53-56");
    expect(tabs()).toEqual(["File*", "Ask"]); // a link that opens both shows the file first
    await clickAsync([...host.querySelectorAll<HTMLElement>(".right-tabs [role=tab]")][1]);
    expect(tabs()).toEqual(["File", "Ask*"]);
    const before = scrolls.length;
    await clickAsync(chip(":380-390")); // same file, other lines
    expect(tabs()).toEqual(["File*", "Ask"]);
    expect($(".code")?.getAttribute("aria-label")).toBe("File contents, lines 380 to 390 highlighted");
    expect(scrolls.slice(before)).toEqual([{ top: expect.any(Number), rightTab: "panel" }]);
    await clickAsync([...host.querySelectorAll<HTMLElement>(".right-tabs [role=tab]")][1]);
    await clickAsync(chip(":380-390")); // the address does not change
    expect(tabs()).toEqual(["File*", "Ask"]);
    expect(scrolls.slice(before)).toHaveLength(2);
    expect(scrolls.every((s) => s.rightTab === "panel")).toBe(true); // never while hidden
  });

  it("keeps the conversation, the draft and Ask's scroll position", async () => {
    await open("/a/2/explore?ask=1");
    typeDraft("half-typed question");
    const list = $("#ask-drawer .drawer-body")!;
    list.scrollTop = 120;
    await clickAsync(chip(":53-56"));
    expect($("#ask-drawer")?.hasAttribute("inert")).toBe(true); // behind the file, still mounted
    await clickAsync([...host.querySelectorAll<HTMLElement>(".right-tabs [role=tab]")][1]);
    expect(tabs()).toEqual(["File", "Ask*"]);
    expect($<HTMLTextAreaElement>("#ask-drawer textarea")!.value).toBe("half-typed question");
    expect($("#ask-drawer .drawer-body")).toBe(list); // the same element, not a remount
    expect(list.scrollTop).toBe(120);
    expect(host.querySelectorAll("#ask-drawer .turn")).toHaveLength(1);
  });
});

describe("at 1600px and above (three columns)", () => {
  it("has no tabs, keeps Ask beside the file, and still scrolls to the cited lines", async () => {
    midWidth = false;
    try {
      await open("/a/2/explore?ask=1");
      await clickAsync(chip(":53-56"));
      expect(host.querySelector(".right-tabs")).toBeNull();
      expect($(".analysis-body")?.hasAttribute("data-tabbed")).toBe(false);
      expect($("#ask-drawer")?.hasAttribute("inert")).toBe(false);
      expect($(".code")?.getAttribute("aria-label")).toBe("File contents, lines 53 to 56 highlighted");
      expect(scrolls).toEqual([{ top: expect.any(Number), rightTab: undefined }]);
    } finally {
      midWidth = true;
    }
  });
});
