// Detector fixture: nothing in this file may be reported. Never executed.
const { exec, execFile, spawn } = require("child_process");

function safe(el, db, user, model) {
  model.eval(); // a method named eval, not the global
  JSON.parse(user.json);
  exec("git status"); // constant command
  exec(`npm test`); // constant template literal
  execFile("git", ["log", user.ref]); // no shell
  spawn("ls", [user.dir]);
  el.innerHTML = ""; // constant
  el.innerHTML = "<p>Loading</p>";
  el.innerHTML = "<style>.a{}</style>" + "<div class='a'></div>"; // constants joined
  exec("git " + "status"); // constants joined
  el.textContent = user.bio; // text, not HTML
  db.query("SELECT * FROM users WHERE id = $1", [user.id]); // parameters
  db.query(`SELECT count(*) FROM users`); // constant SQL
  const msg = `Hello ${user.name}, select an item from the list`; // prose
  const label = "Update " + user.name + " settings"; // prose
  return [msg, label];
}

module.exports = safe;
