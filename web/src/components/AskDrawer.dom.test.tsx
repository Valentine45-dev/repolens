// @vitest-environment jsdom
// The Ask drawer inside the analysis shell, with the API mocked: nothing is ever sent to a server.
// Each test uses its own analysis id, so no test sees another's conversation (the store lives for
// the whole file, as it lives for the whole page).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { BrowserRouter, Route, Routes, useLocation, useNavigate, type NavigateFunction } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, askQuestion, getGraph, type Answer, type Graph, type SnapshotStatus } from "../api";
import { resetAskStore } from "../askStore";
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
  getGraph: vi.fn(),
  askQuestion: vi.fn(() => new Promise<Answer>((resolve) => answers.push(resolve))),
}));

// The answer text "THROW" stands in for any answer that passes the checks and still fails to draw.
vi.mock("./Markdown", () => ({
  Markdown: ({ text }: { text: string }) => {
    if (text === "THROW") throw new Error("cannot draw this answer");
    return <p>{text}</p>;
  },
}));

let host: HTMLDivElement;
let root: Root;
let client: QueryClient;
let navigate: NavigateFunction;
function Navigator() {
  navigate = useNavigate();
  return null;
}
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
  vi.mocked(getGraph).mockReset();
  vi.mocked(getGraph).mockImplementation(async () => graph(node(12, "app/real.py")));
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
  resetAskStore(); // as a new page would; the tests also use their own ids
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
          <Navigator />
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

describe("COR-08: switching from one analysis to another with the shell still mounted", () => {
  const seed = (id: number, question: string) =>
    sessionStorage.setItem(`repolens.ask.${id}`, JSON.stringify([{ id: `t${id}`, question, answer: answer(`Answer for ${id}.`) }]));
  const go = async (url: string) => {
    await act(async () => navigate(url));
    await tick();
  };

  it("shows only the second analysis's turns, and leaves the first one's where they were", async () => {
    seed(31, "Question about app31");
    await open("/a/31/explore?ask=1", (c) => c.setQueryData(["status", 32], status(32)));
    expect(turns()).toHaveLength(1);
    const listOf31 = $("#ask-drawer .drawer-body")!;
    listOf31.scrollTop = 120;
    await go("/a/32/explore?ask=1");
    expect($("#ask-drawer .drawer-body")).not.toBe(listOf31); // a fresh drawer: no scroll position carried over
    expect($("#ask-drawer h2")?.textContent).toContain("example/app32");
    expect(host.textContent).not.toContain("Question about app31");
    expect(turns()).toHaveLength(0);
    expect(sessionStorage.getItem("repolens.ask.32")).toBeNull();
    expect(JSON.parse(sessionStorage.getItem("repolens.ask.31")!)[0].question).toBe("Question about app31");
    await go("/a/31/explore?ask=1");
    expect(turns()).toHaveLength(1);
    expect(turns()[0].textContent).toContain("Question about app31");
  });

  it("files an answer under the analysis it was asked about, even after switching away", async () => {
    await open("/a/33/explore?ask=1", (c) => c.setQueryData(["status", 34], status(34)));
    await ask("Question about app33");
    await go("/a/34/explore?ask=1");
    await answerWith(answer("Answer for 33."));
    expect(turns()).toHaveLength(0);
    expect(host.textContent).not.toContain("Answer for 33.");
    await go("/a/33/explore?ask=1");
    expect(turns()[0].textContent).toContain("Answer for 33.");
  });
});

describe("a reload while a question was being answered", () => {
  it("keeps the question with a note that its answer was not received, and asks nothing again", async () => {
    sessionStorage.setItem("repolens.ask.41", JSON.stringify([
      { id: "a", question: "First question", answer: answer("First answer.") },
      { id: "b", question: "Question cut off by the reload" },
    ]));
    await open("/a/41/explore?ask=1");
    expect(turns()).toHaveLength(2);
    expect(turns()[1].textContent).toContain("Question cut off by the reload");
    expect(turns()[1].textContent).toContain("This question was interrupted by a page reload; the answer was not received.");
    expect(turns()[1].querySelector(".thinking")).toBeNull();
    typeDraft("A new question");
    expect($<HTMLButtonElement>("#ask-drawer button[type=submit]")!.disabled).toBe(false); // nothing is pending
    expect(askQuestion).not.toHaveBeenCalled();
    expect(JSON.parse(sessionStorage.getItem("repolens.ask.41")!)[1].interrupted).toBe(true);
  });
});

describe("SEC-04: saved turns that do not fit", () => {
  const boundaryPage = () => host.textContent?.includes("Something went wrong on this page.");
  const quiet = () => vi.spyOn(console, "error").mockImplementation(() => {});

  it("opens Ask with the valid turns and drops the rest from storage", async () => {
    const old = { id: "old", question: "From an older build", answer: { kind: "ai", status: "answered", answer: "No citations here." } };
    sessionStorage.setItem("repolens.ask.51", JSON.stringify([
      { id: "ok", question: "A good question", answer: answer("A good answer.") },
      old,
      { id: "bad-cite", question: "Bad citation", answer: { ...answer("x"), citations: [{ path: 1 }] } },
      "not a turn",
      { question: "no id" },
    ]));
    const spy = quiet();
    await open("/a/51/explore?ask=1");
    spy.mockRestore();
    expect(boundaryPage()).toBe(false);
    expect(turns()).toHaveLength(1);
    expect(turns()[0].textContent).toContain("A good answer.");
    expect(JSON.parse(sessionStorage.getItem("repolens.ask.51")!).map((t: { id: string }) => t.id)).toEqual(["ok"]);
  });

  it("removes a turn that still fails to draw, keeps the others and says so", async () => {
    sessionStorage.setItem("repolens.ask.52", JSON.stringify([
      { id: "ok", question: "A good question", answer: answer("A good answer.") },
      { id: "boom", question: "Breaks the drawer", answer: answer("THROW") },
    ]));
    const spy = quiet();
    await open("/a/52/explore?ask=1");
    await tick();
    spy.mockRestore();
    expect(boundaryPage()).toBe(false);
    expect(turns()).toHaveLength(1);
    expect(turns()[0].textContent).toContain("A good answer.");
    expect(host.textContent).toContain("An answer could not be shown and was removed from this conversation.");
    expect(JSON.parse(sessionStorage.getItem("repolens.ask.52")!).map((t: { id: string }) => t.id)).toEqual(["ok"]);
  });

  it("turns an answer from the server that it cannot read into one failed line", async () => {
    await open("/a/53/explore?ask=1");
    await ask("Anything?");
    const spy = quiet();
    await answerWith({ kind: "ai", status: "answered", answer: "half an answer" } as unknown as Answer);
    spy.mockRestore();
    expect(boundaryPage()).toBe(false);
    expect(turns()[0].textContent).toContain("The answer could not be shown.");
  });
});

describe("SEC-05: a link that pre-fills a question about a file", () => {
  const scopeLine = () => $(".ask-scope");
  const submit = () => $<HTMLButtonElement>("#ask-drawer button[type=submit]")!;
  const submitForm = () => act(async () => $<HTMLFormElement>("#ask-drawer form")!.requestSubmit());

  it("names the file the id belongs to, not the path in the link, and drops askpath", async () => {
    await open("/a/61/explore?ask=1&askq=About%20README.md%3A%20&askfile=12&askpath=README.md");
    await until(() => !!scopeLine()?.textContent?.includes("app/real.py"));
    expect(scopeLine()?.textContent).toContain("This question includes");
    expect(scopeLine()?.textContent).toContain("app/real.py");
    expect(scopeLine()?.textContent).not.toContain("README.md");
    expect(window.location.search).toBe("?ask=1");
    await submitForm();
    expect(askQuestion).toHaveBeenCalledWith(61, "About README.md:", 12);
  });

  it("drops a file id that is not in this analysis and says so", async () => {
    await open("/a/62/explore?ask=1&askq=Hi&askfile=99&askpath=app/real.py");
    await until(() => !!scopeLine()?.textContent?.includes("not part of this analysis"));
    expect(scopeLine()?.textContent).toContain(
      "The file in this link is not part of this analysis, so the question will not include it.",
    );
    expect(scopeLine()?.textContent).not.toContain("app/real.py");
    await submitForm();
    expect(askQuestion).toHaveBeenCalledWith(62, "Hi", undefined);
  });

  it("waits to send while the link's file is checked against the file index", async () => {
    let index!: (g: Graph) => void;
    vi.mocked(getGraph).mockImplementation(() => new Promise<Graph>((resolve) => (index = resolve)));
    await open("/a/63/explore?ask=1&askq=Hi&askfile=12");
    expect(scopeLine()?.getAttribute("aria-busy")).toBe("true");
    expect(scopeLine()?.textContent).toContain("a file that is being checked");
    expect(submit().disabled).toBe(true);
    await act(async () => textarea().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })));
    await submitForm();
    expect(askQuestion).not.toHaveBeenCalled();
    await act(async () => index(graph(node(12, "app/real.py"))));
    await tick();
    expect(scopeLine()?.textContent).toContain("app/real.py");
    expect(submit().disabled).toBe(false);
    await submitForm();
    expect(askQuestion).toHaveBeenCalledWith(63, "Hi", 12);
  });

  it("never waits for the file index for a question without a file", async () => {
    vi.mocked(getGraph).mockImplementation(() => new Promise<Graph>(() => {})); // never answers
    await open("/a/64/explore?ask=1");
    await ask("What does this repo do?");
    expect(askQuestion).toHaveBeenCalledWith(64, "What does this repo do?", undefined);
  });

  it("never waits for \"Ask about this\" on a file the Explorer's index already has", async () => {
    vi.mocked(getGraph).mockImplementation(() => new Promise<Graph>(() => {})); // never answers
    // The Explorer's own list (tests hidden) is already loaded, as it is when its panel shows a file.
    await open("/a/65/explore?node=12", (c) => c.setQueryData(["graph", 65, false, false], graph(node(12, "app/real.py"))));
    await act(async () => navigate("/a/65/explore?node=12&ask=1&askq=About%20app%2Freal.py%3A%20&askfile=12", { replace: true }));
    await tick();
    expect(scopeLine()?.getAttribute("aria-busy")).toBeNull();
    expect(scopeLine()?.textContent).toContain("app/real.py");
    typeDraft("About app/real.py: what is it?");
    expect(submit().disabled).toBe(false);
    await submitForm();
    expect(askQuestion).toHaveBeenCalledWith(65, "About app/real.py: what is it?", 12);
  });
});

describe("the unread dot: a question that finishes while Ask is out of sight", () => {
  const dot = (sel: string) => $(`${sel} .unread-dot`);
  const said = () => [...host.querySelectorAll("[role=status]")].map((e) => e.textContent).join(" ");
  const tab = (name: string) => [...host.querySelectorAll<HTMLElement>(".right-tabs [role=tab]")].find((t) => t.textContent?.startsWith(name))!;

  it("shows on the Ask button when the answer lands with Ask closed, and clears when Ask is opened", async () => {
    await open("/a/71/explore?ask=1");
    await ask("Where is the login view?");
    await toggleAsk();
    expect(dot(".analysis-ask")).toBeNull(); // nothing yet: still being answered
    await answerWith(answer("In app/views.py."));
    expect(dot(".analysis-ask")).not.toBeNull();
    expect(askButton().textContent).toBe("Ask, new answer"); // its accessible name
    expect(askButton().title).toBe("A new answer is in Ask");
    expect(said()).toContain("Answer ready in Ask.");
    await toggleAsk();
    expect(dot(".analysis-ask")).toBeNull();
    expect(askButton().textContent).toBe("Ask");
    expect(said()).not.toContain("Answer ready in Ask.");
    await toggleAsk(); // closing again does not bring it back
    expect(dot(".analysis-ask")).toBeNull();
  });

  it("does not show for an answer that lands while Ask is on screen", async () => {
    await open("/a/72/explore?ask=1");
    await ask("Where is the login view?");
    await answerWith(answer("In app/views.py."));
    await toggleAsk();
    expect(dot(".analysis-ask")).toBeNull();
  });

  it("says when a question failed while Ask was closed", async () => {
    let fail!: (e: Error) => void;
    vi.mocked(askQuestion).mockImplementationOnce(() => new Promise<Answer>((_, reject) => (fail = reject)));
    await open("/a/74/explore?ask=1");
    await ask("Where is the login view?");
    await toggleAsk();
    await act(async () => fail(new Error("Request failed (500).")));
    expect(askButton().textContent).toBe("Ask, question failed");
    expect(said()).toContain("A question in Ask failed.");
  });

  it("below 1600px shows on the Ask tab while the File tab is in front, and clears when Ask is shown", async () => {
    midWidth = true;
    await open("/a/73/explore?ask=1&node=12");
    expect(tab("File").getAttribute("aria-selected")).toBe("true"); // a link that opens both shows the file
    await click(tab("Ask"));
    await ask("What does app/real.py do?");
    await click(tab("File")); // Ask goes behind the file while it is answered
    await answerWith(answer("It serves the views."));
    expect(dot(".right-tabs")).not.toBeNull();
    expect(tab("Ask").textContent).toBe("Ask, new answer");
    expect(dot(".analysis-ask")).toBeNull(); // the header button would close Ask: no dot there
    await click(tab("Ask"));
    expect(dot(".right-tabs")).toBeNull();
    expect(tab("Ask").textContent).toBe("Ask");
  });
});

describe("a reload while the browser cancels the question's request", () => {
  const UNREACHABLE = "Could not reach the RepoLens server. Check that the API is running.";
  // What the browser does on a reload: the page starts to go, then the request fails (fetch
  // rejects, which api.ts reports as the server being unreachable).
  async function askThenFail(id: number, leaving: string[]) {
    let fail!: (e: Error) => void;
    vi.mocked(askQuestion).mockImplementationOnce(() => new Promise<Answer>((_, reject) => (fail = reject)));
    await open(`/a/${id}/explore?ask=1`);
    await ask("Question cut off by the reload");
    for (const type of leaving) act(() => window.dispatchEvent(new Event(type)));
    await act(async () => fail(new ApiError(UNREACHABLE, 0, true)));
  }
  /** The old page is gone (memory too); the new one reads what was saved. */
  async function reload(id: number) {
    act(() => root.unmount());
    resetAskStore();
    root = createRoot(host);
    await open(`/a/${id}/explore?ask=1`);
  }

  it.each([["beforeunload"], ["pagehide"]])("is not saved as a failure when the request fails after %s", async (type) => {
    const id = type === "beforeunload" ? 81 : 82;
    await askThenFail(id, [type]);
    const saved = JSON.parse(sessionStorage.getItem(`repolens.ask.${id}`)!);
    expect(saved[0].error).toBeUndefined();
    await reload(id);
    expect(turns()).toHaveLength(1);
    expect(turns()[0].textContent).toContain("This question was interrupted by a page reload; the answer was not received.");
    expect(host.textContent).not.toContain(UNREACHABLE);
  });

  it("still shows the server error when the request fails while the page stays open", async () => {
    await askThenFail(83, []);
    expect(turns()[0].textContent).toContain(UNREACHABLE);
    expect(JSON.parse(sessionStorage.getItem("repolens.ask.83")!)[0].error).toBe(UNREACHABLE);
  });

  it("shows the server error after a short wait if the page did not go after all", async () => {
    // e.g. a download link: beforeunload fires but the page stays
    let fail!: (e: Error) => void;
    vi.mocked(askQuestion).mockImplementationOnce(() => new Promise<Answer>((_, reject) => (fail = reject)));
    await open("/a/84/explore?ask=1");
    await ask("Question asked before a download");
    act(() => window.dispatchEvent(new Event("beforeunload")));
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      await act(async () => fail(new ApiError(UNREACHABLE, 0, true)));
      expect(turns()[0].textContent).not.toContain(UNREACHABLE); // still "Working on it…"
      await act(async () => vi.advanceTimersByTime(3000));
    } finally {
      vi.useRealTimers();
    }
    await tick();
    expect(turns()[0].textContent).toContain(UNREACHABLE);
    // The page did not go, so the next failure is reported at once again.
    vi.mocked(askQuestion).mockImplementationOnce(() => Promise.reject(new ApiError(UNREACHABLE, 0, true)));
    await ask("Next question");
    await tick();
    expect(turns()[1].textContent).toContain(UNREACHABLE);
  });
});

describe("Part A: documentation citations", () => {
  it("a doc chip says documentation and opens the doc panel link, a code chip the file node", async () => {
    await open("/a/93/explore?ask=1");
    await ask("What is this project for?");
    await answerWith({
      ...answer("It is a sample."),
      citations: [
        { path: "README.md", start_line: 3, end_line: 9, file_id: 40, symbol_id: null, in_test: false, source: "doc" },
        { path: "app/real.py", start_line: 1, end_line: 2, file_id: 12, symbol_id: 1, in_test: false, source: "code" },
      ],
    });
    const chips = [...turns()[0].querySelectorAll<HTMLAnchorElement>(".citation")];
    expect(chips).toHaveLength(2);
    const [doc, code] = chips;
    expect(doc.dataset.source).toBe("doc");
    expect(doc.textContent).toContain("README.md:3-9");
    expect(doc.textContent).toContain("documentation");
    expect(new URL(doc.href).searchParams.get("doc")).toBe("40");
    expect(new URL(doc.href).searchParams.get("node")).toBeNull();
    expect(new URL(doc.href).searchParams.get("lines")).toBe("3-9");
    expect(code.textContent).not.toContain("documentation");
    expect(new URL(code.href).searchParams.get("node")).toBe("12");
  });
});

describe("Part C: claim check note", () => {
  it("shows the server's note beside the answer, not inside it", async () => {
    await open("/a/94/explore?ask=1");
    await ask("How is a user created?");
    const note = "1 statement removed: the quoted evidence was not found in the cited lines.";
    await answerWith({ ...answer("It creates a user."), status: "unverified", dropped: 1, claims: { total: 2, kept: 1, removed: 1, note } });
    const t = turns()[0];
    const shown = t.querySelector('[data-testid="claims-note"]')!;
    expect(shown.textContent).toContain(note);
    expect(shown.textContent).toContain("not that it supports the statement");
    // the answer text itself is drawn as sent: the note is not part of it
    expect([...t.querySelectorAll("p")].some((p) => p.textContent === "It creates a user.")).toBe(true);
  });

  it("says nothing about claims when the check was off", async () => {
    await open("/a/95/explore?ask=1");
    await ask("How is a user created?");
    await answerWith({ ...answer("It creates a user."), claims: null });
    expect(turns()[0].querySelector('[data-testid="claims-note"]')).toBeNull();
  });
});

describe("A-01: an answer with some sources removed", () => {
  const NONE = "None of the sources this answer cited could be verified";

  it("says which sources were removed, keeps the verified chips, and never says none verified", async () => {
    await open("/a/91/explore?ask=1");
    await ask("How is a user created?");
    await answerWith({ ...answer("A. B. C."), status: "unverified", dropped: 2 });
    const t = turns()[0];
    expect(t.textContent).toContain("2 sources this answer cited could not be verified and were removed.");
    expect(t.textContent).toContain("The sentences they were attached to are not backed by a source.");
    expect(t.textContent).not.toContain(NONE);
    expect(t.querySelectorAll(".citation")).toHaveLength(1); // the verified one stays a chip
    expect(t.textContent).not.toContain("sources could not be verified and were removed."); // no second caption
  });

  it("keeps the 'none verified' line when nothing survived", async () => {
    await open("/a/92/explore?ask=1");
    await ask("How is a user created?");
    await answerWith({ ...answer("A."), status: "unverified", dropped: 1, citations: [] });
    expect(turns()[0].textContent).toContain(NONE);
  });
});
