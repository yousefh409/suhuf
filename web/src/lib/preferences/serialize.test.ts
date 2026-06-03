import { describe, it, expect } from "vitest";
import { parsePreferences, serializePreferences } from "./serialize";
import { DEFAULT_PREFERENCES } from "./types";

describe("parsePreferences", () => {
  it("parses a valid full JSON string correctly", () => {
    const raw = JSON.stringify({
      theme: "sepia",
      textSize: "l",
      arabicFont: "amiri",
      lineSpacing: "compact",
      tashkeel: false,
    });
    expect(parsePreferences(raw)).toEqual({
      theme: "sepia",
      textSize: "l",
      arabicFont: "amiri",
      lineSpacing: "compact",
      tashkeel: false,
    });
  });

  it("falls back to default theme when theme is invalid, preserving other valid fields", () => {
    const raw = JSON.stringify({
      theme: "dark", // invalid
      textSize: "xl",
      arabicFont: "amiri",
      lineSpacing: "compact",
      tashkeel: false,
    });
    const result = parsePreferences(raw);
    expect(result.theme).toBe("paper");
    expect(result.textSize).toBe("xl");
    expect(result.arabicFont).toBe("amiri");
    expect(result.lineSpacing).toBe("compact");
    expect(result.tashkeel).toBe(false);
  });

  it("fills missing fields from defaults", () => {
    const raw = JSON.stringify({ theme: "night" });
    const result = parsePreferences(raw);
    expect(result.theme).toBe("night");
    expect(result.textSize).toBe(DEFAULT_PREFERENCES.textSize);
    expect(result.arabicFont).toBe(DEFAULT_PREFERENCES.arabicFont);
    expect(result.lineSpacing).toBe(DEFAULT_PREFERENCES.lineSpacing);
    expect(result.tashkeel).toBe(DEFAULT_PREFERENCES.tashkeel);
  });

  it("returns all defaults for malformed JSON", () => {
    expect(parsePreferences("{not json}")).toEqual(DEFAULT_PREFERENCES);
  });

  it("returns all defaults for null", () => {
    expect(parsePreferences(null)).toEqual(DEFAULT_PREFERENCES);
  });

  it("returns all defaults for undefined", () => {
    expect(parsePreferences(undefined)).toEqual(DEFAULT_PREFERENCES);
  });

  it("returns all defaults for empty string", () => {
    expect(parsePreferences("")).toEqual(DEFAULT_PREFERENCES);
  });

  it("falls back to true when tashkeel is a non-boolean", () => {
    const raw = JSON.stringify({
      theme: "paper",
      textSize: "m",
      arabicFont: "scheherazade",
      lineSpacing: "comfortable",
      tashkeel: "yes", // invalid: string not boolean
    });
    const result = parsePreferences(raw);
    expect(result.tashkeel).toBe(true);
  });

  it("ignores unknown extra keys", () => {
    const raw = JSON.stringify({
      theme: "sepia",
      textSize: "s",
      arabicFont: "noto-naskh",
      lineSpacing: "compact",
      tashkeel: false,
      unknownKey: "someValue",
    });
    const result = parsePreferences(raw);
    expect(Object.keys(result)).toEqual([
      "theme",
      "textSize",
      "arabicFont",
      "lineSpacing",
      "tashkeel",
    ]);
  });

  it("returns a fresh object (does not alias DEFAULT_PREFERENCES)", () => {
    const result = parsePreferences(null);
    expect(result).not.toBe(DEFAULT_PREFERENCES);
  });
});

describe("serializePreferences", () => {
  it("round-trips: parsePreferences(serializePreferences(x)) === x", () => {
    const prefs = {
      theme: "night" as const,
      textSize: "xl" as const,
      arabicFont: "amiri" as const,
      lineSpacing: "compact" as const,
      tashkeel: false,
    };
    expect(parsePreferences(serializePreferences(prefs))).toEqual(prefs);
  });

  it("serializes exactly the five known keys", () => {
    const prefs = { ...DEFAULT_PREFERENCES };
    const parsed = JSON.parse(serializePreferences(prefs)) as Record<string, unknown>;
    expect(Object.keys(parsed).sort()).toEqual([
      "arabicFont",
      "lineSpacing",
      "tashkeel",
      "textSize",
      "theme",
    ]);
  });
});
