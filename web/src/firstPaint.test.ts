// index.html paints a page-shaped skeleton before any script loads. It is a copy of the real
// markup, so these tests catch it drifting: the text it shows as real must be the app's text, and
// every class it uses must exist in the stylesheet.
import { describe, expect, it } from "vitest";

import { dashedText, FLAT_SOLID, MAP_SOLID } from "./legendText";

// @ts-expect-error node:fs has no type declarations here; the tests run in Node
const { readFileSync } = await import("node:fs");
const read = (rel: string): string => readFileSync(new URL(rel, import.meta.url), "utf8");
const html = read("../index.html");
const home = read("./pages/Home.tsx");
const findings = read("./pages/Findings.tsx");
const css = read("./styles.css");
const squash = (s: string) => s.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();

function template(id: string): string {
  const open = html.indexOf(`<template id="${id}">`);
  if (open === -1) throw new Error(`no template ${id}`);
  const start = html.indexOf(">", open) + 1;
  return html.slice(start, html.indexOf("</template>", start));
}

describe("first paint templates", () => {
  it("has one for each kind of page", () => {
    for (const id of ["fp-topbar", "fp-home", "fp-explore", "fp-findings", "fp-plain", "fp-analysis-head"]) {
      expect(template(id).length).toBeGreaterThan(20);
    }
  });

  it("the home page shows the app's own words", () => {
    const text = squash(template("fp-home"));
    expect(text).toContain("Understand a codebase before you read it.");
    expect(home).toContain("Understand a codebase before you read it.");
    const lede = "RepoLens maps how the files of a public GitHub repository import and call each other. Deep analysis for Python and JavaScript/TypeScript.";
    expect(text).toContain(lede);
    expect(squash(home).replace(/\{" "\}/g, " ")).toContain(lede);
    const message = "Public GitHub repositories only · up to 2,000 files · files over 1 MB are skipped";
    expect(text).toContain(message);
    expect(home).toContain(message);
  });

  it("the example chips are the app's examples", () => {
    const fromApp = [...home.matchAll(/url: "https:\/\/github\.com\/([^"]+)"/g)].map((m) => m[1]);
    const fromHtml = [...template("fp-home").matchAll(/<button type="button" class="chip">([^<]+)<\/button>/g)].map(
      (m) => m[1],
    );
    expect(fromApp.length).toBeGreaterThan(0);
    expect(fromHtml).toEqual(fromApp);
  });

  it("the findings page shows the app's heading text", () => {
    const caption = "These are rule-based checks. They can miss issues and can flag safe code. Review each one.";
    expect(squash(template("fp-findings"))).toContain(caption);
    expect(squash(findings)).toContain(caption);
  });

  it("every class it uses is in the stylesheet", () => {
    const used = new Set<string>();
    for (const id of ["fp-topbar", "fp-home", "fp-recent-row", "fp-analysis-head", "fp-explore", "fp-card", "fp-findings", "fp-plain"]) {
      for (const m of template(id).matchAll(/class="([^"]+)"/g)) for (const c of m[1].split(/\s+/)) used.add(c);
    }
    const missing = [...used].filter((c) => !css.includes(`.${c}`));
    expect(missing).toEqual([]);
  });

  it("reserves room for what arrives with the data, so nothing moves", () => {
    const explore = template("fp-explore");
    expect(explore).toContain("All edges"); // always there; only available when edges are left out
    expect(template("fp-analysis-head")).toContain('class="count mono num"'); // the Findings badge
    expect(css).toContain("scrollbar-gutter: stable");
  });

  it("the Explorer legend uses the app's own words (legendText.ts)", () => {
    const explore = template("fp-explore");
    expect(explore).toContain(MAP_SOLID);
    expect(explore).toContain(dashedText("map", false));
    // The script swaps in the flat and shown-guesses wording; those strings are in the page too.
    expect(html).toContain(`"${FLAT_SOLID}"`);
    expect(html).toContain('" (calls matched by name only)"');
    expect(dashedText("map", true)).toBe("Mostly guesses (calls matched by name only)");
    expect(dashedText("flat", false)).toBe("Guess (hidden; turn on “Guessed calls”)");
    for (const label of ["Tests &amp; examples", "Guessed calls", "All edges", ">Show<"]) {
      expect(explore).toContain(label);
    }
  });

  it("the findings selects have the fixed widths the real page uses", () => {
    for (const kind of ["severity", "rule", "language"]) {
      expect(template("fp-findings")).toContain(`select-${kind}`);
      expect(css).toContain(`.select-${kind} {`);
    }
  });

  it("the placeholders for names and counts are the only grey bars on the home page", () => {
    const bars = template("fp-home").match(/class="skeleton"/g) ?? [];
    expect(bars).toHaveLength(0); // all of it is real text; the recent list adds its own rows
  });
});
