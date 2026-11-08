// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { FindingReach, ReachStep } from "../api";
import { REACH_TAG, REACH_TEXT, ReachBlock, type ReachView } from "./ReachBlock";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const step = (id: number, name: string, over: Partial<ReachStep> = {}): ReachStep => ({
  symbol_id: id,
  symbol_kind: "function",
  name,
  file_id: 100 + id,
  path: `pkg/m${id}.py`,
  start_line: id * 10,
  end_line: id * 10 + 5,
  via: id === 1 ? null : "calls",
  guess: false,
  ...over,
});

const ENTRY = { kind: "console-script", label: "console script `black`", detail: "pyproject.toml: black:main" };

function show(data: FindingReach) {
  const view: ReachView = { status: "ready", data };
  act(() =>
    root.render(
      <MemoryRouter>
        <ReachBlock snapshotId={7} view={view} />
      </MemoryRouter>,
    ),
  );
}
const text = () => host.textContent ?? "";
const chips = () => [...host.querySelectorAll<HTMLAnchorElement>("a.site-chip")];

describe("ReachBlock", () => {
  it("solid: names the entry point and lists the path as clickable chips", () => {
    show({ tier: "solid", entry: ENTRY, path: [step(1, "main"), step(2, "run"), step(3, "helper")] });
    expect(text()).toContain("Reachable from console script black via");
    expect(host.querySelector(".reach-entry code")?.textContent).toBe("black");
    expect(chips().map((c) => c.textContent)).toEqual(["main", "run", "helper"]);
    expect(chips()[2].getAttribute("href")).toBe("/a/7/explore?node=103&lines=30-30");
    expect(chips().every((c) => !c.hasAttribute("data-guess"))).toBe(true);
  });

  it("solid and the finding is the entry point itself: no 'via'", () => {
    show({ tier: "solid", entry: ENTRY, path: [step(1, "main")] });
    expect(text()).toContain("Reachable from console script black");
    expect(text()).not.toContain("via");
    expect(chips()).toHaveLength(1);
  });

  it("a module step is named by its file", () => {
    show({
      tier: "solid",
      entry: ENTRY,
      path: [step(1, "main"), step(2, "m", { symbol_kind: "module", path: "pkg/sub/core.py" })],
    });
    expect(chips()[1].textContent).toBe("core.py");
  });

  it("guess: says it is only through guessed steps and dashes them, with the reason in the title", () => {
    show({
      tier: "guess",
      entry: ENTRY,
      path: [step(1, "main"), step(2, "pick", { guess: true }), step(3, "process")],
    });
    expect(text()).toContain(
      "Reachable only through guessed steps (a call matched by name, a special method Python calls implicitly, or a function defined inside code that is reached)",
    );
    expect(chips()[1].hasAttribute("data-guess")).toBe(true);
    expect(chips()[1].getAttribute("title")).toContain("a call matched by name only");
    expect(chips()[2].hasAttribute("data-guess")).toBe(false);
    expect(text()).toContain("Dashed steps are guesses");
  });

  it("a structural guess is explained as a special method or a nested function, not as a call", () => {
    show({
      tier: "guess",
      entry: ENTRY,
      path: [step(1, "main"), step(2, "__enter__", { symbol_kind: "method", via: "contains", guess: true })],
    });
    const title = chips()[1].getAttribute("title") ?? "";
    expect(title).toContain("a special method Python calls implicitly");
    expect(title).not.toContain("a call matched by name");
    expect(text()).toContain("__enter__ or __deepcopy__");
  });

  it("not checked and no path found use the agreed words and show no path", () => {
    show({ tier: "not_checked", entry: null, path: [] });
    expect(text()).toContain("Not in analysed code, so reachability was not checked");
    expect(chips()).toHaveLength(0);
    show({ tier: "none", entry: null, path: [] });
    expect(text()).toContain("No path found from a detected entry point");
    expect(chips()).toHaveLength(0);
  });

  it("always carries the caption that entry points are found by pattern and can be missed", () => {
    for (const tier of ["solid", "guess", "not_checked", "none"] as const) {
      show({ tier, entry: tier === "solid" || tier === "guess" ? ENTRY : null,
        path: tier === "solid" || tier === "guess" ? [step(1, "main")] : [] });
      expect(text()).toContain("Entry points are detected by pattern and can be missed");
    }
  });

  it("a long path folds to the first two and last three steps and expands on request", () => {
    const path = [step(1, "main"), ...Array.from({ length: 9 }, (_, i) => step(i + 2, `f${i + 2}`))];
    show({ tier: "solid", entry: ENTRY, path });
    expect(chips().map((c) => c.textContent)).toEqual(["main", "f2", "f3", "f8", "f9", "f10"]);
    const more = [...host.querySelectorAll("button")].find((b) => /\+4 more/.test(b.textContent ?? ""));
    expect(more).toBeTruthy();
    act(() => more!.click());
    expect(chips()).toHaveLength(10);
    const fewer = [...host.querySelectorAll("button")].find((b) => b.textContent === "Show fewer");
    expect(fewer).toBeTruthy();
  });

  it("loading and error states say nothing about the code", () => {
    act(() => root.render(<MemoryRouter><ReachBlock snapshotId={7} view={{ status: "loading" }} /></MemoryRouter>));
    expect(text()).toBe("Working out reachability…");
    act(() => root.render(<MemoryRouter><ReachBlock snapshotId={7} view={{ status: "error" }} /></MemoryRouter>));
    expect(text()).toBe("Reachability could not be worked out for this finding.");
  });

  it("never says unreachable, unused or safe", () => {
    const words = /unreachable|unused|dead code|\bsafe\b|not used/i;
    for (const sentence of [...Object.values(REACH_TEXT), ...Object.values(REACH_TAG)]) {
      expect(sentence).not.toMatch(words);
    }
    for (const tier of ["solid", "guess", "not_checked", "none"] as const) {
      const walks = tier === "solid" || tier === "guess";
      show({ tier, entry: walks ? ENTRY : null, path: walks ? [step(1, "main"), step(2, "x")] : [] });
      expect(text()).not.toMatch(words);
    }
  });
});
