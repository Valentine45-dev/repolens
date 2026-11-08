// @vitest-environment jsdom
import type { UseQueryResult } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Finding, FindingsPage } from "../api";
import { FindingsList } from "./Findings";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const F: Finding = {
  id: 7,
  rule_id: "py-eval-exec",
  severity: "high",
  message: "Use of eval() or exec()",
  file_id: 1,
  path: "src/flask/cli.py",
  language: "python",
  line: 1022,
  symbol: null,
  snippet: null,
  in_test: false,
  in_docs: false,
  placeholder: false,
  template_value: false,
  category: "security",
  node_id: 1,
};

const page = (items: Finding[]) =>
  ({
    data: {
      total: items.length, limit: 50, offset: 0, items, notes: [],
      counts: { total: items.length, by_severity: { high: 1, medium: 0, low: 0 }, by_rule: {},
        by_category: { security: 1, quality: 0 }, placeholders: 0, documentation: 0, template_values: 0 },
    },
    error: null,
    isPlaceholderData: false,
  }) as unknown as UseQueryResult<FindingsPage>;

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

describe("the findings list", () => {
  it("opens a finding from anywhere on its row, once, including the location", () => {
    const onSelect = vi.fn();
    act(() =>
      root.render(
        <FindingsList query={page([F])} filtered={false} emptyAction={null} categoryLabel={null}
          showReach={false} selectedId={null} onSelect={onSelect} />,
      ),
    );
    act(() => host.querySelector<HTMLElement>(".location-link")!.click());
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenLastCalledWith(7);
    act(() => host.querySelector<HTMLButtonElement>(".row-button")!.click());
    expect(onSelect).toHaveBeenCalledTimes(2); // the button's own click, not a second one from the row
  });

  it("an empty filter result says what to do next and never reads as a verdict", () => {
    const run = vi.fn();
    act(() =>
      root.render(
        <FindingsList query={page([])} filtered emptyAction={{ label: "Clear filters", run }}
          categoryLabel="Security" showReach={false} selectedId={null} onSelect={() => {}} />,
      ),
    );
    const text = host.textContent ?? "";
    expect(text).toContain("No findings match these filters. These checks can still miss issues.");
    expect(text).not.toMatch(/\bsafe\b|all clear|0 issues/i);
    act(() => host.querySelector<HTMLButtonElement>("button")!.click());
    expect(run).toHaveBeenCalledOnce();
  });

  it("an empty category says which one and offers the others", () => {
    act(() =>
      root.render(
        <FindingsList query={page([])} filtered emptyAction={{ label: "Show all categories", run: () => {} }}
          categoryLabel="Bug / Quality" showReach={false} selectedId={null} onSelect={() => {}} />,
      ),
    );
    expect(host.textContent).toContain("No Bug / Quality findings. These checks can still miss issues.");
  });
});
