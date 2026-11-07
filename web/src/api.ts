// Thin client for the FastAPI backend. Vite proxies /api to it (vite.config.ts).

export type JobStatus = "queued" | "running" | "done" | "failed";

export interface SnapshotStatus {
  snapshot_id: number;
  url: string;
  commit_sha: string;
  job_id: number;
  status: JobStatus;
  stage: string; // queued | fetch | discover | parse | edges | done
  percent: number;
  error: string | null;
  /** Counts within the current stage (parse: files, embed: chunks); null in other stages. */
  progress: { done: number; total: number } | null;
  /** What the analysis kept and left out; null when discover has not run, and on old analyses. */
  receipt: Receipt | null;
  features: Features;
}

export interface Receipt {
  files_kept: number;
  files_skipped: number;
  files_beyond_limit: number; // past the file limit, counted with the same skip rules, not read
  hit_file_limit: boolean;
}

const fileCount = new Intl.NumberFormat("en-US");

/** The notice when the file limit cut an analysis short; null otherwise. The total is "about":
 * files past the limit are counted, not read. */
export function fileLimitNotice(receipt: Receipt | null | undefined): string | null {
  if (!receipt?.hit_file_limit) return null;
  const total = receipt.files_kept + receipt.files_beyond_limit;
  return (
    `Analysed ${fileCount.format(receipt.files_kept)} of about ${fileCount.format(total)} files; ` +
    "the file limit was reached. The remaining files were not analysed."
  );
}

/** What the Ask drawer can do (graph questions work whenever the analysis is done). */
export interface Features {
  ask: boolean; // AI answers from code search
  ask_reason: string | null;
  ai: boolean; // an LLM is configured on the server
  /** Search for questions: non-test code first, then test code in the background. */
  search: "embedding" | "tests" | "ready" | "failed";
  search_progress: { done: number; total: number } | null; // chunks, while search runs
  search_error: string | null;
  retry_search: boolean; // "Retry preparing search" is offered
}

export type Severity = "high" | "medium" | "low";

export interface Finding {
  id: number;
  rule_id: string;
  severity: Severity;
  message: string;
  file_id: number;
  path: string;
  language: string;
  line: number;
  symbol: string | null;
  snippet: string | null; // masked
  in_test: boolean;
  in_docs: boolean; // documentation file (.md, .rst, .txt)
  placeholder: boolean; // hardcoded-secret whose value looks like a stand-in
  category: Category | null;
  node_id: number;
}

/** Security rules and Bug / Quality rules (code-quality checks). */
export type Category = "security" | "quality";

export interface FindingsPage {
  total: number;
  limit: number;
  offset: number;
  items: Finding[];
  counts: {
    total: number;
    by_severity: Record<Severity, number>;
    by_rule: Record<string, number>;
    by_category: Record<Category, number>;
    placeholders: number;
    documentation: number;
  };
  /** Things the list cannot promise, in words (for example the quality checks did not finish). */
  notes: string[];
}

export interface FindingsFilter {
  severity?: Severity;
  rule?: string;
  language?: string;
  path_prefix?: string;
  in_test?: boolean;
  category?: Category;
  placeholder?: boolean;
  limit?: number;
  offset?: number;
}

export interface Rule {
  id: string;
  language: string;
  severity: Severity;
  category: Category;
  title: string;
  checks: string;
  why: string;
  false_positive: string;
}

export interface Citation {
  path: string;
  start_line: number;
  end_line: number;
  file_id: number;
  symbol_id: number;
  in_test: boolean;
}

/** One place an import or call happens, in the file named by `site_path` next to it. */
export interface Site {
  line: number;
  confidence: number | null; // that site's own, for calls; null for imports
}

export interface GraphResult {
  node_id: number;
  kind: string;
  name: string;
  qualified_name: string;
  file_id: number | null;
  path: string | null;
  start_line: number | null;
  end_line: number | null;
  in_test: boolean;
  edge?: "imports" | "calls";
  confidence?: number;
  // Where the import/call happens (graph answers only). site_count counts every line; `sites`
  // lists the first few. null count = this analysis predates sites.
  sites?: Site[];
  site_count?: number | null;
  site_file_id?: number | null;
  site_path?: string | null;
}

export type AskStatus =
  | "answered"
  | "ambiguous"
  | "unverified"
  | "refused"
  | "no_context"
  | "unavailable"
  | "cap_reached";

export interface Answer {
  kind: "graph" | "ai";
  status: AskStatus;
  answer: string;
  citations: Citation[];
  dropped: number;
  /** Search hits when the LLM could not answer (never from model text). Older turns lack it. */
  locations?: Citation[];
  results: GraphResult[];
  prompt_version: string | null;
  retrieval: {
    sent: number;
    used_test_code: boolean;
    from_graph: number;
    scope?: { file_id: number; sent: number }; // "Ask about this" questions only
  } | null;
  // graph answers only
  query?: string;
  target?: GraphResult | null;
  total?: number;
  lower_confidence?: number;
}

export interface Submitted {
  snapshot_id: number;
  job_id: number;
  commit_sha: string;
  status: JobStatus;
}

export interface GraphNode {
  id: number; // file id
  symbol_id: number; // the file's module symbol
  path: string;
  language: string;
  loc: number;
  external_imports: number;
  unresolved_imports: number;
  findings: number;
}

export interface GraphEdge {
  source: number;
  target: number;
  import: boolean;
  calls: number;
  weight: number;
  confidence: number; // 1.0 with an import, else the best call confidence
}

export interface Graph {
  snapshot_id: number;
  min_confidence: number;
  exclude_tests: boolean;
  hidden_files: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// --- The folder-first map (GET /graph?level=&root=, backend app/graph_map.py) ---------------

export type MapLevel = "folder" | "file" | "symbol";

export interface MapNode {
  id: string; // dir:<path> | file:<path> | sym:<id> | more:<path>
  kind: "folder" | "file" | "more" | "module" | "class" | "function" | "method";
  path: string;
  label: string;
  finding_count: number;
  // folder, file and "more" nodes
  file_count?: number;
  test_file_count?: number;
  in_cycle?: boolean | null; // null: cycles not known for this snapshot yet
  cycle_files?: number | null;
  internal_count?: number;
  outside_in?: number;
  outside_out?: number;
  hidden_count?: number; // "more" only
  // file nodes
  file_id?: number;
  symbol_id?: number;
  language?: string;
  loc?: number;
  external_imports?: number;
  unresolved_imports?: number;
  // symbol nodes
  qualified_name?: string;
  start_line?: number | null;
  end_line?: number | null;
  own?: boolean;
}

export interface MapEdge {
  source: string;
  target: string;
  count: number;
  confidence: number;
  guess: boolean; // true only when every underlying edge is a guess
  // folder and file levels
  imports?: number;
  calls?: number;
  guess_calls?: number;
  cycle_edges?: number | null; // null: cycles not known for this snapshot yet
  // symbol level
  type?: "calls" | "defines";
  sites?: { path: string; line: number }[]; // call lines (the first few); calls only
  site_count?: number | null; // every call line; null: not known for this analysis
}

export interface Crumb {
  path: string;
  label: string; // "" for the repo itself
}

export interface MapView {
  snapshot_id: number;
  level: MapLevel;
  root: string; // canonical: what the server opened
  breadcrumbs: Crumb[];
  view_limit: number;
  total_files: number;
  hidden_files: number;
  hidden_files_under_root?: number;
  hidden_symbols?: number;
  hidden_count: number;
  other_findings?: number;
  file?: { file_id: number; path: string; in_cycle: boolean | null; finding_count: number }; // symbol level
  cycle_scope: string;
  cycles_available: boolean;
  cycles: { id: number; size: number; files: string[] }[];
  nodes: MapNode[];
  edges: MapEdge[];
}

export function getMapView(
  snapshotId: number,
  opts: { level: MapLevel; root: string; showTests: boolean; showGuesses: boolean },
  signal?: AbortSignal,
): Promise<MapView> {
  const params = new URLSearchParams({
    level: opts.level,
    exclude_tests: String(!opts.showTests),
    min_confidence: opts.showGuesses ? "0.5" : "0.9",
  });
  if (opts.root) params.set("root", opts.root);
  return request(`/snapshots/${snapshotId}/graph?${params}`, { signal });
}

export interface FileSymbol {
  id: number;
  kind: string;
  name: string;
  qualified_name: string;
  start_line: number | null;
  end_line: number | null;
  signature: string | null;
}

export interface FileDetail {
  id: number;
  path: string;
  language: string | null;
  loc: number;
  content: string;
  symbols: FileSymbol[];
  findings: { id: number; rule_id: string; severity: Severity; line: number; message: string }[];
  external_imports: string[];
  unresolved_imports: string[];
}

export interface Neighbour {
  type: "imports" | "calls";
  confidence: number;
  // Where it happens, in the file `site_path` (file id `site_file_id`).
  sites?: Site[];
  site_count?: number | null;
  site_file_id?: number | null;
  site_path?: string | null;
  symbol: {
    id: number;
    kind: string;
    name: string;
    qualified_name: string;
    file_id: number | null;
    path: string | null;
    start_line: number | null;
    end_line: number | null;
  };
}

export interface Neighbours {
  files: number;
  items: Neighbour[];
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    /** The server could not be reached (or the proxy could not reach it): worth retrying. */
    readonly network = false,
  ) {
    super(message);
  }
}

const UNREACHABLE = "Could not reach the RepoLens server. Check that the API is running.";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(UNREACHABLE, 0, true);
  }
  // The Vite proxy answers 502/503/504 when FastAPI is down or restarting.
  if ([502, 503, 504].includes(response.status)) {
    throw new ApiError(UNREACHABLE, response.status, true);
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Not JSON: keep the generic message.
    }
    throw new ApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

export function isNetworkError(error: unknown): boolean {
  return error instanceof ApiError && error.network;
}

/** `commit` pins a full SHA (the Home examples); without it the API follows the default branch. */
export function submitRepo({ url, commit }: { url: string; commit?: string }): Promise<Submitted> {
  return request("/repos", { method: "POST", body: JSON.stringify({ url, commit }) });
}

/** Re-embed a finished analysis whose search failed (the same job; graph and findings stay). */
export function retrySearch(snapshotId: number): Promise<{ search: string }> {
  return request(`/snapshots/${snapshotId}/search`, { method: "POST" });
}

export function getStatus(snapshotId: number, signal?: AbortSignal): Promise<SnapshotStatus> {
  return request(`/snapshots/${snapshotId}/status`, { signal });
}

export function getGraph(
  snapshotId: number,
  opts: { showTests: boolean; showGuesses: boolean },
  signal?: AbortSignal,
): Promise<Graph> {
  const params = new URLSearchParams({
    exclude_tests: String(!opts.showTests),
    min_confidence: opts.showGuesses ? "0.5" : "0.9",
  });
  return request(`/snapshots/${snapshotId}/graph?${params}`, { signal });
}

export function getFile(snapshotId: number, fileId: number, signal?: AbortSignal): Promise<FileDetail> {
  return request(`/snapshots/${snapshotId}/files/${fileId}`, { signal });
}

export function getNeighbours(
  symbolId: number,
  direction: "dependents" | "dependencies",
  minConfidence: number,
  signal?: AbortSignal,
): Promise<Neighbours> {
  return request(`/symbols/${symbolId}/${direction}?min_confidence=${minConfidence}`, { signal });
}

export function getFindings(
  snapshotId: number,
  filter: FindingsFilter,
  signal?: AbortSignal,
): Promise<FindingsPage> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filter)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  return request(`/snapshots/${snapshotId}/findings?${params}`, { signal });
}

export function getRules(signal?: AbortSignal): Promise<Rule[]> {
  return request("/rules", { signal });
}

/** `fileId` is "Ask about this": that file's code always goes into the context. */
export function askQuestion(snapshotId: number, question: string, fileId?: number): Promise<Answer> {
  return request(`/snapshots/${snapshotId}/ask`, {
    method: "POST",
    body: JSON.stringify(fileId === undefined ? { question } : { question, file_id: fileId }),
  });
}

export function isFinished(status: JobStatus | undefined): boolean {
  return status === "done" || status === "failed";
}

/** 'https://github.com/pallets/itsdangerous' -> 'pallets/itsdangerous' */
export function repoName(url: string): string {
  return url.replace(/^https:\/\/github\.com\//, "").replace(/\.git$/, "").replace(/\/$/, "");
}
