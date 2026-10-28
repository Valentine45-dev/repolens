// Detector fixture: every line marked `expect: <rule>` must be reported. Never executed.
const cp = require("child_process");
const { exec, execSync: run } = require("node:child_process");

function handler(req, res, db, el, user) {
  eval(req.query.code); // expect: js-eval
  const fn = new Function("a", req.body.src); // expect: js-new-function
  const g = Function(req.body.src); // expect: js-new-function

  cp.exec("ls " + req.query.dir); // expect: js-child-process-exec
  cp.execSync(`git log ${req.query.ref}`); // expect: js-child-process-exec
  exec(req.query.cmd, () => {}); // expect: js-child-process-exec
  run(user.cmd); // expect: js-child-process-exec
  require("child_process").exec(user.cmd); // expect: js-child-process-exec

  el.innerHTML = user.bio; // expect: js-inner-html
  el.outerHTML += "<b>" + user.name + "</b>"; // expect: js-inner-html
  el.innerHTML = `<p>${user.name}</p>`; // expect: js-inner-html

  db.query(`SELECT * FROM users WHERE id = ${req.params.id}`); // expect: js-sql-string
  db.query("DELETE FROM sessions WHERE user_id = " + user.id); // expect: js-sql-string
  const sql = "UPDATE accounts SET balance = " + user.balance + " WHERE id = 1"; // expect: js-sql-string
  return fn(g(sql));
}

module.exports = handler;
