const util = require("./util");
const { join, basename: base } = require("path");

module.exports = function legacy(p) {
  return util.trim(join(base(p), "x"));
};
