import { describe, expect, it } from "vitest";

import { findingsCountLabel } from "./findingsCount";

describe("findingsCountLabel", () => {
  it("shows the total when nothing is hidden", () => {
    expect(findingsCountLabel(60, 60)).toBe("(60)");
  });

  it("shows how many match out of all of them when a filter hides some", () => {
    expect(findingsCountLabel(48, 60)).toBe("(48 of 60)");
    expect(findingsCountLabel(0, 60)).toBe("(0 of 60)");
  });

  it("a filter that matches everything reads like no filter", () => {
    expect(findingsCountLabel(7, 7)).toBe("(7)");
  });
});
