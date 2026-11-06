import type { Ref } from "react";

import { splitPath } from "../graphModel";

/** A file path as a panel title: the folder on a line of its own (cut at the left with an
 * ellipsis when it is too long, so the part nearest the file stays), the file name under it (cut
 * at the end). A name is never broken in the middle; the full path is the hover text and the
 * accessible name. */
export function PanelTitle({
  id,
  path,
  titleRef,
}: {
  id: string;
  path: string;
  titleRef?: Ref<HTMLHeadingElement>;
}) {
  const [dir, name] = splitPath(path);
  return (
    <h2
      id={id}
      ref={titleRef}
      tabIndex={-1}
      className="panel-title panel-title-path mono"
      title={path}
      aria-label={path}
    >
      {dir ? (
        // rtl puts the ellipsis on the left; <bdi> keeps the text itself in order
        <span className="panel-title-dir" dir="rtl">
          <bdi>{dir.replace(/\/$/, "")}</bdi>
        </span>
      ) : null}
      <span className="panel-title-name">{name}</span>
    </h2>
  );
}
