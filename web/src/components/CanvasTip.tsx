import { useStore } from "@xyflow/react";
import { type RefObject, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

// The one tooltip of the map and the flat graph (`.map-tip`). The browser's own tooltip (`title`,
// SVG <title>) is not used on the canvas: it showed on top of this one, could not be styled and
// never showed for keyboard focus. Two kinds, told apart by content and position, not colour:
// - an edge tip follows the pointer, first line "A → B: …";
// - a node tip sits under the node's box (above it when there is no room), first line the path
//   in mono. It shows 400 ms after the pointer settles on a node, at once on keyboard focus, and
//   stays while the pointer moves onto it. Esc hides whichever tip is showing, and only the tip.
// The visible tip is aria-hidden: its text is the node's description (aria-describedby) or the
// edge's label, so screen readers get it without the pointer.

export const NODE_TIP_DELAY = 400;
const LEAVE_GRACE = 120; // time to move the pointer from the node onto its tip
const GAP = 6;
const MARGIN = 4;

export type CanvasTip =
  | { kind: "edge"; x: number; y: number; text: string }
  | { kind: "node"; id: string; source: "hover" | "focus" };

export interface CanvasTipApi {
  showEdge(clientX: number, clientY: number, text: string): void;
  hideEdge(): void;
  enterNode(id: string): void;
  leaveNode(): void;
  enterTip(): void;
  leaveTip(): void;
  /** Keyboard focus moved to this node (or off every node, with null). */
  focusNode(id: string | null): void;
  hide(): void;
}

export function useCanvasTip(canvasRef: RefObject<HTMLElement | null>) {
  const [tip, setTip] = useState<CanvasTip | null>(null);
  const timers = useRef<{ show?: ReturnType<typeof setTimeout>; hide?: ReturnType<typeof setTimeout> }>({});
  const api = useMemo<CanvasTipApi>(() => {
    const t = timers.current;
    const clear = () => {
      clearTimeout(t.show);
      clearTimeout(t.hide);
    };
    const dropHover = () =>
      setTip((old) => (old?.kind === "node" && old.source === "hover" ? null : old));
    return {
      showEdge(clientX, clientY, text) {
        clear();
        const box = canvasRef.current?.getBoundingClientRect();
        if (!box) return;
        const x = Math.round(clientX - box.left);
        const y = Math.round(clientY - box.top);
        setTip((old) =>
          old?.kind === "edge" && old.text === text && Math.abs(old.x - x) < 4 && Math.abs(old.y - y) < 4
            ? old
            : { kind: "edge", x, y, text },
        );
      },
      hideEdge: () => setTip((old) => (old?.kind === "edge" ? null : old)),
      enterNode(id) {
        clear();
        t.show = setTimeout(() => setTip({ kind: "node", id, source: "hover" }), NODE_TIP_DELAY);
      },
      leaveNode() {
        clearTimeout(t.show);
        clearTimeout(t.hide);
        t.hide = setTimeout(dropHover, LEAVE_GRACE);
      },
      enterTip: () => clearTimeout(t.hide),
      leaveTip: dropHover,
      focusNode(id) {
        clear();
        setTip((old) =>
          id !== null
            ? { kind: "node", id, source: "focus" }
            : old?.kind === "node" && old.source === "focus"
              ? null
              : old,
        );
      },
      hide() {
        clear();
        setTip(null);
      },
    };
  }, [canvasRef]);
  useEffect(() => {
    const t = timers.current;
    return () => {
      clearTimeout(t.show);
      clearTimeout(t.hide);
    };
  }, []);

  // Esc hides the tip and nothing else: the capture listener runs before the panels' Esc
  // (escapeStack.ts skips a key press whose default was prevented).
  const showing = tip !== null;
  useEffect(() => {
    if (!showing) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.isComposing || e.keyCode === 229) return;
      e.preventDefault();
      api.hide();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [showing, api]);

  return [tip, api] as const;
}

/** True when this focus came from the keyboard (a click also focuses a node; that shows no tip). */
export function focusFromKeyboard(el: Element): boolean {
  try {
    return el.matches(":focus-visible");
  } catch {
    return true;
  }
}

export function EdgeTipView({ tip, canvas }: { tip: Extract<CanvasTip, { kind: "edge" }>; canvas: HTMLElement | null }) {
  return (
    <div
      className="map-tip"
      data-kind="edge"
      aria-hidden="true"
      style={{
        left: tip.x + 14,
        top: tip.y + 14,
        transform: canvas && tip.x > canvas.clientWidth - 340 ? "translateX(calc(-100% - 28px))" : undefined,
      }}
    >
      {tip.text}
    </div>
  );
}

/** Under the node's box (flow coordinates), kept inside the canvas; it moves with the map. */
export function NodeTipView({
  box,
  head,
  lines,
  canvas,
  api,
}: {
  box: { x: number; y: number; width: number; height: number };
  head: string | null; // the path (mono), or nothing for a "N more" node
  lines: string[];
  canvas: HTMLElement | null;
  api: CanvasTipApi;
}) {
  const [tx, ty, zoom] = useStore((s) => s.transform);
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    setSize((old) => (old.w === w && old.h === h ? old : { w, h }));
  });
  const cw = canvas?.clientWidth ?? 0;
  const ch = canvas?.clientHeight ?? 0;
  const left = box.x * zoom + tx;
  const top = box.y * zoom + ty;
  const bottom = (box.y + box.height) * zoom + ty;
  const roomBelow = bottom + GAP + size.h <= ch - MARGIN;
  const roomAbove = top - GAP - size.h >= MARGIN;
  const y = roomBelow || !roomAbove ? bottom + GAP : top - GAP - size.h;
  const x = Math.max(MARGIN, Math.min(left, cw - size.w - MARGIN));
  return (
    <div
      ref={ref}
      className="map-tip"
      data-kind="node"
      data-place={roomBelow || !roomAbove ? "below" : "above"}
      aria-hidden="true"
      style={{ left: x, top: y }}
      onMouseEnter={api.enterTip}
      onMouseLeave={api.leaveTip}
    >
      {head ? <div className="map-tip-head mono">{head}</div> : null}
      {lines.map((line, i) => (
        <div key={i}>{line}</div>
      ))}
    </div>
  );
}
