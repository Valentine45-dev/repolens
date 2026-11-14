import { describe, expect, it } from "vitest";

import {
  buildEntries,
  type ListedFile,
  lowerSameLength,
  matchEntry,
  normaliseQuery,
  pieces,
  RESULT_LIMIT,
  searchEntries,
} from "./fileSearch";

const file = (id: number, path: string, language = "python"): ListedFile => ({ id, path, language });

// A slice of psf/black: source files, plus tests that the server hides when tests are off.
const BLACK = [
  file(1, "src/black/trans.py"),
  file(2, "src/black/linegen.py"),
  file(3, "src/black/__init__.py"),
  file(4, "src/blackd/__init__.py"),
  file(5, "tests/test_black.py"),
  file(6, "tests/test_blackd.py"),
  file(7, "tests/test_trans.py"),
  file(8, "scripts/release.py"),
];
const BLACK_PLAIN = BLACK.filter((f) => !f.path.startsWith("tests/"));

const paths = (query: string, withTests = BLACK, withoutTests: ListedFile[] | null = BLACK_PLAIN) =>
  searchEntries(buildEntries(withTests, withoutTests), query).matches.map((m) => m.entry.path);

describe("ranking", () => {
  it("puts an exact name before a prefix, a substring, a path match and an in-order match", () => {
    const list = [
      file(1, "a/xtransx.py"), // name substring
      file(2, "trans/zz.py"), // path substring (folder part)
      file(3, "a/transformer.py"), // name prefix
      file(4, "t/r/a/n/s.py"), // in order only
      file(5, "deep/folder/trans"), // exact name (no extension)
    ];
    const ranked = searchEntries(buildEntries(list, list), "trans").matches;
    const files = ranked.filter((m) => m.entry.kind === "file");
    expect(files.map((m) => [m.entry.path, m.tier])).toEqual([
      ["deep/folder/trans", 0],
      ["a/transformer.py", 1],
      ["a/xtransx.py", 2],
      ["trans/zz.py", 3],
      ["t/r/a/n/s.py", 4],
    ]);
  });

  it("breaks ties by the shorter path, then A to Z", () => {
    const list = [file(1, "very/long/path/util.py"), file(2, "b/util.py"), file(3, "a/util.py")];
    expect(paths("util.py", list, list)).toEqual(["a/util.py", "b/util.py", "very/long/path/util.py"]);
  });

  it("finds the brief's examples on black", () => {
    expect(paths("test_black")[0]).toBe("tests/test_black.py");
    expect(paths("test_black")).toContain("tests/test_blackd.py");
    expect(paths("trans").slice(0, 2)).toEqual(["src/black/trans.py", "tests/test_trans.py"]);
    expect(paths("src/black/trans.py")[0]).toBe("src/black/trans.py");
  });

  it("is case-insensitive and takes Windows separators, ./ and spaces", () => {
    expect(paths("TRANS.PY")[0]).toBe("src/black/trans.py");
    expect(paths("src\\black\\trans")[0]).toBe("src/black/trans.py");
    expect(paths("./src/black/trans.py")[0]).toBe("src/black/trans.py");
    expect(paths(" test black ")[0]).toBe("tests/test_black.py");
  });

  it("lists folders too, after files of the same tier", () => {
    const ranked = searchEntries(buildEntries(BLACK, BLACK_PLAIN), "black").matches;
    expect(ranked[0].entry).toMatchObject({ kind: "folder", path: "src/black" });
    expect(ranked[0].tier).toBe(0);
    // name prefix: files first, then folders
    const prefix = ranked.filter((m) => m.tier === 1).map((m) => `${m.entry.kind}:${m.entry.path}`);
    expect(prefix).toEqual(["folder:src/blackd"]);
    expect(paths("src/black/")[0]).toBe("src/black");
  });

  it("prefers fewer separate runs among in-order matches", () => {
    const list = [file(1, "x/a_b_c_d.py"), file(2, "x/abcd_zz_qq.py")];
    // "abcdq": abcd together then q, against a,b,c,d,q apart
    const ranked = searchEntries(buildEntries(list, list), "abcdq").matches;
    expect(ranked.map((m) => m.tier)).toEqual([4]);
    expect(ranked[0].entry.path).toBe("x/abcd_zz_qq.py");
    const two = [file(1, "q/w/e/r.py"), file(2, "qwer/zzzzzzzzzzzzzzzzzzzz.py")];
    expect(searchEntries(buildEntries(two, two), "qw/r").matches.map((m) => m.entry.path)[0]).toBe(
      "q/w/e/r.py",
    );
  });

  it("caps the list and says how many matched", () => {
    const many = Array.from({ length: 120 }, (_, i) => file(i + 1, `pkg/mod_${String(i).padStart(3, "0")}.py`));
    const result = searchEntries(buildEntries(many, many), "mod");
    expect(result.total).toBe(120);
    expect(result.matches).toHaveLength(RESULT_LIMIT);
  });

  it("matches nothing for an empty query or one that is not there", () => {
    expect(searchEntries(buildEntries(BLACK, BLACK_PLAIN), "   ").total).toBe(0);
    expect(searchEntries(buildEntries(BLACK, BLACK_PLAIN), "zzzz").total).toBe(0);
  });
});

describe("highlight ranges", () => {
  const entry = (path: string) => buildEntries([file(1, path)], [file(1, path)])[0];

  it("marks the matched characters in the name, by index into the original path", () => {
    expect(matchEntry(entry("src/black/Trans.py"), "trans")?.ranges).toEqual([[10, 15]]);
    expect(matchEntry(entry("src/black/trans.py"), normaliseQuery("black/tr"))?.ranges).toEqual([[4, 12]]);
  });

  it("prefers a match at the start of a folder name", () => {
    expect(matchEntry(entry("xsrc/src/a.py"), "src")?.ranges).toEqual([[5, 8]]);
  });

  it("matches in order from the right, so the hits gather in the name", () => {
    // "t/test_black.py": the "t" right before "_black" (index 5), not the folder's or the first one.
    expect(matchEntry(entry("t/test_black.py"), "tb")?.ranges).toEqual([[5, 6], [7, 8]]);
  });

  it("splits a path into hit and plain pieces for the name and the folder", () => {
    const path = "src/black/trans.py";
    const ranges: [number, number][] = [[4, 12]];
    expect(pieces(path, ranges, 10, path.length)).toEqual([
      { text: "tr", hit: true },
      { text: "ans.py", hit: false },
    ]);
    expect(pieces(path, ranges, 0, 9)).toEqual([
      { text: "src/", hit: false },
      { text: "black", hit: true },
    ]);
  });

  it("keeps indexes when lower case would change a character's length", () => {
    const odd = "İx/İndex.py";
    expect(lowerSameLength(odd)).toHaveLength(odd.length);
    expect(matchEntry(entry(odd), "ndex")?.ranges).toEqual([[4, 8]]);
  });
});

describe("test and example tag", () => {
  it("tags a file only when it is in the list with tests and not in the one without", () => {
    const entries = buildEntries(BLACK, BLACK_PLAIN);
    const tag = (p: string) => entries.find((e) => e.path === p)?.test;
    expect(tag("tests/test_black.py")).toBe(true);
    expect(tag("src/black/trans.py")).toBe(false);
    expect(tag("tests")).toBe(true); // a folder holding only test files
    expect(tag("src")).toBe(false);
  });

  it("tags nothing until the list without tests is there", () => {
    const entries = buildEntries(BLACK, null);
    expect(entries.every((e) => e.test === null)).toBe(true);
  });

  it("does not tag a file that only looks like a test when the server kept it", () => {
    // The server's rule decides; a name with "test" in it is not enough.
    const list = [file(1, "src/attest.py"), file(2, "src/contest/run.py")];
    expect(buildEntries(list, list).every((e) => e.test === false)).toBe(true);
  });
});
