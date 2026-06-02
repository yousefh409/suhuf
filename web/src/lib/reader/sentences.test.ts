import { describe, it, expect } from "vitest";
import { segmentSentences, buildSelectionMap } from "./sentences";
import type { Token } from "./types";

const tok = (id: string, text: string): Token => ({ id, text });

describe("segmentSentences", () => {
  it("splits on Arabic full stop, keeping the punctuation token in the sentence", () => {
    const tokens = [tok("a", "بسم"), tok("b", "الله."), tok("c", "الحمد"), tok("d", "لله")];
    const out = segmentSentences(tokens);
    expect(out.map((s) => s.tokenIds)).toEqual([["a", "b"], ["c", "d"]]);
    expect(out[0].text).toBe("بسم الله.");
    expect(out[1].text).toBe("الحمد لله");
  });

  it("splits on question mark and Arabic semicolon", () => {
    const tokens = [tok("a", "كيف"), tok("b", "حالك؟"), tok("c", "بخير؛"), tok("d", "والحمد")];
    expect(segmentSentences(tokens).map((s) => s.tokenIds)).toEqual([
      ["a", "b"],
      ["c"],
      ["d"],
    ]);
  });

  it("returns the whole block as one sentence when no terminal punctuation", () => {
    const tokens = [tok("a", "قال"), tok("b", "رسول"), tok("c", "الله")];
    const out = segmentSentences(tokens);
    expect(out).toHaveLength(1);
    expect(out[0].tokenIds).toEqual(["a", "b", "c"]);
  });

  it("handles empty token list", () => {
    expect(segmentSentences([])).toEqual([]);
  });
});

describe("buildSelectionMap", () => {
  it("maps each token to its sentence text and position within the sentence", () => {
    const tokens = [tok("a", "بسم"), tok("b", "الله."), tok("c", "الحمد"), tok("d", "لله")];
    const map = buildSelectionMap(tokens);
    expect(map.get("a")).toEqual({ word: "بسم", sentence: "بسم الله.", position: 0 });
    expect(map.get("b")).toEqual({ word: "الله.", sentence: "بسم الله.", position: 1 });
    expect(map.get("c")).toEqual({ word: "الحمد", sentence: "الحمد لله", position: 0 });
    expect(map.get("d")).toEqual({ word: "لله", sentence: "الحمد لله", position: 1 });
  });
});
