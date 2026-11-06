import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { PanelTitle } from "./PanelTitle";

describe("PanelTitle", () => {
  const path = "introduction/migrations/0011_tickits.py";

  it("puts the folder over the file name and never splits the name", () => {
    const html = renderToStaticMarkup(<PanelTitle id="t" path={path} />);
    expect(html).toContain('<span class="panel-title-name">0011_tickits.py</span>');
    expect(html).toContain("<bdi>introduction/migrations</bdi>");
    expect(html).not.toContain("<wbr");
  });

  it("carries the full path as hover text and as its accessible name", () => {
    const html = renderToStaticMarkup(<PanelTitle id="t" path={path} />);
    expect(html).toContain(`title="${path}"`);
    expect(html).toContain(`aria-label="${path}"`);
  });

  it("a file in the repo root has no folder line", () => {
    const html = renderToStaticMarkup(<PanelTitle id="t" path="manage.py" />);
    expect(html).not.toContain("panel-title-dir");
    expect(html).toContain(">manage.py<");
  });
});
