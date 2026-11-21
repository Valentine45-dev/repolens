// @vitest-environment jsdom
import { ReactFlowProvider } from "@xyflow/react";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { GraphEdge, GraphNode } from "../api";
import { mockReactFlowDom } from "../testFlow";
import { NODE_TIP_DELAY } from "./CanvasTip";
import { GraphView } from "./GraphView";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const file = (id: number, path: string, findings = 0): GraphNode => ({
  id, symbol_id: id * 10, path, language: "python", loc: 12, external_imports: 0, unresolved_imports: 0, findings,
});
const NODES = [file(1, "app/a.py", 1), file(2, "app/b.py")];
const EDGES: GraphEdge[] = [{ source: 2, target: 1, import: true, calls: 3, weight: 4, confidence: 1 }];
const POSITIONS = new Map([
  [1, { id: 1, x: 300, y: 0 }],
  [2, { id: 2, x: 0, y: 0 }],
]);

let host: HTMLDivElement;
let root: Root;
let restore: () => void;
beforeEach(() => {
  restore = mockReactFlowDom();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.useRealTimers();
  restore();
});

async function show() {
  act(() =>
    root.render(
      <ReactFlowProvider>
        <GraphView nodes={NODES} edges={EDGES} positions={POSITIONS} selectedId={null} panelOverlay={false} onSelect={() => {}} />
      </ReactFlowProvider>,
    ),
  );
  for (let i = 0; i < 5; i++) await act(async () => {});
}
const nodeEl = (id: number) => host.querySelector<HTMLElement>(`.react-flow__node[data-id="${id}"]`)!;
const tips = () => [...host.querySelectorAll<HTMLElement>(".map-tip")];
const hover = (el: Element) =>
  act(() => {
    el.dispatchEvent(new MouseEvent("mouseover", { bubbles: true, relatedTarget: document.body }));
    el.dispatchEvent(new MouseEvent("mousemove", { bubbles: true, clientX: 50, clientY: 20 }));
  });

describe("flat graph tooltips: the map's, never the browser's", () => {
  it("draws files and edges with no title attribute and no SVG <title>", async () => {
    await show();
    expect(host.querySelectorAll(".react-flow__node")).toHaveLength(2);
    expect(host.querySelectorAll(".react-flow__edge")).toHaveLength(1);
    expect(host.querySelectorAll(".react-flow [title]")).toHaveLength(0);
    expect(host.querySelectorAll(".react-flow title")).toHaveLength(0);
  });

  it("a file's tip: after 400 ms on hover, at once on keyboard focus; path first in mono", async () => {
    vi.useFakeTimers();
    await show();
    hover(nodeEl(1));
    act(() => vi.advanceTimersByTime(NODE_TIP_DELAY));
    expect(tips()).toHaveLength(1);
    expect(tips()[0].querySelector(".map-tip-head.mono")?.textContent).toBe("app/a.py");
    expect(tips()[0].textContent).toContain("Python · 12 lines · 1 finding");
    act(() => nodeEl(2).focus());
    expect(tips()).toHaveLength(1);
    expect(tips()[0].querySelector(".map-tip-head")?.textContent).toBe("app/b.py");
  });

  it("an edge's tip follows the pointer and names both ends; the edge is labelled with it", async () => {
    await show();
    const edge = host.querySelector(".react-flow__edge")!;
    expect(edge.getAttribute("aria-label")).toBe("app/b.py → app/a.py: imports + 3 calls");
    hover(edge);
    expect(tips()).toHaveLength(1);
    expect(tips()[0].dataset.kind).toBe("edge");
    expect(tips()[0].textContent).toBe("app/b.py → app/a.py: imports + 3 calls");
  });

  it("describes each file to screen readers with its tip", async () => {
    await show();
    const desc = document.getElementById(nodeEl(1).getAttribute("aria-describedby") ?? "")?.textContent;
    expect(desc).toBe("Python · 12 lines · 1 finding. Enter opens the file.");
  });
});
