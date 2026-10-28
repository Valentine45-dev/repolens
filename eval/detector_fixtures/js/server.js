// Detector eval fixture: a small Express-style server. Never executed, never installed.
//
// Labels are trailing comments: a line marked "vuln" plus a category is an issue a reviewer
// should see; "safe" plus a category marks code that looks similar but is fine. Categories:
// code-injection, shell-command, html-injection, sql-injection, hardcoded-secret.

const { exec, execSync, execFile } = require("child_process");
const db = require("./db");

const sessionSecret = "f0e1d2c3b4a59687"; // vuln: hardcoded-secret
const dbPassword = process.env.DB_PASSWORD; // safe: hardcoded-secret
const apiToken = "REPLACE_ME"; // safe: hardcoded-secret

function calculate(req, res) {
  res.send(String(eval(req.query.expr))); // vuln: code-injection
}

function version() {
  return eval("1 + 1"); // safe: code-injection
}

function compileFilter(body) {
  return new Function("item", body); // vuln: code-injection
}

const identity = new Function("x", "return x"); // safe: code-injection

function backup(dir) {
  exec(`tar czf backup.tgz ${dir}`); // vuln: shell-command
}

function ping(host, cb) {
  exec("ping -c 1 " + host, cb); // vuln: shell-command
}

function status() {
  return execSync("git status --short"); // safe: shell-command
}

function listDir(dir, cb) {
  execFile("ls", ["-l", dir], cb); // safe: shell-command
}

function showName(el, name) {
  el.innerHTML = name; // vuln: html-injection
}

function showGreeting(el, name) {
  el.outerHTML = `<p>Hello ${name}</p>`; // vuln: html-injection
}

function showBanner(el) {
  el.innerHTML = "<b>Welcome</b>"; // safe: html-injection
}

function showText(el, name) {
  el.textContent = name; // safe: html-injection
}

function findUser(id) {
  return db.query(`SELECT * FROM users WHERE id = ${id}`); // vuln: sql-injection
}

function findByName(name) {
  return db.query("SELECT * FROM users WHERE name = '" + name + "'"); // vuln: sql-injection
}

function findUserSafely(id) {
  return db.query("SELECT * FROM users WHERE id = $1", [id]); // safe: sql-injection
}

module.exports = {
  sessionSecret, dbPassword, apiToken, calculate, version, compileFilter, identity, backup,
  ping, status, listDir, showName, showGreeting, showBanner, showText, findUser, findByName,
  findUserSafely,
};
