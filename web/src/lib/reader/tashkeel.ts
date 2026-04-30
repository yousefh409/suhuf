// Strip the eight Arabic diacritic codepoints (U+064B..U+0652).
// Used in Reader mode when the tashkeel toggle is OFF.

const DIACRITICS = /[\u064B-\u0652]/g;

export function stripTashkeel(text: string): string {
  return text.replace(DIACRITICS, "");
}
