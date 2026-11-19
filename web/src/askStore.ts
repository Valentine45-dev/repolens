// The Ask conversation of each analysis, kept outside the drawer so closing it loses nothing: the
// turns, the half-typed question, the file it includes and the question being answered. The drawer
// only shows this store. A question goes on until the server answers, whether or not the drawer is
// open, and its answer is kept under the analysis it was asked about; it is paid either way, so
// nothing here ever aborts it. Turns are also saved in this browser tab (sessionStorage, spec 5.5)
// so they survive a reload. Each question is still answered on its own: no earlier turns are sent.

import { useSyncExternalStore } from "react";

import { askQuestion } from "./api";
import { isAnswer, parseStoredTurns, type Turn } from "./askTurns";

export type { Turn } from "./askTurns";

/** The file a question includes ("Ask about this"). The path always comes from the analysis's
 * own file index, never from the address; null while a file id from a link is being checked. */
export interface Scope {
  fileId: number;
  path: string | null;
}

/** Why a file named by a link was not included. */
export type ScopeNote = "missing" | "failed";

export interface AskSession {
  turns: Turn[];
  draft: string;
  scope: Scope | null;
  scopeNote: ScopeNote | null;
  /** The question being answered: one per analysis at a time. */
  pending: { id: string; startedAt: number } | null;
  /** Said once above the conversation, e.g. that a turn could not be shown and was removed. */
  notice: string | null;
  /** A question finished while this analysis's Ask was not on screen (closed, or behind the
   * File or Finding tab): the Ask button or tab shows a dot until Ask is seen again. */
  unread: "answer" | "error" | null;
}

const EMPTY: Omit<AskSession, "turns"> = {
  draft: "",
  scope: null,
  scopeNote: null,
  pending: null,
  notice: null,
  unread: null,
};

const sessions = new Map<number, AskSession>();
/** How many drawers of each analysis are on screen now (a count: React may mount one twice). */
const viewing = new Map<number, number>();
const listeners = new Set<() => void>();

// A reload or a move to another page cancels the question's request, and the browser reports
// that as a failed fetch ("Could not reach the RepoLens server"). Saved as such, the question
// would come back after the reload as a server error. So once the page starts to go
// (beforeunload, pagehide) a failure is held back: the turn stays saved as unanswered and the
// next page shows it as interrupted. If the page is still here after LEAVING_GRACE_MS, it did not
// go after all (a download link also fires beforeunload), so the failure was real and is shown.
const LEAVING_GRACE_MS = 3000;
let leaving = false;
const heldFailures = new Set<ReturnType<typeof setTimeout>>();
if (typeof window !== "undefined") {
  const leave = () => {
    leaving = true;
  };
  window.addEventListener("beforeunload", leave);
  window.addEventListener("pagehide", leave);
  window.addEventListener("pageshow", () => {
    leaving = false; // back from the back-forward cache: the page is here again
  });
}

/** Records a failure now, or after the grace period while the page may be going away. */
function reportFailure(record: () => void) {
  if (!leaving) {
    record();
    return;
  }
  const timer = setTimeout(() => {
    heldFailures.delete(timer);
    leaving = false; // still here: the page did not go
    record();
  }, LEAVING_GRACE_MS);
  heldFailures.add(timer);
}

function storageKey(snapshotId: number) {
  return `repolens.ask.${snapshotId}`;
}

/** Saved turns that do not fit what the drawer reads are left out (askTurns). A question still
 * unanswered in storage was cut off by a reload (the request died with the old page): it is kept,
 * marked as interrupted, so it does not vanish without a word. What was changed is saved back. */
function loadTurns(snapshotId: number): Turn[] {
  let raw: string | null;
  try {
    raw = sessionStorage.getItem(storageKey(snapshotId));
  } catch {
    return [];
  }
  const loaded = parseStoredTurns(raw).map((t) =>
    t.answer || t.error || t.interrupted ? t : { ...t, interrupted: true as const },
  );
  if (raw !== null && JSON.stringify(loaded) !== raw) saveTurns(snapshotId, loaded);
  return loaded;
}

function saveTurns(snapshotId: number, turns: Turn[]) {
  try {
    if (turns.length) sessionStorage.setItem(storageKey(snapshotId), JSON.stringify(turns));
    else sessionStorage.removeItem(storageKey(snapshotId));
  } catch {
    // Storage full or blocked: the conversation just does not survive a reload.
  }
}

/** Read once per analysis per page load; after that the store is the truth. */
export function getSession(snapshotId: number): AskSession {
  let session = sessions.get(snapshotId);
  if (!session) {
    session = { ...EMPTY, turns: loadTurns(snapshotId) };
    sessions.set(snapshotId, session);
  }
  return session;
}

function update(snapshotId: number, change: Partial<AskSession>) {
  const before = getSession(snapshotId);
  const next = { ...before, ...change };
  sessions.set(snapshotId, next);
  if (next.turns !== before.turns) saveTurns(snapshotId, next.turns);
  for (const l of listeners) l();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useAskSession(snapshotId: number): AskSession {
  return useSyncExternalStore(subscribe, () => getSession(snapshotId));
}

export function useAskUnread(snapshotId: number): AskSession["unread"] {
  return useSyncExternalStore(subscribe, () => getSession(snapshotId).unread);
}

/** The drawer of this analysis is on screen until the returned function is called. Seeing it is
 * what clears the unread dot. */
export function markViewing(snapshotId: number): () => void {
  viewing.set(snapshotId, (viewing.get(snapshotId) ?? 0) + 1);
  if (getSession(snapshotId).unread) update(snapshotId, { unread: null });
  return () => {
    const left = (viewing.get(snapshotId) ?? 1) - 1;
    if (left > 0) viewing.set(snapshotId, left);
    else viewing.delete(snapshotId);
  };
}

export function setDraft(snapshotId: number, draft: string) {
  update(snapshotId, { draft });
}

export function setScope(snapshotId: number, scope: Scope | null, scopeNote: ScopeNote | null = null) {
  update(snapshotId, { scope, scopeNote });
}

/** Clear is offered only while nothing is being answered. */
export function clearTurns(snapshotId: number) {
  if (getSession(snapshotId).pending) return;
  update(snapshotId, { turns: [], notice: null });
}

/** A turn that still failed to draw (TurnBoundary in the drawer) is removed, from storage too. */
export function removeTurn(snapshotId: number, turnId: string) {
  const session = getSession(snapshotId);
  if (!session.turns.some((t) => t.id === turnId)) return;
  update(snapshotId, {
    turns: session.turns.filter((t) => t.id !== turnId),
    pending: session.pending?.id === turnId ? null : session.pending,
    notice: "An answer could not be shown and was removed from this conversation.",
  });
}

function settle(snapshotId: number, turnId: string, result: Pick<Turn, "answer" | "error">) {
  const session = getSession(snapshotId);
  update(snapshotId, {
    turns: session.turns.map((t) => (t.id === turnId ? { ...t, ...result } : t)),
    pending: session.pending?.id === turnId ? null : session.pending,
    unread: viewing.has(snapshotId) ? session.unread : result.answer ? "answer" : "error",
  });
}

/** Asks one question; the draft and scope go with it (a suggestion or re-ask passes no file). Does
 * nothing while another question of this analysis is being answered. */
export function sendQuestion(snapshotId: number, question: string, fileId?: number) {
  const text = question.trim();
  const session = getSession(snapshotId);
  if (!text || session.pending) return;
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  update(snapshotId, {
    turns: [...session.turns, { id, question: text }],
    draft: "",
    scope: null,
    scopeNote: null,
    pending: { id, startedAt: Date.now() },
    notice: null,
  });
  askQuestion(snapshotId, text, fileId).then(
    // The server's answer gets the same check as a saved one: a shape the drawer cannot read is
    // one failed line, not a crash.
    (answer) =>
      settle(snapshotId, id, isAnswer(answer) ? { answer } : { error: "The answer could not be shown." }),
    (error: unknown) =>
      reportFailure(() =>
        settle(snapshotId, id, { error: error instanceof Error ? error.message : "The question failed." }),
      ),
  );
}

/** Tests only: forget every analysis's conversation, as a page load would (a held failure dies
 * with the old page). */
export function resetAskStore() {
  sessions.clear();
  viewing.clear();
  for (const timer of heldFailures) clearTimeout(timer);
  heldFailures.clear();
  leaving = false;
}
