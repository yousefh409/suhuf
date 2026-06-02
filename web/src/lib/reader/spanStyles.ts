import type { SpanLabel, Token } from "./types";
import { stripTashkeel } from "./tashkeel";

// Span labels that receive inline visual styling in the reader. Other labels
// (person, place, refs, footnote, date_hijri) are not styled inline.
export const INLINE_STYLED_LABELS = new Set<SpanLabel>([
  "isnad",
  "matn",
  "takhrij",
  "quran",
]);

export function inlineSpanClass(label: SpanLabel): string | undefined {
  return INLINE_STYLED_LABELS.has(label) ? `reader-span-${label}` : undefined;
}

// Transmission verbs to faintly accent inside isnad (blocks or inline spans).
// Compared after stripping tashkeel so vocalised forms like حَدَّثَنَا still match.
export const ISNAD_VERBS = new Set([
  "حدثنا",
  "حدثني",
  "أخبرنا",
  "أخبرني",
  "أنبأنا",
  "سمعت",
  "عن",
  "قال",
  "قالت",
  "روى",
]);

export function isTransmissionVerb(token: Token): boolean {
  const stripped = stripTashkeel(token.text).replace(/[^\u0600-\u06FF]/g, "");
  return ISNAD_VERBS.has(stripped);
}
