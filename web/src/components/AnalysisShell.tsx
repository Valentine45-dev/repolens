import { useQuery } from "@tanstack/react-query";
import { useMemo, useRef } from "react";
import { Navigate, NavLink, Outlet, useParams, useSearchParams } from "react-router-dom";

import {
  ApiError,
  fileLimitNotice,
  getFindings,
  getStatus,
  repoName,
  type SnapshotStatus,
} from "../api";
import { useSetParams } from "../links";
import { loadRecent } from "../recent";
import { useRightTab } from "../rightTab";
import { useMediaQuery } from "../useMediaQuery";
import { AskDrawer } from "./AskDrawer";
import { ConnectionNotice, isReconnecting } from "./ConnectionNotice";

export interface AnalysisContext {
  snapshotId: number;
  /** Ask and a file or finding panel share one right column, as tabs (Ask open, 901-1599px). */
  tabbed: boolean;
  /** Undefined until the status has loaded: the page draws its chrome at once and waits for this
   * before it asks for data (an analysis that is not done redirects away). */
  status: SnapshotStatus | undefined;
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
  const askButtonRef = useRef<HTMLButtonElement>(null);

  // Below 1600px three docked columns leave the map or list too narrow, so with Ask open a file or
  // finding panel shares Ask's column as a tab (under 901px both overlay, as before). Which tab is
  // in front is view state only: both stay in the URL and both stay mounted.
  const panelParam = params.get("node") ?? params.get("finding");
  const panelOpen = panelParam !== null;
  const midWidth = useMediaQuery("(min-width: 901px) and (max-width: 1599px)");
  const tabbed = askOpen && panelOpen && midWidth;
  const askPrefill = params.get("askq");
  const [rightTab, setRightTab] = useRightTab(panelParam, askOpen, askPrefill);
  const panelKind = params.get("finding") !== null ? "Finding" : "File";

  const status = useQuery({
    queryKey: ["status", snapshotId],
    queryFn: ({ signal }) => getStatus(snapshotId, signal),
    enabled: valid,
    staleTime: 30_000,
    // While search for questions is prepared after the analysis, keep its state current.
    refetchInterval: (query) =>
      ["embedding", "tests"].includes(query.state.data?.features.search ?? "") ? 2000 : false,
  });
  const done = status.data?.status === "done";
  const counts = useQuery({
    queryKey: ["findings", snapshotId, "count"],
    queryFn: ({ signal }) => getFindings(snapshotId, { limit: 1 }, signal),
    enabled: done,
    staleTime: Infinity,
  });

  // An analysis started in this browser is in the recent list: its name is known before the server
  // answers, so the title is real at once and the tabs beside it never move.
  const known = useMemo(() => loadRecent().find((r) => r.snapshotId === snapshotId), [snapshotId]);

  if (!valid || (status.error instanceof ApiError && status.error.status === 404)) {
    return <Navigate to={`/a/${id}`} replace />;
  }
  if (status.data && !done) return <Navigate to={`/a/${snapshotId}`} replace />;

  const keep = askOpen ? "?ask=1" : "";
  const total = counts.data?.counts.total;
  const limitNotice = fileLimitNotice(status.data?.receipt);
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
          ) : known ? (
            <h1 className="explore-title">
              <a href={known.url} target="_blank" rel="noreferrer" className="mono">
                {repoName(known.url)}
              </a>{" "}
              <span className="repo-sha mono">@ {known.commitSha.slice(0, 7)}</span>
            </h1>
          ) : (
            <div className="skeleton" style={{ width: 240, height: 24 }} aria-busy="true" aria-label="Loading the analysis" />
          )}
          {isReconnecting(status) ? <ConnectionNotice /> : null}
        </div>
        <nav className="analysis-tabs" aria-label="Analysis">
          <NavLink to={`/a/${snapshotId}/explore${keep}`} className="analysis-tab">
            Explorer
          </NavLink>
          <NavLink to={`/a/${snapshotId}/findings${keep}`} className="analysis-tab">
            Findings
            {total !== undefined ? (
              <span className="count mono num">{total}</span>
            ) : (
              // The badge's room, so the tab does not grow when the count arrives.
              <span className="count mono num" style={{ color: "transparent" }} aria-hidden="true">
                00
              </span>
            )}
          </NavLink>
        </nav>
        <button
          ref={askButtonRef}
          type="button"
          className="button button-secondary button-small analysis-ask"
          aria-pressed={askOpen}
          aria-controls="ask-drawer"
          onClick={() => setParams({ ask: askOpen ? null : "1" })}
        >
          Ask
        </button>
      </header>
      {limitNotice ? <p className="analysis-notice caption">{limitNotice}</p> : null}
      {/* data-ask lets a file or finding panel overlay the main column while Ask is open on
          screens too narrow for three docked columns (styles.css). */}
      <div
        className="analysis-body"
        data-ask={askOpen || undefined}
        data-tabbed={tabbed || undefined}
        data-right-tab={tabbed ? rightTab : undefined}
      >
        <div className="analysis-main">
          {status.error && !status.data ? (
            <div className="canvas-message" role="alert">
              <p>{status.error.message}</p>
              <button className="button button-secondary" onClick={() => status.refetch()}>
                Try again
              </button>
            </div>
          ) : (
            <Outlet context={{ snapshotId, tabbed, status: status.data } satisfies AnalysisContext} />
          )}
        </div>
        {tabbed ? (
          <div className="right-tabs" role="tablist" aria-label="Side panels">
            {(
              [
                ["panel", panelKind],
                ["ask", "Ask"],
              ] as const
            ).map(([tab, label]) => (
              <button
                key={tab}
                type="button"
                role="tab"
                className="tab"
                aria-selected={rightTab === tab}
                onClick={() => setRightTab(tab)}
              >
                {label}
              </button>
            ))}
          </div>
        ) : null}
        {askOpen && status.data ? (
          <AskDrawer
            hidden={tabbed && rightTab !== "ask"}
            snapshotId={snapshotId}
            status={status.data}
            onClose={() => {
              setParams({ ask: null, askq: null, askfile: null, askpath: null });
              askButtonRef.current?.focus(); // focus goes back to what opened the drawer
            }}
          />
        ) : null}
      </div>
    </div>
  );
}
