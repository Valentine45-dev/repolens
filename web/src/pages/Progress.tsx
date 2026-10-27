import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError, getStatus, isFinished, repoName, submitRepo, type SnapshotStatus } from "../api";
import { Icon } from "../components/Icon";
import { rememberAnalysis } from "../recent";

// The pipeline's real stages, in order (app/ingest/pipeline.py run_job). Detectors and search
// do not exist yet, so they are not listed.
const STAGES = [
  { id: "fetch", label: "Cloning repository" },
  { id: "discover", label: "Finding source files" },
  { id: "parse", label: "Parsing code" },
  { id: "edges", label: "Resolving imports and calls" },
] as const;

type RowState = "pending" | "active" | "done" | "failed";

function rowStates(status: SnapshotStatus): RowState[] {
  if (status.status === "done") return STAGES.map(() => "done");
  const current = STAGES.findIndex((s) => s.id === status.stage);
  return STAGES.map((_, i) => {
    if (current === -1 || i > current) return "pending"; // queued: nothing started yet
    if (i < current) return "done";
    return status.status === "failed" ? "failed" : "active";
  });
}

// Announced with aria-live, so it changes only when the stage does (the percent lives in the
// ledger row, where a screen reader does not re-read it every second).
function statusLine(status: SnapshotStatus): string {
  switch (status.status) {
    case "queued":
      return "Waiting to start…";
    case "running": {
      const stage = STAGES.find((s) => s.id === status.stage);
      return stage ? `Analyzing: ${stage.label.toLowerCase()}…` : "Analyzing…";
    }
    case "done":
      return "Analysis complete.";
    case "failed":
      return "Analysis failed.";
  }
}

export function Progress() {
  const { id } = useParams();
  const snapshotId = Number(id);
  const valid = Number.isInteger(snapshotId) && snapshotId > 0;

  const query = useQuery({
    queryKey: ["status", snapshotId],
    queryFn: () => getStatus(snapshotId),
    enabled: valid,
    refetchInterval: (q) => (q.state.error || isFinished(q.state.data?.status) ? false : 1000),
  });

  if (!valid || (query.error instanceof ApiError && query.error.status === 404)) {
    return (
      <div className="page">
        <h1 className="page-title">No analysis with this id.</h1>
        <p className="lede">
          It may have been removed. <Link to="/">Start a new analysis</Link>
        </p>
      </div>
    );
  }

  if (query.error) {
    return (
      <div className="page">
        <div className="callout" data-tone="error" role="alert">
          <p className="callout-title">Could not load this analysis.</p>
          <p>{query.error.message}</p>
          <div className="callout-actions">
            <button className="button button-secondary" onClick={() => query.refetch()}>
              Try again
            </button>
          </div>
        </div>
      </div>
    );
  }

  const status = query.data;
  if (!status) return <ProgressSkeleton />;

  const states = rowStates(status);
  return (
    <div className="page">
      <h1 className="repo-heading">
        <a href={status.url} target="_blank" rel="noreferrer">
          {repoName(status.url)}
        </a>{" "}
        <span className="repo-sha">@ {status.commit_sha.slice(0, 7)}</span>
      </h1>
      <p className="status-line" aria-live="polite">
        {statusLine(status)}
      </p>

      <ol className="ledger" aria-label="Analysis stages">
        {STAGES.map((stage, i) => (
          <li key={stage.id} className="ledger-row" data-state={states[i]}>
            <span className="ledger-icon">
              <StageIcon state={states[i]} />
            </span>
            <span>
              {stage.label}
              <span className="visually-hidden">: {states[i]}</span>
            </span>
            <span className="ledger-value">
              {states[i] === "active" ? `${status.percent}%` : null}
              {states[i] === "done" ? "done" : null}
              {states[i] === "failed" ? "failed" : null}
            </span>
          </li>
        ))}
      </ol>

      {status.status === "failed" ? (
        <FailedCallout status={status} />
      ) : status.status !== "done" ? (
        <p className="note">
          You can leave this page. The analysis keeps running; this address brings you back to it.
        </p>
      ) : null}
    </div>
  );
}

function StageIcon({ state }: { state: RowState }) {
  if (state === "done") return <Icon name="check" />;
  if (state === "failed") return <Icon name="x" />;
  if (state === "active") return <Icon name="spinner" />;
  return <Icon name="circle" />;
}

function FailedCallout({ status }: { status: SnapshotStatus }) {
  const navigate = useNavigate();
  const retry = useMutation({
    mutationFn: () => submitRepo(status.url),
    onSuccess: (result) => {
      rememberAnalysis({
        snapshotId: result.snapshot_id,
        url: status.url,
        commitSha: result.commit_sha,
        submittedAt: Date.now(),
      });
      navigate(`/a/${result.snapshot_id}`, { replace: true });
    },
  });
  const stage = STAGES.find((s) => s.id === status.stage)?.label.toLowerCase() ?? "the analysis";

  return (
    <div className="callout" data-tone="error" role="alert">
      <p className="callout-title">Stopped while {stage}.</p>
      <p>{status.error ?? "The server did not give a reason."}</p>
      <p className="caption">
        Retrying starts a new run of the same commit. If it fails again, try a smaller repository.
      </p>
      <div className="callout-actions">
        <button
          className="button button-secondary"
          onClick={() => retry.mutate()}
          disabled={retry.isPending}
        >
          {retry.isPending ? <Icon name="spinner" /> : null}
          Retry analysis
        </button>
      </div>
      {retry.isError ? <p className="field-message" data-tone="error">{retry.error.message}</p> : null}
    </div>
  );
}

function ProgressSkeleton() {
  return (
    <div className="page" aria-busy="true" aria-label="Loading analysis">
      <div className="skeleton" style={{ width: 280, height: 24 }} />
      <div className="skeleton" style={{ width: 160, marginTop: 12 }} />
      <ol className="ledger" aria-hidden="true">
        {STAGES.map((stage) => (
          <li key={stage.id} className="ledger-row">
            <span />
            <span className="skeleton" style={{ width: 180 }} />
            <span />
          </li>
        ))}
      </ol>
    </div>
  );
}
