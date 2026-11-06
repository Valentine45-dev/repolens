// Spec §12.1, Graph loading: grey placeholders where the map will be, at the size and gap of a
// real node (208x76, 14px) in plain rows, so the page keeps its shape while it loads and nothing
// pretends to be a graph. It lives outside the lazy Explore chunk so it is also the Suspense
// fallback while that chunk loads.
import { Icon } from "./Icon";

const CARDS = 24;

export function GraphSkeleton() {
  return (
    <div className="graph-skeleton" role="status" aria-busy="true">
      <span className="visually-hidden">Laying out…</span>
      <div className="graph-skeleton-grid" aria-hidden="true">
        {Array.from({ length: CARDS }, (_, i) => (
          <div key={i} className="graph-skeleton-card">
            <span className="skeleton" style={{ width: "62%" }} />
            <span className="skeleton" style={{ width: "40%", height: 10 }} />
          </div>
        ))}
      </div>
    </div>
  );
}

/** The List view's table, while the files load. */
export function ListSkeleton() {
  return (
    <div className="list-skeleton" role="status" aria-busy="true">
      <span className="visually-hidden">Loading files…</span>
      <div aria-hidden="true">
        {Array.from({ length: 9 }, (_, i) => (
          <div key={i} className="list-skeleton-row">
            <span className="skeleton" style={{ width: `${32 + ((i * 17) % 38)}%` }} />
          </div>
        ))}
      </div>
    </div>
  );
}

/** The breadcrumb row before the view has arrived: the real Up button (disabled) and the real
 * folder names from the address; only the repo name is grey. */
export function CrumbSkeleton({ root }: { root: string }) {
  const parts = root ? root.split("/") : [];
  return (
    <div className="crumb-row">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <span className="icon-button breadcrumbs-up" aria-disabled="true" title="Already at the top">
          <Icon name="up" />
        </span>
        <ol>
          <li>
            <span className="skeleton" style={{ width: 64, height: 14 }} aria-hidden="true" />
          </li>
          {parts.map((part, i) => (
            <li key={i}>
              <span className="breadcrumbs-sep" aria-hidden="true">
                /
              </span>
              <span className={i === parts.length - 1 ? "breadcrumbs-here mono" : "mono"}>{part}</span>
            </li>
          ))}
        </ol>
      </nav>
    </div>
  );
}

/** The Explorer's frame while its code loads (the Suspense fallback): the same crumb row, toolbar
 * and legend as the real page, controls disabled and in the state the address asks for, then the
 * map placeholder. The real Explorer then fills it in without anything moving. */
export function ExploreFrameSkeleton() {
  const params = new URLSearchParams(window.location.search);
  const list = params.get("view") === "list";
  const level = params.get("level");
  const root = (params.get("root") ?? "").replace(/^\/+|\/+$/g, "");
  return (
    <div className="explore">
      {list ? null : <CrumbSkeleton root={level === "flat" ? "" : root} />}
      <div className="toolbar" role="toolbar" aria-label="Graph options">
        <div className="segmented" role="group" aria-label="View">
          <button type="button" aria-pressed={!list} disabled>
            Graph
          </button>
          <button type="button" aria-pressed={list} disabled>
            List
          </button>
        </div>
        {list ? null : (
          <div className="segmented" role="group" aria-label="Level of detail">
            {(["folder", "file", "flat"] as const).map((l) => (
              <button key={l} type="button" aria-pressed={level === l} disabled>
                {l === "folder" ? "Folders" : l === "file" ? "Files" : "Flat"}
              </button>
            ))}
          </div>
        )}
        <label className="check">
          <input type="checkbox" checked={params.get("tests") === "1"} disabled readOnly />
          Show tests &amp; examples
        </label>
        <label className="check">
          <input type="checkbox" checked={params.get("guesses") === "1"} disabled readOnly />
          Show guessed calls
        </label>
        {list ? null : (
          <label className="check" data-disabled>
            <input type="checkbox" disabled readOnly />
            Show all edges
          </label>
        )}
        {list ? null : (
          <button type="button" className="button button-secondary button-small" disabled>
            Fit
          </button>
        )}
        <p className="toolbar-note caption">
          <span className="skeleton toolbar-note-skeleton" aria-hidden="true" />
        </p>
      </div>
      {list ? null : (
        <div className="legend" aria-label="Legend">
          <div className="legend-row">
            <svg width="28" height="8" aria-hidden="true">
              <line x1="0" y1="4" x2="28" y2="4" className="legend-line" />
            </svg>
            Import or call. The number counts connections; thicker means more.
          </div>
          <div className="legend-row" data-muted={params.get("guesses") === "1" ? undefined : true}>
            <svg width="28" height="8" aria-hidden="true">
              <line x1="0" y1="4" x2="28" y2="4" className="legend-line" strokeDasharray="5 4" />
            </svg>
            <span>
              Dashed: mostly best guesses. Dynamic code makes some calls hard to resolve.
              {params.get("guesses") === "1" ? null : " Hidden; turn on “Show guessed calls”."}
            </span>
          </div>
          <p className="legend-note" />
        </div>
      )}
      <div className="explore-body">
        <div className="canvas">{list ? <ListSkeleton /> : <GraphSkeleton />}</div>
      </div>
    </div>
  );
}
