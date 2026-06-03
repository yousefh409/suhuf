export const THEMES = ["paper", "sepia", "night"] as const;
export type Theme = (typeof THEMES)[number];

export const TEXT_SIZES = ["s", "m", "l", "xl"] as const;
export type TextSize = (typeof TEXT_SIZES)[number];

export const ARABIC_FONTS = ["scheherazade", "amiri", "noto-naskh"] as const;
export type ArabicFont = (typeof ARABIC_FONTS)[number];

export const LINE_SPACINGS = ["comfortable", "compact"] as const;
export type LineSpacing = (typeof LINE_SPACINGS)[number];

export interface Preferences {
  theme: Theme;
  textSize: TextSize;
  arabicFont: ArabicFont;
  lineSpacing: LineSpacing;
  tashkeel: boolean;
}

export const DEFAULT_PREFERENCES: Preferences = {
  theme: "paper",
  textSize: "m",
  arabicFont: "scheherazade",
  lineSpacing: "comfortable",
  tashkeel: true,
};
