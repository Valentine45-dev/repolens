// Serve the bench build, open each config in a fresh headless browser with a throwaway profile,
// collect the POSTed result. Usage: node bench_run.mjs <dist dir> <out.json> [runs]
import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, existsSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, extname } from "node:path";

const [dist, outFile, runsArg] = process.argv.slice(2);
const RUNS = Number(runsArg ?? 3);
const PORT = 5199;
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".txt": "text/plain" };
let waiting = null;
const server = createServer((req, res) => {
  if (req.method === "POST" && req.url === "/result") {
    let body = "";
    req.on("data", (d) => (body += d)).on("end", () => { res.end("ok"); waiting?.(JSON.parse(body)); });
    return;
  }
  const path = join(dist, decodeURIComponent(req.url.split("?")[0]) === "/" ? "index.html" : decodeURIComponent(req.url.split("?")[0]));
  if (!existsSync(path)) { res.statusCode = 404; return res.end(); }
  res.setHeader("content-type", TYPES[extname(path)] ?? "application/octet-stream");
  res.setHeader("cache-control", "no-store");
  res.end(readFileSync(path));
});
await new Promise((r) => server.listen(PORT, "127.0.0.1", r));

const BROWSERS = {
  edge: (url, dir) => ["C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", ["--headless=new", `--user-data-dir=${dir}`, "--no-first-run", "--disable-gpu", url]],
  firefox: (url, dir) => ["C:/Program Files/Mozilla Firefox/firefox.exe", ["--headless", "-no-remote", "-profile", dir, url]],
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function once(browser, query) {
  const dir = mkdtempSync(join(tmpdir(), `bench-${browser}-`));
  const [exe, args] = BROWSERS[browser](`http://127.0.0.1:${PORT}/?${query}`, dir);
  const result = new Promise((r) => (waiting = (res) => { if (res.tag === "?" + query) r(res); }));
  const proc = spawn(exe, args, { stdio: "ignore" });
  const res = await Promise.race([result, sleep(150000).then(() => ({ error: "timeout" }))]);
  waiting = null;
  // the launched browser and its children only (it has its own throwaway profile)
  spawn("taskkill", ["/T", "/F", "/PID", String(proc.pid)], { stdio: "ignore" });
  await sleep(1500);
  try { rmSync(dir, { recursive: true, force: true }); } catch {}
  return res;
}
const out = [];
for (const browser of ["edge", "firefox"]) {
  for (let run = 1; run <= RUNS; run++) {
    for (const engine of ["regex", "pre"]) {
      for (const lang of ["python", "javascript"]) {
        for (const warm of (process.env.WARMS ?? "0").split(",")) {
          const r = await once(browser, `engine=${engine}&lang=${lang}&warm=${warm}`);
          out.push({ browser, run, ...r });
          console.log(browser, run, engine, lang, `warm=${warm}`, JSON.stringify(r));
        }
      }
    }
  }
}
writeFileSync(outFile, JSON.stringify(out, null, 2));
server.close();
