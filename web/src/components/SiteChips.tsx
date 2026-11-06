import { Link } from "react-router-dom";

import type { Site } from "../api";

const SHOWN = 3; // lines listed per import or call; "+N more" says how many are left

/** Where an import or call happens, as `file:line` chips. A chip opens the code at that line (a
 * button when `onOpen` is given, a link when `href` is); with neither it is plain text. Nothing
 * at all when the analysis predates sites (`count` null): no line is better than a wrong one. */
export function SiteChips({
  path,
  sites,
  count,
  onOpen,
  href,
}: {
  path: string | null | undefined;
  sites: Site[] | undefined;
  count: number | null | undefined;
  onOpen?: (line: number) => void;
  href?: (line: number) => string;
}) {
  if (!path || !sites?.length) return null;
  const shown = sites.slice(0, SHOWN);
  const more = (count ?? sites.length) - shown.length;
  const name = path.split("/").pop();
  return (
    <span className="site-chips">
      {shown.map((s) => {
        const label = `${name}:${s.line}`;
        const title = `${path}:${s.line}`;
        if (href) {
          return (
            <Link key={s.line} className="site-chip" to={href(s.line)} title={title}>
              {label}
            </Link>
          );
        }
        if (onOpen) {
          return (
            <button
              key={s.line}
              type="button"
              className="site-chip"
              title={title}
              aria-label={`Show ${title}`}
              onClick={() => onOpen(s.line)}
            >
              {label}
            </button>
          );
        }
        return (
          <span key={s.line} className="site-chip" data-static title={title}>
            {label}
          </span>
        );
      })}
      {more > 0 ? <span className="caption">+{more} more</span> : null}
    </span>
  );
}
