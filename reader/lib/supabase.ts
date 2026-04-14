import 'react-native-url-polyfill/auto';
import 'expo-sqlite/localStorage/install';
import { createClient } from '@supabase/supabase-js';
import type { Book, Page, Chapter } from '../types';
import { coverColors } from '../constants/theme';

const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY!;

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    storage: localStorage,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
  },
});

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Map a Supabase `books` row (with joined author) to the reader's Book type. */
function mapBook(row: any, index: number): Book {
  // Map genres array -> first matching category, or null
  const genres: string[] = row.genres ?? [];
  const category = (genres[0] as Book['category']) ?? null;

  return {
    id: row.id,
    openiti_id: row.openiti_id,
    title_ar: row.title_ar ?? '',
    title_en: row.title_lat ?? row.title_ar ?? '',
    author_ar: row.authors?.shuhra_ar ?? null,
    author_en: row.authors?.full_name_ar ?? row.authors?.shuhra_lat ?? null,
    category,
    level: null,
    cover_color: coverColors[index % coverColors.length],
    page_count: row.total_pages ?? 0,
    content_hash: null,
  };
}

/** Map a Supabase `pages` row to the reader's Page type. */
function mapPage(row: any): Page {
  const blocks = row.content_blocks ?? row.blocks ?? [];
  return {
    id: row.id,
    book_id: row.book_id,
    page_number: row.page_number,
    blocks: typeof blocks === 'string' ? JSON.parse(blocks) : blocks,
  };
}

// ─── Public API ───────────────────────────────────────────────────────────────

/** Fetch all books from the catalog. */
export async function fetchBookCatalog(): Promise<Book[]> {
  const { data, error } = await supabase
    .from('books')
    .select('*, authors(shuhra_ar, shuhra_lat, full_name_ar)')
    .order('title_ar', { ascending: true });
  if (error) throw error;
  return (data ?? []).map(mapBook);
}

/** Fetch books by category (matches against the genres array). */
export async function fetchBooksByCategory(category: string): Promise<Book[]> {
  const { data, error } = await supabase
    .from('books')
    .select('*, authors(shuhra_ar, shuhra_lat, full_name_ar)')
    .contains('genres', [category])
    .order('title_ar', { ascending: true });
  if (error) throw error;
  return (data ?? []).map(mapBook);
}

/** Fetch all pages for a book. */
export async function fetchBookPages(bookId: string): Promise<Page[]> {
  const { data, error } = await supabase
    .from('pages')
    .select('*')
    .eq('book_id', bookId)
    .order('page_number', { ascending: true });
  if (error) throw error;
  return (data ?? []).map(mapPage);
}

/** Fetch chapters for a book. */
export async function fetchBookChapters(bookId: string): Promise<Chapter[]> {
  const { data, error } = await supabase
    .from('chapters')
    .select('id, book_id, title, sort_order, page_id, pages!inner(page_number)')
    .eq('book_id', bookId)
    .order('sort_order', { ascending: true });
  if (error) {
    // Fallback: simpler query without join if pages relation fails
    const { data: fallback, error: err2 } = await supabase
      .from('chapters')
      .select('*')
      .eq('book_id', bookId)
      .order('sort_order', { ascending: true });
    if (err2) throw err2;
    return (fallback ?? []).map((row: any) => ({
      id: row.id,
      book_id: row.book_id,
      title: row.title,
      start_page: row.sort_order ?? 1,
    }));
  }
  return (data ?? []).map((row: any) => ({
    id: row.id,
    book_id: row.book_id,
    title: row.title,
    start_page: row.pages?.page_number ?? row.sort_order ?? 1,
  }));
}

/** Search books by title (Arabic or Latinized). */
export async function searchBooks(query: string): Promise<Book[]> {
  const sanitized = query.replace(/[%_,().]/g, '');
  if (!sanitized) return fetchBookCatalog();
  const { data, error } = await supabase
    .from('books')
    .select('*, authors(shuhra_ar, shuhra_lat, full_name_ar)')
    .or(`title_lat.ilike.%${sanitized}%,title_ar.ilike.%${sanitized}%`)
    .order('title_ar', { ascending: true });
  if (error) throw error;
  return (data ?? []).map(mapBook);
}
