// The page's side of code colouring. One long-lived worker (codeColours.worker.ts) holds the
// highlighter for every file; it is made on the first request, so Shiki is only fetched when a code
// view first needs it, and replaced only after a timeout or a crash. Requests go one at a time; a
// cancelled request that has not been sent is dropped, and one already sent is answered with null
// (a stale result never reaches the code view that asked, or any other).
import type { CodeLang, ColouredLine } from "./codeRoles";

/** No answer by then: the worker is stopped (it may be stuck on a pathological line) and the file
 * stays plain. The next request gets a new worker. */
export const TIMEOUT_MS = 10_000;
const CACHE_SIZE = 6; // recent results, so a tab switch or reopening a file does not tokenise again

export interface ColourRequest {
  id: number;
  /** The coloured lines; null when cancelled before the answer came. Rejects on failure. */
  promise: Promise<ColouredLine[] | null>;
  cancel(): void;
}

interface WorkerLike {
  postMessage(message: unknown): void;
  terminate(): void;
  addEventListener(type: "message" | "error" | "messageerror", listener: (event: never) => void): void;
}

interface Job {
  id: number;
  code: string;
  lang: CodeLang;
  cancelled: boolean;
  resolve(lines: ColouredLine[] | null): void;
  reject(err: Error): void;
}

function defaultWorker(): WorkerLike {
  if (typeof Worker === "undefined") throw new Error("Web Workers are not available");
  return new Worker(new URL("./codeColours.worker.ts", import.meta.url), { type: "module" });
}

let makeWorker: () => WorkerLike = defaultWorker;
let worker: WorkerLike | null = null;
let current: Job | null = null;
let timer: ReturnType<typeof setTimeout> | null = null;
const queue: Job[] = [];
const cache = new Map<string, ColouredLine[]>();
let nextId = 1;

/** Tests: use a fake worker and start from a clean state. */
export function resetForTests(factory: () => WorkerLike = defaultWorker): void {
  worker?.terminate();
  worker = null;
  current = null;
  if (timer) clearTimeout(timer);
  timer = null;
  queue.length = 0;
  cache.clear();
  makeWorker = factory;
}

const cacheKey = (code: string, lang: CodeLang) => `${lang}\u0000${code}`;

export function requestColours(code: string, lang: CodeLang): ColourRequest {
  const id = nextId++;
  const hit = cache.get(cacheKey(code, lang));
  if (hit) {
    return { id, promise: Promise.resolve(hit), cancel() {} };
  }
  let job!: Job;
  const promise = new Promise<ColouredLine[] | null>((resolve, reject) => {
    job = { id, code, lang, cancelled: false, resolve, reject };
  });
  queue.push(job);
  pump();
  return {
    id,
    promise,
    cancel() {
      if (job.cancelled) return;
      job.cancelled = true;
      const i = queue.indexOf(job);
      if (i >= 0) queue.splice(i, 1); // never sent
      job.resolve(null); // sent: its answer will be dropped
    },
  };
}

function pump(): void {
  if (current || queue.length === 0) return;
  const job = queue.shift()!;
  try {
    if (!worker) worker = startWorker();
  } catch (err) {
    job.reject(err instanceof Error ? err : new Error(String(err)));
    pump();
    return;
  }
  current = job;
  timer = setTimeout(() => fail(new Error(`Colouring took longer than ${TIMEOUT_MS / 1000} s`)), TIMEOUT_MS);
  worker.postMessage({ id: job.id, code: job.code, lang: job.lang });
}

function startWorker(): WorkerLike {
  const w = makeWorker();
  w.addEventListener("message", ((event: MessageEvent<{ id: number; lines?: ColouredLine[]; error?: string }>) => {
    if (w !== worker) return; // from a worker already replaced
    const job = current;
    if (!job || event.data.id !== job.id) return;
    finish();
    if (event.data.lines) {
      remember(job, event.data.lines);
      job.resolve(job.cancelled ? null : event.data.lines);
    } else {
      job.reject(new Error(event.data.error ?? "Colouring failed"));
    }
    pump();
  }) as never);
  const crashed = (() => {
    if (w === worker) fail(new Error("The colouring worker stopped"));
  }) as never;
  w.addEventListener("error", crashed);
  w.addEventListener("messageerror", crashed);
  return w;
}

function finish(): void {
  if (timer) clearTimeout(timer);
  timer = null;
  current = null;
}

/** Timeout or crash: stop this worker; the next request starts a new one. */
function fail(err: Error): void {
  const job = current;
  finish();
  worker?.terminate();
  worker = null;
  job?.reject(err);
  pump();
}

function remember(job: Job, lines: ColouredLine[]): void {
  const key = cacheKey(job.code, job.lang);
  cache.delete(key);
  cache.set(key, lines);
  if (cache.size > CACHE_SIZE) cache.delete(cache.keys().next().value!);
}
