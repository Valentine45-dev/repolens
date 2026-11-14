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
  /** 0 exact name or path, 1 name prefix, 2 name substring, 3 path substring, 4 in order inside
   * the name, each piece at the start of a word. */
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

const SEPARATORS = new Set(["_", "-", ".", " "]);
const isLetter = (c: string) => c.toLowerCase() !== c.toUpperCase();
const isDigit = (c: string) => c >= "0" && c <= "9";

/** Where a word starts in a name: its first character, after `_ - .` or a space, a capital after
 * a small letter (camelCase), or where letters and digits meet. */
export function isWordStart(name: string, i: number): boolean {
  if (i === 0) return true;
  const prev = name[i - 1];
  const cur = name[i];
  if (SEPARATORS.has(prev)) return true;
  if (isLetter(prev) && isLetter(cur)) return prev === prev.toLowerCase() && cur !== cur.toLowerCase();
  return (isDigit(prev) && isLetter(cur)) || (isLetter(prev) && isDigit(cur));
}

/** An in-order match inside the name only, in pieces that each start a word: "tblack" finds
 * test_black.py, "lrb" finds line_ranges_basic.py, but "trans" does not find
 * fstring_quotations.py (its letters are scattered inside words). Ranges index into the name. */
function wordMatch(name: string, lowerName: string, q: string): Range[] | null {
  const failed = new Set<string>(); // (query index, name index, inside a run) that cannot finish
  const hits: number[] = [];
  const place = (qi: number, from: number, runEnd: number): boolean => {
    if (qi === q.length) return true;
    const memo = `${qi}:${from}:${runEnd}`;
    if (failed.has(memo)) return false;
    // Continue the current run first (fewer pieces), then try each word start further on.
    if (runEnd >= 0 && lowerName[runEnd] === q[qi]) {
      hits.push(runEnd);
      if (place(qi + 1, runEnd + 1, runEnd + 1)) return true;
      hits.pop();
    }
    for (let i = from; i < lowerName.length; i++) {
      if (i === runEnd || lowerName[i] !== q[qi] || !isWordStart(name, i)) continue;
      hits.push(i);
      if (place(qi + 1, i + 1, i + 1)) return true;
      hits.pop();
    }
    failed.add(memo);
    return false;
  };
  if (!place(0, 0, -1)) return null;
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
  if (q.includes("/")) return null; // a path was typed: it has to be in the path as typed
  const inWords = wordMatch(entry.path.slice(nameAt), name, q);
  return inWords ? { entry, tier: 4, ranges: inWords.map(([s, e]) => [s + nameAt, e + nameAt] as Range) } : null;
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
