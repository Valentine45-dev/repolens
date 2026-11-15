// The Ask conversation of each analysis, kept outside the drawer so closing it loses nothing: the
// turns, the half-typed question, the file it includes and the question being answered. The drawer
// only shows this store. A question goes on until the server answers, whether or not the drawer is
// open, and its answer is kept under the analysis it was asked about; it is paid either way, so
// nothing here ever aborts it. Turns are also saved in this browser tab (sessionStorage, spec 5.5)
// so they survive a reload. Each question is still answered on its own: no earlier turns are sent.

import { useSyncExternalStore } from "react";

import { askQuestion, type Answer } from "./api";

export interface Turn {
  id: string;
  question: string;
  answer?: Answer;
  error?: string;
  /** Saved while it was being answered and then the page reloaded: the answer never arrived. */
  interrupted?: true;
}

/** The file a question includes ("Ask about this"). */
export interface Scope {
  fileId: number;
  path: string;
}

export interface AskSession {
  turns: Turn[];
  draft: string;
  scope: Scope | null;
  /** The question being answered: one per analysis at a time. */
  pending: { id: string; startedAt: number } | null;
}

const EMPTY: Omit<AskSession, "turns"> = { draft: "", scope: null, pending: null };

const sessions = new Map<number, AskSession>();
const listeners = new Set<() => void>();

function storageKey(snapshotId: number) {
  return `repolens.ask.${snapshotId}`;
}

/** A question still unanswered in storage was cut off by a reload (the request died with the old
 * page): it is kept, marked as interrupted, so it does not vanish without a word. */
function loadTurns(snapshotId: number): Turn[] {
  let turns: Turn[];
  try {
    const raw = sessionStorage.getItem(storageKey(snapshotId));
    turns = raw ? (JSON.parse(raw) as Turn[]) : [];
  } catch {
    return [];
  }
  const loaded = turns.map((t) => (t.answer || t.error || t.interrupted ? t : { ...t, interrupted: true as const }));
  if (loaded.some((t, i) => t !== turns[i])) saveTurns(snapshotId, loaded);
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

export function setDraft(snapshotId: number, draft: string) {
  update(snapshotId, { draft });
}

export function setScope(snapshotId: number, scope: Scope | null) {
  update(snapshotId, { scope });
}

/** Clear is offered only while nothing is being answered. */
export function clearTurns(snapshotId: number) {
  if (getSession(snapshotId).pending) return;
  update(snapshotId, { turns: [] });
}

function settle(snapshotId: number, turnId: string, result: Pick<Turn, "answer" | "error">) {
  const session = getSession(snapshotId);
  update(snapshotId, {
    turns: session.turns.map((t) => (t.id === turnId ? { ...t, ...result } : t)),
    pending: session.pending?.id === turnId ? null : session.pending,
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
    pending: { id, startedAt: Date.now() },
  });
  askQuestion(snapshotId, text, fileId).then(
    (answer) => settle(snapshotId, id, { answer }),
    (error: unknown) =>
      settle(snapshotId, id, { error: error instanceof Error ? error.message : "The question failed." }),
  );
}

/** Tests only: forget every analysis's conversation, as a page load would. */
export function resetAskStore() {
  sessions.clear();
}
