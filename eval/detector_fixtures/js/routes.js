// Detector eval fixture 2: Express route handlers. Never executed, never installed.
//
// Added after run 1 (commit 0403bcb): fixture 1 (server.js) passes plain function parameters
// into its sinks, but Semgrep's p/javascript rules are mostly taint rules that need input from
// a request (req.query, req.body, req.params) or the browser location to reach the sink. Here
// every dangerous value comes from such a source. Written and labelled before any tool was
// run on it; fixture 1 and its results are unchanged.
//
// Labels are trailing comments: a line marked "vuln" plus a category is an issue a reviewer
// should see; "safe" plus a category marks code that looks similar but is fine. Categories:
// code-injection, shell-command, html-injection, sql-injection, hardcoded-secret.

const express = require("express");
const jwt = require("jsonwebtoken");
const mysql = require("mysql");
const { exec, execFile } = require("child_process");

const app = express();
const connection = mysql.createConnection({ host: "db", user: "app", password: process.env.DB_PASSWORD }); // safe: hardcoded-secret
const jwtSecret = "s3cr3t-signing-key-123"; // vuln: hardcoded-secret

app.get("/token", (req, res) => {
  res.send(jwt.sign({ id: req.query.id }, "inline-signing-key-456")); // vuln: hardcoded-secret
});

app.get("/session", (req, res) => {
  res.send(jwt.sign({ id: req.query.id }, jwtSecret));
});

app.get("/calc", (req, res) => {
  res.json({ value: eval(req.query.expr) }); // vuln: code-injection
});

app.post("/filter", (req, res) => {
  const keep = new Function("item", req.body.filter); // vuln: code-injection
  res.json([1, 2, 3].filter(keep));
});

app.get("/two", (req, res) => {
  res.json({ value: eval("1 + 1") }); // safe: code-injection
});

app.get("/ping", (req, res) => {
  exec("ping -c 1 " + req.query.host, (err, out) => res.send(out)); // vuln: shell-command
});

app.get("/archive/:name", (req, res) => {
  exec(`tar czf /tmp/${req.params.name}.tgz /data`, () => res.end()); // vuln: shell-command
});

app.get("/list", (req, res) => {
  execFile("ls", ["-l", req.query.dir], (err, out) => res.send(out)); // safe: shell-command
});

app.get("/user", (req, res) => {
  connection.query("SELECT * FROM users WHERE id = " + req.query.id, (e, rows) => res.json(rows)); // vuln: sql-injection
});

app.get("/user-by-name", (req, res) => {
  connection.query(`SELECT * FROM users WHERE name = '${req.query.name}'`, (e, rows) => res.json(rows)); // vuln: sql-injection
});

app.get("/user-safe", (req, res) => {
  connection.query("SELECT * FROM users WHERE id = ?", [req.query.id], (e, rows) => res.json(rows)); // safe: sql-injection
});

app.get("/hello", (req, res) => {
  res.send("<h1>Hello " + req.query.name + "</h1>"); // vuln: html-injection
});

app.get("/hello-static", (req, res) => {
  res.send("<h1>Hello</h1>"); // safe: html-injection
});

// Browser code in the same file, with the page URL as the source.
function showSearch() {
  const q = new URLSearchParams(window.location.search).get("q");
  document.getElementById("results").innerHTML = "Results for " + q; // vuln: html-injection
  document.getElementById("title").textContent = q; // safe: html-injection
}

module.exports = { app, showSearch };
