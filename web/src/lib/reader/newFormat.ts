// Normalise the NEW on-disk book format into the legacy in-memory shape the
// reader renderer already consumes. Keeping the conversion here (rather than
// threading a second format through every component) means Block/TokenText/
// ChapterScroll/sentences stay unchanged and we get parity for free.
//
// Core idea: tokenise `block.text` on whitespace into words. Each word gets a
// DERIVED id `${block.key}:${wordIndex}` (there are no stored token ids).
// Char-offset spans become start_token_id/end_token_id by mapping each span's
// [start,end) char range to the words it overlaps.

import type {
  Block,
  Footnote,
  NewBlock,
  NewBook,
  NewFootnote,
  NewPage,
  Page,
  Span,
  Token,
} from "./types";

export type WordSpan = { text: string; start: number; end: number };

/** Split `text` on whitespace, recording each word's [start,end) char range
 *  (end-exclusive). Leading/trailing/collapsed whitespace is ignored. */
export function tokenizeText(text: string): WordSpan[] {
  const out: WordSpan[] = [];
  const re = /\S+/gu;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    out.push({ text: m[0], start: m.index, end: m.index + m[0].length });
  }
  return out;
}

/** Build the token list for a block, zipping per-word raw forms when the block
 *  carries `text_raw`. text and text_raw are expected to have the same word
 *  count; if they drift we just omit the raw form past the shorter list. */
function buildTokens(block: NewBlock): { tokens: Token[]; words: WordSpan[] } {
  const words = tokenizeText(block.text);
  const rawWords =
    block.text_raw != null ? tokenizeText(block.text_raw).map((w) => w.text) : null;
  const tokens = words.map((w, i): Token => {
    const t: Token = { id: `${block.key}:${i}`, text: w.text };
    if (rawWords) t.text_raw = rawWords[i];
    return t;
  });
  return { tokens, words };
}

/** Convert char-offset spans to token-id spans. A word is covered by a span
 *  when the word's [start,end) range overlaps the span's [start,end) range. */
function convertSpans(block: NewBlock, words: WordSpan[]): Span[] {
  const spans = block.spans;
  if (!spans || spans.length === 0) return [];
  const out: Span[] = [];
  for (const s of spans) {
    let lo = -1;
    let hi = -1;
    for (let i = 0; i < words.length; i++) {
      const w = words[i];
      // overlap test for half-open ranges [a,b) and [c,d): a < d && c < b
      if (w.start < s.end && s.start < w.end) {
        if (lo === -1) lo = i;
        hi = i;
      }
    }
    if (lo === -1) continue; // span covers no word (e.g. whitespace-only range)
    out.push({
      start_token_id: `${block.key}:${lo}`,
      end_token_id: `${block.key}:${hi}`,
      label: s.label,
      ref: s.ref ?? null,
      sub_label: s.sub ?? null,
      confidence: s.conf ?? undefined,
    });
  }
  return out;
}

/** Tokenise a poetry verse hemistich string into derived-id tokens. */
function poetryHemistich(blockKey: string, vi: number, hi: number, text: string): Token[] {
  return tokenizeText(text).map((w, wi): Token => ({
    id: `${blockKey}:${vi}:${hi}:${wi}`,
    text: w.text,
  }));
}

/** Convert one NEW block into a legacy in-memory Block. */
export function convertBlock(block: NewBlock): Block {
  const base = {
    key: block.key,
    parser_type: block.parser_type ?? null,
    flags: block.flags ?? [],
    level: block.level ?? null,
    number: block.number ?? null,
  };

  if (block.type === "poetry") {
    const lines = block.lines ?? [];
    return {
      ...base,
      type: "poetry",
      hemistichs: lines.map((verse, vi) =>
        verse.map((hemi, hi) => poetryHemistich(block.key, vi, hi, hemi)),
      ),
    };
  }

  const { tokens, words } = buildTokens(block);
  return {
    ...base,
    type: block.type, // prose | heading | quran
    tokens,
    spans: convertSpans(block, words),
  };
}

function convertFootnote(fn: NewFootnote): Footnote {
  const words = tokenizeText(fn.text);
  return {
    marker: fn.marker,
    tokens: words.map((w, i): Token => ({ id: `fn:${fn.marker}:${i}`, text: w.text })),
  };
}

function convertPage(page: NewPage): Page {
  return {
    page_number: page.page_number,
    volume: page.volume,
    content_blocks: page.blocks.map(convertBlock),
    footnotes: (page.footnotes ?? []).map(convertFootnote),
  };
}

// Shape compatible with the loader's LocalBookFile (queries.ts). Returned so
// the rest of the query layer works unchanged on normalised data.
export type NormalisedBookFile = {
  metadata: NewBook["metadata"];
  pages: Page[];
  chapters: NewBook["chapters"];
};

export function convertNewBook(book: NewBook): NormalisedBookFile {
  return {
    metadata: book.metadata,
    pages: book.pages.map(convertPage),
    chapters: book.chapters,
  };
}
