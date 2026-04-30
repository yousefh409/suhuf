// web/src/lib/recitation/passage.test.ts
import { describe, it, expect } from "vitest";
import { buildPassage } from "./passage";
import type { Block } from "@/lib/reader/types";

const tok = (id: string, text: string) => ({ id, text });

const block = (key: string, type: Block["type"], words: [string, string][]) => ({
  key,
  type,
  tokens: words.map(([id, text]) => tok(id, text)),
}) as Block;

describe("buildPassage", () => {
  it("returns null when chapterBlocks is empty", () => {
    const r = buildPassage({ chapterBlocks: [], anchorBlockKey: "x" });
    expect(r).toBeNull();
  });

  it("returns null when no recitable blocks (only headings)", () => {
    const r = buildPassage({
      chapterBlocks: [block("b1", "heading", [["t1", "بَاب"]])],
      anchorBlockKey: "b1",
    });
    expect(r).toBeNull();
  });

  it("one prose block becomes one phrase", () => {
    const b = block("b1", "prose", [["t1", "الكَلَامُ"], ["t2", "هُوَ"]]);
    const r = buildPassage({ chapterBlocks: [b], anchorBlockKey: "b1" });
    expect(r).not.toBeNull();
    expect(r!.phrases).toEqual(["الكَلَامُ هُوَ"]);
    expect(r!.wordIndexToTokenId).toEqual(["t1", "t2"]);
    expect(r!.startCursor).toBe(0);
  });

  it("anchor in the middle keeps the requested lookbehind", () => {
    const blocks = [
      block("b1", "prose", [["t1", "أَحَدٌ"]]),
      block("b2", "prose", [["t2", "اِثْنَانِ"]]),
      block("b3", "prose", [["t3", "ثَلَاثَةٌ"]]),
      block("b4", "prose", [["t4", "أَرْبَعَةٌ"]]),
    ];
    const r = buildPassage({
      chapterBlocks: blocks,
      anchorBlockKey: "b3",
      lookbehindCount: 2,
      lookaheadPhraseCount: 1,
    });
    expect(r).not.toBeNull();
    expect(r!.phrases).toEqual(["أَحَدٌ", "اِثْنَانِ", "ثَلَاثَةٌ", "أَرْبَعَةٌ"]);
    expect(r!.startCursor).toBe(2);
  });

  it("anchor at chapter start clamps lookbehind to 0", () => {
    const blocks = [
      block("b1", "prose", [["t1", "أَحَدٌ"]]),
      block("b2", "prose", [["t2", "اِثْنَانِ"]]),
    ];
    const r = buildPassage({
      chapterBlocks: blocks,
      anchorBlockKey: "b1",
      lookbehindCount: 2,
      lookaheadPhraseCount: 5,
    });
    expect(r!.startCursor).toBe(0);
    expect(r!.phrases[0]).toBe("أَحَدٌ");
  });

  it("splits long blocks at pause markers (.، ؛ : !) when over 40 words", () => {
    // Build a 50-word block with a Arabic comma at word 25
    const tokens = Array.from({ length: 50 }, (_, i) => {
      const text = i === 24 ? "كَلِمَةٌ،" : "كَلِمَةٌ";
      return tok(`t${i}`, text);
    });
    const b: Block = { key: "long", type: "prose", tokens };
    const r = buildPassage({ chapterBlocks: [b], anchorBlockKey: "long" });
    expect(r).not.toBeNull();
    expect(r!.phrases.length).toBeGreaterThan(1);
    // First chunk should end at the comma (~25 words)
    expect(r!.phrases[0].split(" ").length).toBeLessThanOrEqual(25);
  });

  it("hard-splits at word boundary if no pause markers in long block", () => {
    const tokens = Array.from({ length: 90 }, (_, i) => tok(`t${i}`, "كَلِمَة"));
    const b: Block = { key: "long", type: "prose", tokens };
    const r = buildPassage({ chapterBlocks: [b], anchorBlockKey: "long" });
    expect(r).not.toBeNull();
    // Each phrase ≤ 40 words
    for (const p of r!.phrases) {
      expect(p.split(" ").length).toBeLessThanOrEqual(40);
    }
  });

  it("poetry: each hemistich becomes its own phrase", () => {
    const poetry: Block = {
      key: "p1",
      type: "poetry",
      hemistichs: [[
        [tok("a", "بَيْتٌ"), tok("b", "أَوَّلُ")],
        [tok("c", "بَيْتٌ"), tok("d", "ثَانٍ")],
      ]],
    };
    const r = buildPassage({ chapterBlocks: [poetry], anchorBlockKey: "p1" });
    expect(r!.phrases).toEqual(["بَيْتٌ أَوَّلُ", "بَيْتٌ ثَانٍ"]);
    expect(r!.wordIndexToTokenId).toEqual(["a", "b", "c", "d"]);
  });

  it("flat wordIndexToTokenId aligns with engine's space-split", () => {
    const blocks = [
      block("b1", "prose", [["t1", "وَاحِدٌ"], ["t2", "اِثْنَانِ"]]),
      block("b2", "prose", [["t3", "ثَلَاثَةٌ"]]),
    ];
    const r = buildPassage({ chapterBlocks: blocks, anchorBlockKey: "b1" });
    const allWords = r!.phrases.flatMap((p) => p.split(" "));
    expect(allWords.length).toBe(r!.wordIndexToTokenId.length);
    expect(allWords[0]).toBe("وَاحِدٌ");
    expect(r!.wordIndexToTokenId[0]).toBe("t1");
  });
});
