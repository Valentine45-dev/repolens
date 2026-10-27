import { useMemo } from "react";

import type { GraphNode } from "../api";
import { type Degrees, languageLabel } from "../graphModel";

// The accessible alternative to the graph (spec §5.4): every file, never capped, as a table.
export function FileList({
  nodes,
  deg,
  selectedId,
  onSelect,
}: {
  nodes: GraphNode[];
  deg: Map<number, Degrees>;
  selectedId: number | null;
  onSelect: (fileId: number) => void;
}) {
  const rows = useMemo(() => {
    const total = (n: GraphNode) => (deg.get(n.id)?.uses ?? 0) + (deg.get(n.id)?.usedBy ?? 0);
    return [...nodes].sort((a, b) => total(b) - total(a) || a.path.localeCompare(b.path));
  }, [nodes, deg]);

  return (
    <div className="file-list">
      <table className="table">
        <caption className="visually-hidden">
          Files ranked by connections. Select a file to inspect it.
        </caption>
        <thead>
          <tr>
            <th scope="col">File</th>
            <th scope="col">Language</th>
            <th scope="col" className="num-col">Uses</th>
            <th scope="col" className="num-col">Used by</th>
            <th scope="col" className="num-col">External</th>
            <th scope="col" className="num-col">Unresolved</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((n) => {
            const d = deg.get(n.id);
            return (
              <tr key={n.id} aria-selected={n.id === selectedId}>
                <td>
                  <button type="button" className="row-button mono" onClick={() => onSelect(n.id)}>
                    {n.path}
                  </button>
                </td>
                <td>{languageLabel(n.language)}</td>
                <td className="num-col mono num">{d?.uses ?? 0}</td>
                <td className="num-col mono num">{d?.usedBy ?? 0}</td>
                <td className="num-col mono num">{n.external_imports}</td>
                <td className="num-col mono num">{n.unresolved_imports}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
