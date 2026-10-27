// Detector fixture (TypeScript, ESM imports). Every `expect: <rule>` line must be reported.
import * as childProcess from "child_process";
import cp from "node:child_process";
import { execSync as runSync } from "child_process";

interface Request {
  query: Record<string, string>;
}

export function handler(req: Request, el: HTMLElement, db: { query(sql: string): void }): void {
  const value: unknown = eval(req.query.expr); // expect: js-eval
  childProcess.exec(`convert ${req.query.file} out.png`); // expect: js-child-process-exec
  cp.execSync(req.query.cmd as string); // expect: js-child-process-exec
  runSync(req.query.cmd); // expect: js-child-process-exec
  el.innerHTML = String(value); // expect: js-inner-html
  db.query(`INSERT INTO log (msg) VALUES ('${req.query.msg}')`); // expect: js-sql-string
}
