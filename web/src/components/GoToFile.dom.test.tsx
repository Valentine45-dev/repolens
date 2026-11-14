// @vitest-environment jsdom
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes, useLocation, useOutletContext, useSearchParams } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { type Graph, type GraphNode, getGraph, type SnapshotStatus } from "../api";
import { resetForTests } from "../codeColours";
import { parseLines, useRevealToken, useSetParams } from "../links";
import { AnalysisShell, type AnalysisContext } from "./AnalysisShell";
import { resultHref, SCOPE_NOTE, TESTS_NOTE } from "./GoToFile";
import { NodePanel } from "./NodePanel";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const STATUS: SnapshotStatus = {
  snapshot_id: 7, url: "https://github.com/psf/black", commit_sha: "b4f1fca0000000000000000000000000000000000",
  job_id: 1, status: "done", stage: "done", percent: 100, error: null, progress: null, receipt: null,
  features: { ask: true, ask_reason: null, ai: true, search: "ready", search_progress: null, search_error: null, retry_search: false },
};

const node = (id: number, path: string): GraphNode => ({
  id, symbol_id: id * 10, path, language: "python", loc: 3, external_imports: 0, unresolved_imports: 0, findings: 0,
});
// A slice of psf/black: with tests off the server leaves tests/ out (black: 55 files, 371 hidden).
const ALL = [
  node(1, "src/black/trans.py"),
  node(2, "src/black/linegen.py"),
  node(3, "src/black/__init__.py"),
  node(5, "tests/test_black.py"),
  node(6, "tests/test_blackd.py"),
  node(7, "tests/test_trans.py"),
];
const PLAIN = ALL.filter((n) => !n.path.startsWith("tests/"));
let lists: { all: GraphNode[]; plain: GraphNode[] } = { all: ALL, plain: PLAIN };
// Lets a test hold back the list without tests (as if it were still loading).
let holdPlain: Promise<void> | null = null;

const graphOf = (nodes: GraphNode[], showTests: boolean): Graph => ({
  snapshot_id: 7, min_confidence: 0.9, exclude_tests: !showTests, hidden_files: 0, nodes, edges: [],
});

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  getStatus: vi.fn(async () => STATUS),
  getFindings: vi.fn(async () => ({ total: 0, limit: 1, offset: 0, items: [], notes: [], counts: { total: 0 } })),
  getGraph: vi.fn(async (_id: number, opts: { showTests: boolean }) => {
    if (!opts.showTests && holdPlain) await holdPlain;
    return graphOf(opts.showTests ? lists.all : lists.plain, opts.showTests);
  }),
  getFile: vi.fn(async (_s: number, fileId: number) => {
    const n = lists.all.find((f) => f.id === fileId)!;
    return {
      id: n.id, path: n.path, language: "python", loc: 3, content: `# ${n.path}\nx = 1\ny = 2`,
      symbols: [], findings: [], external_imports: [], unresolved_imports: [],
    };
  }),
  getNeighbours: vi.fn(async () => ({ files: 0, items: [] })),
}));

// Stands in for the Explorer: its own file list (the same query) and the real file panel.
function ExplorePage() {
  const { snapshotId, panelHidden } = useOutletContext<AnalysisContext>();
  const [params] = useSearchParams();
  const setParams = useSetParams();
  const reveal = useRevealToken();
  const showTests = params.get("tests") === "1";
  const showGuesses = params.get("guesses") === "1";
  const graph = useQuery({
    queryKey: ["graph", snapshotId, showTests, showGuesses],
    queryFn: ({ signal }) => getGraph(snapshotId, { showTests, showGuesses }, signal),
    staleTime: Infinity,
  });
  const selected = graph.data?.nodes.find((n) => n.id === Number(params.get("node")));
  return (
    <>
      <input aria-label="A filter field" className="probe-field" />
      <input type="checkbox" aria-label="A checkbox" className="probe-check" />
      {selected ? (
        <NodePanel
          snapshotId={snapshotId}
          node={selected}
          minConfidence={0.9}
          highlight={parseLines(params.get("lines"))}
          reveal={reveal}
          hidden={panelHidden}
          isInGraph={() => true}
          onSelectFile={() => {}}
          onShowLines={() => {}}
          onAsk={() => {}}
          onClose={() => setParams({ node: null, lines: null })}
        />
      ) : null}
    </>
  );
}

let here = "";
function WhereAmI() {
  const location = useLocation();
  here = location.pathname + location.search;
  return null;
}

let host: HTMLDivElement;
let root: Root;
let midWidth = false;
beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  lists = { all: ALL, plain: PLAIN };
  holdPlain = null;
  midWidth = false;
  vi.mocked(getGraph).mockClear();
  window.matchMedia = ((query: string) => ({
    matches: query === "(min-width: 901px) and (max-width: 1599px)" ? midWidth : false,
    addEventListener() {},
    removeEventListener() {},
  })) as unknown as typeof window.matchMedia;
  // jsdom has no modal dialog and no layout: a dialog opens by its attribute; nothing scrolls.
  HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLElement.prototype.scrollTo = function () {} as typeof HTMLElement.prototype.scrollTo;
  resetForTests(() => ({ postMessage() {}, terminate() {}, addEventListener() {} }));
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  sessionStorage.clear();
  resetForTests(() => ({ postMessage() {}, terminate() {}, addEventListener() {} }));
});

async function waitFor(check: () => unknown, what = "condition") {
  for (let i = 0; i < 200; i++) {
    if (check()) return;
    await act(async () => new Promise((r) => setTimeout(r, 10)));
  }
  throw new Error(`timed out waiting for ${what}`);
}

async function visit(url: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () =>
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[url]}>
          <WhereAmI />
          <Routes>
            <Route path="/a/:id" element={<AnalysisShell />}>
              <Route path="explore" element={<ExplorePage />} />
              <Route path="findings" element={<p>Findings list</p>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  );
  await waitFor(() => !searchButton().disabled, "the analysis status");
}

const $ = <T extends Element = HTMLElement>(sel: string) => host.querySelector<T>(sel);
const searchButton = () => $<HTMLButtonElement>(".analysis-search")!;
const dialog = () => $<HTMLDialogElement>("dialog.goto");
const input = () => $<HTMLInputElement>(".goto-input")!;
const options = () => [...host.querySelectorAll<HTMLElement>("[role=option]")];
const optionText = () => options().map((o) => o.textContent);
const params = () => new URLSearchParams(here.split("?")[1] ?? "");

function key(target: EventTarget, k: string, init: KeyboardEventInit = {}) {
  const e = new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true, ...init });
  act(() => {
    target.dispatchEvent(e);
  });
  return e;
}
function type(text: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  act(() => {
    setter.call(input(), text);
    input().dispatchEvent(new Event("input", { bubbles: true }));
  });
}
async function openDialog() {
  searchButton().focus();
  act(() => searchButton().click());
  await waitFor(() => dialog() && !dialog()!.hasAttribute("aria-busy") && !$(".goto-results[aria-busy]"), "the file list");
}
const codeShows = (text: string) => waitFor(() => $(".code")?.textContent?.includes(text), `the code of ${text}`);
async function search(text: string) {
  type(text);
  await waitFor(() => options().length > 0 || $(".goto-message")?.textContent?.includes("No files"), "results");
}

describe("opening the dialog", () => {
  it("opens from the header button and from Ctrl+K, Cmd+K and /", async () => {
    await visit("/a/7/explore");
    expect(searchButton().textContent).toContain("Go to file");
    expect(dialog()).toBeNull();
    for (const press of [{ key: "k", ctrlKey: true }, { key: "k", metaKey: true }, { key: "/" }]) {
      const e = key(document.body, press.key, press);
      expect(e.defaultPrevented).toBe(true); // the browser's own Ctrl+K or quick find stays away
      await waitFor(() => dialog(), "the dialog");
      key(input(), "Escape");
      expect(dialog()).toBeNull();
    }
  });

  it("does not open while the user is typing in a field, but does from a checkbox", async () => {
    await visit("/a/7/explore");
    key($(".probe-field")!, "/");
    key($(".probe-field")!, "k", { ctrlKey: true });
    await act(async () => new Promise((r) => setTimeout(r, 30)));
    expect(dialog()).toBeNull();
    key($(".probe-check")!, "/");
    await waitFor(() => dialog(), "the dialog");
  });

  it("loads no file list until it is opened, then both lists", async () => {
    await visit("/a/7/findings");
    expect(vi.mocked(getGraph)).not.toHaveBeenCalled();
    await openDialog();
    await waitFor(() => vi.mocked(getGraph).mock.calls.length === 2, "two list requests");
    const asked = vi.mocked(getGraph).mock.calls.map((c) => c[1].showTests).sort();
    expect(asked).toEqual([false, true]);
  });
});

describe("in the dialog", () => {
  it("says what to type before anything is typed, and what was not found", async () => {
    await visit("/a/7/explore");
    await openDialog();
    expect($(".goto-message")?.textContent).toBe("Type part of a file or folder name, or a path.");
    await search("zzzz");
    expect($(".goto-message")?.textContent).toBe("No files match “zzzz”");
    expect(options()).toHaveLength(0);
    expect($(".goto-note")?.textContent).toBe(SCOPE_NOTE);
  });

  it("ranks and highlights; Up and Down move, Enter opens, focus goes to the opened file", async () => {
    await visit("/a/7/explore");
    await openDialog();
    await search("trans");
    expect(optionText()[0]).toContain("trans.py");
    expect(optionText()[0]).toContain("src/black");
    expect(options()[0].querySelector(".goto-name mark")?.textContent).toBe("trans");
    const combo = input();
    expect(combo.getAttribute("aria-activedescendant")).toBe(options()[0].id);
    key(combo, "ArrowDown");
    expect(combo.getAttribute("aria-activedescendant")).toBe(options()[1].id);
    expect(options()[1].getAttribute("aria-selected")).toBe("true");
    key(combo, "ArrowUp");
    key(combo, "ArrowUp"); // wraps to the last
    expect(combo.getAttribute("aria-activedescendant")).toBe(options()[options().length - 1].id);
    key(combo, "ArrowDown"); // and back to the first
    key(combo, "Enter");
    expect(dialog()).toBeNull();
    expect(params().get("node")).toBe("1");
    await waitFor(() => $(".code"), "the code");
    expect(document.activeElement?.classList.contains("panel-title")).toBe(true);
  });

  it("Esc closes and gives focus back to what opened it", async () => {
    await visit("/a/7/explore");
    await openDialog();
    expect(document.activeElement).toBe(input());
    key(input(), "Escape");
    expect(dialog()).toBeNull();
    expect(document.activeElement).toBe(searchButton());
  });

  it("a mouse click opens a result", async () => {
    await visit("/a/7/explore");
    await openDialog();
    await search("linegen");
    act(() => options()[0].click());
    expect(params().get("node")).toBe("2");
  });

  it("caps the list and says how many more there are", async () => {
    const many = Array.from({ length: 120 }, (_, i) => node(100 + i, `pkg/mod_${String(i).padStart(3, "0")}.py`));
    lists = { all: many, plain: many };
    await visit("/a/7/explore");
    await openDialog();
    await search("mod_");
    expect(options()).toHaveLength(50);
    expect($(".goto-message")?.textContent).toBe("70 more — keep typing");
  });

  it("opens a folder in the map", async () => {
    await visit("/a/7/explore?guesses=1");
    await openDialog();
    await search("black");
    expect(optionText()[0]).toContain("black");
    expect(options()[0].textContent).toContain("folder");
    key(input(), "Enter");
    expect(here).toBe("/a/7/explore?level=folder&root=src%2Fblack&guesses=1");
  });
});

describe("Esc with a file panel open behind the dialog", () => {
  it("one press closes only the dialog; the panel stays", async () => {
    await visit("/a/7/explore?node=1");
    await waitFor(() => $(".code"), "the panel");
    await openDialog();
    const e = key(input(), "Escape");
    expect(e.defaultPrevented).toBe(true); // so the browser fires no native "cancel" on top
    expect(dialog()).toBeNull();
    expect(params().get("node")).toBe("1");
    expect($(".panel-title")).not.toBeNull();
  });

  it("a native cancel alone (no key event) also closes only the dialog", async () => {
    await visit("/a/7/explore?node=1");
    await waitFor(() => $(".code"), "the panel");
    await openDialog();
    act(() => {
      dialog()!.dispatchEvent(new Event("cancel", { cancelable: true }));
    });
    expect(dialog()).toBeNull();
    expect(params().get("node")).toBe("1");
  });
});

describe("test and example files", () => {
  it("finds a test file that the map hides, says the toggle turns on, and opens it", async () => {
    await visit("/a/7/explore");
    await openDialog();
    await search("test_black");
    expect(optionText()[0]).toContain("test_black.py");
    expect(options()[0].querySelector(".goto-tag")?.textContent).toBe("test or example");
    expect($(".goto-note")?.textContent).toBe(TESTS_NOTE);
    expect(input().getAttribute("aria-describedby")).toBe($(".goto-note")!.id);
    key(input(), "Enter");
    expect(params().get("node")).toBe("5");
    expect(params().get("tests")).toBe("1");
    await codeShows("tests/test_black.py");
  });

  it("does not say the toggle turns on when tests are already shown", async () => {
    await visit("/a/7/explore?tests=1");
    await openDialog();
    await search("test_black");
    await waitFor(() => options()[0].querySelector(".goto-tag"), "the tag");
    expect($(".goto-note")?.textContent).toBe(SCOPE_NOTE);
  });

  it("tags nothing until the list without tests has arrived, then tags only test files", async () => {
    let release!: () => void;
    holdPlain = new Promise<void>((r) => (release = r));
    await visit("/a/7/explore?tests=1"); // only the list with tests is loaded by the page
    await openDialog();
    await search("trans");
    expect(optionText().some((t) => t?.includes("test_trans.py"))).toBe(true);
    expect(host.querySelectorAll(".goto-tag")).toHaveLength(0); // not known yet: no tag at all
    await act(async () => release());
    await waitFor(() => host.querySelector(".goto-tag"), "the tag");
    const tagged = options().filter((o) => o.querySelector(".goto-tag")).map((o) => o.title);
    expect(tagged).toEqual(["tests/test_trans.py"]);
  });
});

describe("the File tab and the Code tab", () => {
  it("brings the File tab forward with the code shown, from the Used by tab and from behind Ask", async () => {
    midWidth = true;
    await visit("/a/7/explore?ask=1&node=2");
    await waitFor(() => $(".code"), "the panel");
    const tab = (name: string) =>
      [...host.querySelectorAll<HTMLElement>("[role=tab]")].find((t) => t.textContent?.startsWith(name))!;
    act(() => tab("Used by").click());
    act(() => tab("Ask").click());
    expect(tab("Ask").getAttribute("aria-selected")).toBe("true");
    await openDialog();
    await search("trans.py");
    key(input(), "Enter");
    await codeShows("src/black/trans.py");
    expect(tab("File").getAttribute("aria-selected")).toBe("true");
    expect(tab("Code").getAttribute("aria-selected")).toBe("true");
    expect(params().get("ask")).toBe("1");
  });
});

describe("from Findings", () => {
  it("opens the file in the Explorer", async () => {
    await visit("/a/7/findings?tests=hide");
    await openDialog();
    await search("linegen");
    key(input(), "Enter");
    expect(here).toBe("/a/7/explore?node=2");
  });
});

describe("the result link", () => {
  const file = { kind: "file", path: "src/a.py", nameAt: 4, lower: "src/a.py", fileId: 9, language: "python" } as const;
  it("is a citation's link, keeping the Explorer's guessed calls, all edges and List view", () => {
    const page = { onExplorer: true, search: "?guesses=1&edges=all&view=list&level=folder&root=x&node=3&ask=1" };
    expect(resultHref(7, { ...file, test: false }, page)).toBe(
      "/a/7/explore?node=9&ask=1&guesses=1&edges=all&view=list",
    );
  });
  it("turns tests on for a test file, and when it is not known yet", () => {
    const page = { onExplorer: true, search: "" };
    expect(resultHref(7, { ...file, test: true }, page)).toBe("/a/7/explore?node=9&tests=1");
    expect(resultHref(7, { ...file, test: null }, page)).toBe("/a/7/explore?node=9&tests=1");
    expect(resultHref(7, { ...file, test: false }, { onExplorer: true, search: "?tests=1" })).toBe(
      "/a/7/explore?node=9&tests=1",
    );
  });
  it("from Findings keeps only Ask (its tests filter means something else)", () => {
    expect(resultHref(7, { ...file, test: false }, { onExplorer: false, search: "?tests=hide&ask=1&view=x" })).toBe(
      "/a/7/explore?node=9&ask=1",
    );
  });
});
