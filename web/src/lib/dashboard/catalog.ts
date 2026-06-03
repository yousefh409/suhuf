import "server-only";

import { createClient } from "@/lib/supabase/server";
import type { DiscoverBook, DiscoverQuery, Genre } from "./types";
import { selectDiscover } from "./select";

function slugify(label: string): string {
  return label.toLowerCase().replace(/\s+/g, "-");
}

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
  word_count: number | null;
  // Supabase returns a single foreign-key join as an array of one
  authors: AuthorRow[] | AuthorRow | null;
};

function getAuthor(authors: AuthorRow[] | AuthorRow | null): AuthorRow | null {
  if (!authors) return null;
  if (Array.isArray(authors)) return authors[0] ?? null;
  return authors;
}

function mapToDiscoverBook(row: BookRow): DiscoverBook {
  const author = getAuthor(row.authors);
  return {
    openitiId: row.openiti_id,
    titleAr: row.title_ar,
    titleLat: row.title_lat ?? undefined,
    titleEn: undefined,
    authorName: author?.shuhra_lat ?? author?.shuhra_ar ?? "Unknown",
    coverUrl: undefined,
    genre: row.genres?.[0] ?? "Uncategorized",
    level: "",
    popularity: row.word_count ?? 0,
  };
}

export async function queryDiscover(query: DiscoverQuery): Promise<DiscoverBook[]> {
  const sb = await createClient();
  const { data, error } = await sb
    .from("books")
    .select("id, openiti_id, title_ar, title_lat, genres, word_count, authors(shuhra_lat, shuhra_ar)");

  if (error) {
    console.error("[catalog] queryDiscover error:", error.message);
    return [];
  }

  const mapped = (data as unknown as BookRow[]).map(mapToDiscoverBook);
  return selectDiscover(mapped, query);
}

export async function queryGenres(): Promise<Genre[]> {
  const sb = await createClient();
  const { data, error } = await sb.from("books").select("genres");

  if (error) {
    console.error("[catalog] queryGenres error:", error.message);
    return [];
  }

  const counts = new Map<string, number>();
  for (const row of data as { genres: string[] | null }[]) {
    for (const label of row.genres ?? []) {
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
  }

  return Array.from(counts.entries())
    .map(([label, count]) => ({ slug: slugify(label), label, count }))
    .sort((a, b) => b.count - a.count);
}
