// The AI answer renderer. Model output is untrusted (CLAUDE.md rule 7): whatever it writes must
// come out as text, never as HTML, links or images.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

const html = (text: string) => renderToStaticMarkup(<Markdown text={text} />);

describe("untrusted text stays text", () => {
  it("never turns a javascript: link into a link", () => {
    const out = html("Click [here](javascript:alert(1)) or <javascript:alert(1)>.");
    expect(out).not.toMatch(/<a[\s>]/);
    expect(out).not.toContain("href");
    expect(out).toContain("[here](javascript:alert(1))"); // shown as written
  });

  it("renders http links as text too (no links at all in answers)", () => {
    const out = html("See [docs](https://example.com) and https://example.com.");
    expect(out).not.toMatch(/<a[\s>]/);
    expect(out).toContain("https://example.com");
  });

  it("escapes raw HTML and images", () => {
    const out = html('<img src=x onerror="alert(1)"> <script>alert(1)</script> ![a](x.png)');
    expect(out).not.toMatch(/<img|<script/);
    expect(out).toContain("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;");
  });

  it("escapes HTML inside code spans and fenced code", () => {
    const out = html("`<b>x</b>`\n\n```\n<script>alert(1)</script>\n```");
    expect(out).not.toMatch(/<script|<b>/);
    expect(out).toContain("&lt;script&gt;");
  });
});

describe("fenced code", () => {
  it("keeps blank lines and indentation inside the fence", () => {
    const out = html("Before\n\n```python\ndef f():\n    a = 1\n\n\n    return a\n```\nAfter");
    expect(out).toContain("<pre");
    expect(out).toContain("def f():\n    a = 1\n\n\n    return a</pre>");
    expect(out).toContain("<p>Before</p>");
    expect(out).toContain("<p>After</p>");
  });

  it("does not treat list or heading syntax inside a fence as markup", () => {
    const out = html("```\n- not a list\n# not a heading\n**not bold**\n```");
    expect(out).not.toContain("<li>");
    expect(out).not.toContain("<strong>");
    expect(out).toContain("- not a list\n# not a heading\n**not bold**");
  });

  it("an unclosed fence still renders the rest as code", () => {
    const out = html("Text\n```\nx = 1\n\ny = 2");
    expect(out).toContain("x = 1\n\ny = 2</pre>");
  });
});

describe("lists", () => {
  it("nests indented bullets under their parent item", () => {
    const out = html("- one\n  - one a\n  - one b\n- two");
    expect(out).toBe(
      '<div class="markdown"><ul><li>one<ul><li>one a</li><li>one b</li></ul></li>' +
        "<li>two</li></ul></div>",
    );
  });

  it("nests three levels and mixed list types", () => {
    const out = html("1. first\n   - detail\n     - deeper\n2. second");
    expect(out).toBe(
      '<div class="markdown"><ol><li>first<ul><li>detail<ul><li>deeper</li></ul></li></ul></li>' +
        "<li>second</li></ol></div>",
    );
  });

  it("joins an indented continuation line to its item", () => {
    const out = html("- a long item\n  that wraps\n- next");
    expect(out).toContain("<li>a long item that wraps</li><li>next</li>");
  });

  it("starts a new list when the list type changes at the top level", () => {
    const out = html("- bullet\n1. number");
    expect(out).toBe('<div class="markdown"><ul><li>bullet</li></ul><ol><li>number</li></ol></div>');
  });

  it("keeps inline code and bold inside list items", () => {
    const out = html("- calls `save()` **twice**");
    expect(out).toContain("<li>calls <code>save()</code> <strong>twice</strong></li>");
  });
});

describe("paragraphs", () => {
  it("joins wrapped lines and splits on blank lines", () => {
    expect(html("one\ntwo\n\nthree")).toBe('<div class="markdown"><p>one two</p><p>three</p></div>');
  });

  it("shows headings as plain paragraphs", () => {
    expect(html("## Summary")).toBe('<div class="markdown"><p>Summary</p></div>');
  });
});
