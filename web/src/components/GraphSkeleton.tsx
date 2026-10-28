// Spec §12.1, Graph loading: a skeleton plus "Laying out…". It lives outside the lazy Explore
// chunk so it is also the Suspense fallback while that chunk loads.
const ROWS = [3, 4, 2];

export function GraphSkeleton() {
  return (
    <div className="canvas-message graph-skeleton" role="status" aria-busy="true">
      <p className="caption">Laying out…</p>
      <div className="graph-skeleton-rows" aria-hidden="true">
        {ROWS.map((count, row) => (
          <div key={row} className="graph-skeleton-row">
            {Array.from({ length: count }, (_, i) => (
              <span key={i} className="skeleton graph-skeleton-node" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
