import { describe, expect, it } from "vitest";

import { repoName } from "./api";
import { stageProgress } from "./progress";

describe("stage counts (spec 5.2)", () => {
  it("counts files while parsing and chunks while embedding", () => {
    expect(stageProgress({ stage: "parse", progress: { done: 340, total: 1204 } })).toBe(
      "340 / 1,204 files",
    );
    expect(stageProgress({ stage: "embed", progress: { done: 400, total: 1600 } })).toBe(
      "400 / 1,600 chunks",
    );
    expect(stageProgress({ stage: "embed", progress: { done: 1, total: 1 } })).toBe("1 / 1 chunk");
  });

  it("shows nothing for quick stages or without counts", () => {
    expect(stageProgress({ stage: "edges", progress: { done: 1, total: 2 } })).toBeNull();
    expect(stageProgress({ stage: "parse", progress: null })).toBeNull();
  });
});

describe("repo name", () => {
  it("keeps GitHub capitalisation", () => {
    expect(repoName("https://github.com/Valentine45-dev/JARVIS")).toBe("Valentine45-dev/JARVIS");
  });
});
