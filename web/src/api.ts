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
  features: Features;
}

/** What the Ask drawer can do (graph questions work whenever the analysis is done). */
export interface Features {
  ask: boolean; // AI answers from code search
  ask_reason: string | null;
  ai: boolean; // an LLM is configured on the server
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
  node_id: number;
}

export interface FindingsPage {
  total: number;
  limit: number;
  offset: number;
  items: Finding[];
  counts: { total: number; by_severity: Record<Severity, number>; by_rule: Record<string, number> };
}

export interface FindingsFilter {
  severity?: Severity;
  rule?: string;
  language?: string;
  path_prefix?: string;
  in_test?: boolean;
  limit?: number;
  offset?: number;
}

export interface Rule {
  id: string;
  language: string;
  severity: Severity;
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
  results: GraphResult[];
  prompt_version: string | null;
  retrieval: { sent: number; used_test_code: boolean; from_graph: number } | null;
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

export function askQuestion(snapshotId: number, question: string): Promise<Answer> {
  return request(`/snapshots/${snapshotId}/ask`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

export function isFinished(status: JobStatus | undefined): boolean {
  return status === "done" || status === "failed";
}

/** 'https://github.com/pallets/itsdangerous' -> 'pallets/itsdangerous' */
export function repoName(url: string): string {
  return url.replace(/^https:\/\/github\.com\//, "").replace(/\.git$/, "").replace(/\/$/, "");
}
