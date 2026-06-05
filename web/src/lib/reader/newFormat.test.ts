import { describe, it, expect } from "vitest";
import { tokenizeText, convertBlock, convertNewBook } from "./newFormat";
import type { NewBlock, NewBook } from "./types";

describe("tokenizeText", () => {
  it("splits on whitespace and records char ranges (end-exclusive)", () => {
    // "ab cd" → "ab"@[0,2), "cd"@[3,5)
    expect(tokenizeText("ab cd")).toEqual([
      { text: "ab", start: 0, end: 2 },
      { text: "cd", start: 3, end: 5 },
    ]);
  });

  it("collapses runs of whitespace and ignores leading/trailing space", () => {
    expect(tokenizeText("  a   bb ")).toEqual([
      { text: "a", start: 2, end: 3 },
      { text: "bb", start: 6, end: 8 },
    ]);
  });

  it("returns empty for blank text", () => {
    expect(tokenizeText("")).toEqual([]);
    expect(tokenizeText("   ")).toEqual([]);
  });
});

describe("convertBlock — prose with char-offset spans", () => {
  const block: NewBlock = {
    key: "b1",
    type: "prose",
    text: "alpha beta gamma delta",
    text_raw: null,
    // "alpha beta" = [0,10), "gamma delta" = [11,22)
    spans: [
      { start: 0, end: 10, label: "isnad", ref: null },
      { start: 11, end: 22, label: "matn", ref: "x" },
    ],
  };

  it("derives token ids as `${key}:${wordIndex}` and keeps prose type", () => {
    const out = convertBlock(block);
    expect(out.type).toBe("prose");
    if (out.type === "poetry") throw new Error("expected prose");
    expect(out.tokens.map((t) => t.id)).toEqual(["b1:0", "b1:1", "b1:2", "b1:3"]);
    expect(out.tokens.map((t) => t.text)).toEqual([
      "alpha",
      "beta",
      "gamma",
      "delta",
    ]);
  });

  it("maps char-offset spans to start_token_id/end_token_id covering overlapping words", () => {
    const out = convertBlock(block);
    expect(out.spans).toEqual([
      { start_token_id: "b1:0", end_token_id: "b1:1", label: "isnad", ref: null, sub_label: null, confidence: undefined },
      { start_token_id: "b1:2", end_token_id: "b1:3", label: "matn", ref: "x", sub_label: null, confidence: undefined },
    ]);
  });
});

describe("convertBlock — text_raw zipped word-by-word", () => {
  it("attaches per-word raw forms when text_raw is present", () => {
    const block: NewBlock = {
      key: "b0",
      type: "prose",
      text: "أَحْمَدُ رَبَّ",
      text_raw: "أحمد رب",
    };
    const out = convertBlock(block);
    if (out.type === "poetry") throw new Error("expected prose");
    expect(out.tokens[0]).toMatchObject({ text: "أَحْمَدُ", text_raw: "أحمد" });
    expect(out.tokens[1]).toMatchObject({ text: "رَبَّ", text_raw: "رب" });
  });

  it("leaves text_raw undefined when block.text_raw is null", () => {
    const out = convertBlock({ key: "b0", type: "prose", text: "a b", text_raw: null });
    if (out.type === "poetry") throw new Error("expected prose");
    expect(out.tokens[0].text_raw).toBeUndefined();
  });
});

describe("convertBlock — poetry from lines", () => {
  it("builds hemistichs[verse][hemistich][token] with derived ids", () => {
    const block: NewBlock = {
      key: "p0",
      type: "poetry",
      text: "",
      lines: [
        ["first half", "second half"],
        ["solo"],
      ],
    };
    const out = convertBlock(block);
    expect(out.type).toBe("poetry");
    if (out.type !== "poetry") throw new Error("expected poetry");
    expect(out.hemistichs).toHaveLength(2);
    expect(out.hemistichs[0][0].map((t) => t.text)).toEqual(["first", "half"]);
    expect(out.hemistichs[0][1].map((t) => t.text)).toEqual(["second", "half"]);
    // ids unique across the whole block
    const ids = out.hemistichs.flat().flat().map((t) => t.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe("convertBlock — quran block type passes through", () => {
  it("keeps the quran type and tokenises text", () => {
    const out = convertBlock({ key: "q0", type: "quran", text: "إِنَّا أَعْطَيْنَاكَ" });
    expect(out.type).toBe("quran");
    if (out.type === "poetry") throw new Error("expected quran");
    expect(out.tokens.map((t) => t.id)).toEqual(["q0:0", "q0:1"]);
  });

  it("drops spans that overlap no word (whitespace-only range)", () => {
    // span [5,6) lands on the single space → covers no word
    const out = convertBlock({
      key: "b0",
      type: "prose",
      text: "alpha beta",
      spans: [{ start: 5, end: 6, label: "matn" }],
    });
    if (out.type === "poetry") throw new Error("expected prose");
    expect(out.spans).toEqual([]);
  });
});

describe("convertNewBook", () => {
  it("maps pages → content_blocks/footnotes and keeps chapter block_index", () => {
    const book: NewBook = {
      metadata: {
        openiti_id: "x",
        title_ar: "ك",
        author_openiti_id: "a",
      },
      pages: [
        {
          page_number: 5,
          volume: 1,
          blocks: [{ key: "b0", type: "heading", text: "باب", level: 2 }],
          footnotes: [{ marker: "(1)", text: "حاشية أولى" }],
        },
      ],
      chapters: [
        { title: "باب", level: 2, page_number: 5, sort_order: 1, block_index: 0 },
      ],
    };
    const out = convertNewBook(book);
    expect(out.pages[0].content_blocks).toHaveLength(1);
    expect(out.pages[0].content_blocks[0].type).toBe("heading");
    expect(out.pages[0].footnotes?.[0].tokens.map((t) => t.text)).toEqual([
      "حاشية",
      "أولى",
    ]);
    expect(out.pages[0].footnotes?.[0].tokens[0].id).toBe("fn:(1):0");
    expect(out.chapters[0].block_index).toBe(0);
    expect(out.metadata.title_ar).toBe("ك");
  });

  it("makes token ids globally unique across pages (per-page block keys collide otherwise)", () => {
    const page = (pn: number): NewBook["pages"][number] => ({
      page_number: pn,
      volume: 1,
      blocks: [{ key: "b0", type: "prose", text: "كلمة أخرى" }], // same per-page key on both pages
    });
    const book: NewBook = {
      metadata: { openiti_id: "x", title_ar: "ك", author_openiti_id: "a" },
      pages: [page(1), page(2)],
      chapters: [],
    };
    const out = convertNewBook(book);
    const ids = out.pages.flatMap((p) =>
      p.content_blocks.flatMap((b) => ("tokens" in b ? b.tokens.map((t) => t.id) : [])),
    );
    expect(ids).toEqual(["pg0_b0:0", "pg0_b0:1", "pg1_b0:0", "pg1_b0:1"]);
    expect(new Set(ids).size).toBe(ids.length); // no collisions across pages
  });
});
