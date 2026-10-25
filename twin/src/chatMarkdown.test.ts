import { describe, expect, it } from "vitest";
import { parseChatMarkdown, parseInline } from "./chatMarkdown";

describe("parseInline", () => {
  it("splits bold and italic runs", () => {
    expect(parseInline("Go to **Café (Gastraum)**, it is *open*.")).toEqual([
      { text: "Go to " },
      { text: "Café (Gastraum)", bold: true },
      { text: ", it is " },
      { text: "open", italic: true },
      { text: "." },
    ]);
  });

  it("keeps lone stars, arithmetic and underscores literal", () => {
    expect(parseInline("2 * 3 = 6 and room_type stays")).toEqual([{ text: "2 * 3 = 6 and room_type stays" }]);
  });

  it("allows italic inside bold and drops backticks", () => {
    expect(parseInline("**the *left* lever** `L1`")).toEqual([
      { text: "the ", bold: true },
      { text: "left", bold: true, italic: true },
      { text: " lever", bold: true },
      { text: " L1" },
    ]);
  });

  it("never turns markup into anything but text", () => {
    const parts = parseInline("<img src=x onerror=alert(1)> **<b>hi</b>**");
    expect(parts.map((p) => p.text).join("")).toBe("<img src=x onerror=alert(1)> <b>hi</b>");
  });
});

describe("parseChatMarkdown", () => {
  it("reads paragraphs, line breaks and numbered lists", () => {
    const blocks = parseChatMarkdown("Two options:\nboth are close.\n\n1. **Café (Gastraum)**, 20 m\n2. Kitchen, 35 m\n\nEnjoy!");
    expect(blocks.map((b) => b.kind)).toEqual(["p", "ol", "p"]);
    expect(blocks[0]).toEqual({ kind: "p", lines: [[{ text: "Two options:" }], [{ text: "both are close." }]] });
    expect(blocks[1]).toEqual({
      kind: "ol",
      start: 1,
      items: [[{ text: "Café (Gastraum)", bold: true }, { text: ", 20 m" }], [{ text: "Kitchen, 35 m" }]],
    });
  });

  it("reads bulleted lists right after a line and keeps the list start", () => {
    const blocks = parseChatMarkdown("Here:\n- WC 0.12\n* WC 0.14\n3) third");
    expect(blocks).toEqual([
      { kind: "p", lines: [[{ text: "Here:" }]] },
      { kind: "ul", items: [[{ text: "WC 0.12" }], [{ text: "WC 0.14" }]] },
      { kind: "ol", start: 3, items: [[{ text: "third" }]] },
    ]);
  });

  it("reads a heading as a bold line", () => {
    expect(parseChatMarkdown("## Route")).toEqual([{ kind: "p", lines: [[{ text: "Route", bold: true }]] }]);
  });
});
