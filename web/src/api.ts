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
}

export interface Submitted {
  snapshot_id: number;
  job_id: number;
  commit_sha: string;
  status: JobStatus;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
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
  } catch {
    throw new ApiError(UNREACHABLE, 0);
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Not JSON (e.g. the proxy's 502 page): keep the generic message.
    }
    if (response.status === 502 || response.status === 504) detail = UNREACHABLE;
    throw new ApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

export function submitRepo(url: string): Promise<Submitted> {
  return request("/repos", { method: "POST", body: JSON.stringify({ url }) });
}

export function getStatus(snapshotId: number): Promise<SnapshotStatus> {
  return request(`/snapshots/${snapshotId}/status`);
}

export function isFinished(status: JobStatus | undefined): boolean {
  return status === "done" || status === "failed";
}

/** 'https://github.com/pallets/itsdangerous' -> 'pallets/itsdangerous' */
export function repoName(url: string): string {
  return url.replace(/^https:\/\/github\.com\//, "").replace(/\.git$/, "").replace(/\/$/, "");
}
