import { useState } from "react";
import { Link } from "react-router-dom";

import type { Site } from "../api";
import { GUESS_BELOW } from "../graphModel";

export const SHOWN = 3; // lines listed per import or call; "+N more" lists the rest (see below)

/** Which sites a row lists. Collapsed: the first SHOWN. Expanded: every site the server sent
 * (at most 20 per row: the server stores and returns no more). `unlisted` is how many lines exist
 * beyond what can be listed, for an honest "N more lines are not listed" after expanding. */
export function visibleSites(
  sites: Site[],
  count: number | null | undefined,
  expanded: boolean,
): { shown: Site[]; hidden: number; unlisted: number } {
  const total = Math.max(count ?? sites.length, sites.length);
  const shown = expanded ? sites : sites.slice(0, SHOWN);
  return { shown, hidden: sites.length - shown.length, unlisted: total - sites.length };
}

/** Where an import or call happens, as `file:line` chips. A chip opens the code at that line (a
 * button when `onOpen` is given, a link when `href` is); with neither it is plain text. "+N more"
 * is a button that lists the rest of the row's lines, and "Show fewer" folds them again. Nothing
 * at all when the analysis predates sites (`count` null): no line is better than a wrong one. */
export function SiteChips({
  path,
  sites,
  count,
  onOpen,
  href,
  defaultExpanded = false,
}: {
  path: string | null | undefined;
  sites: Site[] | undefined;
  count: number | null | undefined;
  onOpen?: (line: number) => void;
  href?: (line: number) => string;
  defaultExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  if (!path || !sites?.length) return null;
  const { shown, hidden, unlisted } = visibleSites(sites, count, expanded);
  const name = path.split("/").pop();
  const canFold = sites.length > SHOWN;
  return (
    <span className="site-chips">
      {shown.map((s) => {
        const label = `${name}:${s.line}`;
        const guess = s.confidence !== null && s.confidence < GUESS_BELOW;
        const title = `${path}:${s.line}${guess ? " (best guess: matched by name only)" : ""}`;
        const common = { className: "site-chip", title, "data-guess": guess || undefined };
        if (href) {
          return (
            <Link key={s.line} {...common} to={href(s.line)}>
              {label}
            </Link>
          );
        }
        if (onOpen) {
          return (
            <button
              key={s.line}
              type="button"
              {...common}
              aria-label={`Show ${title}`}
              onClick={() => onOpen(s.line)}
            >
              {label}
            </button>
          );
        }
        return (
          <span key={s.line} {...common} data-static>
            {label}
          </span>
        );
      })}
      {canFold && !expanded && hidden + unlisted > 0 ? (
        <button
          type="button"
          className="site-chip site-chip-more"
          aria-expanded={false}
          title={`List ${hidden === 1 ? "the other line" : `${hidden} more lines`}`}
          onClick={() => setExpanded(true)}
        >
          +{hidden + unlisted} more
        </button>
      ) : null}
      {expanded && unlisted > 0 ? (
        <span className="caption">{unlisted} more not listed</span>
      ) : null}
      {canFold && expanded ? (
        <button
          type="button"
          className="site-chip site-chip-more"
          aria-expanded={true}
          onClick={() => setExpanded(false)}
        >
          Show fewer
        </button>
      ) : null}
    </span>
  );
}
