import { create } from 'zustand';
import type { Book, DownloadedBook, BookCategory } from '../types';
import { fetchBookCatalog, fetchBooksByCategory, searchBooks } from '../lib/supabase';
import { getDownloadedBooks } from '../lib/database';
import { downloadBook as downloadBookService } from '../lib/book-download';

interface LibraryState {
  catalog: Book[];
  downloadedBooks: DownloadedBook[];
  selectedCategory: BookCategory | null;
  searchQuery: string;
  isLoading: boolean;
  downloadProgress: Record<string, { downloaded: number; total: number }>;

  loadCatalog: () => Promise<void>;
  loadDownloadedBooks: () => Promise<void>;
  filterByCategory: (category: BookCategory | null) => Promise<void>;
  search: (query: string) => Promise<void>;
  downloadBook: (book: Book) => Promise<void>;
}

export const useLibraryStore = create<LibraryState>((set, get) => ({
  catalog: [],
  downloadedBooks: [],
  selectedCategory: null,
  searchQuery: '',
  isLoading: false,
  downloadProgress: {},

  loadCatalog: async () => {
    set({ isLoading: true });
    try {
      const catalog = await fetchBookCatalog();
      set({ catalog, isLoading: false });
    } catch {
      set({ isLoading: false });
    }
  },

  loadDownloadedBooks: async () => {
    try {
      const downloadedBooks = await getDownloadedBooks();
      set({ downloadedBooks });
    } catch {
      // SQLite read failed — keep existing list
    }
  },

  filterByCategory: async (category) => {
    set({ selectedCategory: category, isLoading: true });
    try {
      const catalog = category ? await fetchBooksByCategory(category) : await fetchBookCatalog();
      set({ catalog, isLoading: false });
    } catch {
      set({ isLoading: false });
    }
  },

  search: async (query) => {
    set({ searchQuery: query, isLoading: true });
    try {
      const catalog = query ? await searchBooks(query) : await fetchBookCatalog();
      set({ catalog, isLoading: false });
    } catch {
      set({ isLoading: false });
    }
  },

  downloadBook: async (book) => {
    set((s) => ({
      downloadProgress: { ...s.downloadProgress, [book.id]: { downloaded: 0, total: book.page_count } },
    }));
    try {
      await downloadBookService(book, (downloaded, total) => {
        set((s) => ({
          downloadProgress: { ...s.downloadProgress, [book.id]: { downloaded, total } },
        }));
      });
      await get().loadDownloadedBooks();
    } catch {
      // download failed — clear stuck progress
    } finally {
      set((s) => {
        const { [book.id]: _, ...rest } = s.downloadProgress;
        return { downloadProgress: rest };
      });
    }
  },
}));
