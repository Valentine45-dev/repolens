// @vitest-environment jsdom
// COR-05: with tests hidden, the file panel's Used by / Uses count what the map and the List view
// count, and say how many test or example files were left out.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { GraphNode, Neighbour } from "../api";
import { NodePanel } from "./NodePanel";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const HELPERS: GraphNode = {
  id: 1, symbol_id: 10, path: "src/flask/helpers.py", language: "python", loc: 600, external_imports: 1,
  unresolved_imports: 0, findings: 0,
};
const item = (fileId: number | null, path: string, kind = "module"): Neighbour => ({
  type: "imports", confidence: 1, site_file_id: fileId, site_path: path, sites: [], site_count: 0,
  symbol: { id: (fileId ?? 0) * 10 + 1, kind, name: path, qualified_name: path, file_id: fileId, path: fileId === null ? null : path, start_line: 1, end_line: 1 },
} as Neighbour);
// flask: 9 files in src/ use helpers.py, and 13 test files.
const CODE = Array.from({ length: 9 }, (_, i) => item(100 + i, `src/flask/m${i}.py`));
const TESTS = Array.from({ length: 13 }, (_, i) => item(200 + i, `tests/test_${i}.py`));
const inGraph = (id: number) => id === 1 || (id >= 100 && id < 109) || id === 300;

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  getFile: vi.fn(async () => ({ id: 1, path: HELPERS.path, language: "python", loc: 1, content: "x = 1", symbols: [], findings: [], external_imports: [], unresolved_imports: [] })),
  getNeighbours: vi.fn(async (_id: number, direction: string) =>
    direction === "dependents"
      ? { symbol: {}, min_confidence: 0.9, files: 22, items: [...CODE, ...TESTS] }
      : { symbol: {}, min_confidence: 0.9, files: 2, items: [item(300, "src/flask/globals.py"), item(201, "tests/conftest.py"), item(null, "werkzeug", "external")] },
  ),
}));

let host: HTMLDivElement;
let root: Root;
let showTests: number;
beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  showTests = 0;
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

async function show(testsHidden: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  act(() =>
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <NodePanel
            snapshotId={6} node={HELPERS} minConfidence={0.9} highlight={null}
            isInGraph={testsHidden ? inGraph : () => true} testsHidden={testsHidden} onShowTests={() => (showTests += 1)}
            onSelectFile={() => {}} onShowLines={() => {}} onAsk={() => {}} onClose={() => {}}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  );
  for (let i = 0; i < 10; i++) await act(async () => new Promise((r) => setTimeout(r, 0)));
}
const fact = (name: string) =>
  [...host.querySelectorAll(".panel-facts div")].find((d) => d.querySelector("dt")?.textContent === name)
    ?.querySelector("dd")?.textContent;
const openTab = (name: string) =>
  act(() => [...host.querySelectorAll<HTMLButtonElement>("[role=tab]")].find((t) => t.textContent === name)!.click());
const rows = () => [...host.querySelectorAll(".neighbour-head")].map((r) => r.textContent);
const note = () => host.querySelector(".neighbour-hidden")?.textContent ?? null;

describe("Used by and Uses with tests hidden (COR-05)", () => {
  it("counts the 9 files the map counts, lists those 9, and says 13 test files are hidden", async () => {
    await show(true);
    expect(fact("Used by")).toBe("9 files");
    openTab("Used by");
    expect(rows()).toHaveLength(9);
    expect(host.querySelectorAll(".neighbour-head button")).toHaveLength(9); // every row opens
    expect(note()).toBe("13 test or example files also use this file; they're hidden. Show tests & examples");
    act(() => host.querySelector<HTMLButtonElement>(".neighbour-hidden button")!.click());
    expect(showTests).toBe(1);
  });

  it("Uses: the hidden test file is left out, the external import stays", async () => {
    await show(true);
    expect(fact("Uses")).toBe("1 file");
    openTab("Uses");
    expect(rows()).toEqual(["src/flask/globals.py", "werkzeugexternal"]);
    expect(note()).toBe("This file also uses 1 test or example file; it's hidden. Show tests & examples");
  });

  it("with tests shown, counts and lists every file and adds no note", async () => {
    await show(false);
    expect(fact("Used by")).toBe("22 files");
    openTab("Used by");
    expect(rows()).toHaveLength(22);
    expect(note()).toBeNull();
  });
});
