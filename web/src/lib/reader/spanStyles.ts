import type { SpanLabel } from "./types";

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
