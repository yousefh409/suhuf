import {
  ARABIC_FONTS,
  DEFAULT_PREFERENCES,
  LINE_SPACINGS,
  TEXT_SIZES,
  THEMES,
  type Preferences,
} from "./types";

/**
 * Validate and coerce an already-parsed (unknown) value into a Preferences
 * object. Each field is checked against its allowed value set; anything
 * missing or invalid falls back to DEFAULT_PREFERENCES. Never throws.
 */
export function coercePreferences(value: unknown): Preferences {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return { ...DEFAULT_PREFERENCES };
  }

  const obj = value as Record<string, unknown>;

  const theme = (THEMES as readonly string[]).includes(obj["theme"] as string)
    ? (obj["theme"] as Preferences["theme"])
    : DEFAULT_PREFERENCES.theme;

  const textSize = (TEXT_SIZES as readonly string[]).includes(obj["textSize"] as string)
    ? (obj["textSize"] as Preferences["textSize"])
    : DEFAULT_PREFERENCES.textSize;

  const arabicFont = (ARABIC_FONTS as readonly string[]).includes(obj["arabicFont"] as string)
    ? (obj["arabicFont"] as Preferences["arabicFont"])
    : DEFAULT_PREFERENCES.arabicFont;

  const lineSpacing = (LINE_SPACINGS as readonly string[]).includes(obj["lineSpacing"] as string)
    ? (obj["lineSpacing"] as Preferences["lineSpacing"])
    : DEFAULT_PREFERENCES.lineSpacing;

  const tashkeel =
    typeof obj["tashkeel"] === "boolean" ? obj["tashkeel"] : DEFAULT_PREFERENCES.tashkeel;

  return { theme, textSize, arabicFont, lineSpacing, tashkeel };
}

export function parsePreferences(raw: string | null | undefined): Preferences {
  if (!raw) return { ...DEFAULT_PREFERENCES };

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { ...DEFAULT_PREFERENCES };
  }

  return coercePreferences(parsed);
}

export function serializePreferences(prefs: Preferences): string {
  return JSON.stringify({
    theme: prefs.theme,
    textSize: prefs.textSize,
    arabicFont: prefs.arabicFont,
    lineSpacing: prefs.lineSpacing,
    tashkeel: prefs.tashkeel,
  });
}
