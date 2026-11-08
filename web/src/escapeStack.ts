import { type RefObject, useEffect, useRef } from "react";

/** One Escape key for every closable side panel (file panel, finding panel, Ask). Esc closes the
 * panel that holds focus; with focus elsewhere it closes the most recently opened one that can be
 * seen (a panel behind a tab, or hidden, is skipped). One panel per key press, never two. */
interface Layer {
  ref: RefObject<HTMLElement | null>;
  close: () => void;
}

const layers: Layer[] = [];

function visible(el: HTMLElement): boolean {
  if (el.closest("[inert]")) return false;
  const style = getComputedStyle(el);
  return style.display !== "none" && style.visibility !== "hidden";
}

/** The layer Esc should close now, or null. Exported for tests. */
export function topLayer(active: Element | null): Layer | null {
  const holding = [...layers].reverse().find((l) => l.ref.current && active && l.ref.current.contains(active));
  if (holding) return holding;
  return [...layers].reverse().find((l) => l.ref.current && visible(l.ref.current)) ?? null;
}

function onKey(e: KeyboardEvent) {
  if (e.key !== "Escape" || e.defaultPrevented) return;
  const layer = topLayer(document.activeElement);
  if (layer) {
    e.preventDefault();
    layer.close();
  }
}

/** Registers a panel while it is mounted. The newest registration is the top. */
export function useEscapeToClose(ref: RefObject<HTMLElement | null>, close: () => void) {
  const closeRef = useRef(close);
  closeRef.current = close;
  useEffect(() => {
    const layer: Layer = { ref, close: () => closeRef.current() };
    if (layers.length === 0) window.addEventListener("keydown", onKey);
    layers.push(layer);
    return () => {
      layers.splice(layers.indexOf(layer), 1);
      if (layers.length === 0) window.removeEventListener("keydown", onKey);
    };
  }, [ref]);
}
