import { describe, it, expect } from "vitest";
import { stripTashkeel } from "./tashkeel";

describe("stripTashkeel", () => {
  it("removes fatha, kasra, damma, sukun, shadda, tanween marks", () => {
    expect(stripTashkeel("حَدَّثَنَا")).toBe("حدثنا");
  });

  it("is idempotent on text without diacritics", () => {
    expect(stripTashkeel("حدثنا")).toBe("حدثنا");
  });

  it("does not touch non-Arabic text", () => {
    expect(stripTashkeel("hello")).toBe("hello");
  });

  it("handles empty string", () => {
    expect(stripTashkeel("")).toBe("");
  });

  it("preserves spaces and punctuation", () => {
    expect(stripTashkeel("بِسْمِ اللَّهِ، الرَّحْمَنِ.")).toBe("بسم الله، الرحمن.");
  });
});
