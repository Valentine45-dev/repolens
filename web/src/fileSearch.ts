// "Go to file": the list of files and folders the dialog searches, and the matcher. Pure; no
// React. The lists come from the flat file graph (GET /snapshots/{id}/graph), which holds every
// file the panel can open: parsed Python / JavaScript / TypeScript files.

export interface ListedFile {
  id: number;
  path: string;
  language: string;
}

export interface SearchEntry {
  kind: "file" | "folder";
  path: string;
  /** Where the last path segment (the name) starts. */
  nameAt: number;
  /** The path lower-cased character by character, so every index matches `path`. */
  lower: string;
  fileId: number | null; // files only
  language: string | null; // files only
  /** A test or example file (or a folder holding only those), by the server's own rule: it is in
   * the list with tests but not in the list without. null: not known yet (that list is loading). */
  test: boolean | null;
}

export type Range = [start: number, end: number]; // end exclusive, indexes into `path`

export interface SearchMatch {
  entry: SearchEntry;
  /** 0 exact name or path, 1 name prefix, 2 name substring, 3 path substring, 4 in order. */
  tier: number;
  ranges: Range[];
}

export interface SearchResult {
  total: number;
  matches: SearchMatch[]; // the best `limit`, best first
}

export const RESULT_LIMIT = 50;

export const LANG_MARK: Record<string, string> = { python: "py", javascript: "js", typescript: "ts" };

/** Lower case without changing the length (a few characters, such as "İ", grow when lower-cased:
 * those stay as they are), so a match index is also an index into the original. */
export function lowerSameLength(text: string): string {
  let out = "";
  for (const ch of text) {
    const low = ch.toLowerCase();
    out += low.length === ch.length ? low : ch;
  }
  return out;
}

/** What is matched: lower case, "\" as "/", no whitespace, no leading "./" or "/". */
export function normaliseQuery(query: string): string {
  return lowerSameLength(query)
    .replace(/\s+/g, "")
    .replace(/\\/g, "/")
    .replace(/^(\.\/)+/, "")
    .replace(/^\/+/, "");
}

function makeEntry(kind: SearchEntry["kind"], path: string, extra: Partial<SearchEntry>): SearchEntry {
  return {
    kind,
    path,
    nameAt: path.lastIndexOf("/") + 1,
    lower: lowerSameLength(path),
    fileId: null,
    language: null,
    test: null,
    ...extra,
  };
}

/** Every file in `withTests` and every folder above one. `withoutTests` (the list the server gives
 * with tests and examples left out) decides the test tag; until it is there, `test` is null, so no
 * file is ever tagged wrongly. */
export function buildEntries(withTests: ListedFile[], withoutTests: ListedFile[] | null): SearchEntry[] {
  const plain = withoutTests ? new Set(withoutTests.map((f) => f.id)) : null;
  const entries: SearchEntry[] = [];
  // folder path -> does it hold a file that is not a test?
  const folders = new Map<string, boolean>();
  for (const f of withTests) {
    const test = plain ? !plain.has(f.id) : null;
    entries.push(makeEntry("file", f.path, { fileId: f.id, language: f.language, test }));
    for (let i = f.path.indexOf("/"); i > 0; i = f.path.indexOf("/", i + 1)) {
      const folder = f.path.slice(0, i);
      folders.set(folder, (folders.get(folder) ?? false) || test === false);
    }
  }
  for (const [path, holdsPlain] of folders) {
    entries.push(makeEntry("folder", path, { test: plain ? !holdsPlain : null }));
  }
  return entries;
}

/** `q` in order inside `text`, matched from the right so the hits gather in the name. */
function subsequence(text: string, q: string): Range[] | null {
  const hits: number[] = [];
  let j = q.length - 1;
  for (let i = text.length - 1; i >= 0 && j >= 0; i--) {
    if (text[i] === q[j]) {
      hits.push(i);
      j--;
    }
  }
  if (j >= 0) return null;
  hits.reverse();
  const ranges: Range[] = [];
  for (const i of hits) {
    const last = ranges[ranges.length - 1];
    if (last && last[1] === i) last[1] = i + 1;
    else ranges.push([i, i + 1]);
  }
  return ranges;
}

/** The first place `q` starts a path segment, else its first place; -1 if it is not there. */
function pathIndex(lower: string, q: string): number {
  let first = -1;
  for (let i = lower.indexOf(q); i >= 0; i = lower.indexOf(q, i + 1)) {
    if (i === 0 || lower[i - 1] === "/") return i;
    if (first < 0) first = i;
  }
  return first;
}

/** How `entry` matches the normalised query, or null. */
export function matchEntry(entry: SearchEntry, q: string): SearchMatch | null {
  if (!q) return null;
  const { lower, nameAt } = entry;
  const name = lower.slice(nameAt);
  const whole = q.replace(/\/+$/, "") || q; // "src/black/" names the folder src/black
  if (lower === whole) return { entry, tier: 0, ranges: [[0, lower.length]] };
  if (name === q) return { entry, tier: 0, ranges: [[nameAt, lower.length]] };
  if (name.startsWith(q)) return { entry, tier: 1, ranges: [[nameAt, nameAt + q.length]] };
  const inName = name.indexOf(q);
  if (inName >= 0) return { entry, tier: 2, ranges: [[nameAt + inName, nameAt + inName + q.length]] };
  const inPath = pathIndex(lower, q);
  if (inPath >= 0) return { entry, tier: 3, ranges: [[inPath, inPath + q.length]] };
  const ranges = subsequence(lower, q);
  return ranges ? { entry, tier: 4, ranges } : null;
}

/** Best first: tier; then, for in-order matches, fewer separate runs; files before folders;
 * the shorter path; then A to Z. */
export function compareMatches(a: SearchMatch, b: SearchMatch): number {
  return (
    a.tier - b.tier ||
    (a.tier === 4 ? a.ranges.length - b.ranges.length : 0) ||
    (a.entry.kind === b.entry.kind ? 0 : a.entry.kind === "file" ? -1 : 1) ||
    a.entry.path.length - b.entry.path.length ||
    (a.entry.path < b.entry.path ? -1 : a.entry.path > b.entry.path ? 1 : 0)
  );
}

export function searchEntries(entries: SearchEntry[], query: string, limit = RESULT_LIMIT): SearchResult {
  const q = normaliseQuery(query);
  if (!q) return { total: 0, matches: [] };
  const all: SearchMatch[] = [];
  for (const entry of entries) {
    const m = matchEntry(entry, q);
    if (m) all.push(m);
  }
  all.sort(compareMatches);
  return { total: all.length, matches: all.slice(0, limit) };
}

export interface Piece {
  text: string;
  hit: boolean;
}

/** `path.slice(from, to)` cut into matched and unmatched pieces, for highlighting. */
export function pieces(path: string, ranges: Range[], from: number, to: number): Piece[] {
  const out: Piece[] = [];
  let at = from;
  for (const [s, e] of ranges) {
    const start = Math.max(s, from);
    const end = Math.min(e, to);
    if (end <= start) continue;
    if (start > at) out.push({ text: path.slice(at, start), hit: false });
    out.push({ text: path.slice(start, end), hit: true });
    at = end;
  }
  if (at < to) out.push({ text: path.slice(at, to), hit: false });
  return out;
}
