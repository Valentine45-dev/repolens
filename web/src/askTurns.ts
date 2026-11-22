// What a saved Ask turn must look like before the drawer draws it. Turns come back from this
// tab's sessionStorage, which an older build (with another Answer shape) or a hand edit may have
// written; answers come from the server. Anything the drawer would read and could crash on is
// checked here; a turn that does not fit is left out, the rest are kept.

import type { Answer, Citation, GraphResult } from "./api";

export interface Turn {
  id: string;
  question: string;
  answer?: Answer;
  error?: string;
  /** Saved while it was being answered and then the page reloaded: the answer never arrived. */
  interrupted?: true;
}

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const isStr = (v: unknown): v is string => typeof v === "string";
const isInt = (v: unknown): v is number => Number.isInteger(v);
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const optional = (v: unknown, check: (v: unknown) => boolean) => v === undefined || check(v);
const nullable = (check: (v: unknown) => boolean) => (v: unknown) => v === null || check(v);
const listOf = (check: (v: unknown) => boolean) => (v: unknown) => Array.isArray(v) && v.every(check);

function isCitation(v: unknown): v is Citation {
  return (
    isObj(v) &&
    isStr(v.path) &&
    isInt(v.start_line) &&
    isInt(v.end_line) &&
    isInt(v.file_id) &&
    typeof v.in_test === "boolean"
  );
}

function isSite(v: unknown): boolean {
  return isObj(v) && isInt(v.line) && (v.confidence === null || isNum(v.confidence));
}

function isResult(v: unknown): v is GraphResult {
  return (
    isObj(v) &&
    isNum(v.node_id) &&
    isStr(v.kind) &&
    isStr(v.name) &&
    isStr(v.qualified_name) &&
    nullable(isInt)(v.file_id) &&
    nullable(isStr)(v.path) &&
    nullable(isInt)(v.start_line) &&
    nullable(isInt)(v.end_line) &&
    typeof v.in_test === "boolean" &&
    optional(v.edge, (e) => e === "imports" || e === "calls") &&
    optional(v.sites, listOf(isSite)) &&
    optional(v.site_count, nullable(isNum)) &&
    optional(v.site_file_id, nullable(isInt)) &&
    optional(v.site_path, nullable(isStr))
  );
}

function isClaims(v: unknown): boolean {
  return isObj(v) && isInt(v.total) && isInt(v.kept) && isInt(v.removed) && nullable(isStr)(v.note);
}

export function isAnswer(v: unknown): v is Answer {
  return (
    isObj(v) &&
    (v.kind === "graph" || v.kind === "ai") &&
    isStr(v.status) &&
    isStr(v.answer) &&
    listOf(isCitation)(v.citations) &&
    isNum(v.dropped) &&
    listOf(isResult)(v.results) &&
    optional(v.locations, listOf(isCitation)) &&
    (v.retrieval === null || (isObj(v.retrieval) && optional(v.retrieval.scope, isObj))) &&
    optional(v.claims, nullable(isClaims)) &&
    optional(v.query, isStr) &&
    optional(v.target, nullable(isObj))
  );
}

function isTurn(v: unknown): v is Turn {
  if (!isObj(v) || !isStr(v.id) || !isStr(v.question)) return false;
  const outcomes = [v.answer !== undefined, v.error !== undefined, v.interrupted !== undefined];
  if (outcomes.filter(Boolean).length > 1) return false;
  return optional(v.answer, isAnswer) && optional(v.error, isStr) && optional(v.interrupted, (i) => i === true);
}

/** The saved conversation, without anything that does not fit (or a repeated turn id). */
export function parseStoredTurns(raw: string | null): Turn[] {
  if (!raw) return [];
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(data)) return [];
  const seen = new Set<string>();
  return data.filter((t): t is Turn => {
    if (!isTurn(t) || seen.has(t.id)) return false;
    seen.add(t.id);
    return true;
  });
}
