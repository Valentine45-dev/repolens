// Addresses inside an analysis (spec §3.6: state lives in the URL).

import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

export interface LineRange {
  start: number;
  end: number;
}

/** Explorer with a file selected and, optionally, lines highlighted. `tests` makes a test
 * file visible (the graph hides test files by default); `ask` keeps the Ask drawer open. */
export function exploreHref(
  snapshotId: number,
  opts: { fileId?: number; lines?: LineRange | null; tests?: boolean; ask?: boolean } = {},
): string {
  const params = new URLSearchParams();
  if (opts.fileId !== undefined) params.set("node", String(opts.fileId));
  if (opts.lines) params.set("lines", `${opts.lines.start}-${opts.lines.end}`);
  if (opts.tests) params.set("tests", "1");
  if (opts.ask) params.set("ask", "1");
  const query = params.toString();
  return `/a/${snapshotId}/explore${query ? `?${query}` : ""}`;
}

/** '12-15' -> {12, 15}; '12' -> {12, 12}; anything else -> null. */
export function parseLines(value: string | null): LineRange | null {
  const m = value?.match(/^(\d+)(?:-(\d+))?$/);
  if (!m) return null;
  const start = Number(m[1]);
  const end = Number(m[2] ?? m[1]);
  return start >= 1 && end >= start ? { start, end } : null;
}

/** Set or clear search params. Builds on the address bar, not the router's possibly stale
 * copy, so two quick changes never lose the first. */
export function useSetParams() {
  const [, setParams] = useSearchParams();
  return useCallback(
    (changes: Record<string, string | null>, replace = true) => {
      const next = new URLSearchParams(window.location.search);
      for (const [key, value] of Object.entries(changes)) {
        if (value === null) next.delete(key);
        else next.set(key, value);
      }
      setParams(next, { replace });
    },
    [setParams],
  );
}
