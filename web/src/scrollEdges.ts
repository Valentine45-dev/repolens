import { type RefObject, useCallback, useEffect, useState } from "react";

export interface Edges {
  top: boolean; // there is more content above what is in view
  bottom: boolean; // there is more content below
}

/** Whether a scroll area has more content above or below, with a pixel of tolerance for the
 * fractional scroll positions some browsers report. */
export function edgesOf(scrollTop: number, clientHeight: number, scrollHeight: number): Edges {
  return { top: scrollTop > 1, bottom: scrollTop + clientHeight < scrollHeight - 1 };
}

/** Live edges of a scroll area: on scroll, on resize of the area or its content. */
export function useScrollEdges(ref: RefObject<HTMLElement | null>): Edges {
  const [edges, setEdges] = useState<Edges>({ top: false, bottom: false });
  const measure = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const next = edgesOf(el.scrollTop, el.clientHeight, el.scrollHeight);
    setEdges((prev) => (prev.top === next.top && prev.bottom === next.bottom ? prev : next));
  }, [ref]);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    measure();
    el.addEventListener("scroll", measure, { passive: true });
    const resize = typeof ResizeObserver === "function" ? new ResizeObserver(measure) : null;
    resize?.observe(el);
    // Content growing or shrinking (an answer arriving, suggestions loading) changes scrollHeight.
    const mutate = typeof MutationObserver === "function" ? new MutationObserver(measure) : null;
    mutate?.observe(el, { childList: true, subtree: true, characterData: true });
    return () => {
      el.removeEventListener("scroll", measure);
      resize?.disconnect();
      mutate?.disconnect();
    };
  }, [ref, measure]);
  return edges;
}
