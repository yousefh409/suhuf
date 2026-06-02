import { describe, it, expect } from "vitest";
import { inlineSpanClass, isTransmissionVerb } from "./spanStyles";

describe("inlineSpanClass", () => {
  it("returns the styled class for inline-styled labels", () => {
    expect(inlineSpanClass("isnad")).toBe("reader-span-isnad");
    expect(inlineSpanClass("matn")).toBe("reader-span-matn");
    expect(inlineSpanClass("takhrij")).toBe("reader-span-takhrij");
    expect(inlineSpanClass("quran")).toBe("reader-span-quran");
  });

  it("returns undefined for labels that are not inline-styled", () => {
    expect(inlineSpanClass("person")).toBeUndefined();
    expect(inlineSpanClass("footnote")).toBeUndefined();
    expect(inlineSpanClass("date_hijri")).toBeUndefined();
  });
});

describe("isTransmissionVerb", () => {
  it("matches a vocalised transmission verb", () => {
    expect(isTransmissionVerb({ id: "t1", text: "حَدَّثَنَا" })).toBe(true);
  });

  it("does not match a non-verb word", () => {
    expect(isTransmissionVerb({ id: "t2", text: "محمد" })).toBe(false);
  });
});
