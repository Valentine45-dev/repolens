// "Recent analyses (this browser)": the last submissions, kept in localStorage only.
// Storage can be unavailable (private windows, blocked site data), so every access is guarded
// and the page works without it.

export interface RecentAnalysis {
  snapshotId: number;
  url: string;
  commitSha: string;
  submittedAt: number; // epoch ms
}

const KEY = "repolens.recent";
const LIMIT = 10;

export function loadRecent(): RecentAnalysis[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (r): r is RecentAnalysis =>
        typeof r?.snapshotId === "number" &&
        typeof r?.url === "string" &&
        typeof r?.commitSha === "string" &&
        typeof r?.submittedAt === "number",
    );
  } catch {
    return [];
  }
}

export function rememberAnalysis(entry: RecentAnalysis): void {
  const rest = loadRecent().filter((r) => r.snapshotId !== entry.snapshotId);
  try {
    window.localStorage.setItem(KEY, JSON.stringify([entry, ...rest].slice(0, LIMIT)));
  } catch {
    // Storage full or blocked: the list is a convenience, not state.
  }
}

const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

/** '2 days ago', 'yesterday', 'just now' */
export function age(epochMs: number, now = Date.now()): string {
  const seconds = Math.round((epochMs - now) / 1000);
  if (Math.abs(seconds) < 45) return "just now";
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ["minute", 60],
    ["hour", 3600],
    ["day", 86400],
    ["week", 604800],
  ];
  let unit: Intl.RelativeTimeFormatUnit = "minute";
  let size = 60;
  for (const [u, s] of steps) {
    if (Math.abs(seconds) >= s) {
      unit = u;
      size = s;
    }
  }
  return relative.format(Math.round(seconds / size), unit);
}
