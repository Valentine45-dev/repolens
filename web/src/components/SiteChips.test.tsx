import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { SiteChips } from "./SiteChips";

const sites = [10, 13, 20, 25, 30].map((line) => ({ line, confidence: null }));

describe("SiteChips", () => {
  it("lists the first three lines as file:line and counts the rest", () => {
    const html = renderToStaticMarkup(
      <SiteChips path="app/main.py" sites={sites} count={5} onOpen={() => {}} />,
    );
    expect(html).toContain("main.py:10");
    expect(html).toContain("main.py:20");
    expect(html).not.toContain("main.py:25");
    expect(html).toContain("+2 more");
    expect(html).toContain('title="app/main.py:10"'); // the full path on hover
    expect(html).toContain("<button");
  });

  it("links to the given address when asked for a link", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <SiteChips path="a/b.py" sites={sites.slice(0, 1)} count={1} href={(l) => `/x?lines=${l}`} />
      </MemoryRouter>,
    );
    expect(html).toContain('href="/x?lines=10"');
    expect(html).not.toContain("more");
  });

  it("is plain text without an opener, and shows nothing for an analysis that predates sites", () => {
    expect(renderToStaticMarkup(<SiteChips path="a.py" sites={sites.slice(0, 1)} count={1} />)).toContain(
      "data-static",
    );
    expect(renderToStaticMarkup(<SiteChips path="a.py" sites={[]} count={null} />)).toBe("");
    expect(renderToStaticMarkup(<SiteChips path={null} sites={sites} count={5} />)).toBe("");
  });
});
