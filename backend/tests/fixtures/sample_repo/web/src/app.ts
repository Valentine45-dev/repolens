import fs from "node:fs";
import React from "react";
import { Cache, formatName as fmt } from "./lib";
import { double } from "./lib/math.js";
import * as math from "@lib/math";
import "./missing";

export class App extends Cache<string> {
  render(name: string): string {
    return fmt(name) + math.add(1, double(2));
  }
}

export const loadView = () => import("./view");

export default function main(): void {
  const app = new App();
  fs.writeFileSync("out.txt", app.render("x"));
  React.createElement("div");
}
