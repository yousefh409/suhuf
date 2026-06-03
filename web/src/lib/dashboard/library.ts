import "server-only";

import { createClient } from "@/lib/supabase/server";
import type {
  LibraryEntry,
  LibraryStatus,
  ContinueReadingItem,
  RecommendedBook,
} from "./types";

type AuthorRow = {
  shuhra_lat: string | null;
  shuhra_ar: string | null;
};

type BookRow = {
  id: string;
  openiti_id: string;
  title_ar: string;
  title_lat: string | null;
  genres: string[] | null;
  total_pages: number | null;
  // Supabase returns FK join as array of one
  authors: AuthorRow[] | AuthorRow | null;
};

type LibraryRow = {
  book_id: string;
  status: string;
  last_opened_at: string | null;
  books: BookRow[] | BookRow | null;
};

type PositionRow = {
  book_id: string;
  pages: { page_number: number } | { page_number: number }[] | null;
};

function getAuthor(authors: AuthorRow[] | AuthorRow | null): AuthorRow | null {
  if (!authors) return null;
  if (Array.isArray(authors)) return authors[0] ?? null;
  return authors;
}

function getBook(books: BookRow[] | BookRow | null): BookRow | null {
  if (!books) return null;
  if (Array.isArray(books)) return books[0] ?? null;
  return books;
}

function getPageNumber(pages: { page_number: number } | { page_number: number }[] | null): number | null {
  if (!pages) return null;
  if (Array.isArray(pages)) return pages[0]?.page_number ?? null;
  return pages.page_number;
}

function calcProgress(pageNumber: number | null, totalPages: number | null): number {
  if (!pageNumber || !totalPages || totalPages === 0) return 0;
  return Math.min(100, Math.max(0, Math.round((pageNumber / totalPages) * 100)));
}

/** Build a map of book_id → progressPercent from user_reading_positions + pages */
async function buildProgressMap(
  userId: string,
  bookIds: string[],
): Promise<Map<string, number>> {
  const map = new Map<string, number>();
  if (bookIds.length === 0) return map;

  const sb = await createClient();

  // Fetch positions with page data
  const { data: positions, error } = await sb
    .from("user_reading_positions")
    .select("book_id, pages(page_number)")
    .eq("user_id", userId)
    .in("book_id", bookIds);

  if (error) {
    console.error("[library] buildProgressMap error:", error.message);
    return map;
  }

  // Also fetch total_pages for each book
  const { data: books, error: bErr } = await sb
    .from("books")
    .select("id, total_pages")
    .in("id", bookIds);

  if (bErr) {
    console.error("[library] buildProgressMap books error:", bErr.message);
    return map;
  }

  const totalPagesById = new Map<string, number>();
  for (const b of (books ?? []) as { id: string; total_pages: number | null }[]) {
    if (b.total_pages) totalPagesById.set(b.id, b.total_pages);
  }

  for (const pos of (positions ?? []) as unknown as PositionRow[]) {
    const pageNumber = getPageNumber(pos.pages);
    const totalPages = totalPagesById.get(pos.book_id) ?? null;
    map.set(pos.book_id, calcProgress(pageNumber, totalPages));
  }

  return map;
}

export async function queryLibrary(status: LibraryStatus): Promise<LibraryEntry[]> {
  const sb = await createClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return [];

  const { data, error } = await sb
    .from("user_library")
    .select("book_id, status, last_opened_at, books(id, openiti_id, title_ar, title_lat, genres, total_pages, authors(shuhra_lat, shuhra_ar))")
    .eq("user_id", user.id)
    .eq("status", status);

  if (error) {
    console.error("[library] queryLibrary error:", error.message);
    return [];
  }

  const rows = data as unknown as LibraryRow[];
  const bookIds = rows.map((r) => r.book_id);
  const progressMap = await buildProgressMap(user.id, bookIds);

  return rows.map((row): LibraryEntry => {
    const book = getBook(row.books);
    const author = getAuthor(book?.authors ?? null);
    return {
      openitiId: book?.openiti_id ?? "",
      titleAr: book?.title_ar ?? "",
      titleLat: book?.title_lat ?? undefined,
      titleEn: undefined,
      authorName: author?.shuhra_lat ?? author?.shuhra_ar ?? "Unknown",
      coverUrl: undefined,
      status: row.status as LibraryStatus,
      progressPercent: progressMap.get(row.book_id) ?? 0,
      lastOpenedAt: row.last_opened_at ?? "",
      genre: book?.genres?.[0] ?? undefined,
      level: undefined,
    };
  });
}

export async function queryContinueReading(): Promise<ContinueReadingItem[]> {
  const sb = await createClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return [];

  const { data, error } = await sb
    .from("user_library")
    .select("book_id, status, last_opened_at, books(id, openiti_id, title_ar, title_lat, genres, total_pages, authors(shuhra_lat, shuhra_ar))")
    .eq("user_id", user.id)
    .eq("status", "in_progress")
    .order("last_opened_at", { ascending: false, nullsFirst: false })
    .limit(3);

  if (error) {
    console.error("[library] queryContinueReading error:", error.message);
    return [];
  }

  const rows = data as unknown as LibraryRow[];
  const bookIds = rows.map((r) => r.book_id);
  const progressMap = await buildProgressMap(user.id, bookIds);

  return rows.map((row): ContinueReadingItem => {
    const book = getBook(row.books);
    const author = getAuthor(book?.authors ?? null);
    return {
      openitiId: book?.openiti_id ?? "",
      titleAr: book?.title_ar ?? "",
      titleLat: book?.title_lat ?? undefined,
      titleEn: undefined,
      authorName: author?.shuhra_lat ?? author?.shuhra_ar ?? "Unknown",
      coverUrl: undefined,
      genre: book?.genres?.[0] ?? undefined,
      level: undefined,
      progressPercent: progressMap.get(row.book_id) ?? 0,
      lastOpenedAt: row.last_opened_at ?? "",
    };
  });
}

export async function queryRecommended(): Promise<RecommendedBook[]> {
  const sb = await createClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return [];

  // Get book IDs already in user's library
  const { data: libraryData, error: libErr } = await sb
    .from("user_library")
    .select("book_id")
    .eq("user_id", user.id);

  if (libErr) {
    console.error("[library] queryRecommended library error:", libErr.message);
    return [];
  }

  const ownedIds = (libraryData ?? []).map((r: { book_id: string }) => r.book_id);

  let query = sb
    .from("books")
    .select("id, openiti_id, title_ar, title_lat, genres, authors(shuhra_lat, shuhra_ar)")
    .order("created_at", { ascending: false })
    .limit(10);

  // Exclude owned books if there are any
  if (ownedIds.length > 0) {
    query = query.not("id", "in", `(${ownedIds.join(",")})`);
  }

  const { data, error } = await query;

  if (error) {
    console.error("[library] queryRecommended books error:", error.message);
    return [];
  }

  type RecommendedRow = {
    id: string;
    openiti_id: string;
    title_ar: string;
    title_lat: string | null;
    genres: string[] | null;
    authors: AuthorRow[] | AuthorRow | null;
  };

  return (data as unknown as RecommendedRow[]).map((row): RecommendedBook => {
    const author = getAuthor(row.authors);
    return {
      openitiId: row.openiti_id,
      titleAr: row.title_ar,
      titleLat: row.title_lat ?? undefined,
      titleEn: undefined,
      authorName: author?.shuhra_lat ?? author?.shuhra_ar ?? "Unknown",
      coverUrl: undefined,
      genre: row.genres?.[0] ?? "Uncategorized",
      level: undefined,
    };
  });
}
