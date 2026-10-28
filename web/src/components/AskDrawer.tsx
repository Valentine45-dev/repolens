import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  askQuestion,
  getFindings,
  getGraph,
  repoName,
  type Answer,
  type GraphResult,
  type SnapshotStatus,
} from "../api";
import { degrees } from "../graphModel";
import { exploreHref, useSetParams } from "../links";
import { Icon } from "./Icon";
import { Markdown } from "./Markdown";

const MAX_CHARS = 1000; // the API's limit
const UNAVAILABLE = "AI answers are unavailable right now. Graph questions still work.";

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
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const { features } = status;

  // Block bodies: an effect may return only a cleanup function, and newer browsers make
  // scrollIntoView return a Promise.
  useEffect(() => {
    saveTurns(snapshotId, turns);
  }, [snapshotId, turns]);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
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

  return (
    <aside id="ask-drawer" className="drawer" aria-labelledby={titleId}>
      <header className="panel-header">
        <div className="panel-heading">
          <h2 id={titleId} className="panel-title">
            Ask about <span className="mono">{repoName(status.url)}</span>
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
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close Ask (Esc)">
          <Icon name="x" />
        </button>
      </header>

      <div className="drawer-body">
        {!features.ai ? (
          <p className="note drawer-notice" data-tone="warning">
            {UNAVAILABLE}
          </p>
        ) : !features.ask && features.ask_reason ? (
          <p className="note drawer-notice" data-tone="warning">
            {features.ask_reason} Graph questions still work.
          </p>
        ) : null}

        {turns.length === 0 ? (
          <Suggestions snapshotId={snapshotId} aiReady={features.ai && features.ask} onPick={send} />
        ) : (
          <ol className="conversation" aria-label="Conversation">
            {turns.map((turn) => (
              <li key={turn.id} className="turn">
                <p className="turn-question">
                  <span className="turn-who">You</span> {turn.question}
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
                    <p className="note" data-tone="warning" role="alert">
                      {turn.error}
                    </p>
                  ) : (
                    <p className="caption thinking">
                      <Icon name="spinner" size={14} /> Looking through the code… this can take
                      up to 40 seconds.
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}
        <div ref={endRef} />
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
            aria-label="Send question"
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
      <p className="caption">Suggested</p>
      <ul>
        {questions.map((q) => (
          <li key={q.text}>
            <button type="button" className="suggestion" onClick={() => onPick(q.text)}>
              {q.text}
              <span className="caption">{q.kind === "graph" ? "From the graph" : "AI answer"}</span>
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

function shortName(r: GraphResult): string {
  if (r.kind === "module") return r.path ?? r.qualified_name;
  if (r.kind === "external") return r.qualified_name;
  return r.qualified_name.split(":").pop() ?? r.name;
}

/** The question again with the ambiguous target swapped for the chosen candidate. */
function reask(question: string, query: string, r: GraphResult): string {
  const pick = r.kind === "module" ? (r.path ?? r.qualified_name) : r.qualified_name;
  const at = question.toLowerCase().indexOf(query.toLowerCase());
  return at === -1 ? question : question.slice(0, at) + pick + question.slice(at + query.length);
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
  const graph = answer.kind === "graph";
  const degraded = ["unavailable", "cap_reached", "no_context", "refused"].includes(answer.status);
  return (
    <div className="answer" data-status={answer.status}>
      <p className="answer-meta">
        <span className="turn-who">RepoLens</span>
        <span className="answer-kind" data-kind={answer.kind}>
          {graph ? "From the graph" : "AI answer"}
        </span>
      </p>

      {degraded ? (
        <p className="note" data-tone="warning">
          {answer.answer}
        </p>
      ) : graph ? (
        <p>{answer.answer}</p>
      ) : (
        <Markdown text={answer.answer} />
      )}

      {answer.status === "unverified" ? (
        <p className="note" data-tone="warning">
          None of the sources this answer cited could be verified, so it is shown without sources.
          Check the code before relying on it.
        </p>
      ) : null}

      {answer.status === "ambiguous" ? (
        <p className="caption">Pick one to ask the same question about it.</p>
      ) : null}
      {graph && answer.results.length ? (
        <ul className="results">
          {answer.results.map((r) => {
            const href = resultHref(snapshotId, r);
            return (
              <li key={`${r.node_id}-${r.edge ?? ""}`}>
                {answer.status === "ambiguous" && answer.query ? (
                  <button
                    type="button"
                    className="row-button mono"
                    disabled={busy}
                    onClick={() => onAsk(reask(question, answer.query!, r))}
                  >
                    {shortName(r)}
                  </button>
                ) : href ? (
                  <Link to={href} className="row-button mono">
                    {shortName(r)}
                  </Link>
                ) : (
                  <span className="mono">{shortName(r)}</span>
                )}
                {r.kind !== "module" && r.path ? <span className="caption mono"> {r.path}</span> : null}
                {r.edge ? <span className="caption"> · {r.edge}</span> : null}
                {r.kind === "external" ? <span className="tag">external</span> : null}
                {r.in_test ? <span className="tag">test</span> : null}
              </li>
            );
          })}
        </ul>
      ) : null}

      {answer.citations.length ? (
        <div className="sources">
          <p className="caption">Sources</p>
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
                  {c.path}:{c.start_line}
                  {c.end_line !== c.start_line ? `-${c.end_line}` : ""}
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
