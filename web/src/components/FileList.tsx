import { useMemo } from "react";

import type { GraphNode } from "../api";
import { type Degrees, languageLabel } from "../graphModel";
import { plural } from "../mapModel";
import { PathText } from "./PathText";

// The accessible alternative to the graph (spec §5.4): every file, never capped, as a table.
export function FileList({
  nodes,
  deg,
  selectedId,
  onSelect,
  root,
  onClearRoot,
}: {
  nodes: GraphNode[];
  deg: Map<number, Degrees>;
  selectedId: number | null;
  onSelect: (fileId: number) => void;
  root?: string; // only files under this folder (from the map's "N more" node)
  onClearRoot?: () => void;
}) {
  const rows = useMemo(() => {
    const total = (n: GraphNode) => (deg.get(n.id)?.uses ?? 0) + (deg.get(n.id)?.usedBy ?? 0);
    const inside = root ? nodes.filter((n) => n.path === root || n.path.startsWith(`${root}/`)) : nodes;
    return [...inside].sort((a, b) => total(b) - total(a) || a.path.localeCompare(b.path));
  }, [nodes, deg, root]);

  return (
    <div className="file-list">
      {root ? (
        <div className="list-filter" role="status">
          <span>
            Showing {plural(rows.length, "file")} under <span className="mono">{root}</span> (of{" "}
            {nodes.length})
          </span>
          <button type="button" className="button button-secondary button-small" onClick={onClearRoot}>
            Show all files
          </button>
        </div>
      ) : null}
      <table className="table">
        <caption className="visually-hidden">
          Files ranked by connections. Select a file to inspect it.
        </caption>
        <thead>
          <tr>
            <th scope="col">File</th>
            <th scope="col" className="col-optional">Language</th>
            <th scope="col" className="num-col">Uses</th>
            <th scope="col" className="num-col">Used by</th>
            <th scope="col" className="num-col col-optional">External</th>
            <th scope="col" className="num-col col-optional">Unresolved</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((n) => {
            const d = deg.get(n.id);
            return (
              <tr key={n.id} aria-selected={n.id === selectedId}>
                <td>
                  <button type="button" className="row-button mono" onClick={() => onSelect(n.id)}>
                    <PathText path={n.path} />
                  </button>
                </td>
                <td className="col-optional">{languageLabel(n.language)}</td>
                <td className="num-col mono num">{d?.uses ?? 0}</td>
                <td className="num-col mono num">{d?.usedBy ?? 0}</td>
                <td className="num-col mono num col-optional">{n.external_imports}</td>
                <td className="num-col mono num col-optional">{n.unresolved_imports}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
