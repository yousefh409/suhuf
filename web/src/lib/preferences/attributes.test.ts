import { describe, it, expect } from "vitest";
import { preferencesToAttributes } from "./attributes";
import { ARABIC_FONTS, LINE_SPACINGS, TEXT_SIZES, THEMES } from "./types";

describe("preferencesToAttributes", () => {
  it("maps each theme value to data-app-theme", () => {
    for (const theme of THEMES) {
      const result = preferencesToAttributes({
        theme,
        textSize: "m",
        arabicFont: "scheherazade",
        lineSpacing: "comfortable",
        tashkeel: true,
      });
      expect(result["data-app-theme"]).toBe(theme);
    }
  });

  it("maps each textSize value to data-text-size", () => {
    for (const textSize of TEXT_SIZES) {
      const result = preferencesToAttributes({
        theme: "paper",
        textSize,
        arabicFont: "scheherazade",
        lineSpacing: "comfortable",
        tashkeel: true,
      });
      expect(result["data-text-size"]).toBe(textSize);
    }
  });

  it("maps each lineSpacing value to data-line-spacing", () => {
    for (const lineSpacing of LINE_SPACINGS) {
      const result = preferencesToAttributes({
        theme: "paper",
        textSize: "m",
        arabicFont: "scheherazade",
        lineSpacing,
        tashkeel: true,
      });
      expect(result["data-line-spacing"]).toBe(lineSpacing);
    }
  });

  it("maps each arabicFont value to data-arabic-font", () => {
    for (const arabicFont of ARABIC_FONTS) {
      const result = preferencesToAttributes({
        theme: "paper",
        textSize: "m",
        arabicFont,
        lineSpacing: "comfortable",
        tashkeel: true,
      });
      expect(result["data-arabic-font"]).toBe(arabicFont);
    }
  });

  it("returns exactly the four expected keys with no tashkeel or extra keys", () => {
    const result = preferencesToAttributes({
      theme: "sepia",
      textSize: "l",
      arabicFont: "amiri",
      lineSpacing: "compact",
      tashkeel: false,
    });
    expect(Object.keys(result).sort()).toEqual([
      "data-app-theme",
      "data-arabic-font",
      "data-line-spacing",
      "data-text-size",
    ]);
    expect("tashkeel" in result).toBe(false);
  });
});
