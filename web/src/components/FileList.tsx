import { Fragment, useMemo } from "react";

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
                    <BreakablePath path={n.path} />
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

/** A path that may wrap only after a "/", never inside a name. */
export function BreakablePath({ path }: { path: string }) {
  const parts = path.split("/");
  return (
    <>
      {parts.map((part, i) => (
        <Fragment key={i}>
          {part}
          {i < parts.length - 1 ? (
            <>
              /<wbr />
            </>
          ) : null}
        </Fragment>
      ))}
    </>
  );
}
