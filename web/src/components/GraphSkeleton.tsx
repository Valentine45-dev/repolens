// Spec §12.1, Graph loading: grey placeholder nodes where the map will be, so the page keeps its
// shape while it loads. It lives outside the lazy Explore chunk so it is also the Suspense
// fallback while that chunk loads, and AnalysisShell shows it while the analysis loads.
const COLUMNS = [1, 3, 2, 2];

export function GraphSkeleton() {
  return (
    <div className="graph-skeleton" role="status" aria-busy="true">
      <span className="visually-hidden">Laying out…</span>
      <div className="graph-skeleton-map" aria-hidden="true">
        {COLUMNS.map((count, col) => (
          <div key={col} className="graph-skeleton-col">
            {Array.from({ length: count }, (_, i) => (
              <div key={i} className="graph-skeleton-card">
                <span className="skeleton" style={{ width: "62%" }} />
                <span className="skeleton" style={{ width: "40%", height: 10 }} />
              </div>
            ))}
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

/** One bar the height of a breadcrumb row, so the toolbar does not jump when the crumbs arrive. */
export function CrumbSkeleton() {
  return (
    <div className="crumb-row" aria-hidden="true">
      <span className="skeleton" style={{ width: 30, height: 30 }} />
      <span className="skeleton" style={{ width: 180, marginLeft: 8 }} />
    </div>
  );
}
