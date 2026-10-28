import { useMutation, useQueries } from "@tanstack/react-query";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { ApiError, getStatus, isFinished, repoName, submitRepo, type SnapshotStatus } from "../api";
import { Icon } from "../components/Icon";
import { age, loadRecent, rememberAnalysis } from "../recent";

// Same shape the API accepts (app/ingest/clone.py normalize_repo_url).
const GITHUB_URL = /^https:\/\/github\.com\/[A-Za-z0-9-]+\/[A-Za-z0-9._-]+?(\.git)?\/?$/;

// Repos ingested and checked end to end (PROGRESS.md), pinned to the analysed commit so a click
// always reopens that finished analysis and never starts a new one when the repo moves on.
const EXAMPLES = [
  { url: "https://github.com/pallets/itsdangerous", commit: "672971d66a2ef9f85151e53283113f33d642dabd" },
  { url: "https://github.com/expressjs/express", commit: "1c6f1b0fe4000977b9a7b4f34097e4d527dd9824" },
  { url: "https://github.com/sindresorhus/ky", commit: "3541888878c4d303a8bc2ad61815f4e048f55a5d" },
  // Intentionally vulnerable Django app; used for the real-world precision eval.
  { url: "https://github.com/adeyosemanputra/pygoat", commit: "46fef968f3f44d1191363baf936aaa3335dc5c6d" },
];

function validate(value: string): string | null {
  const url = value.trim();
  if (!url) return "Paste a repository URL.";
  if (!url.startsWith("https://github.com/")) return "Only public GitHub repositories are supported.";
  if (!GITHUB_URL.test(url)) return "Use the form https://github.com/owner/repo.";
  return null;
}

export function Home() {
  const navigate = useNavigate();
  const location = useLocation();
  const inputRef = useRef<HTMLInputElement>(null);
  const messageId = useId();
  const [url, setUrl] = useState("");
  const [touched, setTouched] = useState(false);

  // "New analysis" in the top bar lands here with the field focused.
  useEffect(() => {
    if ((location.state as { focusUrl?: boolean } | null)?.focusUrl) inputRef.current?.focus();
  }, [location.key, location.state]);

  const submit = useMutation({
    mutationFn: submitRepo,
    onSuccess: (result, submitted) => {
      rememberAnalysis({
        snapshotId: result.snapshot_id,
        url: submitted.url,
        commitSha: result.commit_sha,
        submittedAt: Date.now(),
      });
      navigate(`/a/${result.snapshot_id}`);
    },
  });

  const formatError = validate(url);
  const showFormatError = touched && formatError !== null;
  const serverError = submit.isError ? submit.error.message : null;
  const message = showFormatError ? formatError : serverError;

  function start(target: string, commit?: string) {
    setUrl(target);
    setTouched(true);
    if (validate(target) === null) submit.mutate({ url: target.trim(), commit });
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (formatError) {
      setTouched(true);
      inputRef.current?.focus();
      return;
    }
    start(url);
  }

  return (
    <div className="page">
      <h1 className="page-title">Understand a codebase before you read it.</h1>
      <p className="lede">
        RepoLens maps how the files of a public GitHub repository import and call each other.
        Deep analysis for Python and JavaScript/TypeScript.
      </p>

      <form onSubmit={onSubmit} noValidate aria-busy={submit.isPending}>
        <label htmlFor="repo-url" className="visually-hidden">
          GitHub repository URL
        </label>
        <div className="submit-row">
          <div className="field">
            <input
              ref={inputRef}
              id="repo-url"
              className="input"
              type="url"
              inputMode="url"
              autoComplete="off"
              spellCheck={false}
              placeholder="https://github.com/owner/repo"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                if (submit.isError) submit.reset();
              }}
              onBlur={() => url && setTouched(true)}
              aria-invalid={message ? true : undefined}
              aria-describedby={messageId}
              disabled={submit.isPending}
            />
            {!formatError && !serverError && (
              <span className="field-icon">
                <Icon name="check" label="Valid GitHub URL" />
              </span>
            )}
          </div>
          <button className="button" type="submit" disabled={submit.isPending}>
            {submit.isPending ? <Icon name="spinner" /> : null}
            {submit.isPending ? "Starting" : "Analyze"}
          </button>
        </div>
        <p
          id={messageId}
          className="field-message"
          data-tone={message ? "error" : undefined}
          role={message ? "alert" : undefined}
        >
          {message ?? "Public GitHub repositories only · up to 2,000 files · files over 1 MB are skipped"}
        </p>
      </form>

      <div className="examples">
        <span className="examples-label">Try an example</span>
        {EXAMPLES.map((example) => (
          <button
            key={example.url}
            type="button"
            className="chip"
            onClick={() => start(example.url, example.commit)}
            disabled={submit.isPending}
          >
            {repoName(example.url)}
          </button>
        ))}
      </div>

      <RecentAnalyses />
    </div>
  );
}

function RecentAnalyses() {
  const [recent] = useState(loadRecent);
  const statuses = useQueries({
    queries: recent.map((r) => ({
      queryKey: ["status", r.snapshotId],
      queryFn: () => getStatus(r.snapshotId),
      // Poll only while an analysis is running; one that failed to load (e.g. removed from the
      // server) is not polled again.
      refetchInterval: (query: { state: { data?: SnapshotStatus; status: string } }) =>
        query.state.status === "error" || isFinished(query.state.data?.status) ? false : 3000,
    })),
  });

  if (recent.length === 0) return null;

  return (
    <section className="section" aria-labelledby="recent-title">
      <h2 id="recent-title" className="section-title">
        Recent analyses <span className="caption">this browser</span>
      </h2>
      <ul className="list">
        {recent.map((r, i) => {
          const { data, error } = statuses[i];
          return (
            <li key={r.snapshotId} className="list-row">
              <Link to={`/a/${r.snapshotId}`} className="list-link">
                <span className="list-name mono">{repoName(r.url)}</span>
                <span className="list-meta">
                  <StatusLabel
                    status={data?.status}
                    missing={Boolean(error)}
                    removed={error instanceof ApiError && error.status === 404}
                  />
                  <span aria-hidden="true">·</span>
                  <span className="mono num">{r.commitSha.slice(0, 7)}</span>
                  <span aria-hidden="true">·</span>
                  <span>{age(r.submittedAt)}</span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function StatusLabel({
  status,
  missing,
  removed,
}: {
  status?: SnapshotStatus["status"];
  missing: boolean;
  removed: boolean;
}) {
  if (removed) return <span className="status">Removed</span>;
  if (missing) return <span className="status">Unavailable</span>;
  if (!status) return <span className="skeleton" style={{ width: 56 }} aria-label="Loading status" />;
  if (status === "done") {
    return (
      <span className="status" data-state="done">
        <Icon name="check" size={14} />
        Ready
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="status" data-state="failed">
        <Icon name="x" size={14} />
        Failed
      </span>
    );
  }
  return (
    <span className="status">
      <Icon name="spinner" size={14} />
      Analyzing
    </span>
  );
}
