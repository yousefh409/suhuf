import { createClient } from '@supabase/supabase-js';
import type { Book, Page, Chapter } from '../types';

const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY!;

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

/** Fetch all books from the catalog. */
export async function fetchBookCatalog(): Promise<Book[]> {
  const { data, error } = await supabase
    .from('books')
    .select('*')
    .order('title_en', { ascending: true });
  if (error) throw error;
  return data as Book[];
}

/** Fetch books by category. */
export async function fetchBooksByCategory(category: string): Promise<Book[]> {
  const { data, error } = await supabase
    .from('books')
    .select('*')
    .eq('category', category)
    .order('title_en', { ascending: true });
  if (error) throw error;
  return data as Book[];
}

/** Fetch all pages for a book. */
export async function fetchBookPages(bookId: string): Promise<Page[]> {
  const { data, error } = await supabase
    .from('pages')
    .select('*')
    .eq('book_id', bookId)
    .order('page_number', { ascending: true });
  if (error) throw error;
  return (data as any[]).map((row) => ({
    ...row,
    blocks: typeof row.blocks === 'string' ? JSON.parse(row.blocks) : row.blocks,
  }));
}

/** Fetch chapters for a book. */
export async function fetchBookChapters(bookId: string): Promise<Chapter[]> {
  const { data, error } = await supabase
    .from('chapters')
    .select('*')
    .eq('book_id', bookId)
    .order('start_page', { ascending: true });
  if (error) throw error;
  return data as Chapter[];
}

/** Search books by title (Arabic or English). */
export async function searchBooks(query: string): Promise<Book[]> {
  const { data, error } = await supabase
    .from('books')
    .select('*')
    .or(`title_en.ilike.%${query}%,title_ar.ilike.%${query}%,author_en.ilike.%${query}%`)
    .order('title_en', { ascending: true });
  if (error) throw error;
  return data as Book[];
}
