import { useState } from "react";
import { Link } from "react-router-dom";

import type { FindingReach, ReachStep, ReachTier } from "../api";
import { exploreHref } from "../links";

export type ReachView =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; data: FindingReach };

/** The sentence for each tier. None of them says "unreachable", "unused" or "safe": a path is a
 * way the code could run, found by following imports and name-based calls, and "no path found"
 * only means this analysis found none. */
export const REACH_TEXT: Record<ReachTier, string> = {
  solid: "Reachable from",
  guess:
    "Reachable only through guessed steps (a call matched by name, a special method Python calls implicitly, or a function defined inside code that is reached)",
  not_checked: "Not in analysed code, so reachability was not checked",
  none: "No path found from a detected entry point",
};

/** Short tag for a list row (shown only when the list is ordered by reachability). */
export const REACH_TAG: Record<ReachTier, string> = {
  solid: "reachable",
  guess: "reachable by guess",
  not_checked: "not checked",
  none: "no path found",
};

const COLLAPSE_AFTER = 7;

/** "console script `black`" -> text with the backticked part as code. */
function Label({ text }: { text: string }) {
  return (
    <>
      {text.split("`").map((part, i) =>
        i % 2 ? <code key={i}>{part}</code> : <span key={i}>{part}</span>,
      )}
    </>
  );
}

function stepName(step: ReachStep): string {
  return step.symbol_kind === "module" ? (step.path?.split("/").pop() ?? step.name) : step.name;
}

const VIA_NOTE: Record<string, string> = {
  calls: "a call matched by name only",
  contains:
    "a special method Python calls implicitly, or a function defined inside code that is reached; no call to it was seen",
  imports: "an import inside a function that is reached",
};

function Chip({ snapshotId, step }: { snapshotId: number; step: ReachStep }) {
  const where = step.path ? `${step.path}:${step.start_line}` : step.name;
  const title = step.guess
    ? `${where} (best guess: ${VIA_NOTE[step.via ?? ""] ?? "not confirmed"})`
    : where;
  return (
    <Link
      className="site-chip"
      data-guess={step.guess || undefined}
      title={title}
      to={exploreHref(snapshotId, {
        fileId: step.file_id,
        lines: { start: step.start_line, end: step.start_line },
      })}
    >
      {stepName(step)}
    </Link>
  );
}

/** Where the finding's code can be reached from, as a sentence and a path of clickable chips. */
export function ReachBlock({ snapshotId, view }: { snapshotId: number; view: ReachView }) {
  const [expanded, setExpanded] = useState(false);
  if (view.status === "loading") {
    // The shape of the answer (a sentence, a row of chips, a caption), so the rule text below it
    // does not jump down when it arrives.
    return (
      <div className="reach" role="status" aria-busy="true">
        <span className="visually-hidden">Working out reachability…</span>
        <span className="skeleton" style={{ display: "block", width: "85%" }} aria-hidden="true" />
        <span className="reach-path" aria-hidden="true">
          {[64, 48, 88, 72].map((w, i) => (
            <span key={i} className="skeleton" style={{ width: w, height: "var(--chip-h)" }} />
          ))}
        </span>
        <span className="skeleton" style={{ display: "block", width: "70%", height: 12 }} aria-hidden="true" />
      </div>
    );
  }
  if (view.status === "error") {
    return <p className="caption">Reachability could not be worked out for this finding.</p>;
  }
  const { tier, entry, path } = view.data;
  const hasPath = (tier === "solid" || tier === "guess") && entry !== null && path.length > 0;
  const rest = hasPath ? path.slice(1) : [];
  const fold = !expanded && rest.length > COLLAPSE_AFTER;
  const items: (ReachStep | "fold")[] = fold
    ? [...rest.slice(0, 2), "fold", ...rest.slice(-3)]
    : rest;
  const hidden = fold ? rest.length - 5 : 0;
  return (
    <div className="reach" data-tier={tier}>
      <p className="reach-line">
        {REACH_TEXT[tier]}
        {tier === "solid" && entry ? (
          <>
            {" "}
            <span className="reach-entry">
              <Label text={entry.label} />
            </span>
            {rest.length ? " via" : ""}
          </>
        ) : null}
      </p>
      {hasPath ? (
        <>
          <div className="reach-path" aria-label="Path from the entry point to this code">
            <Chip snapshotId={snapshotId} step={path[0]} />
            {items.map((step, i) => (
              <span key={step === "fold" ? "fold" : `${step.symbol_id}-${i}`} className="reach-step">
                <span className="reach-arrow" aria-hidden="true">
                  →{" "}
                </span>
                {step === "fold" ? (
                  <button
                    type="button"
                    className="site-chip site-chip-more"
                    aria-expanded={false}
                    onClick={() => setExpanded(true)}
                  >
                    +{hidden} more
                  </button>
                ) : (
                  <Chip snapshotId={snapshotId} step={step} />
                )}
              </span>
            ))}
            {expanded && rest.length > COLLAPSE_AFTER ? (
              <button
                type="button"
                className="site-chip site-chip-more"
                aria-expanded={true}
                onClick={() => setExpanded(false)}
              >
                Show fewer
              </button>
            ) : null}
          </div>
          {tier === "guess" && entry ? (
            <p className="caption reach-guess-note">
              Starts at <Label text={entry.label} />. Dashed steps are the guesses (a special method
              is one such as __enter__ or __deepcopy__).
            </p>
          ) : null}
        </>
      ) : null}
      <p className="caption">
        Entry points are detected by pattern and can be missed. This says where a path was found,
        not whether the code runs.
      </p>
    </div>
  );
}
