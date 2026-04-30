import "server-only";
import { promises as fs } from "node:fs";
import path from "node:path";
import { cache } from "react";
import type { Author, Book, BookListItem, Chapter, Page } from "./types";

type PageRange = { volume: number; page_number: number };

// Reader reads from local JSON dumps produced by:
//   python -m ingestion ingest <uri> --dump web/data --dry-run
// Three suffix tiers, in preference order:
//   <openiti_id>.enriched.json   — full pipeline (parse + tashkeel + Claude)
//   <openiti_id>.tashkeeled.json — parse + tashkeel
//   <openiti_id>.parsed.json     — parse only
// Reader picks the highest-tier file present.
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

/** Build a lookup so the renderer can stamp chapter anchors on heading
 *  blocks without scanning the chapter list per block.
 *  Map shape: page_number → block_index → sort_order.
 *  Synthesized chapters are skipped — they have no real heading block to
 *  anchor onto (volume markers, not in-text headings). */
export function chapterAnchorMap(
  chapters: Chapter[],
): Map<number, Map<number, number>> {
  const out = new Map<number, Map<number, number>>();
  for (const c of chapters) {
    if (c.synthesized) continue;
    if (typeof c.block_index !== "number") continue;
    let inner = out.get(c.page_number);
    if (!inner) {
      inner = new Map();
      out.set(c.page_number, inner);
    }
    inner.set(c.block_index, c.sort_order);
  }
  return out;
}

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

type LoadTier = "enriched" | "tashkeeled" | "parsed";

async function readFileIfExists(p: string): Promise<string | null> {
  try {
    return await fs.readFile(p, "utf-8");
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw e;
  }
}

const _loadBookFile = cache(async (
  openitiId: string,
): Promise<{ data: LocalBookFile; tier: LoadTier } | null> => {
  const tiers: { suffix: string; tier: LoadTier }[] = [
    { suffix: ".enriched.json", tier: "enriched" },
    { suffix: ".tashkeeled.json", tier: "tashkeeled" },
    { suffix: ".parsed.json", tier: "parsed" },
  ];
  for (const { suffix, tier } of tiers) {
    const raw = await readFileIfExists(path.join(DATA_DIR, `${openitiId}${suffix}`));
    if (raw) return { data: JSON.parse(raw) as LocalBookFile, tier };
  }
  return null;
});

const _listDataIds = cache(async (): Promise<string[]> => {
  let entries: string[];
  try {
    entries = await fs.readdir(DATA_DIR);
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw e;
  }
  const ids = new Set<string>();
  for (const filename of entries) {
    const m = filename.match(/^(.+?)\.(enriched|tashkeeled|parsed)\.json$/);
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
    const { data, tier } = loaded;
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
      has_tashkeel: tier === "enriched" || tier === "tashkeeled",
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
  const { data, tier } = loaded;
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
    has_tashkeel: tier === "enriched" || tier === "tashkeeled",
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
