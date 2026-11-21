// @vitest-environment jsdom
// The Findings page as a visitor gets it (real shell and page, mocked API): the numbers in its
// menus, a page past the end, and where focus goes when a finding is closed.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Finding, FindingsFilter, FindingsPage, SnapshotStatus } from "../api";
import { resetAskStore } from "../askStore";
import { AnalysisShell } from "../components/AnalysisShell";
import { Findings } from "./Findings";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const STATUS: SnapshotStatus = {
  snapshot_id: 2, url: "https://github.com/example/app", commit_sha: "46fef968f3f44d1191363baf936aaa3335dc5c6d",
  job_id: 1, status: "done", stage: "done", percent: 100, error: null, progress: null, receipt: null,
  features: { ask: true, ask_reason: null, ai: true, search: "ready", search_progress: null, search_error: null, retry_search: false },
};
const finding = (id: number): Finding => ({
  id, rule_id: "hardcoded-secret", severity: "high", message: `Finding ${id}`, file_id: 1, path: `app/f${id}.py`,
  language: "python", line: 3, symbol: null, snippet: "x = [redacted]", in_test: false, in_docs: false,
  placeholder: false, template_value: false, category: "security", node_id: 10,
});
// PyGoat's whole-snapshot counts: Security 70 and Bug / Quality 11; Medium 2 and Low 12 overall.
const COUNTS: FindingsPage["counts"] = {
  total: 81, by_severity: { high: 67, medium: 2, low: 12 }, by_rule: { "hardcoded-secret": 50, "ruff-F821": 2 },
  by_category: { security: 70, quality: 11 }, placeholders: 0, documentation: 0, template_values: 0,
};
type Respond = (filter: FindingsFilter) => Promise<FindingsPage>;
let respond: Respond;
const page = (items: Finding[], total: number, extra: Partial<FindingsPage> = {}): FindingsPage => ({
  total, limit: 50, offset: 0, items, notes: [], counts: COUNTS, ...extra,
});

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  getStatus: vi.fn(async () => STATUS),
  getFindings: vi.fn(async (_s: number, filter: FindingsFilter) => respond(filter)),
  getFindingReach: vi.fn(async () => ({ tier: "none", entry: null, path: [] })),
  getRules: vi.fn(async () => [
    { id: "hardcoded-secret", title: "Hardcoded secret", category: "security" },
    { id: "ruff-F821", title: "Undefined name", category: "quality" },
  ]),
}));

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  window.matchMedia = ((query: string) => ({
    matches: false, media: query, addEventListener() {}, removeEventListener() {},
  })) as unknown as typeof window.matchMedia;
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  respond = async () => page([finding(1), finding(2)], 2);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  resetAskStore();
});

async function open(url: string) {
  window.history.replaceState(null, "", url);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  act(() =>
    root.render(
      <QueryClientProvider client={client}>
        <BrowserRouter>
          <Routes>
            <Route path="/a/:id" element={<AnalysisShell />}>
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
  for (let i = 0; i < 20; i++) await act(async () => new Promise((r) => setTimeout(r, 0)));
}
const select = (label: string) =>
  [...host.querySelectorAll<HTMLSelectElement>("select")].find(
    (s) => host.querySelector(`label[for="${s.id}"]`)?.textContent === label,
  )!;
const options = (label: string) => [...select(label).options].map((o) => o.textContent);

describe("severity menu while the counts are not known (COR-07)", () => {
  it("shows no number, never (0), until the counts arrive", async () => {
    respond = () => new Promise(() => {}); // never answers
    await open("/a/2/findings");
    expect(options("Severity")).toEqual(["All", "High", "Medium", "Low"]);
  });
});

describe("a page past the end of the list (COR-06)", () => {
  it("says so, never 'No Security findings', shows no pager, and offers the last page", async () => {
    respond = async (f) => page((f.offset ?? 0) >= 70 ? [] : [finding((f.offset ?? 0) + 1)], 70, { offset: f.offset ?? 0 });
    await open("/a/2/findings?page=99");
    const message = host.querySelector(".empty-state")?.textContent ?? "";
    expect(message).toContain("Page 100 is past the end of this list (70 findings, 2 pages).");
    expect(message).not.toContain("No Security findings");
    expect(host.querySelector(".pager")).toBeNull();
    const last = [...host.querySelectorAll<HTMLButtonElement>(".empty-state button")].find((b) => b.textContent === "Go to the last page")!;
    act(() => last.click());
    await settle();
    expect(new URLSearchParams(window.location.search).get("page")).toBe("1");
    expect(host.querySelector(".finding-row")?.textContent).toContain("Finding 51");
    expect(host.querySelector(".pager")?.textContent).toContain("51–70 of 70");
  });

  it("an empty category still says it has none (no change)", async () => {
    respond = async () => page([], 0);
    await open("/a/2/findings");
    expect(host.querySelector(".empty-state")?.textContent).toContain("No Security findings.");
  });
});

describe("closing a finding gives focus back to its row (A11Y-01)", () => {
  const rowButton = (id: number) => host.querySelector<HTMLButtonElement>(`[data-finding-id="${id}"] .row-button`)!;
  it("with the close button", async () => {
    await open("/a/2/findings");
    act(() => rowButton(2).click());
    await settle();
    expect(document.activeElement?.classList.contains("panel-title")).toBe(true);
    const close = [...host.querySelectorAll<HTMLButtonElement>("aside.panel button")].find((b) =>
      b.getAttribute("aria-label")?.startsWith("Close"),
    )!;
    act(() => close.click());
    await settle();
    expect(host.querySelector("aside.panel")).toBeNull();
    expect(document.activeElement).toBe(rowButton(2));
  });

  it("with Esc, after moving from one finding to another: the row of the one that was open", async () => {
    await open("/a/2/findings");
    act(() => rowButton(1).click());
    await settle();
    act(() => rowButton(2).click());
    await settle();
    act(() => {
      document.activeElement!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    });
    await settle();
    expect(host.querySelector("aside.panel")).toBeNull();
    expect(document.activeElement).toBe(rowButton(2));
  });
});

describe("menu numbers are what each choice lists (COR-04)", () => {
  // PyGoat: Security has High 67, Medium 0, Low 3 (Low 1 with test code hidden); the whole
  // snapshot has Medium 2 and Low 12 because of the Bug / Quality findings.
  beforeEach(() => {
    respond = async (f) =>
      page([finding(1)], 70, {
        facets: f.in_test === false
          ? { severity: { high: 67, medium: 0, low: 1 }, rule: { "hardcoded-secret": 48 } }
          : f.category === "security"
            ? { severity: { high: 67, medium: 0, low: 3 }, rule: { "hardcoded-secret": 50 } }
            : { severity: { high: 67, medium: 2, low: 12 }, rule: { "hardcoded-secret": 50, "ruff-F821": 2 } },
      });
  });

  it("the Security tab counts Security findings only, not the snapshot's", async () => {
    await open("/a/2/findings");
    expect(options("Severity")).toEqual(["All", "High (67)", "Medium (0)", "Low (3)"]);
    expect(options("Rule")).toEqual(["All", "Hardcoded secret (50)"]);
  });

  it("follows the other filters too: hiding test code changes Low (3) to Low (1)", async () => {
    await open("/a/2/findings?tests=hide");
    expect(options("Severity")).toEqual(["All", "High (67)", "Medium (0)", "Low (1)"]);
    expect(options("Rule")).toEqual(["All", "Hardcoded secret (48)"]);
  });

  it("All categories: the snapshot's numbers, and every rule", async () => {
    await open("/a/2/findings?category=all");
    expect(options("Severity")).toEqual(["All", "High (67)", "Medium (2)", "Low (12)"]);
    expect(options("Rule")).toEqual(["All", "Hardcoded secret (50)", "Undefined name (2)"]);
  });
});
