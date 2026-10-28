// A small Markdown subset for AI answers: paragraphs, bullet and numbered lists (nested by
// indentation), fenced code, inline code and bold. It builds React elements only (no innerHTML)
// and renders no links or images at all: `[text](url)` stays text whatever the scheme, so a
// `javascript:` URL can never become clickable. LLM output is untrusted (CLAUDE.md rule 7).
// Used instead of a Markdown library because answers are short and this is all the prompt asks
// for. Tests: Markdown.test.tsx.

import type { ReactNode } from "react";

interface ListNode {
  ordered: boolean;
  items: { text: string; children: ListNode[] }[];
}

type Block = { kind: "p"; text: string } | { kind: "list"; list: ListNode } | { kind: "code"; text: string };

interface RawItem {
  indent: number;
  ordered: boolean;
  text: string;
}

const ITEM = /^(\s*)([-*]|\d+[.)])\s+(.*)$/;

/** Nest items by indentation: deeper than the item before -> a child list of that item. */
function buildList(raw: RawItem[]): ListNode {
  const root: ListNode = { ordered: raw[0].ordered, items: [] };
  const stack: { indent: number; list: ListNode }[] = [{ indent: raw[0].indent, list: root }];
  for (const r of raw) {
    while (stack.length > 1 && r.indent < stack[stack.length - 1].indent) stack.pop();
    const top = stack[stack.length - 1];
    if (r.indent > top.indent && top.list.items.length) {
      const child: ListNode = { ordered: r.ordered, items: [] };
      top.list.items[top.list.items.length - 1].children.push(child);
      stack.push({ indent: r.indent, list: child });
      child.items.push({ text: r.text, children: [] });
    } else {
      top.list.items.push({ text: r.text, children: [] });
    }
  }
  return root;
}

function parse(source: string): Block[] {
  const blocks: Block[] = [];
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  let para: string[] = [];
  let items: RawItem[] = [];
  const flushPara = () => {
    if (para.length) blocks.push({ kind: "p", text: para.join(" ") });
    para = [];
  };
  const flushList = () => {
    if (items.length) blocks.push({ kind: "list", list: buildList(items) });
    items = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim().startsWith("```")) {
      flushPara();
      flushList();
      const code: string[] = [];
      for (i++; i < lines.length && !lines[i].trim().startsWith("```"); i++) code.push(lines[i]);
      blocks.push({ kind: "code", text: code.join("\n") });
      continue;
    }
    const m = line.match(ITEM);
    if (m) {
      flushPara();
      const item = { indent: m[1].length, ordered: !m[2].startsWith("-") && !m[2].startsWith("*"), text: m[3] };
      // A different list type at the outermost level starts a new list.
      if (items.length && item.indent <= items[0].indent && item.ordered !== items[0].ordered) flushList();
      items.push(item);
      continue;
    }
    if (!line.trim()) {
      flushPara();
      continue; // a blank line between items keeps the list going
    }
    if (items.length && !para.length && /^\s+/.test(line)) {
      items[items.length - 1].text += ` ${line.trim()}`; // continuation of the item above
      continue;
    }
    flushList();
    para.push(line.trim().replace(/^#{1,6}\s+/, ""));
  }
  flushPara();
  flushList();
  return blocks;
}

function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const pattern = /`([^`]+)`|\*\*([^*]+)\*\*/g;
  let last = 0;
  for (const m of text.matchAll(pattern)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(m[1] !== undefined ? <code key={m.index}>{m[1]}</code> : <strong key={m.index}>{m[2]}</strong>);
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function List({ list }: { list: ListNode }) {
  const Tag = list.ordered ? "ol" : "ul";
  return (
    <Tag>
      {list.items.map((item, i) => (
        <li key={i}>
          {inline(item.text)}
          {item.children.map((child, j) => (
            <List key={j} list={child} />
          ))}
        </li>
      ))}
    </Tag>
  );
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="markdown">
      {parse(text).map((block, i) => {
        if (block.kind === "code") return <pre key={i} className="mono">{block.text}</pre>;
        if (block.kind === "p") return <p key={i}>{inline(block.text)}</p>;
        return <List key={i} list={block.list} />;
      })}
    </div>
  );
}
