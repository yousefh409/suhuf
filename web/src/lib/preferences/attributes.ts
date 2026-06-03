import type { Preferences } from "./types";

export function preferencesToAttributes(prefs: Preferences): Record<string, string> {
  return {
    "data-app-theme": prefs.theme,
    "data-text-size": prefs.textSize,
    "data-line-spacing": prefs.lineSpacing,
    "data-arabic-font": prefs.arabicFont,
  };
}
