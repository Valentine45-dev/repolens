import { describe, expect, it } from "vitest";

import { fileLimitNotice } from "./api";

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
