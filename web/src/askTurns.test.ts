import { describe, expect, it } from "vitest";

import { isAnswer, parseStoredTurns } from "./askTurns";

const answer = {
  kind: "graph", status: "answered", answer: "2 files import it.", dropped: 0, prompt_version: null, retrieval: null,
  citations: [],
  results: [{
    node_id: 3, kind: "module", name: "a", qualified_name: "pkg.a", file_id: 3, path: "pkg/a.py",
    start_line: 1, end_line: 9, in_test: false, edge: "imports", sites: [{ line: 4, confidence: null }], site_count: 1,
    site_file_id: 3, site_path: "pkg/a.py",
  }],
};

describe("saved Ask turns", () => {
  it("keeps answered, failed and interrupted turns, and a question still waiting", () => {
    const turns = [
      { id: "1", question: "q", answer },
      { id: "2", question: "q", error: "Request failed (500)." },
      { id: "3", question: "q", interrupted: true },
      { id: "4", question: "q" },
    ];
    expect(parseStoredTurns(JSON.stringify(turns))).toEqual(turns);
  });

  it("drops what does not fit and keeps the rest", () => {
    const raw = JSON.stringify([
      { id: "1", question: "q", answer },
      { id: "1", question: "same id again", answer },
      { id: "2", question: "q", answer: { ...answer, results: [{ ...answer.results[0], qualified_name: 5 }] } },
      { id: "3", question: "q", answer: { ...answer, kind: "llm" } },
      { id: "4", question: "q", answer, error: "both" },
      { id: "5", question: "q", interrupted: "yes" },
      { id: 6, question: "q" },
      null,
    ]);
    expect(parseStoredTurns(raw).map((t) => t.id)).toEqual(["1"]);
  });

  it("reads nothing from text that is not a list of turns", () => {
    expect(parseStoredTurns(null)).toEqual([]);
    expect(parseStoredTurns("{not json")).toEqual([]);
    expect(parseStoredTurns('{"id":"1"}')).toEqual([]);
  });

  it("checks an answer from the server the same way", () => {
    expect(isAnswer(answer)).toBe(true);
    expect(isAnswer({ ...answer, citations: [{ path: "a.py", start_line: 1, end_line: 2, file_id: "3", in_test: false }] })).toBe(false);
    expect(isAnswer({ ...answer, locations: "none" })).toBe(false);
    expect(isAnswer(undefined)).toBe(false);
  });
});
