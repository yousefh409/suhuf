import "server-only";
import { getSupabase } from "@/lib/supabase";
import type { Author, Book, BookListItem, Chapter, Page } from "./types";

type PageRange = { volume: number; page_number: number };

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

export async function listBooks(): Promise<BookListItem[]> {
  const sb = getSupabase();
  const { data, error } = await sb
    .from("books")
    .select(
      "openiti_id,title_ar,title_lat,total_pages,total_volumes,has_tashkeel,authors:author_id(shuhra_ar,full_name_ar)",
    )
    .order("openiti_id");
  if (error) throw error;
  return (data ?? []).map((b: Record<string, unknown>) => {
    const author = b.authors as { shuhra_ar?: string; full_name_ar?: string } | null;
    return {
      openiti_id: b.openiti_id as string,
      title_ar: b.title_ar as string,
      title_lat: (b.title_lat as string | null) ?? null,
      total_pages: (b.total_pages as number | null) ?? null,
      total_volumes: (b.total_volumes as number | null) ?? null,
      has_tashkeel: (b.has_tashkeel as boolean | null) ?? null,
      author_name_ar: author?.full_name_ar ?? author?.shuhra_ar ?? null,
    };
  });
}

export async function getBook(
  openitiId: string,
): Promise<{ book: Book; author: Author | null } | null> {
  const sb = getSupabase();
  const { data, error } = await sb
    .from("books")
    .select("*,authors:author_id(*)")
    .eq("openiti_id", openitiId)
    .maybeSingle();
  if (error) throw error;
  if (!data) return null;
  const { authors: authorRow, ...bookFields } = data as Record<string, unknown> & {
    authors?: Author | null;
  };
  return { book: bookFields as unknown as Book, author: authorRow ?? null };
}

export async function getEffectiveChapters(bookId: string): Promise<Chapter[]> {
  const sb = getSupabase();
  const [chapRes, pageRes] = await Promise.all([
    sb
      .from("chapters")
      .select("id,title,level,sort_order,pages:page_id(page_number,volume)")
      .eq("book_id", bookId)
      .order("sort_order"),
    sb
      .from("pages")
      .select("volume,page_number")
      .eq("book_id", bookId),
  ]);
  if (chapRes.error) throw chapRes.error;
  if (pageRes.error) throw pageRes.error;

  const real: Chapter[] = (chapRes.data ?? []).map((c: Record<string, unknown>) => {
    const pageJoin = c.pages as { page_number?: number; volume?: number } | null;
    return {
      id: c.id as string,
      title: c.title as string,
      level: c.level as number,
      sort_order: c.sort_order as number,
      page_number: pageJoin?.page_number ?? 0,
      volume: pageJoin?.volume ?? 1,
    };
  });

  return synthesizeChapters(real, pageRes.data as PageRange[] ?? []);
}

export async function getAllPagesForBook(bookId: string): Promise<Page[]> {
  const sb = getSupabase();
  const { data, error } = await sb
    .from("pages")
    .select("page_number,volume,content_blocks")
    .eq("book_id", bookId)
    .order("volume")
    .order("page_number");
  if (error) throw error;
  return (data ?? []) as Page[];
}
