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

/** Convert a FlowBook into the NewBook shape: one prose block per page carrying
 *  the page's label spans (the `hadith` container tag is dropped — it is the unit
 *  boundary, not a styled span; unit identity lives in `annotations`). */
export function flowToNewBook(book: FlowBook): NewBook {
  return {
    metadata: book.metadata,
    chapters: book.chapters,
    pages: book.pages.map((p) => {
      const { text, spans } = parseFlowPage(p.tagged, p.open_tags);
      const newSpans: NewSpan[] = spans
        .filter((s) => s.end > s.start && SPAN_LABELS.has(s.label))
        .map((s) => ({
          start: s.start,
          end: s.end,
          label: s.label as SpanLabel,
          ref: null,
          sub: null,
          conf: null,
        }));
      const block: NewBlock = { key: "b0", type: "prose", text, spans: newSpans };
      return { page_number: p.page_number, volume: p.volume, blocks: [block] };
    }),
  };
}
