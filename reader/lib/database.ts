import * as SQLite from 'expo-sqlite';
import type { DownloadedBook, Page, ReadingProgress, DayStats } from '../types';

let db: SQLite.SQLiteDatabase | null = null;

export async function initDatabase(): Promise<SQLite.SQLiteDatabase> {
  if (db) return db;
  db = await SQLite.openDatabaseAsync('suhuf.db');

  await db.execAsync(`
    PRAGMA journal_mode = WAL;

    CREATE TABLE IF NOT EXISTS books (
      id TEXT PRIMARY KEY,
      openiti_id TEXT UNIQUE NOT NULL,
      title_ar TEXT NOT NULL,
      title_en TEXT,
      author_ar TEXT,
      author_en TEXT,
      category TEXT,
      level TEXT,
      cover_color TEXT DEFAULT '#5C4B3A',
      page_count INTEGER NOT NULL DEFAULT 0,
      content_hash TEXT,
      downloaded_at TEXT NOT NULL,
      last_read_page INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS pages (
      id TEXT PRIMARY KEY,
      book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
      page_number INTEGER NOT NULL,
      blocks TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS chapters (
      id TEXT PRIMARY KEY,
      book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
      title TEXT NOT NULL,
      start_page INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS reading_progress (
      book_id TEXT PRIMARY KEY REFERENCES books(id),
      current_page INTEGER NOT NULL DEFAULT 1,
      total_time_seconds INTEGER DEFAULT 0,
      pages_read_today INTEGER DEFAULT 0,
      last_opened TEXT
    );

    CREATE TABLE IF NOT EXISTS bookmarks (
      id TEXT PRIMARY KEY,
      book_id TEXT NOT NULL REFERENCES books(id),
      page_number INTEGER NOT NULL,
      token_id TEXT,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS highlights (
      id TEXT PRIMARY KEY,
      book_id TEXT NOT NULL REFERENCES books(id),
      token_id_start TEXT NOT NULL,
      token_id_end TEXT NOT NULL,
      color TEXT DEFAULT 'yellow',
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS notes (
      id TEXT PRIMARY KEY,
      book_id TEXT NOT NULL REFERENCES books(id),
      token_id TEXT NOT NULL,
      text TEXT NOT NULL,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS irab_cache (
      word TEXT NOT NULL,
      sentence_hash TEXT NOT NULL,
      model_version TEXT NOT NULL,
      result_json TEXT NOT NULL,
      created_at TEXT NOT NULL,
      PRIMARY KEY (word, sentence_hash, model_version)
    );

    CREATE TABLE IF NOT EXISTS translation_cache (
      text_hash TEXT NOT NULL,
      model_version TEXT NOT NULL,
      result_json TEXT NOT NULL,
      created_at TEXT NOT NULL,
      PRIMARY KEY (text_hash, model_version)
    );

    CREATE TABLE IF NOT EXISTS stats (
      date TEXT PRIMARY KEY,
      pages_read INTEGER DEFAULT 0,
      words_learned INTEGER DEFAULT 0,
      time_seconds INTEGER DEFAULT 0
    );
  `);

  return db;
}

export function getDatabase(): SQLite.SQLiteDatabase {
  if (!db) throw new Error('Database not initialized. Call initDatabase() first.');
  return db;
}

export async function getDownloadedBooks(): Promise<DownloadedBook[]> {
  const d = getDatabase();
  return d.getAllAsync<DownloadedBook>('SELECT * FROM books ORDER BY last_read_page DESC');
}

export async function saveBookLocally(book: DownloadedBook): Promise<void> {
  const d = getDatabase();
  await d.runAsync(
    `INSERT OR REPLACE INTO books (id, openiti_id, title_ar, title_en, author_ar, author_en, category, level, cover_color, page_count, content_hash, downloaded_at, last_read_page)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    book.id, book.openiti_id, book.title_ar, book.title_en,
    book.author_ar, book.author_en, book.category, book.level,
    book.cover_color, book.page_count, book.content_hash,
    book.downloaded_at, book.last_read_page
  );
}

export async function savePages(pages: Page[]): Promise<void> {
  const d = getDatabase();
  for (const page of pages) {
    await d.runAsync(
      'INSERT OR REPLACE INTO pages (id, book_id, page_number, blocks) VALUES (?, ?, ?, ?)',
      page.id, page.book_id, page.page_number, JSON.stringify(page.blocks)
    );
  }
}

export async function getPagesByBook(bookId: string): Promise<Page[]> {
  const d = getDatabase();
  const rows = await d.getAllAsync<{ id: string; book_id: string; page_number: number; blocks: string }>(
    'SELECT * FROM pages WHERE book_id = ? ORDER BY page_number ASC', bookId
  );
  return rows.map((r) => ({ ...r, blocks: JSON.parse(r.blocks) }));
}

export async function getReadingProgress(bookId: string): Promise<ReadingProgress | null> {
  const d = getDatabase();
  return d.getFirstAsync<ReadingProgress>(
    'SELECT * FROM reading_progress WHERE book_id = ?', bookId
  );
}

export async function updateReadingProgress(bookId: string, page: number): Promise<void> {
  const d = getDatabase();
  const now = new Date().toISOString();
  await d.runAsync(
    `INSERT INTO reading_progress (book_id, current_page, last_opened)
     VALUES (?, ?, ?)
     ON CONFLICT(book_id) DO UPDATE SET current_page = ?, last_opened = ?`,
    bookId, page, now, page, now
  );
}

export async function getTodayStats(): Promise<DayStats> {
  const d = getDatabase();
  const today = new Date().toISOString().split('T')[0];
  const row = await d.getFirstAsync<DayStats>(
    'SELECT * FROM stats WHERE date = ?', today
  );
  return row ?? { date: today, pages_read: 0, words_learned: 0, time_seconds: 0 };
}

export async function incrementStat(field: 'pages_read' | 'words_learned' | 'time_seconds', amount: number): Promise<void> {
  const d = getDatabase();
  const today = new Date().toISOString().split('T')[0];
  await d.runAsync(
    `INSERT INTO stats (date, ${field}) VALUES (?, ?)
     ON CONFLICT(date) DO UPDATE SET ${field} = ${field} + ?`,
    today, amount, amount
  );
}
