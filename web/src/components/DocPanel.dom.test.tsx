// @vitest-environment jsdom
// The documentation panel: plain text only (never HTML from the file), cited lines highlighted.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { getFile } from "../api";
import { DocPanel } from "./DocPanel";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  getFile: vi.fn(),
}));

const README = [
  "# Sample",
  "",
  "<script>window.__docPanelRan = true</script>",
  '<img src=x onerror="window.__docPanelRan = true">',
  "**bold** and [a link](https://example.com)",
  "end",
].join("\n");

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  HTMLElement.prototype.scrollTo = function () {} as typeof HTMLElement.prototype.scrollTo;
  window.matchMedia = ((query: string) => ({
    matches: false, media: query, addEventListener() {}, removeEventListener() {},
  })) as unknown as typeof window.matchMedia;
  vi.mocked(getFile).mockResolvedValue({
    id: 40, path: "README.md", language: null, loc: 6, content: README, symbols: [], findings: [],
    external_imports: [], unresolved_imports: [],
  } as unknown as Awaited<ReturnType<typeof getFile>>);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

async function render(onClose = () => {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () =>
    root.render(
      <QueryClientProvider client={client}>
        <DocPanel snapshotId={1} fileId={40} highlight={{ start: 3, end: 4 }} reveal={null} hidden={false} onClose={onClose} />
      </QueryClientProvider>,
    ),
  );
  for (let i = 0; i < 20 && !host.querySelector(".code-text"); i++) {
    await act(async () => new Promise((r) => setTimeout(r, 10)));
  }
}

it("shows Markdown with HTML in it as plain text, never as elements", async () => {
  await render();
  const text = host.querySelector(".code-text")!;
  expect(text.textContent).toContain("<script>window.__docPanelRan = true</script>");
  expect(text.textContent).toContain("**bold** and [a link](https://example.com)");
  expect(host.querySelector("script, img, a, strong, h1")).toBeNull();
  expect((window as { __docPanelRan?: boolean }).__docPanelRan).toBeUndefined();
});

it("is labelled documentation, highlights the cited lines and closes", async () => {
  const onClose = vi.fn();
  await render(onClose);
  expect(host.querySelector('[data-testid="doc-panel"]')!.textContent).toContain("README.md");
  expect(host.querySelector('.tag[data-kind="doc"]')!.textContent).toBe("documentation");
  expect(host.querySelector(".code")!.getAttribute("aria-label")).toBe("File contents, lines 3 to 4 highlighted");
  expect(host.querySelector(".panel-facts, [role=tablist]")).toBeNull(); // no Used by / Uses
  await act(async () => host.querySelector<HTMLButtonElement>(".panel-header button")!.click());
  expect(onClose).toHaveBeenCalled();
});
