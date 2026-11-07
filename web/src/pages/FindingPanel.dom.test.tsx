// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { Finding } from "../api";
import { FindingPanel } from "./Findings";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const SECRET: Finding = {
  id: 1,
  rule_id: "hardcoded-secret",
  severity: "high",
  message: "Possible hardcoded secret (secret-assignment).",
  file_id: 10,
  path: "dockerized_labs/broken_auth_lab/app.py",
  language: "python",
  line: 16,
  symbol: null,
  snippet: "app.secret_key = [redacted]",
  in_test: false,
  in_docs: false,
  placeholder: false,
  template_value: false,
  category: "security",
  node_id: 10,
};

const TEMPLATE_NOTE = "Looks like a template value; if deployed as-is, it's a publicly known key.";

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

function show(finding: Finding) {
  act(() =>
    root.render(
      <MemoryRouter>
        <FindingPanel snapshotId={2} finding={finding} rule={undefined} onClose={() => {}} />
      </MemoryRouter>,
    ),
  );
}
const notes = () => [...host.querySelectorAll(".panel-body > p.note")].map((n) => n.textContent);

describe("FindingPanel notes", () => {
  it("explains a template value in code, in the same place as the documentation note", () => {
    show({
      ...SECRET,
      template_value: true,
      message: "Possible hardcoded secret (secret-assignment); looks like a template value.",
    });
    expect(notes()).toEqual([TEMPLATE_NOTE]);
    // the note sits in the panel body directly under the header, where the documentation note is
    const body = host.querySelector(".panel-body")!;
    expect(body.firstElementChild?.textContent).toBe(TEMPLATE_NOTE);
  });

  it("shows the documentation note for documentation and no template note", () => {
    show({ ...SECRET, in_docs: true, severity: "low", path: "README.md" });
    expect(notes()).toEqual(["In documentation, so it is probably an example."]);
  });

  it("shows no template note on an ordinary secret, and no placeholder wording on a template value", () => {
    show(SECRET);
    expect(notes()).toEqual([]);
    show({ ...SECRET, template_value: true });
    expect(notes().join(" ")).not.toMatch(/does not run/);
  });

  it("shows the placeholder note, not the template note, for a placeholder in a file that does not run", () => {
    show({ ...SECRET, placeholder: true, severity: "low", path: "docs/setup.md", in_docs: true });
    expect(notes().some((n) => /does not run/.test(n ?? ""))).toBe(true);
    expect(notes()).not.toContain(TEMPLATE_NOTE);
  });
});
