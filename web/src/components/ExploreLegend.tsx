import type { ReactNode } from "react";

import { dashedText, FLAT_SOLID, MAP_SOLID } from "../legendText";
import { CYCLE_CAPTION } from "../mapModel";
import { Icon } from "./Icon";

/** The strip under the toolbar. Line 1 is the key (what a line means) with the view's counts on
 * the right; line 2 is the status (what is left out, the zoom note) and exists only when it has
 * something to say. A strip, not an overlay, so it never hides a node. Used by the Explorer and by
 * its loading frame, so both draw the same thing. */
export function ExploreLegend({
  kind,
  showGuesses,
  cycle = false,
  facts,
  status = null,
}: {
  kind: "map" | "flat";
  showGuesses: boolean;
  cycle?: boolean;
  facts?: ReactNode; // the flat graph's counts; a map view says them in the breadcrumb row
  status?: string | null;
}) {
  return (
    <div className="legend" aria-label="Legend">
      <div className="legend-key">
        <span className="legend-row">
          <svg width="28" height="8" aria-hidden="true">
            <line x1="0" y1="4" x2="28" y2="4" className="legend-line" />
          </svg>
          {kind === "map" ? MAP_SOLID : FLAT_SOLID}
        </span>
        <span className="legend-row" data-muted={!showGuesses || undefined}>
          <svg width="28" height="8" aria-hidden="true">
            <line x1="0" y1="4" x2="28" y2="4" className="legend-line" strokeDasharray="5 4" />
          </svg>
          {dashedText(kind, showGuesses)}
        </span>
        {cycle ? (
          <span className="legend-row legend-cycle">
            <Icon name="cycle" size={14} />
            {CYCLE_CAPTION}
          </span>
        ) : null}
        {facts !== undefined ? (
          <span className="legend-facts" aria-live="polite">
            {facts}
          </span>
        ) : null}
      </div>
      {status ? <p className="legend-status">{status}</p> : null}
    </div>
  );
}

/** The "Show" group in the Explorer toolbar: one visible word for three checkboxes, so the toolbar
 * fits one row beside the Ask panel. Each checkbox's name keeps its full meaning in the group. */
export function ShowGroup({ children }: { children: ReactNode }) {
  return (
    <div className="toolbar-group" role="group" aria-labelledby="explore-show-label">
      <span id="explore-show-label" className="toolbar-group-label">
        Show
      </span>
      {children}
    </div>
  );
}

export const SHOW_ALL_EDGES_TITLE = "Draw every connection, not only the strongest";
export const ALL_EDGES_SHOWN_TITLE = "All connections are already shown.";
