// The small markdown subset Wanda writes in chat replies: **bold**, *italic*, numbered and bulleted lists, line
// breaks, a "# heading" read as a bold line. Parsed into plain data so the chat bubble builds React nodes from it
// (no HTML string, so a reply can never inject markup). Spoken replies use voice.spokenText instead.

export interface Inline {
  text: string;
  bold?: boolean;
  italic?: boolean;
}

export type Block =
  | { kind: "p"; lines: Inline[][] }
  | { kind: "ul"; items: Inline[][] }
  | { kind: "ol"; start: number; items: Inline[][] };

const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*(\d+)[.)]\s+(.*)$/;
const HEADING = /^\s*#{1,6}\s+(.*)$/;

/** **bold** and *italic* runs (italic also inside bold); backticks are dropped, everything else stays literal. */
export function parseInline(text: string, bold = false): Inline[] {
  const out: Inline[] = [];
  const push = (part: Inline) => {
    if (!part.text) return;
    const last = out[out.length - 1];
    if (last && !!last.bold === !!part.bold && !!last.italic === !!part.italic) last.text += part.text;
    else out.push(part);
  };
  const clean = text.replace(/`/g, "");
  if (!bold) {
    const parts = clean.split(/(\*\*(?:[^*\n]|\*(?!\*))+?\*\*)/g);
    for (const part of parts) {
      if (/^\*\*(?:[^*\n]|\*(?!\*))+?\*\*$/.test(part)) for (const inner of parseInline(part.slice(2, -2), true)) push(inner);
      else for (const inner of italics(part, false)) push(inner);
    }
    return out;
  }
  for (const inner of italics(clean, true)) push(inner);
  return out;
}

function italics(text: string, bold: boolean): Inline[] {
  // *word* or *a few words*: the star hugs the text on both sides (so "2 * 3" stays literal)
  return text
    .split(/(\*[^*\s](?:[^*\n]*[^*\s])?\*)/g)
    .filter(Boolean)
    .map((part) =>
      /^\*[^*\s](?:[^*\n]*[^*\s])?\*$/.test(part)
        ? { text: part.slice(1, -1), italic: true, ...(bold ? { bold } : {}) }
        : { text: part, ...(bold ? { bold } : {}) },
    );
}

/** Paragraphs (blank lines between them, single line breaks kept), bulleted and numbered lists. */
export function parseChatMarkdown(text: string): Block[] {
  const blocks: Block[] = [];
  let current: Block | null = null;
  const close = () => {
    if (current) blocks.push(current);
    current = null;
  };
  for (const raw of text.replace(/\r\n?/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      close();
      continue;
    }
    const bullet = BULLET.exec(line);
    const numbered = NUMBERED.exec(line);
    if (bullet) {
      if (current?.kind !== "ul") {
        close();
        current = { kind: "ul", items: [] };
      }
      current.items.push(parseInline(bullet[1]));
    } else if (numbered) {
      if (current?.kind !== "ol") {
        close();
        current = { kind: "ol", start: Number(numbered[1]), items: [] };
      }
      current.items.push(parseInline(numbered[2]));
    } else {
      if (current?.kind !== "p") {
        close();
        current = { kind: "p", lines: [] };
      }
      const heading = HEADING.exec(line);
      current.lines.push(heading ? parseInline(heading[1], true) : parseInline(line.trim()));
    }
  }
  close();
  return blocks;
}
