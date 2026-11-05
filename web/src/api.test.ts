import { afterEach, describe, expect, it, vi } from "vitest";

import { askQuestion, fileLimitNotice } from "./api";

describe("askQuestion", () => {
  afterEach(() => vi.unstubAllGlobals());

  function stubFetch() {
    const fetchMock = vi.fn(
      async (_url: string, _init: RequestInit) => new Response("{}", { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("sends the file for a scoped question", async () => {
    const fetchMock = stubFetch();
    await askQuestion(7, "About a.py: what is this?", 42);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toEqual({
      question: "About a.py: what is this?",
      file_id: 42,
    });
  });

  it("sends only the question when there is no scope", async () => {
    const fetchMock = stubFetch();
    await askQuestion(7, "What is this?");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toEqual({
      question: "What is this?",
    });
  });
});

describe("file-limit notice", () => {
  it("says what was analysed and what was not, with an approximate total", () => {
    expect(
      fileLimitNotice({
        files_kept: 2000,
        files_skipped: 310,
        files_beyond_limit: 741,
        hit_file_limit: true,
      }),
    ).toBe(
      "Analysed 2,000 of about 2,741 files; the file limit was reached. " +
        "The remaining files were not analysed.",
    );
  });

  it("shows nothing under the limit or for old analyses, and never reads as a verdict", () => {
    expect(
      fileLimitNotice({
        files_kept: 41,
        files_skipped: 9,
        files_beyond_limit: 0,
        hit_file_limit: false,
      }),
    ).toBeNull();
    expect(fileLimitNotice(null)).toBeNull();
    expect(fileLimitNotice(undefined)).toBeNull();
    const text = fileLimitNotice({
      files_kept: 3,
      files_skipped: 0,
      files_beyond_limit: 1,
      hit_file_limit: true,
    });
    expect(text).not.toMatch(/safe|all clear|issues|complete/i);
  });
});
