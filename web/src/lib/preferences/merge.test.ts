import { describe, it, expect } from "vitest";
import { mergePreferences } from "./merge";
import { DEFAULT_PREFERENCES } from "./types";
import type { Preferences } from "./types";

const cookiePrefs: Preferences = {
  theme: "sepia",
  textSize: "l",
  arabicFont: "amiri",
  lineSpacing: "compact",
  tashkeel: false,
};

describe("mergePreferences", () => {
  it("when db is null: effective equals cookie and seedDb is true", () => {
    const { effective, seedDb } = mergePreferences(cookiePrefs, null);
    expect(effective).toEqual(cookiePrefs);
    expect(seedDb).toBe(true);
  });

  it("when db is null: effective is a fresh object, not the cookie reference", () => {
    const { effective } = mergePreferences(cookiePrefs, null);
    expect(effective).not.toBe(cookiePrefs);
  });

  it("when db has a full set of prefs: effective equals db values and seedDb is false", () => {
    const db: Partial<Preferences> = {
      theme: "night",
      textSize: "xl",
      arabicFont: "noto-naskh",
      lineSpacing: "comfortable",
      tashkeel: true,
    };
    const { effective, seedDb } = mergePreferences(cookiePrefs, db);
    expect(effective).toEqual({
      theme: "night",
      textSize: "xl",
      arabicFont: "noto-naskh",
      lineSpacing: "comfortable",
      tashkeel: true,
    });
    expect(seedDb).toBe(false);
  });

  it("when db is partial: provided field wins, missing fields come from defaults", () => {
    const db: Partial<Preferences> = { theme: "night" };
    const { effective, seedDb } = mergePreferences(cookiePrefs, db);
    expect(effective.theme).toBe("night");
    expect(effective.textSize).toBe(DEFAULT_PREFERENCES.textSize);
    expect(effective.arabicFont).toBe(DEFAULT_PREFERENCES.arabicFont);
    expect(effective.lineSpacing).toBe(DEFAULT_PREFERENCES.lineSpacing);
    expect(effective.tashkeel).toBe(DEFAULT_PREFERENCES.tashkeel);
    expect(seedDb).toBe(false);
  });

  it("when db is empty object: all fields come from defaults and seedDb is false", () => {
    const { effective, seedDb } = mergePreferences(cookiePrefs, {});
    expect(effective).toEqual(DEFAULT_PREFERENCES);
    expect(seedDb).toBe(false);
  });
});
