import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  askQuestion,
  getFindings,
  getGraph,
  repoName,
  retrySearch,
  type Answer,
  type GraphResult,
  type SnapshotStatus,
} from "../api";
import { degrees } from "../graphModel";
import { exploreHref, useSetParams } from "../links";
import { Icon } from "./Icon";
import { Markdown } from "./Markdown";
import { PathText } from "./PathText";

const MAX_CHARS = 1000; // the API's limit
const SHOWN_RESULTS = 5; // graph results before "Show all N"
const WIDE_KEY = "repolens.ask.wide";

interface Turn {
  id: string;
  question: string;
  answer?: Answer;
  error?: string;
}

// The conversation is per snapshot and lives in this browser tab only (spec 5.5). Each question
// is still answered on its own: no earlier turns are sent to the server.
function storageKey(snapshotId: number) {
  return `repolens.ask.${snapshotId}`;
}

function loadTurns(snapshotId: number): Turn[] {
  try {
    const raw = sessionStorage.getItem(storageKey(snapshotId));
    const turns = raw ? (JSON.parse(raw) as Turn[]) : [];
    return turns.filter((t) => t.answer || t.error); // a reload drops an unanswered question
  } catch {
    return [];
  }
}

function saveTurns(snapshotId: number, turns: Turn[]) {
  try {
    if (turns.length) sessionStorage.setItem(storageKey(snapshotId), JSON.stringify(turns));
    else sessionStorage.removeItem(storageKey(snapshotId));
  } catch {
    // Storage full or blocked: the conversation just does not survive a reload.
  }
}

// The wide drawer is a per-viewer convenience, remembered in this browser when storage works.
function loadWide(): boolean {
  try {
    return localStorage.getItem(WIDE_KEY) === "1";
  } catch {
    return false;
  }
}

function saveWide(wide: boolean) {
  try {
    if (wide) localStorage.setItem(WIDE_KEY, "1");
    else localStorage.removeItem(WIDE_KEY);
  } catch {
    // Not remembered; the toggle still works for this visit.
  }
}

export function AskDrawer({
  snapshotId,
  status,
  onClose,
}: {
  snapshotId: number;
  status: SnapshotStatus;
  onClose: () => void;
}) {
  const titleId = useId();
  const inputId = useId();
  const [params] = useSearchParams();
  const setParams = useSetParams();
  const [turns, setTurns] = useState<Turn[]>(() => loadTurns(snapshotId));
  const [draft, setDraft] = useState("");
  const [wide, setWide] = useState(loadWide);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const lastTurnRef = useRef<HTMLLIElement>(null);
  const { features } = status;
  const name = repoName(status.url);

  // Block bodies: an effect may return only a cleanup function, and newer browsers make
  // scrollIntoView return a Promise.
  useEffect(() => {
    saveTurns(snapshotId, turns);
  }, [snapshotId, turns]);
  // Show the newest turn from its question down, so its "AI answer" / "From the graph" label is
  // read first; scrolling to the end would land a long answer mid-way.
  useEffect(() => {
    lastTurnRef.current?.scrollIntoView({ block: "start" });
  }, [turns]);

  // "Ask about this" (node panel) arrives as ?askq=...: prefill once, then drop it from the URL.
  const prefill = params.get("askq");
  useEffect(() => {
    if (prefill === null) return;
    setDraft(prefill);
    setParams({ askq: null });
    requestAnimationFrame(() => {
      const el = inputRef.current;
      if (el) {
        el.focus();
        el.setSelectionRange(el.value.length, el.value.length);
      }
    });
  }, [prefill, setParams]);
  // Focus the input when the drawer opens (the prefill effect focuses it in that case).
  useEffect(() => {
    if (prefill === null) inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && document.activeElement?.closest("#ask-drawer")) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const ask = useMutation({
    mutationFn: ({ question }: { id: string; question: string }) => askQuestion(snapshotId, question),
    onSuccess: (answer, { id }) =>
      setTurns((all) => all.map((t) => (t.id === id ? { ...t, answer } : t))),
    onError: (error, { id }) =>
      setTurns((all) => all.map((t) => (t.id === id ? { ...t, error: error.message } : t))),
  });

  function send(question: string) {
    const text = question.trim();
    if (!text || ask.isPending) return;
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setTurns((all) => [...all, { id, question: text }]);
    setDraft("");
    ask.mutate({ id, question: text });
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    send(draft);
  }

  function toggleWide() {
    setWide((w) => {
      saveWide(!w);
      return !w;
    });
  }

  return (
    <aside id="ask-drawer" className="drawer" data-wide={wide || undefined} aria-labelledby={titleId}>
      <header className="panel-header drawer-header">
        <div className="panel-heading drawer-heading">
          <h2 id={titleId} className="panel-title drawer-title">
            <span className="drawer-title-lead">Ask about</span>{" "}
            <span className="mono drawer-repo" title={name}>
              {name}
            </span>
          </h2>
          <p className="caption">Each question is answered on its own, from this commit.</p>
        </div>
        {turns.length ? (
          <button
            type="button"
            className="button button-secondary button-small"
            onClick={() => setTurns([])}
            disabled={ask.isPending}
          >
            Clear
          </button>
        ) : null}
        <button
          type="button"
          className="icon-button drawer-size"
          onClick={toggleWide}
          aria-pressed={wide}
          aria-label={wide ? "Make the Ask panel narrower" : "Make the Ask panel wider"}
          title={wide ? "Narrower" : "Wider"}
        >
          <Icon name={wide ? "collapse" : "expand"} />
        </button>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close Ask (Esc)">
          <Icon name="x" />
        </button>
      </header>

      <div className="drawer-body">
        <DrawerBanner snapshotId={snapshotId} status={status} />

        {turns.length === 0 ? (
          <Suggestions snapshotId={snapshotId} aiReady={features.ai && features.ask} onPick={send} />
        ) : (
          <ol className="conversation" aria-label="Conversation">
            {turns.map((turn, i) => (
              <li key={turn.id} className="turn" ref={i === turns.length - 1 ? lastTurnRef : undefined}>
                <p className="turn-question">
                  <span className="visually-hidden">You asked: </span>
                  {turn.question}
                </p>
                <div className="turn-answer" aria-live="polite">
                  {turn.answer ? (
                    <AnswerView
                      snapshotId={snapshotId}
                      question={turn.question}
                      answer={turn.answer}
                      onAsk={send}
                      busy={ask.isPending}
                    />
                  ) : turn.error ? (
                    <p className="turn-note" role="alert">
                      <Icon name="x" size={14} /> {turn.error}
                    </p>
                  ) : (
                    <p className="turn-note thinking">
                      <Icon name="spinner" size={14} /> Looking through the code… this can take
                      up to 40 seconds.
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>

      <form className="ask-form" onSubmit={submit}>
        <label htmlFor={inputId} className="visually-hidden">
          Question
        </label>
        <textarea
          id={inputId}
          ref={inputRef}
          className="input ask-input"
          rows={2}
          maxLength={MAX_CHARS}
          value={draft}
          placeholder="Ask a question about this codebase…"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              send(draft);
            }
          }}
        />
        <div className="ask-form-row">
          <span className="caption num">
            {draft.length > MAX_CHARS - 100 ? `${draft.length}/${MAX_CHARS}` : "Enter to send"}
          </span>
          <button
            type="submit"
            className="button button-small"
            disabled={!draft.trim() || ask.isPending}
          >
            {ask.isPending ? <Icon name="spinner" size={14} /> : <Icon name="send" size={14} />}
            Ask
          </button>
        </div>
      </form>
    </aside>
  );
}

/** Suggested questions built from this snapshot's data (spec 5.5): the most depended-on files
 * and a file with findings. Nothing generic, and AI questions only when AI can answer. */
function Suggestions({
  snapshotId,
  aiReady,
  onPick,
}: {
  snapshotId: number;
  aiReady: boolean;
  onPick: (question: string) => void;
}) {
  const graph = useQuery({
    queryKey: ["graph", snapshotId, false, false],
    queryFn: ({ signal }) => getGraph(snapshotId, { showTests: false, showGuesses: false }, signal),
    staleTime: Infinity,
  });
  const findings = useQuery({
    queryKey: ["findings", snapshotId, { in_test: false, limit: 5 }],
    queryFn: ({ signal }) => getFindings(snapshotId, { in_test: false, limit: 5 }, signal),
    staleTime: Infinity,
  });

  const questions = useMemo(() => {
    const out: { text: string; kind: "graph" | "ai" }[] = [];
    if (graph.data) {
      const deg = degrees(graph.data);
      const hubs = [...graph.data.nodes]
        .filter((n) => (deg.get(n.id)?.usedBy ?? 0) > 0)
        .sort((a, b) => (deg.get(b.id)?.usedBy ?? 0) - (deg.get(a.id)?.usedBy ?? 0));
      if (hubs[0]) out.push({ text: `What depends on ${hubs[0].path}?`, kind: "graph" });
      if (aiReady && hubs[0]) out.push({ text: `What does ${hubs[0].path} do?`, kind: "ai" });
      if (hubs[1]) out.push({ text: `Which files import ${hubs[1].path}?`, kind: "graph" });
    }
    const withFinding = findings.data?.items.find((f) => f.symbol) ?? findings.data?.items[0];
    if (withFinding) {
      out.push(
        aiReady
          ? { text: `What does the code around ${withFinding.path}:${withFinding.line} do?`, kind: "ai" }
          : { text: `What does ${withFinding.path} import?`, kind: "graph" },
      );
    }
    return out;
  }, [graph.data, findings.data, aiReady]);

  if (!questions.length) {
    return (
      <p className="caption drawer-hint">
        Ask how something works, or ask the graph: “Which files import <span className="mono">path</span>?”,
        “Who calls <span className="mono">name</span>?”, “What does <span className="mono">path</span> depend on?”
      </p>
    );
  }
  return (
    <div className="suggestions">
      <h3 className="drawer-section-title">Suggested questions</h3>
      <ul>
        {questions.map((q) => (
          <li key={q.text}>
            <button type="button" className="suggestion" onClick={() => onPick(q.text)}>
              <span className="suggestion-text">{q.text}</span>
              <span className="suggestion-kind caption">
                <Icon name={q.kind === "graph" ? "graph" : "spark"} size={14} />
                {q.kind === "graph" ? "From the graph" : "AI answer"}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function resultHref(snapshotId: number, r: GraphResult): string | null {
  if (r.file_id === null) return null;
  const lines =
    r.kind !== "module" && r.start_line !== null
      ? { start: r.start_line, end: r.end_line ?? r.start_line }
      : null;
  return exploreHref(snapshotId, { fileId: r.file_id, lines, tests: r.in_test, ask: true });
}

/** Python's dotted module for a file, as the parser builds it (backend parse.module_name). */
function pythonModule(path: string): string {
  const parts = path.replace(/\.pyi?$/, "").split("/");
  if (parts[parts.length - 1] === "__init__" && parts.length > 1) parts.pop();
  return parts.join(".");
}

/** A symbol's name without its module: the file path is shown under it. JS names are
 * `module:Name.method`; Python names are `pkg.mod.Name.method`. */
function shortName(r: GraphResult): string {
  if (r.kind === "module") return r.path ?? r.qualified_name;
  if (r.kind === "external") return r.qualified_name;
  if (r.qualified_name.includes(":")) return r.qualified_name.split(":").pop() ?? r.name;
  const mod = r.path ? pythonModule(r.path) : "";
  return mod && r.qualified_name.startsWith(`${mod}.`)
    ? r.qualified_name.slice(mod.length + 1)
    : r.qualified_name;
}

const lineCount = new Intl.NumberFormat("en-US");

/** One line for a failed AI question; the reason that applies to all of them is the banner. */
function failedLine(answer: Answer): string {
  return answer.status === "unavailable" ? "No AI answer for this question." : answer.answer;
}

/** A file result spans its whole file; a function or class its own lines. Packages have none. */
function linesOf(r: GraphResult): string | null {
  if (r.start_line === null || r.end_line === null) return null;
  const n = r.end_line - r.start_line + 1;
  return `${lineCount.format(n)} ${n === 1 ? "line" : "lines"}`;
}

function kindIcon(r: GraphResult): "file" | "package" | "symbol" {
  if (r.kind === "module") return "file";
  if (r.kind === "external" || r.kind === "unresolved") return "package";
  return "symbol";
}

/** The question again with the ambiguous target swapped for the chosen candidate. */
function reask(question: string, query: string, r: GraphResult): string {
  const pick = r.kind === "module" ? (r.path ?? r.qualified_name) : r.qualified_name;
  const at = question.toLowerCase().indexOf(query.toLowerCase());
  return at === -1 ? question : question.slice(0, at) + pick + question.slice(at + query.length);
}

function ResultRow({
  snapshotId,
  question,
  answer,
  r,
  onAsk,
  busy,
}: {
  snapshotId: number;
  question: string;
  answer: Answer;
  r: GraphResult;
  onAsk: (question: string) => void;
  busy: boolean;
}) {
  const body = (
    <>
      <Icon name={kindIcon(r)} size={14} />
      <span className="result-name">
        <span className="mono result-primary">
          <PathText path={shortName(r)} sep={r.kind === "module" ? "/" : "."} />
        </span>
        {r.kind !== "module" && r.path ? (
          <span className="mono result-path">
            <PathText path={r.path} />
          </span>
        ) : null}
      </span>
      <span className="result-meta">
        {r.edge ? <span className="caption">{r.edge}</span> : null}
        {r.kind === "external" ? <span className="tag">external</span> : null}
        {r.kind === "unresolved" ? (
          <span className="tag" data-kind="unresolved">
            unresolved
          </span>
        ) : null}
        {r.in_test ? <span className="tag">test</span> : null}
        {linesOf(r) ? <span className="caption mono num">{linesOf(r)}</span> : null}
      </span>
    </>
  );
  if (answer.status === "ambiguous" && answer.query) {
    return (
      <button
        type="button"
        className="result-row"
        disabled={busy}
        onClick={() => onAsk(reask(question, answer.query!, r))}
      >
        {body}
      </button>
    );
  }
  const href = resultHref(snapshotId, r);
  return href ? (
    <Link to={href} className="result-row">
      {body}
    </Link>
  ) : (
    <span className="result-row" data-static>
      {body}
    </span>
  );
}

function AnswerView({
  snapshotId,
  question,
  answer,
  onAsk,
  busy,
}: {
  snapshotId: number;
  question: string;
  answer: Answer;
  onAsk: (question: string) => void;
  busy: boolean;
}) {
  const [showAll, setShowAll] = useState(false);
  const graph = answer.kind === "graph";

  // A failed AI question gets one line; the reason that applies to every question (no model,
  // search not ready) is the banner at the top of the drawer.
  if (["unavailable", "cap_reached", "no_context", "refused"].includes(answer.status)) {
    return (
      <p className="turn-note" data-status={answer.status}>
        <Icon name="x" size={14} /> {failedLine(answer)}
      </p>
    );
  }

  const results = showAll ? answer.results : answer.results.slice(0, SHOWN_RESULTS);
  const hidden = answer.results.length - results.length;
  return (
    <div className="answer" data-status={answer.status}>
      <h3 className="answer-head">
        <Icon name={graph ? "graph" : "spark"} />
        {graph ? "From the graph" : "AI answer"}
      </h3>

      {graph ? <p>{answer.answer}</p> : <Markdown text={answer.answer} />}

      {answer.status === "unverified" ? (
        <p className="turn-note">
          <Icon name="x" size={14} /> None of the sources this answer cited could be verified, so it
          is shown without sources. Check the code before relying on it.
        </p>
      ) : null}

      {answer.status === "ambiguous" ? (
        <p className="caption">Pick one to ask the same question about it.</p>
      ) : null}
      {graph && answer.results.length ? (
        <>
          <ul className="result-rows">
            {results.map((r) => (
              <li key={`${r.node_id}-${r.edge ?? ""}`}>
                <ResultRow
                  snapshotId={snapshotId}
                  question={question}
                  answer={answer}
                  r={r}
                  onAsk={onAsk}
                  busy={busy}
                />
              </li>
            ))}
          </ul>
          {hidden > 0 ? (
            <button type="button" className="link-button" onClick={() => setShowAll(true)}>
              {/* "more", not "all": a capped answer lists only the first 50 (its text says so) */}
              Show {hidden} more
            </button>
          ) : null}
        </>
      ) : null}

      {answer.citations.length ? (
        <div className="sources">
          <h4 className="drawer-section-title">Relevant source files</h4>
          <ul className="citation-list">
            {answer.citations.map((c) => (
              <li key={`${c.path}:${c.start_line}-${c.end_line}`}>
                <Link
                  className="citation"
                  to={exploreHref(snapshotId, {
                    fileId: c.file_id,
                    lines: { start: c.start_line, end: c.end_line },
                    tests: c.in_test,
                    ask: true,
                  })}
                >
                  <Icon name="file" size={14} />
                  <span>
                    <PathText path={c.path} />:{c.start_line}
                    {c.end_line !== c.start_line ? `-${c.end_line}` : ""}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {answer.dropped > 0 && answer.status !== "unverified" ? (
        <p className="caption">
          {answer.dropped === 1
            ? "1 source could not be verified and was removed."
            : `${answer.dropped} sources could not be verified and were removed.`}
        </p>
      ) : null}
      {answer.retrieval?.used_test_code ? (
        <p className="caption">Based on test or example code: no other code matched.</p>
      ) : null}
    </div>
  );
}

const chunkCount = new Intl.NumberFormat("en-US");

// The one place that says why AI answers are off or limited (spec 12.1: say what happened and
// what to do next), with "Retry preparing search" when that is the fix. Graph questions always
// work, so the banner says so; each failed AI turn below then needs only one line.
function DrawerBanner({ snapshotId, status }: { snapshotId: number; status: SnapshotStatus }) {
  const queryClient = useQueryClient();
  const { features } = status;
  const retry = useMutation({
    mutationFn: () => retrySearch(snapshotId),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["status", snapshotId] }),
  });

  let title: string | null = null;
  let body: string | null = null;
  let busy = false;
  if (!features.ai) {
    title = "AI answers are unavailable right now.";
    body = "Graph questions still work: ask which files import, call or depend on something.";
  } else if (features.search === "embedding") {
    const p = features.search_progress;
    title = "Preparing search for questions…";
    body =
      (p ? `${chunkCount.format(p.done)} / ${chunkCount.format(p.total)} chunks. ` : "") +
      "Graph questions work now.";
    busy = true;
  } else if (features.retry_search) {
    title = features.ask ? "Test code is not searchable." : "AI answers are unavailable for this analysis.";
    body =
      (features.search_error ?? features.ask_reason ?? "") +
      (features.ask ? " AI answers still use the rest of the code." : " Graph questions still work.");
  } else if (!features.ask && features.ask_reason) {
    title = "AI answers are unavailable for this analysis.";
    body = `${features.ask_reason} Graph questions still work.`;
  }
  if (!title) return null;

  return (
    <div className="callout drawer-banner" role="status" aria-live="polite" aria-busy={busy || undefined}>
      <p className="callout-title">
        {busy ? <Icon name="spinner" size={14} /> : null}
        {title}
      </p>
      <p>{body}</p>
      {features.retry_search && features.ai ? (
        <div className="callout-actions">
          <button
            type="button"
            className="button button-secondary button-small"
            onClick={() => retry.mutate()}
            disabled={retry.isPending}
          >
            {retry.isPending ? <Icon name="spinner" size={14} /> : null}
            {retry.isPending ? "Starting" : "Retry preparing search"}
          </button>
          {retry.isError ? <p className="caption">{retry.error.message}</p> : null}
        </div>
      ) : null}
    </div>
  );
}
