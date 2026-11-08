import { describe, expect, it } from "vitest";

import { documentTitle } from "./documentTitle";

describe("browser tab titles", () => {
  it("say where you are, most specific first, then the app", () => {
    expect(documentTitle(["challenge", "Explorer", "adeyosemanputra/pygoat"])).toBe(
      "challenge · Explorer · adeyosemanputra/pygoat — RepoLens",
    );
    expect(documentTitle([null, "Findings", "pallets/flask"])).toBe("Findings · pallets/flask — RepoLens");
    expect(documentTitle([])).toBe("RepoLens");
  });
});
