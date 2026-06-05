// Normalise the FLOW on-disk format (<uri>.flow.json) into the NewBook shape the
// reader already understands, so convertNewBook + the renderer stay unchanged.
//
// A flow book is one continuous tagged document sliced into page rows. Each page
// carries a `tagged` fragment whose tags may have opened on an earlier page
// (recorded in `open_tags`) and may stay open past this page. `parseFlowPage`
// seeds the open-tag stack, parses the fragment, and closes any still-open tag at
// the page end, yielding the page `text` and its label spans. Each page becomes
// one prose NewBlock carrying those spans.
//
// Known gap (follow-up): the flow AI pass leaves chapter/section headings as
// untagged text, so a heading currently renders as prose. The chapter TOC still
// comes from `chapters`.

import type { NewBook, NewBlock, NewSpan, SpanLabel } from "./types";

export type OpenTag = { name: string; id: string | null };

export type FlowPage = {
  page_number: number;
  volume: number;
  tagged: string;
  open_tags: OpenTag[];
  text: string;
  start_offset: number;
};

export type FlowAnnotation = {
  id: string;
  label: string;
  start: number;
  end: number;
  meta: Record<string, unknown>;
};

export type FlowBook = {
  metadata: NewBook["metadata"];
  pages: FlowPage[];
  chapters: NewBook["chapters"];
  annotations: FlowAnnotation[];
};

export type ParsedSpan = { start: number; end: number; label: string; id: string | null };

const TAG_SPLIT = /(<[^>]+>)/;
const TAG = /^<\s*(\/?)\s*([a-z_]+)(?:\s[^>]*?)?>$/;
const ID_ATTR = /\bid="([^"]+)"/;

const SPAN_LABELS = new Set<string>([
  "quran", "person", "place", "book_ref", "hadith_ref", "date_hijri",
  "footnote", "isnad", "matn", "takhrij",
]);

function unescape(s: string): string {
  return s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
}

/** Tolerant compile of one flow page fragment. Seeds the inherited open-tag
 *  stack (those tags began before this page, so start at offset 0), parses the
 *  fragment, and closes any tag still open at the page end. Returns the page
 *  plain text and the label spans over it. Assumes the underlying document is
 *  well-formed (slices come from a balanced tagged document). */
export function parseFlowPage(
  tagged: string,
  openTags: OpenTag[],
): { text: string; spans: ParsedSpan[] } {
  const stack: { label: string; id: string | null; start: number }[] = [];
  const spans: ParsedSpan[] = [];
  let text = "";

  for (const o of openTags) stack.push({ label: o.name, id: o.id, start: 0 });

  for (const part of tagged.split(TAG_SPLIT)) {
    if (!part) continue;
    const m = part.startsWith("<") ? TAG.exec(part) : null;
    if (m) {
      const closing = m[1] === "/";
      const name = m[2];
      if (!closing) {
        const idm = ID_ATTR.exec(part);
        stack.push({ label: name, id: idm ? idm[1] : null, start: text.length });
      } else {
        for (let i = stack.length - 1; i >= 0; i--) {
          if (stack[i].label === name) {
            const t = stack.splice(i, 1)[0];
            spans.push({ start: t.start, end: text.length, label: t.label, id: t.id });
            break;
          }
        }
      }
    } else {
      text += unescape(part);
    }
  }

  for (const t of stack) {
    spans.push({ start: t.start, end: text.length, label: t.label, id: t.id });
  }
  spans.sort((a, b) => a.start - b.start || b.end - a.end);
  return { text, spans };
}

/** Inline label spans within `[s,e)`, clipped and re-based to block-local
 *  offsets. The `heading` container is excluded (it drives block splitting, not
 *  inline styling). */
function clipSpans(spans: ParsedSpan[], s: number, e: number): NewSpan[] {
  return spans
    .filter((sp) => sp.label !== "heading" && SPAN_LABELS.has(sp.label) && sp.start < e && s < sp.end)
    .map((sp) => ({
      start: Math.max(sp.start, s) - s,
      end: Math.min(sp.end, e) - s,
      label: sp.label as SpanLabel,
      ref: null,
      sub: null,
      conf: null,
    }))
    .filter((sp) => sp.end > sp.start);
}

/** Split one page's text into blocks at the given heading ranges (page-local
 *  offsets): prose around the headings, a `heading` block for each. A page with
 *  no heading is one prose block. Inline spans (isnad/matn/person/...) are
 *  clipped per block; the `hadith` container is dropped (unit identity lives in
 *  `annotations`). */
function pageToBlocks(
  text: string,
  spans: ParsedSpan[],
  headingRanges: [number, number][],
): NewBlock[] {
  const headings = headingRanges
    .map(([s, e]): [number, number] => [Math.max(0, s), Math.min(text.length, e)])
    .filter(([s, e]) => e > s)
    .sort((a, b) => a[0] - b[0]);

  if (headings.length === 0) {
    return [{ key: "b0", type: "prose", text, spans: clipSpans(spans, 0, text.length) }];
  }

  const blocks: NewBlock[] = [];
  let cursor = 0;
  const add = (s: number, e: number, type: "prose" | "heading") => {
    if (e <= s) return;
    const block: NewBlock = {
      key: `b${blocks.length}`,
      type,
      text: text.slice(s, e),
      spans: clipSpans(spans, s, e),
    };
    if (type === "heading") block.level = 1;
    blocks.push(block);
  };
  for (const [hs, he] of headings) {
    add(cursor, hs, "prose");
    add(hs, he, "heading");
    cursor = he;
  }
  add(cursor, text.length, "prose");
  return blocks;
}

/** Convert a FlowBook into the NewBook shape: each page split into prose/heading
 *  blocks (headings come from standoff `heading` annotations mapped to page-local
 *  offsets), so headings render as headings and the hadith body styles
 *  continuously across page seams. */
export function flowToNewBook(book: FlowBook): NewBook {
  const headingAnns = book.annotations.filter((a) => a.label === "heading");
  return {
    metadata: book.metadata,
    chapters: book.chapters,
    pages: book.pages.map((p) => {
      const { text, spans } = parseFlowPage(p.tagged, p.open_tags);
      const localHeadings: [number, number][] = headingAnns
        .map((a): [number, number] => [a.start - p.start_offset, a.end - p.start_offset])
        .filter(([s, e]) => e > 0 && s < text.length);
      return {
        page_number: p.page_number,
        volume: p.volume,
        blocks: pageToBlocks(text, spans, localHeadings),
      };
    }),
  };
}
