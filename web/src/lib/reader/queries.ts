import "server-only";
import { promises as fs } from "node:fs";
import path from "node:path";
import { cache } from "react";
import type { Author, Book, BookListItem, Chapter, Page } from "./types";

type PageRange = { volume: number; page_number: number };

// Reader reads from local JSON dumps produced by:
//   python -m ingestion ingest <uri> --dump web/data --dry-run --skip-enrich
// Files are <openiti_id>.parsed.json (raw parse) and <openiti_id>.tashkeeled.json
// (with diacritization). Tashkeeled wins when both exist.
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

/** Filter all pages of a book to those that belong to the given chapter.
 *  - Synthesized chapter: one volume == one chapter, return all of that volume.
 *  - Real chapter: return same-volume pages with page_number in
 *    [chapter.page_number, nextChapter.page_number) on the same volume.
 *    If nextChapter is null, return through end of that volume.
 *    Real chapters spanning volumes are out of scope for v1; we cut at the
 *    volume boundary. */
export function pagesInChapter(
  allPages: Page[],
  chapter: Chapter,
  nextChapter: Chapter | null,
): Page[] {
  if (chapter.synthesized) {
    return allPages.filter((p) => p.volume === chapter.volume);
  }
  return allPages.filter((p) => {
    if (p.volume !== chapter.volume) return false;
    if (p.page_number < chapter.page_number) return false;
    if (
      nextChapter &&
      nextChapter.volume === chapter.volume &&
      p.page_number >= nextChapter.page_number
    ) {
      return false;
    }
    return true;
  });
}

// ---------- local file loading ----------

type RawChapter = {
  title: string;
  level: number;
  page_number: number;
  sort_order: number;
  parent_index?: number | null;
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
};

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
): Promise<{ data: LocalBookFile; tashkeeled: boolean } | null> => {
  const tashkeeled = await readFileIfExists(
    path.join(DATA_DIR, `${openitiId}.tashkeeled.json`),
  );
  if (tashkeeled) {
    return { data: JSON.parse(tashkeeled) as LocalBookFile, tashkeeled: true };
  }
  const parsed = await readFileIfExists(
    path.join(DATA_DIR, `${openitiId}.parsed.json`),
  );
  if (parsed) {
    return { data: JSON.parse(parsed) as LocalBookFile, tashkeeled: false };
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
    const m = filename.match(/^(.+?)\.(tashkeeled|parsed)\.json$/);
    if (m) ids.add(m[1]);
  }
  return [...ids].sort();
});

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
    const { data, tashkeeled } = loaded;
    items.push({
      openiti_id: id,
      title_ar: data.metadata.title_ar,
      title_lat: data.metadata.title_lat ?? null,
      total_pages: data.pages.length,
      total_volumes: maxVolume(data.pages),
      has_tashkeel: tashkeeled,
      author_name_ar: data.metadata.author_openiti_id,
    });
  }
  return items;
}

export async function getBook(
  openitiId: string,
): Promise<{ book: Book; author: Author | null } | null> {
  const loaded = await _loadBookFile(openitiId);
  if (!loaded) return null;
  const { data, tashkeeled } = loaded;
  const book: Book = {
    id: openitiId,
    openiti_id: openitiId,
    title_ar: data.metadata.title_ar,
    title_lat: data.metadata.title_lat ?? null,
    description: null,
    genres: data.metadata.genres ?? null,
    total_pages: data.pages.length,
    total_volumes: maxVolume(data.pages),
    has_tashkeel: tashkeeled,
    language: data.metadata.language ?? null,
    author_id: data.metadata.author_openiti_id,
  };
  const author: Author = {
    id: data.metadata.author_openiti_id,
    openiti_id: data.metadata.author_openiti_id,
    full_name_ar: null,
    shuhra_ar: null,
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
