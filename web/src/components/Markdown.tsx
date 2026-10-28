// A small Markdown subset for AI answers: paragraphs, bullet and numbered lists, fenced code,
// inline code and bold. It builds React elements only (no innerHTML), so the model's text can
// never become HTML, links or images: LLM output is untrusted (CLAUDE.md rule 7). Used instead
// of a Markdown library because answers are short and this is all the prompt asks for.

import type { ReactNode } from "react";

type Block =
  | { kind: "p"; text: string }
  | { kind: "ul" | "ol"; items: string[] }
  | { kind: "code"; text: string };

const BULLET = /^\s*[-*]\s+/;
const NUMBER = /^\s*\d+[.)]\s+/;

function parse(source: string): Block[] {
  const blocks: Block[] = [];
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  let para: string[] = [];
  const flush = () => {
    if (para.length) blocks.push({ kind: "p", text: para.join(" ") });
    para = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim().startsWith("```")) {
      flush();
      const code: string[] = [];
      for (i++; i < lines.length && !lines[i].trim().startsWith("```"); i++) code.push(lines[i]);
      blocks.push({ kind: "code", text: code.join("\n") });
      continue;
    }
    const list = BULLET.test(line) ? "ul" : NUMBER.test(line) ? "ol" : null;
    if (list) {
      flush();
      const marker = list === "ul" ? BULLET : NUMBER;
      const last = blocks[blocks.length - 1];
      const item = line.replace(marker, "");
      if (last && last.kind === list) last.items.push(item);
      else blocks.push({ kind: list, items: [item] });
      continue;
    }
    if (!line.trim()) {
      flush();
      continue;
    }
    // A continuation line of a list item stays with it.
    const last = blocks[blocks.length - 1];
    if (!para.length && last && (last.kind === "ul" || last.kind === "ol") && /^\s+/.test(line)) {
      last.items[last.items.length - 1] += ` ${line.trim()}`;
      continue;
    }
    para.push(line.trim().replace(/^#{1,6}\s+/, ""));
  }
  flush();
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

export function Markdown({ text }: { text: string }) {
  return (
    <div className="markdown">
      {parse(text).map((block, i) => {
        if (block.kind === "code") return <pre key={i} className="mono">{block.text}</pre>;
        if (block.kind === "p") return <p key={i}>{inline(block.text)}</p>;
        const List = block.kind;
        return (
          <List key={i}>
            {block.items.map((item, j) => (
              <li key={j}>{inline(item)}</li>
            ))}
          </List>
        );
      })}
    </div>
  );
}
