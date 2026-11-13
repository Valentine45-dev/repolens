// Addresses inside an analysis (spec §3.6: state lives in the URL).

import { useCallback, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";

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

/** Findings under a folder (or in one file). `hideTests` matches a map that hides tests, so the
 * list adds up to the number on the node. A folder gets a trailing "/" so `src` never also
 * matches `src2`. */
export function findingsHref(
  snapshotId: number,
  opts: { path: string; folder: boolean; hideTests: boolean; ask?: boolean },
): string {
  // The map counts every finding, so the list opens on "All"; its default is Security only.
  const params = new URLSearchParams({ category: "all" });
  if (opts.path) params.set("path", opts.folder ? `${opts.path.replace(/\/$/, "")}/` : opts.path);
  if (opts.hideTests) params.set("tests", "hide");
  if (opts.ask) params.set("ask", "1");
  return `/a/${snapshotId}/findings?${params}`;
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

/** Router state for an "open these lines" link (citation chips, graph results and line chips,
 * Open in Explorer, reachability chips): the file panel comes to the front and the lines are
 * scrolled into view, also when the address does not change (the same chip clicked again). */
export const REVEAL = { reveal: true } as const;

/** Changes on every navigation that carries REVEAL, and only then: a later navigation without it
 * (a replace that tidies the address, a map toggle) keeps the last value. Null until the first. */
export function useRevealToken(): string | null {
  const location = useLocation();
  const state = location.state as { reveal?: unknown } | null;
  const key = state?.reveal === true ? location.key : null;
  const [last, setLast] = useState(key);
  if (key !== null && key !== last) setLast(key);
  return key ?? last;
}
