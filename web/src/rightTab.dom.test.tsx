// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { type RightTab, useRightTab } from "./rightTab";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
let current: RightTab = "panel";
let choose: (t: RightTab) => void = () => {};
beforeEach(() => {
  host = document.createElement("div");
  root = createRoot(host);
});
afterEach(() => act(() => root.unmount()));

function Probe(props: { panel: string | null; ask: boolean; prefill: string | null }) {
  const [tab, setTab] = useRightTab(props.panel, props.ask, props.prefill);
  current = tab;
  choose = setTab;
  return null;
}
const show = (panel: string | null, ask: boolean, prefill: string | null = null) =>
  act(() => root.render(<Probe panel={panel} ask={ask} prefill={prefill} />));

describe("which side panel is in front when Ask and a panel share a column", () => {
  it("a link that opens both shows the panel first", () => {
    show("789", true);
    expect(current).toBe("panel");
  });

  it("opening Ask brings Ask to the front; picking another file brings the file back", () => {
    show("789", false);
    show("789", true);
    expect(current).toBe("ask");
    show("790", true);
    expect(current).toBe("panel");
  });

  it("'Ask about this' (a new prefill) brings Ask to the front", () => {
    show("789", true);
    show("789", true, "About app.py: ");
    expect(current).toBe("ask");
  });

  it("the user's choice sticks until something new is opened", () => {
    show("789", true);
    act(() => choose("ask"));
    show("789", true);
    expect(current).toBe("ask");
  });
});
