import { useQuery } from "@tanstack/react-query";
import { Navigate, NavLink, Outlet, useParams, useSearchParams } from "react-router-dom";

import { ApiError, getFindings, getStatus, repoName, type SnapshotStatus } from "../api";
import { useSetParams } from "../links";
import { AskDrawer } from "./AskDrawer";
import { ConnectionNotice, isReconnecting } from "./ConnectionNotice";

export interface AnalysisContext {
  snapshotId: number;
  status: SnapshotStatus;
}

// Header on every tab (spec §3.4): repo, commit, tabs, Ask. The Ask drawer (?ask=1) stays open
// across tabs because tab links keep that one parameter. Only tabs that exist are shown.
export function AnalysisShell() {
  const { id } = useParams();
  const snapshotId = Number(id);
  const valid = Number.isInteger(snapshotId) && snapshotId > 0;
  const [params] = useSearchParams();
  const askOpen = params.get("ask") === "1";
  const setParams = useSetParams();

  const status = useQuery({
    queryKey: ["status", snapshotId],
    queryFn: ({ signal }) => getStatus(snapshotId, signal),
    enabled: valid,
    staleTime: 30_000,
  });
  const done = status.data?.status === "done";
  const counts = useQuery({
    queryKey: ["findings", snapshotId, "count"],
    queryFn: ({ signal }) => getFindings(snapshotId, { limit: 1 }, signal),
    enabled: done,
    staleTime: Infinity,
  });

  if (!valid || (status.error instanceof ApiError && status.error.status === 404)) {
    return <Navigate to={`/a/${id}`} replace />;
  }
  if (status.data && !done) return <Navigate to={`/a/${snapshotId}`} replace />;

  const keep = askOpen ? "?ask=1" : "";
  const total = counts.data?.counts.total;
  return (
    <div className="analysis">
      <header className="analysis-header">
        <div className="analysis-heading">
          {status.data ? (
            <h1 className="explore-title">
              <a href={status.data.url} target="_blank" rel="noreferrer" className="mono">
                {repoName(status.data.url)}
              </a>{" "}
              <span className="repo-sha mono">@ {status.data.commit_sha.slice(0, 7)}</span>
            </h1>
          ) : (
            <div className="skeleton" style={{ width: 240, height: 20 }} />
          )}
          {isReconnecting(status) ? <ConnectionNotice /> : null}
        </div>
        <nav className="analysis-tabs" aria-label="Analysis">
          <NavLink to={`/a/${snapshotId}/explore${keep}`} className="analysis-tab">
            Explorer
          </NavLink>
          <NavLink to={`/a/${snapshotId}/findings${keep}`} className="analysis-tab">
            Findings
            {total !== undefined ? <span className="count mono num">{total}</span> : null}
          </NavLink>
        </nav>
        <button
          type="button"
          className="button button-secondary button-small analysis-ask"
          aria-pressed={askOpen}
          aria-controls="ask-drawer"
          onClick={() => setParams({ ask: askOpen ? null : "1" })}
        >
          Ask
        </button>
      </header>
      <div className="analysis-body">
        <div className="analysis-main">
          {status.data ? (
            <Outlet context={{ snapshotId, status: status.data } satisfies AnalysisContext} />
          ) : status.error ? (
            <div className="canvas-message" role="alert">
              <p>{status.error.message}</p>
              <button className="button button-secondary" onClick={() => status.refetch()}>
                Try again
              </button>
            </div>
          ) : (
            <div className="canvas-message" aria-busy="true">
              <p className="caption">Loading analysis…</p>
            </div>
          )}
        </div>
        {askOpen && status.data ? (
          <AskDrawer
            snapshotId={snapshotId}
            status={status.data}
            onClose={() => setParams({ ask: null, askq: null })}
          />
        ) : null}
      </div>
    </div>
  );
}
