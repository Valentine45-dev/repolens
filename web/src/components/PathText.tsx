import { Fragment } from "react";

/** A path that wraps only after a "/" (DESIGN.md), never inside a file or folder name. With
 * sep=".", a dotted symbol name (`_Mixin.navigate`) wraps only after a dot. */
export function PathText({ path, sep = "/" }: { path: string; sep?: "/" | "." }) {
  return (
    <>
      {path.split(sep).map((part, i) => (
        <Fragment key={i}>
          {i ? (
            <>
              {sep}
              <wbr />
            </>
          ) : null}
          {part}
        </Fragment>
      ))}
    </>
  );
}
