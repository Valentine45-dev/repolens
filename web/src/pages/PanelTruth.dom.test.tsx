// @vitest-environment jsdom
// COR-03: a file or finding in the URL that the page cannot show. The shell must not put an empty
// File or Finding tab in front of Ask, and the page says why (real shell, Explorer and Findings
// page; mocked API).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  type Finding,
  type FindingsPage,
  type Graph,
  type GraphNode,
  type MapView as MapViewData,
  type SnapshotStatus,
} from "../api";
import { resetAskStore } from "../askStore";
import { AnalysisShell } from "../components/AnalysisShell";
import { mockReactFlowDom } from "../testFlow";
import { Explore } from "./Explore";
import { Findings } from "./Findings";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const STATUS: SnapshotStatus = {
  snapshot_id: 2, url: "https://github.com/example/app", commit_sha: "46fef968f3f44d1191363baf936aaa3335dc5c6d",
  job_id: 1, status: "done", stage: "done", percent: 100, error: null, progress: null, receipt: null,
  features: { ask: true, ask_reason: null, ai: true, search: "ready", search_progress: null, search_error: null, retry_search: false },
};
const file = (id: number, path: string): GraphNode => ({
  id, symbol_id: id * 10, path, language: "python", loc: 10, external_imports: 0, unresolved_imports: 0, findings: 0,
});
const CODE = [file(1, "app/a.py"), file(2, "app/b.py")];
const TEST = file(9, "tests/test_app.py");
const graph = (showTests: boolean): Graph => ({
  snapshot_id: 2, min_confidence: 0.9, exclude_tests: !showTests, hidden_files: showTests ? 0 : 1,
  nodes: showTests ? [...CODE, TEST] : CODE, edges: [],
});
const mapNode = (n: GraphNode) => ({
  id: `file:${n.path}`, kind: "file" as const, path: n.path, label: n.path, finding_count: 0, file_id: n.id,
  language: "python", loc: 10, in_cycle: false,
});
const map = (showTests: boolean): MapViewData => ({
  snapshot_id: 2, level: "file", root: "", breadcrumbs: [{ path: "", label: "" }], view_limit: 60,
  total_files: 3, hidden_files: 0, hidden_count: 0, cycle_scope: "", cycles_available: true, cycles: [],
  nodes: (showTests ? [...CODE, TEST] : CODE).map(mapNode), edges: [],
});
const FINDING: Finding = {
  id: 1, rule_id: "hardcoded-secret", severity: "high", message: "Possible hardcoded secret.", file_id: 1,
  path: "app/a.py", language: "python", line: 3, symbol: null, snippet: "x = [redacted]", in_test: false,
  in_docs: false, placeholder: false, template_value: false, category: "security", node_id: 10,
};
const PAGE: FindingsPage = {
  total: 1, limit: 50, offset: 0, items: [FINDING], notes: [],
  counts: { total: 1, by_severity: { high: 1, medium: 0, low: 0 }, by_rule: { "hardcoded-secret": 1 },
    by_category: { security: 1, quality: 0 }, placeholders: 0, documentation: 0, template_values: 0 },
};

vi.mock("../api", async (importOriginal) => {
  const real = await importOriginal<typeof import("../api")>();
  return {
    ...real,
    getStatus: vi.fn(async () => STATUS),
    getGraph: vi.fn(async (_s: number, o: { showTests: boolean }) => graph(o.showTests)),
    getMapView: vi.fn(async (_s: number, o: { showTests: boolean }) => map(o.showTests)),
    getFindings: vi.fn(async () => PAGE),
    getFindingReach: vi.fn(async () => ({ tier: "none", entry: null, path: [] })),
    getRules: vi.fn(async () => []),
    getNeighbours: vi.fn(async () => ({ symbol: {}, min_confidence: 0.9, files: 0, items: [] })),
    getFile: vi.fn(async (_s: number, id: number) => {
      if (id === 99999) throw new real.ApiError("File not found.", 404);
      const path = id === 5160 ? "lab/docker-compose.yml" : (graph(true).nodes.find((n) => n.id === id)?.path ?? "x");
      return { id, path, language: id === 5160 ? null : "python", loc: 1, content: "x = 1", symbols: [], findings: [],
        external_imports: [], unresolved_imports: [] };
    }),
  };
});

let host: HTMLDivElement;
let root: Root;
let restoreFlow: () => void;
beforeEach(() => {
  restoreFlow = mockReactFlowDom();
  window.matchMedia = ((query: string) => ({
    matches: query === "(min-width: 901px) and (max-width: 1599px)",
    addEventListener() {},
    removeEventListener() {},
  })) as unknown as typeof window.matchMedia;
  Element.prototype.scrollTo = () => {};
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  restoreFlow();
  resetAskStore();
  sessionStorage.clear();
});

async function open(url: string) {
  window.history.replaceState(null, "", url);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: (_n, e) => !(e instanceof ApiError && e.status < 500) && _n < 1 } },
  });
  act(() =>
    root.render(
      <QueryClientProvider client={client}>
        <BrowserRouter>
          <Routes>
            <Route path="/a/:id" element={<AnalysisShell />}>
              <Route path="explore" element={<Explore />} />
              <Route path="findings" element={<Findings />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>,
    ),
  );
  await settle();
}
async function settle() {
  for (let i = 0; i < 25; i++) await act(async () => new Promise((r) => setTimeout(r, 0)));
}
const tabs = () => [...host.querySelectorAll(".right-tabs [role=tab]")].map((t) => t.textContent);
const askShown = () => {
  const drawer = document.getElementById("ask-drawer");
  return drawer !== null && drawer.getAttribute("aria-hidden") !== "true";
};
const hint = () => host.querySelector(".canvas-hint[role=status]")?.textContent ?? null;
const search = () => new URLSearchParams(window.location.search);

describe("a file or finding in the URL that cannot be shown (COR-03)", () => {
  it("a hidden test file: no empty File tab, Ask stays in view, and one click shows it", async () => {
    await open("/a/2/explore?ask=1&node=9");
    expect(tabs()).toEqual([]);
    expect(askShown()).toBe(true);
    expect(host.querySelector("aside.panel")).toBeNull();
    expect(hint()).toBe("tests/test_app.py is a test or example file, hidden on the map. Show tests & examples");
    const button = [...host.querySelectorAll<HTMLButtonElement>(".canvas-hint button")].find(
      (b) => b.textContent === "Show tests & examples",
    )!;
    act(() => button.click());
    await settle();
    expect(search().get("tests")).toBe("1");
    expect(search().get("node")).toBe("9");
    expect(host.querySelector("aside.panel")?.textContent).toContain("test_app.py");
    expect(tabs()).toEqual(["File", "Ask"]);
  });

  it("an id this analysis does not have: says so and drops it, Ask stays", async () => {
    await open("/a/2/explore?ask=1&node=99999");
    expect(hint()).toBe("The link pointed to a file that isn't in this analysis.");
    expect(search().get("node")).toBeNull();
    expect(search().get("ask")).toBe("1");
    expect(tabs()).toEqual([]);
    expect(askShown()).toBe(true);
  });

  it("a file that is not code: says so and drops it", async () => {
    await open("/a/2/explore?node=5160&lines=12-12");
    expect(hint()).toBe("lab/docker-compose.yml isn't code, so it isn't on the map.");
    expect(search().get("node")).toBeNull();
    expect(search().get("lines")).toBeNull();
  });

  it("a file that can be shown still opens in the File tab in front (no change)", async () => {
    await open("/a/2/explore?ask=1&node=1");
    expect(host.querySelector("aside.panel")?.textContent).toContain("a.py");
    expect(tabs()).toEqual(["File", "Ask"]);
    expect(hint()).toBeNull();
  });

  it("a finding that is not in this list: a note, the link dropped, Ask stays in view", async () => {
    await open("/a/2/findings?ask=1&finding=777");
    expect(host.querySelector(".note[role=status]")?.textContent).toBe(
      "The finding in this link isn't in this list (another page, or hidden by a filter).",
    );
    expect(search().get("finding")).toBeNull();
    expect(tabs()).toEqual([]);
    expect(askShown()).toBe(true);
    expect(host.querySelector("aside.panel")).toBeNull();
  });
});
