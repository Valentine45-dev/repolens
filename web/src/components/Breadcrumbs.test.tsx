import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Breadcrumbs } from "./Breadcrumbs";

function render(view: Parameters<typeof Breadcrumbs>[0]["view"], search = "") {
  return renderToStaticMarkup(
    <MemoryRouter>
      <Breadcrumbs view={view} repo="itsdangerous" search={search} />
    </MemoryRouter>,
  );
}

describe("Breadcrumbs", () => {
  const view = {
    level: "folder" as const,
    breadcrumbs: [
      { path: "", label: "" },
      { path: "src", label: "src" },
      { path: "src/itsdangerous", label: "itsdangerous" },
    ],
  };

  it("shows repo / src / itsdangerous with the repo name first and the current folder last", () => {
    const html = render(view);
    const text = html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
    expect(text).toContain("itsdangerous / src / itsdangerous");
    expect(html).toContain('aria-current="page"');
  });

  it("makes earlier crumbs links that keep the toggles and set level and root", () => {
    const html = render(view, "?tests=1&guesses=1&node=9");
    expect(html).toContain('href="/?tests=1&amp;guesses=1&amp;level=folder"'); // repo root
    expect(html).toContain('href="/?tests=1&amp;guesses=1&amp;level=folder&amp;root=src"');
    expect(html).not.toContain("node=9"); // a move closes the panel
  });

  it("has an Up link to the parent, and a disabled Up at the repo", () => {
    expect(render(view)).toContain('aria-label="Up one level"');
    const top = render({ level: "folder", breadcrumbs: [{ path: "", label: "" }] });
    expect(top).toContain('aria-disabled="true"');
    expect(top).not.toContain('aria-label="Up one level"');
  });
});
