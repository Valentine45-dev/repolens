import { Link } from "react-router-dom";

import type { MapView } from "../api";
import { crumbChanges, crumbLabel, paramsWith, upChanges } from "../mapModel";
import { Icon } from "./Icon";

/** repo / src / itsdangerous, plus an Up button. Each crumb is a real link (it opens in a new tab,
 * and Back undoes it); the last one is where you are. */
export function Breadcrumbs({
  view,
  repo,
  search,
}: {
  view: Pick<MapView, "level" | "breadcrumbs">;
  repo: string;
  search: string; // the current query string, so the toggles survive a move
}) {
  const crumbs = view.breadcrumbs;
  const up = upChanges(view);
  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      {up ? (
        <Link
          to={paramsWith(search, up)}
          className="icon-button breadcrumbs-up"
          aria-label="Up one level"
          title="Up one level"
        >
          <Icon name="up" />
        </Link>
      ) : (
        <span className="icon-button breadcrumbs-up" aria-disabled="true" title="Already at the top">
          <Icon name="up" />
        </span>
      )}
      <ol>
        {crumbs.map((crumb, i) => {
          const last = i === crumbs.length - 1;
          return (
            <li key={`${i}:${crumb.path}`}>
              {i > 0 ? (
                <span className="breadcrumbs-sep" aria-hidden="true">
                  /
                </span>
              ) : null}
              {last ? (
                <span aria-current="page" className="breadcrumbs-here mono">
                  {crumbLabel(crumb, repo)}
                </span>
              ) : (
                <Link to={paramsWith(search, crumbChanges(view, i))} className="mono">
                  {crumbLabel(crumb, repo)}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
