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
  addEventListener(type: "message" | "error" | "messageerror", listener: (event: Event) => void): void;
}

/** A warm-up job runs our own sample, so it is allowed longer (a slow first start in Firefox). */
const WARM_TIMEOUT_MS = 30_000;

interface Job {
  id: number;
  code: string;
  lang: CodeLang;
  /** Background warm-up: lowest priority, no result, failures only noted in the console. */
  warm?: boolean;
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
  warmedUp = false;
  makeWorker = factory;
}

let warmedUp = false;

/** Start the worker and warm these grammars in the background, once per page session, so the first
 * file opened colours without the start-up wait. A file asked for meanwhile goes first.
 * Python only by default: measured on the eval PC (eval/results/screenshots-code-highlight/
 * warmup.json), warming Python cut its first file from ~0.8-1.1 s to ~0.14 s in Edge and from
 * ~1.2-2.3 s to ~0.5-0.7 s in Firefox, while warming JavaScript gave nothing (its precompiled
 * grammar has no compile step left; the cost is running it over the file). Starting the worker
 * still helps a JS-first repository. */
export function warmUpColours(langs: CodeLang[] = ["python"]): void {
  if (warmedUp) return;
  warmedUp = true;
  for (const lang of langs) {
    const job: Job = {
      id: nextId++,
      code: "",
      lang,
      warm: true,
      cancelled: false,
      resolve() {},
      reject(err) {
        console.info("Code colours warm-up did not finish; colours will start on first use.", err);
      },
    };
    queue.push(job);
  }
  pump();
}

/** Warm up once the browser is idle (after the map has drawn); never on a data-saver connection.
 * Returns a cancel for an unmount before it ran. */
export function scheduleWarmUp(): () => void {
  if (warmedUp) return () => {};
  const g = globalThis as {
    navigator?: { connection?: { saveData?: boolean } };
    requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
    cancelIdleCallback?: (handle: number) => void;
  };
  if (g.navigator?.connection?.saveData) return () => {};
  const run = () => warmUpColours();
  if (typeof g.requestIdleCallback === "function") {
    const handle = g.requestIdleCallback(run, { timeout: 5000 });
    return () => g.cancelIdleCallback?.(handle);
  }
  const handle = setTimeout(run, 1500);
  return () => clearTimeout(handle);
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
  const firstWarm = queue.findIndex((j) => j.warm);
  if (firstWarm < 0) queue.push(job);
  else queue.splice(firstWarm, 0, job); // ahead of warm-up jobs not yet sent
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
  const limit = job.warm ? WARM_TIMEOUT_MS : TIMEOUT_MS;
  timer = setTimeout(() => fail(new Error(`Colouring took longer than ${limit / 1000} s`)), limit);
  worker.postMessage(job.warm ? { id: job.id, warm: true, lang: job.lang } : { id: job.id, code: job.code, lang: job.lang });
}

function startWorker(): WorkerLike {
  const w = makeWorker();
  w.addEventListener("message", (event) => {
    if (w !== worker) return; // from a worker already replaced
    const data = (event as MessageEvent<{ id: number; lines?: ColouredLine[]; error?: string }>).data;
    const job = current;
    if (!job || data.id !== job.id) return;
    finish();
    if (data.lines) {
      if (!job.warm) remember(job, data.lines);
      job.resolve(job.cancelled ? null : data.lines);
    } else {
      job.reject(new Error(data.error ?? "Colouring failed"));
    }
    pump();
  });
  const crashed = () => {
    if (w === worker) fail(new Error("The colouring worker stopped"));
  };
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
