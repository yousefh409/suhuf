import type { Book, DownloadedBook } from '../types';
import { fetchBookPages, fetchBookChapters } from './supabase';
import { getDatabase, saveBookLocally, savePages } from './database';

/** Download all pages + chapters for a book from Supabase to local SQLite. */
export async function downloadBook(
  book: Book,
  onProgress?: (downloaded: number, total: number) => void
): Promise<void> {
  const pages = await fetchBookPages(book.id);
  onProgress?.(0, pages.length);

  const chapters = await fetchBookChapters(book.id);

  const downloadedBook: DownloadedBook = {
    ...book,
    downloaded_at: new Date().toISOString(),
    last_read_page: 1,
  };
  await saveBookLocally(downloadedBook);

  const BATCH_SIZE = 20;
  for (let i = 0; i < pages.length; i += BATCH_SIZE) {
    const batch = pages.slice(i, i + BATCH_SIZE);
    await savePages(batch);
    onProgress?.(Math.min(i + BATCH_SIZE, pages.length), pages.length);
  }

  const db = getDatabase();
  for (const chapter of chapters) {
    await db.runAsync(
      'INSERT OR REPLACE INTO chapters (id, book_id, title, start_page) VALUES (?, ?, ?, ?)',
      chapter.id, chapter.book_id, chapter.title, chapter.start_page
    );
  }
}

/** Check if a book is already downloaded locally. */
export async function isBookDownloaded(bookId: string): Promise<boolean> {
  const db = getDatabase();
  const row = await db.getFirstAsync<{ id: string }>(
    'SELECT id FROM books WHERE id = ?', bookId
  );
  return row !== null;
}

/** Delete a downloaded book and all its local data. */
export async function deleteDownloadedBook(bookId: string): Promise<void> {
  const db = getDatabase();
  await db.runAsync('DELETE FROM pages WHERE book_id = ?', bookId);
  await db.runAsync('DELETE FROM chapters WHERE book_id = ?', bookId);
  await db.runAsync('DELETE FROM reading_progress WHERE book_id = ?', bookId);
  await db.runAsync('DELETE FROM bookmarks WHERE book_id = ?', bookId);
  await db.runAsync('DELETE FROM highlights WHERE book_id = ?', bookId);
  await db.runAsync('DELETE FROM notes WHERE book_id = ?', bookId);
  await db.runAsync('DELETE FROM books WHERE id = ?', bookId);
}
