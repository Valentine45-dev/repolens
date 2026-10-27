const http = require("http");

const app = {};
const res = {};

app.listen = function listen(port) {
  const server = http.createServer(this.handle);
  return server.listen(port);
};

app.handle = (req) => {
  res.send(req.url);
};

res.send = function send(body) {
  return body;
};

exports.version = () => "1.0";

module.exports.create = function () {
  return Object.create(app);
};

module.exports = {
  app,
  start(port) {
    return app.listen(port);
  },
  stop: function () {},
  ping: () => "pong",
};
