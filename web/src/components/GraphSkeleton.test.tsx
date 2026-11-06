import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CrumbSkeleton, GraphSkeleton } from "./GraphSkeleton";

describe("loading placeholders", () => {
  it("the breadcrumb row is real except for the repo name", () => {
    const html = renderToStaticMarkup(<CrumbSkeleton root="src/flask" />);
    expect(html).toContain("breadcrumbs-up");
    expect(html).toContain('aria-disabled="true"');
    expect(html).toContain(">src<");
    expect(html).toContain(">flask<");
    // exactly one grey bar: the repo name
    expect(html.match(/class="skeleton"/g)).toHaveLength(1);
  });

  it("no folder names are invented when the address names none", () => {
    const html = renderToStaticMarkup(<CrumbSkeleton root="" />);
    expect(html).not.toContain("breadcrumbs-sep");
  });

  it("the map placeholder is plain rows of node-sized cards, not a graph shape", () => {
    const html = renderToStaticMarkup(<GraphSkeleton />);
    expect(html).toContain("graph-skeleton-grid");
    expect(html.match(/graph-skeleton-card/g)?.length).toBeGreaterThanOrEqual(12);
    expect(html).not.toContain("<svg"); // no edges drawn
    expect(html).toContain("Laying out…"); // for screen readers
  });
});
