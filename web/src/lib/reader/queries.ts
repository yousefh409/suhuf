import "server-only";
import { promises as fs } from "node:fs";
import path from "node:path";
import { cache } from "react";
import type { Author, Book, BookListItem, Chapter, NewBlock, NewBook, Page } from "./types";
import { convertNewBook } from "./newFormat";
import { flowToNewBook, type FlowBook } from "./flowFormat";
import { createClient } from "@/lib/supabase/server";

// The reader loads books from Supabase (the tagged format in pages.content_blocks)
// in production — local-file reads via node:fs do not work on Cloudflare Workers —
// and whenever READER_SOURCE=supabase. In dev it defaults to the local dumps, so
// the edit -> dump -> reload loop is unchanged (set READER_SOURCE=local to force
// local even in production-like builds).
const USE_SUPABASE =
  process.env.READER_SOURCE === "supabase" ||
  (process.env.NODE_ENV === "production" && process.env.READER_SOURCE !== "local");

type PageRange = { volume: number; page_number: number };

// Reader reads from local JSON dumps produced by:
//   python -m ingestion ingest <uri> --dump web/data --dry-run
// Suffix tiers, in preference order:
//   <openiti_id>.book.json       — NEW simpler format (char-offset spans, no tokens)
//   <openiti_id>.enriched.json   — full pipeline (parse + tashkeel + annotate + Claude meta)
//   <openiti_id>.annotated.json  — parse + tashkeel + Claude annotation pass
//   <openiti_id>.tashkeeled.json — parse + tashkeel
//   <openiti_id>.parsed.json     — parse only
// Reader picks the highest-tier file present. The NEW .book.json is normalised
// into the legacy in-memory shape (see newFormat.ts) so the rest of this layer
// and the renderer stay unchanged.
const DATA_DIR = path.join(process.cwd(), "data");

/** If real chapters exist, return them. Otherwise generate one synthetic
 *  chapter per distinct volume, titled "Volume N", at that volume's earliest
 *  page_number. */
export function synthesizeChapters(
  real: Chapter[],
  pageRanges: PageRange[],
): Chapter[] {
  if (real.length > 0) return real;
  if (pageRanges.length === 0) return [];

  const earliestByVolume = new Map<number, number>();
  for (const { volume, page_number } of pageRanges) {
    const cur = earliestByVolume.get(volume);
    if (cur === undefined || page_number < cur) {
      earliestByVolume.set(volume, page_number);
    }
  }

  return [...earliestByVolume.entries()]
    .sort(([a], [b]) => a - b)
    .map(([volume, firstPage], i) => ({
      title: `Volume ${volume}`,
      level: 0,
      page_number: firstPage,
      volume,
      sort_order: i + 1,
      synthesized: true,
    }));
}

export { chapterAnchorMap } from "./chapters";

// ---------- local file loading ----------

type RawChapter = {
  title: string;
  level: number;
  page_number: number;
  sort_order: number;
  parent_index?: number | null;
  block_index?: number | null;
};

type EnrichedBookData = {
  title_en?: string | null;
  description?: string | null;
  genres?: string[] | null;
  composition_date_ah?: number | null;
  commentary_on?: string | null;
  abridgement_of?: string | null;
};

type EnrichedAuthorData = {
  full_name_en?: string | null;
  bio_en?: string | null;
  birth_ah?: number | null;
  death_ah?: number | null;
  primary_fields?: string[] | null;
};

// Author yml (parsed by ingestion/metadata.py). Field names mirror the
// `_AUTH_FIELD_MAP` in that module; OpenITI's `_AR` keys map to our `_lat`.
type AuthorYmlData = {
  shuhra_lat?: string;
  ism_lat?: string;
  nasab_lat?: string;
  kunya_lat?: string;
  laqab_lat?: string;
  nisba_lat?: string;
  birth_ah?: number;
  death_ah?: number;
};

type LocalBookFile = {
  metadata: {
    openiti_id: string;
    title_ar: string;
    title_lat?: string | null;
    author_openiti_id: string;
    genres?: string[];
    language?: string;
    word_count?: number | null;
    char_count?: number | null;
  };
  pages: Page[];
  chapters: RawChapter[];
  // Only present in enriched.json
  enrichment?: {
    book?: EnrichedBookData;
    author?: EnrichedAuthorData;
  };
  author_data?: AuthorYmlData;
};

type LoadTier = "flow" | "book" | "enriched" | "annotated" | "tashkeeled" | "parsed";

const TASHKEEL_RE = /[\u064B-\u065F\u0670]/u;

/** Sample tokens until we find tashkeel or hit a budget. */
export function hasTashkeel(pages: Page[], budget = 100): boolean {
  let sampled = 0;
  for (const page of pages) {
    for (const block of page.content_blocks) {
      const tokens =
        block.type === "poetry"
          ? block.hemistichs.flat().flat()
          : block.tokens;
      for (const t of tokens) {
        if (TASHKEEL_RE.test(t.text)) return true;
        if (++sampled >= budget) return false;
      }
    }
  }
  return false;
}

async function readFileIfExists(p: string): Promise<string | null> {
  try {
    return await fs.readFile(p, "utf-8");
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw e;
  }
}

// Reconstruct a NewBook from Supabase rows (pages.content_blocks holds the new
// tagged blocks) and normalise it the same way as a local .book.json. Chapter
// block_index is derived by matching the chapter title to a heading block in its
// page (the chapters table has no block_index column).
async function _loadBookFromSupabase(
  openitiId: string,
): Promise<{ data: LocalBookFile; tier: LoadTier } | null> {
  const supabase = await createClient();
  const { data: bookRow } = await supabase
    .from("books")
    .select("id, title_ar, title_lat, genres, language, authors(openiti_id)")
    .eq("openiti_id", openitiId)
    .maybeSingle();
  if (!bookRow) return null;

  const [{ data: pageRows }, { data: chapterRows }] = await Promise.all([
    supabase
      .from("pages")
      .select("id, page_number, volume, content_blocks")
      .eq("book_id", bookRow.id)
      .order("volume", { ascending: true })
      .order("page_number", { ascending: true }),
    supabase
      .from("chapters")
      .select("title, level, sort_order, page_id")
      .eq("book_id", bookRow.id)
      .order("sort_order", { ascending: true }),
  ]);

  const pages = (pageRows ?? []).map((p) => ({
    page_number: p.page_number as number,
    volume: p.volume as number,
    blocks: p.content_blocks as NewBlock[],
    footnotes: [],
  }));
  const pageById = new Map((pageRows ?? []).map((p) => [p.id, p]));

  const chapters = (chapterRows ?? []).map((c) => {
    const pg = c.page_id ? pageById.get(c.page_id) : undefined;
    const blocks = (pg?.content_blocks as NewBlock[] | undefined) ?? [];
    const bi = blocks.findIndex(
      (b) => b.type === "heading" && (b.text ?? "").trim() === c.title.trim(),
    );
    return {
      title: c.title as string,
      level: c.level as number,
      page_number: (pg?.page_number as number) ?? 1,
      sort_order: c.sort_order as number,
      block_index: bi >= 0 ? bi : null,
    };
  });

  const authorRel = bookRow.authors as { openiti_id: string } | { openiti_id: string }[] | null;
  const author_openiti_id = Array.isArray(authorRel)
    ? authorRel[0]?.openiti_id ?? ""
    : authorRel?.openiti_id ?? "";

  const newBook: NewBook = {
    metadata: {
      openiti_id: openitiId,
      title_ar: bookRow.title_ar as string,
      title_lat: (bookRow.title_lat as string | null) ?? null,
      author_openiti_id,
      genres: (bookRow.genres as string[] | null) ?? [],
      language: (bookRow.language as string | null) ?? undefined,
    },
    pages,
    chapters,
  };
  return { data: convertNewBook(newBook) as LocalBookFile, tier: "book" };
}

const _loadBookFile = cache(async (
  openitiId: string,
): Promise<{ data: LocalBookFile; tier: LoadTier } | null> => {
  if (USE_SUPABASE) return _loadBookFromSupabase(openitiId);
  // Read all tiers in parallel; missing files just return null.
  const [flowRaw, bookRaw, enrichedRaw, annotatedRaw, tashkeeledRaw, parsedRaw] = await Promise.all([
    readFileIfExists(path.join(DATA_DIR, `${openitiId}.flow.json`)),
    readFileIfExists(path.join(DATA_DIR, `${openitiId}.book.json`)),
    readFileIfExists(path.join(DATA_DIR, `${openitiId}.enriched.json`)),
    readFileIfExists(path.join(DATA_DIR, `${openitiId}.annotated.json`)),
    readFileIfExists(path.join(DATA_DIR, `${openitiId}.tashkeeled.json`)),
    readFileIfExists(path.join(DATA_DIR, `${openitiId}.parsed.json`)),
  ]);

  // FLOW format wins when present: the continuous tagged document sliced into
  // page rows. flowToNewBook parses each page (with its open-tag stack) into the
  // NewBook shape, then convertNewBook normalises it like any other new book.
  if (flowRaw) {
    const normalised = convertNewBook(flowToNewBook(JSON.parse(flowRaw) as FlowBook));
    return { data: normalised as LocalBookFile, tier: "flow" };
  }

  // NEW format wins when present: it's the whole Book object, normalised into
  // the legacy LocalBookFile shape so everything downstream is unchanged.
  if (bookRaw) {
    const normalised = convertNewBook(JSON.parse(bookRaw) as NewBook);
    return { data: normalised as LocalBookFile, tier: "book" };
  }

  // Defense: a higher-tier file from a run where tashkeel was skipped
  // (no engine, or engine failed) silently shadows a good lower-tier
  // file with diacritics. If the chosen tier is missing tashkeel, splice
  // pages from the highest lower tier that has it — we keep the higher
  // tier's metadata *and* the diacritics.
  const lowerRawsWithTashkeel = [annotatedRaw, tashkeeledRaw];
  const trySplice = (data: LocalBookFile): LocalBookFile => {
    if (hasTashkeel(data.pages)) return data;
    for (const lowerRaw of lowerRawsWithTashkeel) {
      if (!lowerRaw) continue;
      const lower = JSON.parse(lowerRaw) as LocalBookFile;
      if (hasTashkeel(lower.pages)) {
        data.pages = lower.pages;
        return data;
      }
    }
    return data;
  };

  if (enrichedRaw) {
    return { data: trySplice(JSON.parse(enrichedRaw) as LocalBookFile), tier: "enriched" };
  }
  if (annotatedRaw) {
    return { data: trySplice(JSON.parse(annotatedRaw) as LocalBookFile), tier: "annotated" };
  }
  if (tashkeeledRaw) {
    return { data: JSON.parse(tashkeeledRaw) as LocalBookFile, tier: "tashkeeled" };
  }
  if (parsedRaw) {
    return { data: JSON.parse(parsedRaw) as LocalBookFile, tier: "parsed" };
  }
  return null;
});

const _listDataIds = cache(async (): Promise<string[]> => {
  // No local data dir in Supabase mode (and node:fs is unavailable on Workers).
  if (USE_SUPABASE) return [];
  let entries: string[];
  try {
    entries = await fs.readdir(DATA_DIR);
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw e;
  }
  const ids = new Set<string>();
  for (const filename of entries) {
    const m = filename.match(/^(.+?)\.(book|enriched|annotated|tashkeeled|parsed)\.json$/);
    if (m) ids.add(m[1]);
  }
  return [...ids].sort();
});

function authorDisplayAr(data: LocalBookFile): string | null {
  const yml = data.author_data;
  if (!yml) return null;
  const parts = [yml.kunya_lat, yml.ism_lat, yml.nasab_lat, yml.shuhra_lat].filter(Boolean);
  return parts.length > 0 ? parts.join(" ") : (yml.shuhra_lat ?? null);
}

function maxVolume(pages: Page[]): number {
  return pages.length > 0 ? Math.max(...pages.map((p) => p.volume)) : 0;
}

// ---------- public query API ----------

export async function listBooks(): Promise<BookListItem[]> {
  const ids = await _listDataIds();
  const items: BookListItem[] = [];
  for (const id of ids) {
    const loaded = await _loadBookFile(id);
    if (!loaded) continue;
    const { data } = loaded;
    const enrichedBook = data.enrichment?.book ?? {};
    const enrichedAuthor = data.enrichment?.author ?? {};
    items.push({
      openiti_id: id,
      title_ar: data.metadata.title_ar,
      title_lat: data.metadata.title_lat ?? null,
      title_en: enrichedBook.title_en ?? null,
      description: enrichedBook.description ?? null,
      genres: enrichedBook.genres ?? data.metadata.genres ?? null,
      total_pages: data.pages.length,
      total_volumes: maxVolume(data.pages),
      has_tashkeel: hasTashkeel(data.pages),
      author_name_ar: authorDisplayAr(data) ?? data.metadata.author_openiti_id,
      author_name_en: enrichedAuthor.full_name_en ?? null,
    });
  }
  return items;
}

export async function getBook(
  openitiId: string,
): Promise<{ book: Book; author: Author | null } | null> {
  const loaded = await _loadBookFile(openitiId);
  if (!loaded) return null;
  const { data } = loaded;
  const enrichedBook = data.enrichment?.book ?? {};
  const enrichedAuthor = data.enrichment?.author ?? {};
  const yml = data.author_data ?? {};

  const book: Book = {
    id: openitiId,
    openiti_id: openitiId,
    title_ar: data.metadata.title_ar,
    title_lat: data.metadata.title_lat ?? null,
    title_en: enrichedBook.title_en ?? null,
    description: enrichedBook.description ?? null,
    genres: enrichedBook.genres ?? data.metadata.genres ?? null,
    composition_date_ah: enrichedBook.composition_date_ah ?? null,
    commentary_on: enrichedBook.commentary_on ?? null,
    abridgement_of: enrichedBook.abridgement_of ?? null,
    total_pages: data.pages.length,
    total_volumes: maxVolume(data.pages),
    has_tashkeel: hasTashkeel(data.pages),
    language: data.metadata.language ?? null,
    author_id: data.metadata.author_openiti_id,
  };
  const author: Author = {
    id: data.metadata.author_openiti_id,
    openiti_id: data.metadata.author_openiti_id,
    full_name_ar: authorDisplayAr(data),
    shuhra_ar: yml.shuhra_lat ?? null,
    full_name_en: enrichedAuthor.full_name_en ?? null,
    bio_en: enrichedAuthor.bio_en ?? null,
    birth_ah: enrichedAuthor.birth_ah ?? yml.birth_ah ?? null,
    death_ah: enrichedAuthor.death_ah ?? yml.death_ah ?? null,
    primary_fields: enrichedAuthor.primary_fields ?? null,
  };
  return { book, author };
}

export async function getEffectiveChapters(bookId: string): Promise<Chapter[]> {
  // bookId === openiti_id in local mode.
  const loaded = await _loadBookFile(bookId);
  if (!loaded) return [];
  const { data } = loaded;

  // Ingestion's Chapter doesn't carry volume; it always uses volume=1 today.
  // If/when chapters span volumes, this needs to look up each chapter's page row.
  const real: Chapter[] = data.chapters.map((c) => ({
    title: c.title,
    level: c.level,
    page_number: c.page_number,
    volume: 1,
    sort_order: c.sort_order,
    block_index: c.block_index ?? null,
  }));

  const pageRanges: PageRange[] = data.pages.map((p) => ({
    volume: p.volume,
    page_number: p.page_number,
  }));
  return synthesizeChapters(real, pageRanges);
}

export async function getAllPagesForBook(bookId: string): Promise<Page[]> {
  const loaded = await _loadBookFile(bookId);
  if (!loaded) return [];
  return loaded.data.pages;
}
