// @vitest-environment jsdom
import { ReactFlowProvider } from "@xyflow/react";
import { act, useRef } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MapView as MapViewData } from "../api";
import { useEscapeToClose } from "../escapeStack";
import { edgeBudgetFor, selectEdges } from "../mapModel";
import { mockReactFlowDom } from "../testFlow";
import { NODE_TIP_DELAY } from "./CanvasTip";
import { MapView } from "./MapView";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const VIEW: MapViewData = {
  snapshot_id: 2, level: "file", root: "", breadcrumbs: [{ path: "", label: "" }], view_limit: 60,
  total_files: 2, hidden_files: 0, hidden_count: 0, cycle_scope: "", cycles_available: true, cycles: [],
  nodes: [
    { id: "file:app/a.py", kind: "file", path: "app/a.py", label: "app/a.py", finding_count: 2, file_id: 1,
      language: "python", loc: 10, in_cycle: false },
    { id: "file:app/b.py", kind: "file", path: "app/b.py", label: "app/b.py", finding_count: 0, file_id: 2,
      language: "python", loc: 5, in_cycle: false },
  ],
  edges: [{ source: "file:app/b.py", target: "file:app/a.py", count: 3, confidence: 1, guess: false,
    imports: 1, calls: 2, guess_calls: 0 }],
};
const POSITIONS = new Map([
  ["file:app/a.py", { x: 300, y: 0, rank: 1 }],
  ["file:app/b.py", { x: 0, y: 0, rank: 0 }],
]);

let host: HTMLDivElement;
let root: Root;
let panelClosed = 0;
let restore: () => void;
beforeEach(() => {
  restore = mockReactFlowDom();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  panelClosed = 0;
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.useRealTimers();
  restore();
});

// A side panel that is open: Esc would close it.
function Panel() {
  const ref = useRef<HTMLElement>(null);
  useEscapeToClose(ref, () => (panelClosed += 1));
  return <aside ref={ref}>panel</aside>;
}

async function show() {
  act(() =>
    root.render(
      <MemoryRouter>
        <ReactFlowProvider>
          <MapView
            view={VIEW}
            positions={POSITIONS}
            selection={selectEdges(VIEW.edges, edgeBudgetFor(VIEW.nodes.length))}
            showAll={false}
            snapshotId={2}
            hideTests
            selectedFileId={null}
            panelOverlay={false}
            onAction={() => {}}
            onClear={() => {}}
            onZoomedIn={() => {}}
          />
        </ReactFlowProvider>
        <Panel />
      </MemoryRouter>,
    ),
  );
  for (let i = 0; i < 5; i++) await act(async () => {});
}
const nodeEl = (id: string) => host.querySelector<HTMLElement>(`.react-flow__node[data-id="${id}"]`)!;
const tips = () => [...host.querySelectorAll<HTMLElement>(".map-tip")];
const hover = (el: Element) =>
  act(() => {
    el.dispatchEvent(new MouseEvent("mouseover", { bubbles: true, relatedTarget: document.body }));
    el.dispatchEvent(new MouseEvent("mousemove", { bubbles: true, clientX: 50, clientY: 20 }));
  });

describe("map tooltips: ours only, never the browser's", () => {
  it("draws nodes and edges with no title attribute and no SVG <title>", async () => {
    await show();
    expect(host.querySelectorAll(".react-flow__node")).toHaveLength(2);
    expect(host.querySelectorAll(".react-flow__edge")).toHaveLength(1);
    expect(host.querySelectorAll(".react-flow [title]")).toHaveLength(0);
    expect(host.querySelectorAll(".react-flow title")).toHaveLength(0);
  });

  it("hovering a node shows one tip after 400 ms, the path first in mono, under the node", async () => {
    vi.useFakeTimers();
    await show();
    hover(nodeEl("file:app/a.py"));
    act(() => vi.advanceTimersByTime(NODE_TIP_DELAY - 1));
    expect(tips()).toHaveLength(0);
    act(() => vi.advanceTimersByTime(1));
    expect(tips()).toHaveLength(1);
    const tip = tips()[0];
    expect(tip.dataset.kind).toBe("node");
    expect(tip.querySelector(".map-tip-head.mono")?.textContent).toBe("app/a.py");
    expect(tip.textContent).toContain("Python · 10 lines · 2 findings");
    expect(tip.getAttribute("aria-hidden")).toBe("true");
    expect(tip.dataset.place).toBe("below");
    // Leaving the node hides it after a short grace (time to reach the tip itself).
    act(() => nodeEl("file:app/a.py").dispatchEvent(new MouseEvent("mouseout", { bubbles: true, relatedTarget: document.body })));
    act(() => vi.advanceTimersByTime(200));
    expect(tips()).toHaveLength(0);
  });

  it("keyboard focus shows the tip at once; Esc hides only the tip, not the open panel", async () => {
    await show();
    act(() => nodeEl("file:app/b.py").focus());
    expect(tips()).toHaveLength(1);
    expect(tips()[0].querySelector(".map-tip-head")?.textContent).toBe("app/b.py");
    const esc = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    act(() => nodeEl("file:app/b.py").dispatchEvent(esc));
    expect(tips()).toHaveLength(0);
    expect(panelClosed).toBe(0);
    // With no tip showing, Esc closes the panel as before.
    act(() => nodeEl("file:app/b.py").dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true })));
    expect(panelClosed).toBe(1);
  });

  it("gives screen readers the tip text: node description, edge label", async () => {
    await show();
    const a = nodeEl("file:app/a.py");
    expect(a.getAttribute("aria-label")).toBe("app/a.py");
    const desc = document.getElementById(a.getAttribute("aria-describedby") ?? "")?.textContent ?? "";
    expect(desc).toContain("Python · 10 lines · 2 findings.");
    expect(desc).toContain("Enter opens the file.");
    expect(desc).not.toContain("delete");
    const edge = host.querySelector(".react-flow__edge")!;
    expect(edge.getAttribute("aria-label")).toMatch(/^app\/b\.py → app\/a\.py: /);
  });

  it("hovering an edge shows exactly one tip, starting with its two ends", async () => {
    await show();
    hover(host.querySelector(".react-flow__edge")!);
    expect(tips()).toHaveLength(1);
    expect(tips()[0].dataset.kind).toBe("edge");
    expect(tips()[0].textContent).toMatch(/^app\/b\.py → app\/a\.py: /);
  });
});
