// A documentation file (README, docs text) opened from an Ask citation. Docs are not on the map,
// so this panel has no Used by / Uses: just the text, as plain text (Markdown is never rendered,
// so HTML in it shows as written), with the cited lines highlighted.
import { useQuery } from "@tanstack/react-query";
import { useId } from "react";

import { getFile } from "../api";
import type { LineRange } from "../links";
import { CloseButton } from "./CloseButton";
import { CodeView } from "./NodePanel";
import { PanelTitle } from "./PanelTitle";

export function DocPanel({
  snapshotId,
  fileId,
  highlight,
  reveal,
  hidden,
  onClose,
}: {
  snapshotId: number;
  fileId: number;
  highlight: LineRange | null;
  reveal: string | null;
  hidden: boolean;
  onClose: () => void;
}) {
  const titleId = useId();
  const file = useQuery({
    queryKey: ["file", snapshotId, fileId],
    queryFn: ({ signal }) => getFile(snapshotId, fileId, signal),
    staleTime: Infinity,
  });
  const lines = file.data ? file.data.content.split("\n").length - (file.data.content.endsWith("\n") ? 1 : 0) : null;
  return (
    <aside className="panel doc-panel" aria-labelledby={titleId} data-testid="doc-panel">
      <header className="panel-header">
        <div className="panel-heading">
          <PanelTitle id={titleId} path={file.data?.path ?? "Documentation"} />
          <p className="caption">
            <span className="tag" data-kind="doc">
              documentation
            </span>{" "}
            {lines !== null ? (
              <>
                <span className="mono num">{lines}</span> lines ·{" "}
              </>
            ) : null}
            shown as plain text
          </p>
        </div>
        <CloseButton what="documentation panel" onClose={onClose} />
      </header>
      <div className="panel-body">
        {file.data ? (
          <CodeView
            key={fileId}
            path={file.data.path}
            content={file.data.content}
            highlight={highlight}
            reveal={reveal}
            hidden={hidden}
          />
        ) : file.error ? (
          <p className="panel-message">This file could not be loaded.</p>
        ) : (
          <p className="panel-message">Loading…</p>
        )}
      </div>
    </aside>
  );
}
