// @vitest-environment jsdom
// The Ask drawer inside the analysis shell, with the API mocked: nothing is ever sent to a server.
// Each test uses its own analysis id, so no test sees another's conversation (the store lives for
// the whole file, as it lives for the whole page).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { askQuestion, getGraph, type Answer, type Graph, type SnapshotStatus } from "../api";
import { AnalysisShell } from "./AnalysisShell";
import { ErrorBoundary } from "./ErrorBoundary";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const status = (id: number): SnapshotStatus => ({
  snapshot_id: id, url: `https://github.com/example/app${id}`, commit_sha: "46fef968f3f44d1191363baf936aaa3335dc5c6d",
  job_id: 1, status: "done", stage: "done", percent: 100, error: null, progress: null, receipt: null,
  features: { ask: true, ask_reason: null, ai: true, search: "ready", search_progress: null, search_error: null, retry_search: false },
});
const answer = (text: string): Answer => ({
  kind: "ai", status: "answered", answer: text, dropped: 0, results: [], prompt_version: "test",
  retrieval: { sent: 1, used_test_code: false, from_graph: 0 },
  citations: [{ path: "app/real.py", start_line: 1, end_line: 2, file_id: 12, symbol_id: 1, in_test: false }],
});
const node = (id: number, path: string) => ({
  id, symbol_id: id, path, language: "python", loc: 3, external_imports: 0, unresolved_imports: 0, findings: 0,
});
const graph = (...nodes: ReturnType<typeof node>[]): Graph =>
  ({ snapshot_id: 0, min_confidence: 0.9, exclude_tests: false, hidden_files: 0, nodes, edges: [] }) as unknown as Graph;

// Every question waits until the test answers it.
let answers: ((a: Answer) => void)[] = [];
vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  getStatus: vi.fn(async (id: number) => status(id)),
  getFindings: vi.fn(async () => ({ total: 0, limit: 1, offset: 0, items: [], notes: [], counts: { total: 0 } })),
  getGraph: vi.fn(async () => graph(node(12, "app/real.py"))),
  askQuestion: vi.fn(() => new Promise<Answer>((resolve) => answers.push(resolve))),
}));

let host: HTMLDivElement;
let root: Root;
let client: QueryClient;
let midWidth = false;
function App() {
  const location = useLocation();
  return (
    <ErrorBoundary resetKey={location.pathname}>
      <Routes>
        <Route path="/a/:id" element={<AnalysisShell />}>
          <Route path="explore" element={<p>map</p>} />
        </Route>
      </Routes>
    </ErrorBoundary>
  );
}

beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  answers = [];
  midWidth = false;
  vi.mocked(askQuestion).mockClear();
  vi.mocked(getGraph).mockClear();
  window.matchMedia = ((query: string) => ({
    matches: query === "(min-width: 901px) and (max-width: 1599px)" ? midWidth : false,
    media: query,
    addEventListener() {},
    removeEventListener() {},
  })) as unknown as typeof window.matchMedia;
  HTMLElement.prototype.scrollTo = function () {} as typeof HTMLElement.prototype.scrollTo;
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  sessionStorage.clear();
});

const tick = () => act(async () => new Promise((r) => setTimeout(r, 10)));
async function until(check: () => boolean) {
  for (let i = 0; i < 50 && !check(); i++) await tick();
}
/** The real address bar (useSetParams reads it), so BrowserRouter on jsdom's history. */
async function open(url: string, prepare?: (client: QueryClient) => void) {
  window.history.replaceState(null, "", url);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  prepare?.(client);
  await act(async () =>
    root.render(
      <QueryClientProvider client={client}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>,
    ),
  );
  await until(() => !!host.querySelector("#ask-drawer") || !!host.querySelector(".analysis-ask"));
  await tick();
}
const $ = <T extends Element = HTMLElement>(sel: string) => host.querySelector<T>(sel);
const drawer = () => $("#ask-drawer");
const askButton = () => $<HTMLButtonElement>(".analysis-ask")!;
const turns = () => [...host.querySelectorAll("#ask-drawer .turn")];
const click = (el: Element) => act(async () => (el as HTMLElement).click());
const textarea = () => $<HTMLTextAreaElement>("#ask-drawer textarea")!;
function typeDraft(text: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
  act(() => {
    setter.call(textarea(), text);
    textarea().dispatchEvent(new Event("input", { bubbles: true }));
  });
}
async function ask(text: string) {
  typeDraft(text);
  await act(async () => $<HTMLFormElement>("#ask-drawer form")!.requestSubmit());
}
async function toggleAsk() {
  await click(askButton());
  await tick();
}
const answerWith = (a: Answer) => act(async () => answers.shift()!(a));

describe("COR-01: closing Ask while a question is answered", () => {
  it("keeps the question and its answer, and sends the question once", async () => {
    await open("/a/21/explore?ask=1");
    await ask("Where is the login view?");
    expect(turns()).toHaveLength(1);
    await toggleAsk(); // close while "Working on it…"
    expect(drawer()).toBeNull();
    await answerWith(answer("It is in app/views.py."));
    await toggleAsk(); // open again
    expect(turns()).toHaveLength(1);
    expect(turns()[0].textContent).toContain("Where is the login view?");
    expect(turns()[0].textContent).toContain("It is in app/views.py.");
    expect(askQuestion).toHaveBeenCalledTimes(1);
    expect(JSON.parse(sessionStorage.getItem("repolens.ask.21")!)[0].answer.answer).toBe("It is in app/views.py.");
  });

  it("shows the question still being worked on when Ask is opened again before the answer", async () => {
    await open("/a/24/explore?ask=1");
    await ask("What does app/real.py do?");
    await toggleAsk();
    await toggleAsk();
    expect(turns()).toHaveLength(1);
    expect(turns()[0].querySelector(".thinking")).not.toBeNull();
    expect($<HTMLButtonElement>("#ask-drawer button[type=submit]")!.disabled).toBe(true); // one at a time
    await answerWith(answer("Done."));
    expect(turns()[0].textContent).toContain("Done.");
    expect(askQuestion).toHaveBeenCalledTimes(1);
  });

  it("keeps a half-typed question when Ask is closed and opened again", async () => {
    await open("/a/22/explore?ask=1");
    typeDraft("half-typed question");
    await toggleAsk();
    await toggleAsk();
    expect(textarea().value).toBe("half-typed question");
  });

  it("keeps the draft when Esc in the question box closes Ask", async () => {
    await open("/a/23/explore?ask=1");
    typeDraft("about the settings");
    textarea().focus();
    await act(async () => textarea().dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true })));
    expect(drawer()).toBeNull();
    await toggleAsk();
    expect(textarea().value).toBe("about the settings");
  });
});
