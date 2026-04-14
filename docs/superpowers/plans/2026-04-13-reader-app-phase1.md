# Reader App Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Suhuf reader app (Expo, iPad + iPhone) with offline reading, word-tap grammar analysis, translation, and Ask AI chat.

**Architecture:** Expo SDK 54 + TypeScript app with Expo Router v6 file-based navigation. Books download from Supabase to local SQLite for offline reading. Word analysis calls Supabase Edge Functions (Claude Sonnet) with local caching. No auth, no payments.

**Tech Stack:** Expo SDK 54, TypeScript, Expo Router v6, expo-sqlite, Zustand, @gorhom/bottom-sheet, Supabase JS, Supabase Edge Functions (Deno), Claude Sonnet API

**Spec:** `docs/superpowers/specs/2026-04-13-reader-app-phase1-design.md`

**Paper designs:** All screens are in Paper (file: "Stuff", page: "Suhoof"). Extract exact colors, fonts, spacing from Paper using `get_computed_styles` and `get_jsx` during UI tasks.

---

## File Structure

```
reader/
├── app.json
├── package.json
├── tsconfig.json
├── babel.config.js
├── jest.config.js
├── app/
│   ├── _layout.tsx              # Root layout: fonts, SQLite provider, Zustand
│   ├── index.tsx                # Library Main screen
│   ├── discover.tsx             # Library Discover screen
│   ├── profile.tsx              # Profile screen
│   ├── settings.tsx             # Settings screen
│   └── book/
│       └── [id].tsx             # Reading Session screen
├── components/
│   ├── library/
│   │   ├── StatsRow.tsx         # 4 stat cards (pages, words, streak, time)
│   │   ├── ContinueReading.tsx  # Continue reading section with book rows
│   │   ├── BookCard.tsx         # Reusable book card (cover, title, author, progress)
│   │   ├── BookGrid.tsx         # Grid of BookCards for discover/recommended
│   │   ├── CategoryPills.tsx    # Horizontal category filter pills
│   │   └── FilteredTabs.tsx     # In Progress / Saved / Completed tabs
│   ├── reader/
│   │   ├── PageView.tsx         # Single page of Arabic text (block renderer)
│   │   ├── ArabicBlock.tsx      # Renders a single block (prose, hadith, poetry, etc.)
│   │   ├── ArabicWord.tsx       # Single tappable word with diacritics
│   │   ├── WordPopup.tsx        # Inline popup (Grammar / Translate / Copy)
│   │   └── TashkeelToggle.tsx   # Toggle button for diacritics
│   ├── word-detail/
│   │   ├── WordDetailSheet.tsx  # Bottom sheet container with tab navigation
│   │   ├── TranslationTab.tsx   # Translation content
│   │   ├── IrabTab.tsx          # Grammar analysis content
│   │   ├── AskAiTab.tsx         # Chat interface
│   │   └── LoadingState.tsx     # Skeleton loading for bottom sheet
│   └── ui/
│       ├── Header.tsx           # Reusable screen header
│       └── ProgressBar.tsx      # Colored progress bar
├── lib/
│   ├── supabase.ts              # Supabase client init
│   ├── database.ts              # SQLite open + migrations
│   ├── book-download.ts         # Download book pages from Supabase to SQLite
│   ├── word-analysis.ts         # Fetch i'rab/translate/ask-ai from Edge Functions
│   └── hash.ts                  # NFC normalization + SHA-256 hashing
├── stores/
│   ├── library.ts               # Book catalog + download state
│   ├── reader.ts                # Current book, page, word selection
│   ├── settings.ts              # Font, display, AI preferences
│   └── stats.ts                 # Reading stats (pages, words, time, streak)
├── types/
│   └── index.ts                 # All TypeScript types
├── constants/
│   └── theme.ts                 # Colors, fonts, spacing extracted from Paper
└── __tests__/
    ├── lib/
    │   ├── database.test.ts
    │   ├── book-download.test.ts
    │   ├── word-analysis.test.ts
    │   └── hash.test.ts
    ├── stores/
    │   ├── library.test.ts
    │   ├── reader.test.ts
    │   ├── settings.test.ts
    │   └── stats.test.ts
    └── components/
        └── reader/
            └── ArabicWord.test.tsx

supabase/
├── migrations/
│   ├── 20260413000000_waitlist_schema.sql   # (existing)
│   └── 20260413100000_book_schema.sql       # NEW: books, pages, chapters
└── functions/
    ├── irab/
    │   └── index.ts                          # I'rab Edge Function
    ├── translate/
    │   └── index.ts                          # Translation Edge Function
    └── ask-ai/
        └── index.ts                          # Ask AI Edge Function
```

---

## Task 1: Expo Project Scaffolding

**Files:**
- Create: `reader/package.json`, `reader/app.json`, `reader/tsconfig.json`, `reader/babel.config.js`, `reader/jest.config.js`, `reader/app/_layout.tsx`, `reader/app/index.tsx`

- [ ] **Step 1: Create Expo project**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
npx create-expo-app@latest reader --template blank-typescript
```

- [ ] **Step 2: Install core dependencies**

```bash
cd reader
npx expo install expo-sqlite expo-font expo-splash-screen expo-image expo-status-bar
npm install @supabase/supabase-js zustand @gorhom/bottom-sheet react-native-reanimated react-native-gesture-handler
npm install --save-dev jest @testing-library/react-native @testing-library/jest-native @types/jest ts-jest
```

- [ ] **Step 3: Configure babel for reanimated**

Replace `reader/babel.config.js`:

```js
module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    plugins: ['react-native-reanimated/plugin'],
  };
};
```

- [ ] **Step 4: Configure Jest**

Create `reader/jest.config.js`:

```js
module.exports = {
  preset: 'jest-expo',
  transformIgnorePatterns: [
    'node_modules/(?!((jest-)?react-native|@react-native(-community)?)|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@sentry/react-native|native-base|react-native-svg)',
  ],
  setupFilesAfterSetup: [],
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx'],
};
```

- [ ] **Step 5: Create minimal root layout**

Create `reader/app/_layout.tsx`:

```tsx
import { Stack } from 'expo-router';

export default function RootLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
    </Stack>
  );
}
```

- [ ] **Step 6: Create placeholder home screen**

Replace `reader/app/index.tsx`:

```tsx
import { View, Text, StyleSheet } from 'react-native';

export default function LibraryMain() {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Library</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#F5F0EB' },
  title: { fontSize: 32, fontWeight: '700', color: '#2C2417' },
});
```

- [ ] **Step 7: Verify app runs on iOS simulator**

```bash
cd reader
npx expo start --ios
```

Expected: App launches in iOS simulator showing "Library" text centered on warm off-white background.

- [ ] **Step 8: Commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add reader/
git commit -m "feat(reader): scaffold Expo project with core dependencies"
```

---

## Task 2: Supabase Book Schema Migration

**Files:**
- Create: `supabase/migrations/20260413100000_book_schema.sql`

- [ ] **Step 1: Write the migration**

Create `supabase/migrations/20260413100000_book_schema.sql`:

```sql
-- Books table: catalog of all available books
CREATE TABLE IF NOT EXISTS books (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  openiti_id TEXT UNIQUE NOT NULL,
  title_ar TEXT NOT NULL,
  title_en TEXT NOT NULL,
  author_ar TEXT,
  author_en TEXT,
  category TEXT NOT NULL,
  level TEXT NOT NULL CHECK (level IN ('Beginner', 'Intermediate', 'Advanced')),
  cover_color TEXT DEFAULT '#5C4B3A',
  page_count INTEGER NOT NULL DEFAULT 0,
  content_hash TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Pages table: each page is a JSON array of typed blocks
CREATE TABLE IF NOT EXISTS pages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL,
  blocks JSONB NOT NULL DEFAULT '[]',
  UNIQUE(book_id, page_number)
);

-- Chapters table: table of contents
CREATE TABLE IF NOT EXISTS chapters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  start_page INTEGER NOT NULL
);

-- Indexes for common queries
CREATE INDEX idx_pages_book_id ON pages(book_id);
CREATE INDEX idx_pages_book_page ON pages(book_id, page_number);
CREATE INDEX idx_chapters_book_id ON chapters(book_id);
CREATE INDEX idx_books_category ON books(category);
CREATE INDEX idx_books_level ON books(level);
```

- [ ] **Step 2: Apply migration to Supabase**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
npx supabase db push
```

Expected: Migration applies successfully. Tables `books`, `pages`, `chapters` created.

- [ ] **Step 3: Verify tables exist**

```bash
npx supabase db query "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('books', 'pages', 'chapters');"
```

Expected: All 3 tables listed.

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/20260413100000_book_schema.sql
git commit -m "feat(supabase): add book schema migration (books, pages, chapters)"
```

---

## Task 3: TypeScript Types + Theme Constants

**Files:**
- Create: `reader/types/index.ts`, `reader/constants/theme.ts`

- [ ] **Step 1: Define all TypeScript types**

Create `reader/types/index.ts`:

```ts
// === Book & Content ===

export type BookCategory =
  | 'Nahw' | 'Sarf' | 'Hadith' | 'Fiqh' | 'Tafseer'
  | 'Aqeedah' | 'Balagha' | 'Lugha' | 'Sirah' | 'Tazkiyah'
  | 'Usul al-Fiqh';

export type BookLevel = 'Beginner' | 'Intermediate' | 'Advanced';

export interface Book {
  id: string;
  openiti_id: string;
  title_ar: string;
  title_en: string;
  author_ar: string | null;
  author_en: string | null;
  category: BookCategory;
  level: BookLevel;
  cover_color: string;
  page_count: number;
  content_hash: string | null;
}

export type BlockType = 'prose' | 'hadith' | 'isnad' | 'matn' | 'poetry' | 'biography' | 'heading';

export interface Token {
  id: string;       // e.g. "p42_b1_w5"
  text: string;     // Arabic word (may include clitics)
  tashkeel: string; // Diacritized form
}

export interface Block {
  type: BlockType;
  tokens: Token[];
}

export interface Page {
  id: string;
  book_id: string;
  page_number: number;
  blocks: Block[];
}

export interface Chapter {
  id: string;
  book_id: string;
  title: string;
  start_page: number;
}

// === Local User Data ===

export interface ReadingProgress {
  book_id: string;
  current_page: number;
  total_time_seconds: number;
  pages_read_today: number;
  last_opened: string; // ISO date
}

export interface Bookmark {
  id: string;
  book_id: string;
  page_number: number;
  token_id: string | null;
  created_at: string;
}

export interface Highlight {
  id: string;
  book_id: string;
  token_id_start: string;
  token_id_end: string;
  color: string;
  created_at: string;
}

export interface Note {
  id: string;
  book_id: string;
  token_id: string;
  text: string;
  created_at: string;
}

export interface DayStats {
  date: string;
  pages_read: number;
  words_learned: number;
  time_seconds: number;
}

// === I'rab / Translation ===

export interface IrabResult {
  pos: string;
  role: string;
  role_ar: string;
  case: string;
  case_ar: string;
  marker: string;
  marker_ar: string;
  why: string;
  meaning: string;
}

export interface RelatedWord {
  word: string;
  root: string;
  meaning: string;
}

export interface TranslationResult {
  translation: string;
  related_words: RelatedWord[];
}

export interface AskAiMessage {
  role: 'user' | 'assistant';
  content: string;
}

// === Settings ===

export type ArabicFont = 'Noto Naskh Arabic' | 'Amiri' | 'Scheherazade New';
export type AiLanguage = 'English' | 'Arabic';
export type GrammarDetail = 'Simple' | 'Detailed' | 'Expert';

export interface Settings {
  fontSize: number;          // 18-32
  arabicFont: ArabicFont;
  aiLanguage: AiLanguage;
  grammarDetail: GrammarDetail;
  showTashkeel: boolean;
  notificationsEnabled: boolean;
}

// === Download State ===

export interface DownloadedBook extends Book {
  downloaded_at: string;
  last_read_page: number;
}
```

- [ ] **Step 2: Extract theme from Paper designs**

Use Paper MCP tools: `get_computed_styles` on key elements from the Library Main artboard (57Q-1) to get exact hex values, font sizes, and spacing. Create `reader/constants/theme.ts`:

```ts
// Colors extracted from Paper designs (artboard: Library Main 57Q-1)
// Run: get_computed_styles on key nodes to get exact values
export const colors = {
  background: '#F5F0EB',
  card: '#FFFFFF',
  cardBorder: '#E8E0D8',
  primary: '#3D3526',        // Dark brown - buttons, headers
  accent: '#B8860B',         // Gold/amber - progress bars, active states
  textPrimary: '#2C2417',    // Near-black, warm
  textSecondary: '#8A7D6B',  // Muted warm gray
  textTertiary: '#B5A898',   // Lighter muted
  success: '#6B8E4E',        // Completed indicator
  error: '#C45C4A',          // Error states
  white: '#FFFFFF',
} as const;

// Book cover color presets (from Paper designs)
export const coverColors = [
  '#5C4B3A', '#3D3526', '#4A5D4A', '#2E4A4A',
  '#6B5B4A', '#4A3F32', '#5A6B5A', '#3A4A3A',
] as const;

export const fonts = {
  arabic: {
    primary: 'Noto Naskh Arabic',
    amiri: 'Amiri',
    scheherazade: 'Scheherazade New',
  },
  ui: {
    regular: 'DM Sans',
    serif: 'Instrument Serif',
  },
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
  sectionGap: 32,
  screenPadding: 24,
} as const;

export const typography = {
  // UI text (English)
  h1: { fontSize: 28, fontWeight: '700' as const, lineHeight: 34 },
  h2: { fontSize: 22, fontWeight: '600' as const, lineHeight: 28 },
  h3: { fontSize: 18, fontWeight: '600' as const, lineHeight: 24 },
  body: { fontSize: 16, fontWeight: '400' as const, lineHeight: 22 },
  caption: { fontSize: 13, fontWeight: '400' as const, lineHeight: 18 },
  label: { fontSize: 11, fontWeight: '500' as const, lineHeight: 14, letterSpacing: 0.5, textTransform: 'uppercase' as const },
  // Stat numbers
  stat: { fontSize: 36, fontWeight: '700' as const, lineHeight: 42 },
  statLabel: { fontSize: 11, fontWeight: '500' as const, lineHeight: 14, letterSpacing: 0.8, textTransform: 'uppercase' as const },
} as const;

export const borderRadius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  full: 9999,
} as const;
```

- [ ] **Step 3: Commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add reader/types/ reader/constants/
git commit -m "feat(reader): add TypeScript types and theme constants"
```

---

## Task 4: Supabase Client + Book Catalog API

**Files:**
- Create: `reader/lib/supabase.ts`, `reader/__tests__/lib/supabase.test.ts`

- [ ] **Step 1: Create .env file for reader**

Create `reader/.env`:

```
EXPO_PUBLIC_SUPABASE_URL=<your-supabase-url>
EXPO_PUBLIC_SUPABASE_ANON_KEY=<your-anon-key>
```

Add to `reader/.gitignore`:

```
.env
```

- [ ] **Step 2: Write the Supabase client**

Create `reader/lib/supabase.ts`:

```ts
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
```

- [ ] **Step 3: Commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add reader/lib/supabase.ts reader/.env reader/.gitignore
git commit -m "feat(reader): add Supabase client with book catalog API"
```

---

## Task 5: SQLite Database Layer

**Files:**
- Create: `reader/lib/database.ts`, `reader/__tests__/lib/database.test.ts`

- [ ] **Step 1: Write the failing test**

Create `reader/__tests__/lib/database.test.ts`:

```ts
import * as SQLite from 'expo-sqlite';
import { initDatabase, getDownloadedBooks, saveBookLocally, getPagesByBook } from '../../lib/database';

// expo-sqlite mock
jest.mock('expo-sqlite', () => {
  const rows: Record<string, any[]> = {};
  return {
    openDatabaseAsync: jest.fn().mockResolvedValue({
      execAsync: jest.fn().mockImplementation(async (sql: string) => {
        // Track CREATE TABLE calls
      }),
      runAsync: jest.fn().mockImplementation(async (sql: string, ...params: any[]) => {
        return { lastInsertRowId: 1, changes: 1 };
      }),
      getAllAsync: jest.fn().mockResolvedValue([]),
      getFirstAsync: jest.fn().mockResolvedValue(null),
    }),
  };
});

describe('database', () => {
  it('initDatabase opens DB and runs migrations', async () => {
    const db = await initDatabase();
    expect(SQLite.openDatabaseAsync).toHaveBeenCalledWith('suhuf.db');
    expect(db.execAsync).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd reader
npx jest __tests__/lib/database.test.ts --no-cache
```

Expected: FAIL — `initDatabase` not found.

- [ ] **Step 3: Write the database module**

Create `reader/lib/database.ts`:

```ts
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
      title_en TEXT NOT NULL,
      author_ar TEXT,
      author_en TEXT,
      category TEXT NOT NULL,
      level TEXT NOT NULL,
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
```

- [ ] **Step 4: Run tests**

```bash
cd reader
npx jest __tests__/lib/database.test.ts --no-cache
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add reader/lib/database.ts reader/__tests__/lib/database.test.ts
git commit -m "feat(reader): add SQLite database layer with migrations and CRUD"
```

---

## Task 6: Hash Utility (NFC + SHA-256)

**Files:**
- Create: `reader/lib/hash.ts`, `reader/__tests__/lib/hash.test.ts`

- [ ] **Step 1: Write the failing test**

Create `reader/__tests__/lib/hash.test.ts`:

```ts
import { normalizeArabic, hashSentence } from '../../lib/hash';

describe('hash', () => {
  it('normalizes Arabic text to NFC', () => {
    // Same Arabic word in different Unicode normalization forms should normalize to same string
    const nfc = normalizeArabic('كِتَابٌ');
    const nfd = normalizeArabic('كِتَابٌ'.normalize('NFD'));
    expect(nfc).toBe(nfd);
  });

  it('produces consistent hashes for same input', async () => {
    const hash1 = await hashSentence('بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ');
    const hash2 = await hashSentence('بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ');
    expect(hash1).toBe(hash2);
    expect(hash1).toHaveLength(64); // SHA-256 hex
  });

  it('produces different hashes for different input', async () => {
    const hash1 = await hashSentence('الكِتَاب');
    const hash2 = await hashSentence('القَلَم');
    expect(hash1).not.toBe(hash2);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd reader
npx jest __tests__/lib/hash.test.ts --no-cache
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement hash utility**

Create `reader/lib/hash.ts`:

```ts
import * as Crypto from 'expo-crypto';

/** Normalize Arabic text to NFC form for consistent hashing. */
export function normalizeArabic(text: string): string {
  return text.normalize('NFC');
}

/** Hash a sentence using SHA-256 after NFC normalization. Returns hex string. */
export async function hashSentence(sentence: string): Promise<string> {
  const normalized = normalizeArabic(sentence);
  return Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, normalized);
}
```

- [ ] **Step 4: Install expo-crypto**

```bash
cd reader
npx expo install expo-crypto
```

- [ ] **Step 5: Run tests**

```bash
npx jest __tests__/lib/hash.test.ts --no-cache
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add reader/lib/hash.ts reader/__tests__/lib/hash.test.ts
git commit -m "feat(reader): add NFC normalization and SHA-256 hashing for cache keys"
```

---

## Task 7: Book Download Service

**Files:**
- Create: `reader/lib/book-download.ts`, `reader/__tests__/lib/book-download.test.ts`

- [ ] **Step 1: Write the failing test**

Create `reader/__tests__/lib/book-download.test.ts`:

```ts
import { downloadBook, isBookDownloaded } from '../../lib/book-download';

// Mock dependencies
jest.mock('../../lib/supabase', () => ({
  fetchBookPages: jest.fn().mockResolvedValue([
    { id: 'p1', book_id: 'b1', page_number: 1, blocks: [{ type: 'prose', tokens: [] }] },
    { id: 'p2', book_id: 'b1', page_number: 2, blocks: [{ type: 'prose', tokens: [] }] },
  ]),
  fetchBookChapters: jest.fn().mockResolvedValue([
    { id: 'c1', book_id: 'b1', title: 'Chapter 1', start_page: 1 },
  ]),
}));

jest.mock('../../lib/database', () => ({
  getDatabase: jest.fn().mockReturnValue({
    getFirstAsync: jest.fn().mockResolvedValue(null),
    runAsync: jest.fn().mockResolvedValue({ lastInsertRowId: 1, changes: 1 }),
  }),
  saveBookLocally: jest.fn().mockResolvedValue(undefined),
  savePages: jest.fn().mockResolvedValue(undefined),
}));

describe('book-download', () => {
  it('downloads book pages and saves to SQLite', async () => {
    const { saveBookLocally, savePages } = require('../../lib/database');
    const book = {
      id: 'b1', openiti_id: 'test', title_ar: 'كتاب', title_en: 'Book',
      author_ar: null, author_en: null, category: 'Nahw', level: 'Beginner',
      cover_color: '#5C4B3A', page_count: 2, content_hash: null,
    };
    await downloadBook(book);
    expect(saveBookLocally).toHaveBeenCalled();
    expect(savePages).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd reader
npx jest __tests__/lib/book-download.test.ts --no-cache
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement download service**

Create `reader/lib/book-download.ts`:

```ts
import type { Book, DownloadedBook } from '../types';
import { fetchBookPages, fetchBookChapters } from './supabase';
import { getDatabase, saveBookLocally, savePages } from './database';

/** Download all pages + chapters for a book from Supabase to local SQLite. */
export async function downloadBook(
  book: Book,
  onProgress?: (downloaded: number, total: number) => void
): Promise<void> {
  // Fetch all pages from Supabase
  const pages = await fetchBookPages(book.id);
  onProgress?.(0, pages.length);

  // Fetch chapters
  const chapters = await fetchBookChapters(book.id);

  // Save book record locally
  const downloadedBook: DownloadedBook = {
    ...book,
    downloaded_at: new Date().toISOString(),
    last_read_page: 1,
  };
  await saveBookLocally(downloadedBook);

  // Save pages in batches
  const BATCH_SIZE = 20;
  for (let i = 0; i < pages.length; i += BATCH_SIZE) {
    const batch = pages.slice(i, i + BATCH_SIZE);
    await savePages(batch);
    onProgress?.(Math.min(i + BATCH_SIZE, pages.length), pages.length);
  }

  // Save chapters
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
```

- [ ] **Step 4: Run tests**

```bash
cd reader
npx jest __tests__/lib/book-download.test.ts --no-cache
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add reader/lib/book-download.ts reader/__tests__/lib/book-download.test.ts
git commit -m "feat(reader): add book download service (Supabase -> local SQLite)"
```

---

## Task 8: Word Analysis Service

**Files:**
- Create: `reader/lib/word-analysis.ts`, `reader/__tests__/lib/word-analysis.test.ts`

- [ ] **Step 1: Write the failing test**

Create `reader/__tests__/lib/word-analysis.test.ts`:

```ts
import { fetchIrab, fetchTranslation, getCachedIrab } from '../../lib/word-analysis';

jest.mock('../../lib/supabase', () => ({
  supabase: {
    functions: {
      invoke: jest.fn().mockResolvedValue({
        data: {
          pos: 'noun', role: 'mudaf_ilayh', role_ar: 'مضاف إليه',
          case: 'majrur', case_ar: 'مجرور', marker: 'tanween_kasra',
          marker_ar: 'تنوين كسر', why: 'Test reason', meaning: 'path',
        },
        error: null,
      }),
    },
  },
}));

jest.mock('../../lib/database', () => ({
  getDatabase: jest.fn().mockReturnValue({
    getFirstAsync: jest.fn().mockResolvedValue(null),
    runAsync: jest.fn().mockResolvedValue({ lastInsertRowId: 1, changes: 1 }),
  }),
}));

jest.mock('../../lib/hash', () => ({
  hashSentence: jest.fn().mockResolvedValue('abc123hash'),
}));

describe('word-analysis', () => {
  it('fetches i\'rab from Edge Function when not cached', async () => {
    const result = await fetchIrab('طَرِيقٍ', 'بِكُلِّ طَرِيقٍ', 1);
    expect(result.pos).toBe('noun');
    expect(result.role).toBe('mudaf_ilayh');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd reader
npx jest __tests__/lib/word-analysis.test.ts --no-cache
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement word analysis service**

Create `reader/lib/word-analysis.ts`:

```ts
import type { IrabResult, TranslationResult, AskAiMessage } from '../types';
import { supabase } from './supabase';
import { getDatabase } from './database';
import { hashSentence } from './hash';

const MODEL_VERSION = 'v1';

/** Fetch i'rab analysis. Checks local cache first, then calls Edge Function. */
export async function fetchIrab(word: string, sentence: string, position: number): Promise<IrabResult> {
  // Check local cache
  const cached = await getCachedIrab(word, sentence);
  if (cached) return cached;

  // Call Edge Function
  const { data, error } = await supabase.functions.invoke('irab', {
    body: { word, sentence, position },
  });
  if (error) throw new Error(`I'rab fetch failed: ${error.message}`);

  // Cache locally
  await cacheIrab(word, sentence, data);
  return data as IrabResult;
}

/** Fetch translation. Checks local cache first, then calls Edge Function. */
export async function fetchTranslation(sentence: string): Promise<TranslationResult> {
  const cached = await getCachedTranslation(sentence);
  if (cached) return cached;

  const { data, error } = await supabase.functions.invoke('translate', {
    body: { sentence },
  });
  if (error) throw new Error(`Translation fetch failed: ${error.message}`);

  await cacheTranslation(sentence, data);
  return data as TranslationResult;
}

/** Send a question to the Ask AI Edge Function. Not cached. */
export async function askAi(
  word: string,
  sentence: string,
  question: string,
  history: AskAiMessage[]
): Promise<string> {
  const { data, error } = await supabase.functions.invoke('ask-ai', {
    body: { word, sentence, question, history },
  });
  if (error) throw new Error(`Ask AI failed: ${error.message}`);
  return data.response as string;
}

// === Cache helpers ===

export async function getCachedIrab(word: string, sentence: string): Promise<IrabResult | null> {
  const db = getDatabase();
  const sentenceHash = await hashSentence(sentence);
  const row = await db.getFirstAsync<{ result_json: string }>(
    'SELECT result_json FROM irab_cache WHERE word = ? AND sentence_hash = ? AND model_version = ?',
    word, sentenceHash, MODEL_VERSION
  );
  return row ? JSON.parse(row.result_json) : null;
}

async function cacheIrab(word: string, sentence: string, result: IrabResult): Promise<void> {
  const db = getDatabase();
  const sentenceHash = await hashSentence(sentence);
  await db.runAsync(
    `INSERT OR REPLACE INTO irab_cache (word, sentence_hash, model_version, result_json, created_at)
     VALUES (?, ?, ?, ?, ?)`,
    word, sentenceHash, MODEL_VERSION, JSON.stringify(result), new Date().toISOString()
  );
}

async function getCachedTranslation(sentence: string): Promise<TranslationResult | null> {
  const db = getDatabase();
  const textHash = await hashSentence(sentence);
  const row = await db.getFirstAsync<{ result_json: string }>(
    'SELECT result_json FROM translation_cache WHERE text_hash = ? AND model_version = ?',
    textHash, MODEL_VERSION
  );
  return row ? JSON.parse(row.result_json) : null;
}

async function cacheTranslation(sentence: string, result: TranslationResult): Promise<void> {
  const db = getDatabase();
  const textHash = await hashSentence(sentence);
  await db.runAsync(
    `INSERT OR REPLACE INTO translation_cache (text_hash, model_version, result_json, created_at)
     VALUES (?, ?, ?, ?)`,
    textHash, MODEL_VERSION, JSON.stringify(result), new Date().toISOString()
  );
}
```

- [ ] **Step 4: Run tests**

```bash
cd reader
npx jest __tests__/lib/word-analysis.test.ts --no-cache
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add reader/lib/word-analysis.ts reader/__tests__/lib/word-analysis.test.ts
git commit -m "feat(reader): add word analysis service with local cache"
```

---

## Task 9: Zustand Stores

**Files:**
- Create: `reader/stores/library.ts`, `reader/stores/reader.ts`, `reader/stores/settings.ts`, `reader/stores/stats.ts`

- [ ] **Step 1: Write the library store**

Create `reader/stores/library.ts`:

```ts
import { create } from 'zustand';
import type { Book, DownloadedBook, BookCategory } from '../types';
import { fetchBookCatalog, fetchBooksByCategory, searchBooks } from '../lib/supabase';
import { getDownloadedBooks } from '../lib/database';
import { downloadBook as downloadBookService, isBookDownloaded } from '../lib/book-download';

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
    const downloadedBooks = await getDownloadedBooks();
    set({ downloadedBooks });
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
    await downloadBookService(book, (downloaded, total) => {
      set((s) => ({
        downloadProgress: { ...s.downloadProgress, [book.id]: { downloaded, total } },
      }));
    });
    // Remove from progress, reload downloaded list
    set((s) => {
      const { [book.id]: _, ...rest } = s.downloadProgress;
      return { downloadProgress: rest };
    });
    await get().loadDownloadedBooks();
  },
}));
```

- [ ] **Step 2: Write the reader store**

Create `reader/stores/reader.ts`:

```ts
import { create } from 'zustand';
import type { Page, Chapter, Token, IrabResult, TranslationResult, AskAiMessage } from '../types';
import { getPagesByBook, updateReadingProgress } from '../lib/database';
import { fetchIrab, fetchTranslation, askAi } from '../lib/word-analysis';

interface ReaderState {
  bookId: string | null;
  pages: Page[];
  chapters: Chapter[];
  currentPage: number;
  showTashkeel: boolean;

  // Word selection
  selectedToken: Token | null;
  selectedSentence: string | null;
  showWordPopup: boolean;
  wordPopupPosition: { x: number; y: number } | null;

  // Word detail
  showWordDetail: boolean;
  activeTab: 'translation' | 'irab' | 'ask-ai';
  irabResult: IrabResult | null;
  translationResult: TranslationResult | null;
  isLoadingAnalysis: boolean;
  analysisError: string | null;

  // Ask AI
  chatHistory: AskAiMessage[];
  isAiTyping: boolean;

  // Actions
  loadBook: (bookId: string) => Promise<void>;
  goToPage: (page: number) => void;
  toggleTashkeel: () => void;
  selectWord: (token: Token, sentence: string, position: { x: number; y: number }) => void;
  clearSelection: () => void;
  openGrammar: () => Promise<void>;
  openTranslation: () => Promise<void>;
  openAskAi: () => void;
  sendAiQuestion: (question: string) => Promise<void>;
  closeWordDetail: () => void;
}

export const useReaderStore = create<ReaderState>((set, get) => ({
  bookId: null,
  pages: [],
  chapters: [],
  currentPage: 1,
  showTashkeel: true,

  selectedToken: null,
  selectedSentence: null,
  showWordPopup: false,
  wordPopupPosition: null,

  showWordDetail: false,
  activeTab: 'irab',
  irabResult: null,
  translationResult: null,
  isLoadingAnalysis: false,
  analysisError: null,

  chatHistory: [],
  isAiTyping: false,

  loadBook: async (bookId) => {
    const pages = await getPagesByBook(bookId);
    set({ bookId, pages, currentPage: 1 });
  },

  goToPage: (page) => {
    const { bookId, pages } = get();
    if (page >= 1 && page <= pages.length) {
      set({ currentPage: page });
      if (bookId) updateReadingProgress(bookId, page);
    }
  },

  toggleTashkeel: () => set((s) => ({ showTashkeel: !s.showTashkeel })),

  selectWord: (token, sentence, position) => {
    set({
      selectedToken: token,
      selectedSentence: sentence,
      showWordPopup: true,
      wordPopupPosition: position,
      showWordDetail: false,
    });
  },

  clearSelection: () => {
    set({
      selectedToken: null,
      selectedSentence: null,
      showWordPopup: false,
      wordPopupPosition: null,
    });
  },

  openGrammar: async () => {
    const { selectedToken, selectedSentence } = get();
    if (!selectedToken || !selectedSentence) return;
    set({
      showWordPopup: false,
      showWordDetail: true,
      activeTab: 'irab',
      isLoadingAnalysis: true,
      analysisError: null,
      irabResult: null,
    });
    try {
      const result = await fetchIrab(selectedToken.text, selectedSentence, 0);
      set({ irabResult: result, isLoadingAnalysis: false });
    } catch (e: any) {
      set({ analysisError: e.message, isLoadingAnalysis: false });
    }
  },

  openTranslation: async () => {
    const { selectedSentence } = get();
    if (!selectedSentence) return;
    set({
      showWordPopup: false,
      showWordDetail: true,
      activeTab: 'translation',
      isLoadingAnalysis: true,
      analysisError: null,
      translationResult: null,
    });
    try {
      const result = await fetchTranslation(selectedSentence);
      set({ translationResult: result, isLoadingAnalysis: false });
    } catch (e: any) {
      set({ analysisError: e.message, isLoadingAnalysis: false });
    }
  },

  openAskAi: () => {
    set({
      showWordPopup: false,
      showWordDetail: true,
      activeTab: 'ask-ai',
      chatHistory: [],
    });
  },

  sendAiQuestion: async (question) => {
    const { selectedToken, selectedSentence, chatHistory } = get();
    if (!selectedToken || !selectedSentence) return;
    const newHistory: AskAiMessage[] = [...chatHistory, { role: 'user', content: question }];
    set({ chatHistory: newHistory, isAiTyping: true });
    try {
      const response = await askAi(selectedToken.text, selectedSentence, question, newHistory);
      set({
        chatHistory: [...newHistory, { role: 'assistant', content: response }],
        isAiTyping: false,
      });
    } catch {
      set({
        chatHistory: [...newHistory, { role: 'assistant', content: 'Sorry, something went wrong. Please try again.' }],
        isAiTyping: false,
      });
    }
  },

  closeWordDetail: () => {
    set({
      showWordDetail: false,
      irabResult: null,
      translationResult: null,
      chatHistory: [],
      selectedToken: null,
      selectedSentence: null,
    });
  },
}));
```

- [ ] **Step 3: Write the settings store**

Create `reader/stores/settings.ts`:

```ts
import { create } from 'zustand';
import type { Settings, ArabicFont, AiLanguage, GrammarDetail } from '../types';

interface SettingsState extends Settings {
  setFontSize: (size: number) => void;
  setArabicFont: (font: ArabicFont) => void;
  setAiLanguage: (lang: AiLanguage) => void;
  setGrammarDetail: (level: GrammarDetail) => void;
  toggleTashkeel: () => void;
  toggleNotifications: () => void;
}

export const useSettingsStore = create<SettingsState>((set) => ({
  fontSize: 24,
  arabicFont: 'Noto Naskh Arabic',
  aiLanguage: 'English',
  grammarDetail: 'Detailed',
  showTashkeel: true,
  notificationsEnabled: true,

  setFontSize: (fontSize) => set({ fontSize }),
  setArabicFont: (arabicFont) => set({ arabicFont }),
  setAiLanguage: (aiLanguage) => set({ aiLanguage }),
  setGrammarDetail: (grammarDetail) => set({ grammarDetail }),
  toggleTashkeel: () => set((s) => ({ showTashkeel: !s.showTashkeel })),
  toggleNotifications: () => set((s) => ({ notificationsEnabled: !s.notificationsEnabled })),
}));
```

- [ ] **Step 4: Write the stats store**

Create `reader/stores/stats.ts`:

```ts
import { create } from 'zustand';
import { getTodayStats, incrementStat } from '../lib/database';
import type { DayStats } from '../types';

interface StatsState {
  today: DayStats;
  weeklyWords: number;
  streak: number;
  totalTimeToday: string; // Formatted "Xh Ym"

  loadStats: () => Promise<void>;
  recordPageRead: () => Promise<void>;
  recordWordLearned: () => Promise<void>;
  recordTime: (seconds: number) => Promise<void>;
}

export const useStatsStore = create<StatsState>((set, get) => ({
  today: { date: '', pages_read: 0, words_learned: 0, time_seconds: 0 },
  weeklyWords: 0,
  streak: 0,
  totalTimeToday: '0m',

  loadStats: async () => {
    const today = await getTodayStats();
    const hours = Math.floor(today.time_seconds / 3600);
    const minutes = Math.floor((today.time_seconds % 3600) / 60);
    const totalTimeToday = hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
    set({ today, totalTimeToday });
  },

  recordPageRead: async () => {
    await incrementStat('pages_read', 1);
    await get().loadStats();
  },

  recordWordLearned: async () => {
    await incrementStat('words_learned', 1);
    await get().loadStats();
  },

  recordTime: async (seconds) => {
    await incrementStat('time_seconds', seconds);
    await get().loadStats();
  },
}));
```

- [ ] **Step 5: Commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add reader/stores/
git commit -m "feat(reader): add Zustand stores (library, reader, settings, stats)"
```

---

## Task 10: Root Layout (fonts, SQLite provider, splash screen)

**Files:**
- Modify: `reader/app/_layout.tsx`

- [ ] **Step 1: Update root layout with font loading and SQLite init**

Replace `reader/app/_layout.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { Stack } from 'expo-router';
import { useFonts } from 'expo-font';
import * as SplashScreen from 'expo-splash-screen';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { StyleSheet } from 'react-native';
import { initDatabase } from '../lib/database';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const [dbReady, setDbReady] = useState(false);

  const [fontsLoaded] = useFonts({
    'NotoNaskhArabic': require('../assets/fonts/NotoNaskhArabic-Regular.ttf'),
    'NotoNaskhArabic-Bold': require('../assets/fonts/NotoNaskhArabic-Bold.ttf'),
    'Amiri': require('../assets/fonts/Amiri-Regular.ttf'),
    'Amiri-Bold': require('../assets/fonts/Amiri-Bold.ttf'),
    'ScheherazadeNew': require('../assets/fonts/ScheherazadeNew-Regular.ttf'),
    'DMSans': require('../assets/fonts/DMSans-Regular.ttf'),
    'DMSans-Medium': require('../assets/fonts/DMSans-Medium.ttf'),
    'DMSans-SemiBold': require('../assets/fonts/DMSans-SemiBold.ttf'),
    'DMSans-Bold': require('../assets/fonts/DMSans-Bold.ttf'),
  });

  useEffect(() => {
    initDatabase().then(() => setDbReady(true));
  }, []);

  useEffect(() => {
    if (fontsLoaded && dbReady) {
      SplashScreen.hideAsync();
    }
  }, [fontsLoaded, dbReady]);

  if (!fontsLoaded || !dbReady) return null;

  return (
    <GestureHandlerRootView style={styles.root}>
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="discover" />
        <Stack.Screen name="profile" />
        <Stack.Screen name="settings" />
        <Stack.Screen name="book/[id]" />
      </Stack>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
});
```

- [ ] **Step 2: Download font files**

Download the required font files to `reader/assets/fonts/`. Use Google Fonts:

```bash
mkdir -p reader/assets/fonts
cd reader/assets/fonts
# Download NotoNaskhArabic, Amiri, ScheherazadeNew, DMSans .ttf files from Google Fonts
# The exact download commands depend on availability — use curl or manual download
```

Note: The executing agent should download these from Google Fonts CDN or use `@expo-google-fonts` packages as an alternative. If using packages:

```bash
cd reader
npx expo install @expo-google-fonts/noto-naskh-arabic @expo-google-fonts/amiri @expo-google-fonts/scheherazade-new @expo-google-fonts/dm-sans
```

Then update the `useFonts` call to use the package imports instead of local files.

- [ ] **Step 3: Verify app still launches**

```bash
cd reader
npx expo start --ios
```

Expected: App loads fonts, initializes SQLite, hides splash screen, shows Library placeholder.

- [ ] **Step 4: Commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add reader/app/_layout.tsx reader/assets/
git commit -m "feat(reader): root layout with font loading, SQLite init, splash screen"
```

---

## Task 11: Supabase Edge Functions (i'rab, translate, ask-ai)

**Files:**
- Create: `supabase/functions/irab/index.ts`, `supabase/functions/translate/index.ts`, `supabase/functions/ask-ai/index.ts`

- [ ] **Step 1: Create i'rab Edge Function**

Create `supabase/functions/irab/index.ts`:

```ts
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const ANTHROPIC_API_KEY = Deno.env.get('ANTHROPIC_API_KEY')!;

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const { word, sentence, position } = await req.json();

    if (!word || !sentence) {
      return new Response(
        JSON.stringify({ error: 'word and sentence are required' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    const systemPrompt = `You are an expert Arabic grammarian (نحوي). You analyze Arabic words in their sentence context and return grammatical analysis (إعراب).

Return a JSON object with these exact fields:
- pos: part of speech in English (noun, verb, particle, adjective, pronoun, etc.)
- role: grammatical role in English (subject, object, predicate, mudaf_ilayh, khabar, mubtada, etc.)
- role_ar: grammatical role in Arabic (مبتدأ، خبر، فاعل، مفعول به، مضاف إليه، etc.)
- case: grammatical case in English (marfu, mansub, majrur, majzum, mabni)
- case_ar: grammatical case in Arabic (مرفوع، منصوب، مجرور، مجزوم، مبني)
- marker: case marker in English (damma, fatha, kasra, sukun, tanween_damma, tanween_fatha, tanween_kasra)
- marker_ar: case marker in Arabic (ضمة، فتحة، كسرة، سكون، تنوين ضم، تنوين فتح، تنوين كسر)
- why: 1-2 sentence explanation mixing Arabic grammar terms with English explanation of WHY this word has this case in this sentence. Reference the specific grammar rule.
- meaning: brief English dictionary meaning of the word

Return ONLY valid JSON, no markdown fences.`;

    const userPrompt = `Analyze this word in context:

Word: ${word}
Full sentence: ${sentence}
Position in sentence: ${position}

Provide the full إعراب analysis as JSON.`;

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 500,
        messages: [
          { role: 'user', content: userPrompt },
        ],
        system: systemPrompt,
      }),
    });

    const data = await response.json();
    const text = data.content[0].text;
    const result = JSON.parse(text);

    return new Response(JSON.stringify(result), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (error) {
    return new Response(
      JSON.stringify({ error: error.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
```

- [ ] **Step 2: Create translate Edge Function**

Create `supabase/functions/translate/index.ts`:

```ts
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const ANTHROPIC_API_KEY = Deno.env.get('ANTHROPIC_API_KEY')!;

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const { sentence } = await req.json();

    if (!sentence) {
      return new Response(
        JSON.stringify({ error: 'sentence is required' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    const systemPrompt = `You are an expert translator of classical Arabic texts. Translate the given Arabic sentence to English, preserving the scholarly register.

Also identify the primary root (جذر) of the most significant content word in the sentence and provide 4-6 related words from the same root.

For Islamic/Arabic terms that are commonly transliterated (e.g., hadith, fiqh, sunnah, i'rab), transliterate them and add a brief parenthetical gloss on first use.

Return a JSON object with:
- translation: the English translation
- related_words: array of objects with { word (Arabic with tashkeel), root (Arabic letters spaced), meaning (English) }

Return ONLY valid JSON, no markdown fences.`;

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 600,
        messages: [
          { role: 'user', content: `Translate this Arabic sentence and provide related vocabulary:\n\n${sentence}` },
        ],
        system: systemPrompt,
      }),
    });

    const data = await response.json();
    const text = data.content[0].text;
    const result = JSON.parse(text);

    return new Response(JSON.stringify(result), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (error) {
    return new Response(
      JSON.stringify({ error: error.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
```

- [ ] **Step 3: Create ask-ai Edge Function**

Create `supabase/functions/ask-ai/index.ts`:

```ts
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const ANTHROPIC_API_KEY = Deno.env.get('ANTHROPIC_API_KEY')!;

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const { word, sentence, question, history } = await req.json();

    if (!word || !sentence || !question) {
      return new Response(
        JSON.stringify({ error: 'word, sentence, and question are required' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    const systemPrompt = `You are a patient, knowledgeable Arabic grammar teacher. A student is reading a classical Arabic text and has a question about a specific word.

Context:
- Word: ${word}
- Sentence: ${sentence}

Answer their question clearly, mixing Arabic grammar terminology with English explanations. Use examples when helpful. Keep answers concise (2-4 paragraphs max). When referencing Arabic grammatical terms, show them in Arabic script.`;

    const messages = [
      ...(history || []).map((m: { role: string; content: string }) => ({
        role: m.role,
        content: m.content,
      })),
      { role: 'user', content: question },
    ];

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 800,
        messages,
        system: systemPrompt,
      }),
    });

    const data = await response.json();
    const text = data.content[0].text;

    return new Response(JSON.stringify({ response: text }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (error) {
    return new Response(
      JSON.stringify({ error: error.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
```

- [ ] **Step 4: Set ANTHROPIC_API_KEY as Supabase secret**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
npx supabase secrets set ANTHROPIC_API_KEY=<your-api-key>
```

- [ ] **Step 5: Deploy Edge Functions**

```bash
npx supabase functions deploy irab
npx supabase functions deploy translate
npx supabase functions deploy ask-ai
```

Expected: All 3 functions deploy successfully.

- [ ] **Step 6: Test i'rab function with curl**

```bash
curl -i --request POST '<SUPABASE_URL>/functions/v1/irab' \
  --header 'Authorization: Bearer <ANON_KEY>' \
  --header 'Content-Type: application/json' \
  --data '{"word":"طَرِيقٍ","sentence":"بِكُلِّ طَرِيقٍ فَمَا يَزْدَادُ","position":1}'
```

Expected: 200 response with valid JSON i'rab analysis.

- [ ] **Step 7: Commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add supabase/functions/
git commit -m "feat(supabase): add Edge Functions for i'rab, translate, and ask-ai"
```

---

## Task 12: UI Components — Header + ProgressBar + BookCard

**Files:**
- Create: `reader/components/ui/Header.tsx`, `reader/components/ui/ProgressBar.tsx`, `reader/components/library/BookCard.tsx`

- [ ] **Step 1: Build Header component**

Create `reader/components/ui/Header.tsx`. Extract exact styles from Paper artboard `57Q-1` (Library Main) header using `get_computed_styles`. The component should render the screen title on the left and optional action buttons on the right.

```tsx
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { colors, typography, spacing } from '../../constants/theme';

interface HeaderProps {
  title: string;
  showBack?: boolean;
  rightContent?: React.ReactNode;
}

export function Header({ title, showBack, rightContent }: HeaderProps) {
  const router = useRouter();
  return (
    <View style={styles.container}>
      <View style={styles.left}>
        {showBack && (
          <Pressable onPress={() => router.back()} style={styles.backButton}>
            <Text style={styles.backText}>{'‹ Library'}</Text>
          </Pressable>
        )}
        {!showBack && <Text style={styles.title}>{title}</Text>}
      </View>
      {showBack && <Text style={styles.centerTitle}>{title}</Text>}
      <View style={styles.right}>{rightContent}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.screenPadding,
    paddingVertical: spacing.md,
    backgroundColor: colors.background,
  },
  left: { flex: 1, alignItems: 'flex-start' },
  right: { flex: 1, alignItems: 'flex-end', flexDirection: 'row', justifyContent: 'flex-end', gap: spacing.sm },
  title: { fontFamily: 'DMSans-Bold', ...typography.h1, color: colors.textPrimary },
  centerTitle: { fontFamily: 'DMSans-SemiBold', ...typography.h3, color: colors.textPrimary },
  backButton: { paddingVertical: spacing.xs },
  backText: { fontFamily: 'DMSans', fontSize: 16, color: colors.textSecondary },
});
```

- [ ] **Step 2: Build ProgressBar component**

Create `reader/components/ui/ProgressBar.tsx`:

```tsx
import { View, StyleSheet } from 'react-native';
import { colors, borderRadius } from '../../constants/theme';

interface ProgressBarProps {
  progress: number; // 0-1
  color?: string;
  height?: number;
}

export function ProgressBar({ progress, color = colors.accent, height = 4 }: ProgressBarProps) {
  return (
    <View style={[styles.track, { height }]}>
      <View style={[styles.fill, { width: `${Math.min(progress * 100, 100)}%`, backgroundColor: color, height }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  track: { flex: 1, backgroundColor: '#E8E0D8', borderRadius: borderRadius.full, overflow: 'hidden' },
  fill: { borderRadius: borderRadius.full },
});
```

- [ ] **Step 3: Build BookCard component**

Create `reader/components/library/BookCard.tsx`. This is the reusable card shown in Continue Reading, In Progress tabs, and Recommended sections. Extract exact dimensions and styles from Paper.

```tsx
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import type { Book, DownloadedBook } from '../../types';
import { colors, typography, spacing, borderRadius } from '../../constants/theme';
import { ProgressBar } from '../ui/ProgressBar';

interface BookCardProps {
  book: Book | DownloadedBook;
  variant?: 'large' | 'medium' | 'small';
  progress?: number; // 0-1, only for downloaded books
  onPress?: () => void;
}

export function BookCard({ book, variant = 'medium', progress, onPress }: BookCardProps) {
  const router = useRouter();

  const handlePress = () => {
    if (onPress) {
      onPress();
    } else {
      router.push(`/book/${book.id}`);
    }
  };

  return (
    <Pressable style={[styles.container, variantStyles[variant]]} onPress={handlePress}>
      {/* Book cover */}
      <View style={[styles.cover, variantCoverStyles[variant], { backgroundColor: book.cover_color }]}>
        <Text style={[styles.coverText, variant === 'small' && styles.coverTextSmall]}>
          {book.title_ar}
        </Text>
        {progress !== undefined && progress > 0 && (
          <View style={styles.progressBadge}>
            <Text style={styles.progressBadgeText}>{Math.round(progress * 100)}%</Text>
          </View>
        )}
      </View>

      {/* Book info */}
      <Text style={[styles.title, variant === 'small' && styles.titleSmall]} numberOfLines={2}>
        {book.title_en}
      </Text>
      <Text style={styles.author} numberOfLines={1}>
        {book.author_en ?? book.author_ar}
      </Text>

      {/* Progress bar for downloaded books */}
      {progress !== undefined && (
        <View style={styles.progressContainer}>
          <ProgressBar progress={progress} />
        </View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: { },
  cover: {
    borderRadius: borderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
  },
  coverText: {
    fontFamily: 'NotoNaskhArabic-Bold',
    fontSize: 18,
    color: '#FFFFFF',
    textAlign: 'center',
    paddingHorizontal: spacing.sm,
  },
  coverTextSmall: { fontSize: 14 },
  progressBadge: {
    position: 'absolute',
    top: spacing.xs,
    right: spacing.xs,
    backgroundColor: colors.accent,
    borderRadius: borderRadius.full,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  progressBadgeText: { fontFamily: 'DMSans-SemiBold', fontSize: 11, color: '#FFFFFF' },
  title: { fontFamily: 'DMSans-SemiBold', fontSize: 14, color: colors.textPrimary, marginTop: spacing.sm },
  titleSmall: { fontSize: 13 },
  author: { fontFamily: 'DMSans', fontSize: 12, color: colors.textSecondary, marginTop: 2 },
  progressContainer: { marginTop: spacing.sm },
});

const variantStyles: Record<string, any> = {
  large: { width: '100%' },
  medium: { width: 170 },
  small: { width: 140 },
};

const variantCoverStyles: Record<string, any> = {
  large: { width: '100%', height: 100 },
  medium: { width: 170, height: 110 },
  small: { width: 140, height: 90 },
};
```

- [ ] **Step 4: Verify components render in the app**

Temporarily import BookCard into `app/index.tsx` with mock data and confirm it renders on the simulator.

- [ ] **Step 5: Commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add reader/components/
git commit -m "feat(reader): add Header, ProgressBar, and BookCard components"
```

---

## Task 13: Library Main Screen

**Files:**
- Create: `reader/components/library/StatsRow.tsx`, `reader/components/library/ContinueReading.tsx`, `reader/components/library/FilteredTabs.tsx`, `reader/components/library/BookGrid.tsx`
- Modify: `reader/app/index.tsx`

- [ ] **Step 1: Build StatsRow component**

Create `reader/components/library/StatsRow.tsx`. Match Paper design exactly — 4 horizontal cards with large numbers and uppercase labels.

- [ ] **Step 2: Build ContinueReading component**

Create `reader/components/library/ContinueReading.tsx`. Shows up to 3 in-progress books as horizontal cards with cover, title, author, progress bar, and "Resume" button on the first.

- [ ] **Step 3: Build FilteredTabs component**

Create `reader/components/library/FilteredTabs.tsx`. Three pill tabs (In Progress, Saved, Completed) with counts. Below: horizontal scroll of BookCard components.

- [ ] **Step 4: Build BookGrid component**

Create `reader/components/library/BookGrid.tsx`. Responsive grid of BookCard components — 5 columns on iPad, 2-3 on iPhone. Used for Recommended section and Discover.

- [ ] **Step 5: Assemble Library Main screen**

Replace `reader/app/index.tsx` with the full Library Main screen, composing all the above components. Connect to `useLibraryStore` and `useStatsStore`. Call `loadCatalog()` and `loadDownloadedBooks()` on mount.

- [ ] **Step 6: Screenshot and compare with Paper**

Launch in iOS simulator. Take a screenshot and compare side-by-side with Paper artboard `57Q-1`. Adjust spacing, fonts, colors until pixel-faithful.

- [ ] **Step 7: Commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add reader/app/index.tsx reader/components/library/
git commit -m "feat(reader): build Library Main screen with stats, continue reading, tabs, recommendations"
```

---

## Task 14: Library Discover Screen

**Files:**
- Create: `reader/app/discover.tsx`, `reader/components/library/CategoryPills.tsx`

- [ ] **Step 1: Build CategoryPills component**

Create `reader/components/library/CategoryPills.tsx`. Horizontal scroll of pill buttons with category name + count. Active state shows filled background. Match Paper artboard `57R-1`.

- [ ] **Step 2: Build Discover screen**

Create `reader/app/discover.tsx`. Header with back button + "Discover" title. Search bar. CategoryPills. BookGrid below. Sort button. Connect to `useLibraryStore` for filtering and search.

- [ ] **Step 3: Screenshot and compare with Paper**

Compare with Paper artboard `57R-1`. Adjust until matching.

- [ ] **Step 4: Commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add reader/app/discover.tsx reader/components/library/CategoryPills.tsx
git commit -m "feat(reader): build Library Discover screen with search and category filters"
```

---

## Task 15: Reading Session — Page Rendering

**Files:**
- Create: `reader/app/book/[id].tsx`, `reader/components/reader/PageView.tsx`, `reader/components/reader/ArabicBlock.tsx`, `reader/components/reader/ArabicWord.tsx`, `reader/components/reader/TashkeelToggle.tsx`

- [ ] **Step 1: Build ArabicWord component**

Create `reader/components/reader/ArabicWord.tsx`. A tappable word that renders Arabic text with or without diacritics. On tap, measures its position and calls `selectWord` from the reader store.

```tsx
import { Text, Pressable, StyleSheet } from 'react-native';
import type { Token } from '../../types';
import { useSettingsStore } from '../../stores/settings';

interface ArabicWordProps {
  token: Token;
  onPress: (token: Token, layout: { x: number; y: number }) => void;
}

export function ArabicWord({ token, onPress }: ArabicWordProps) {
  const { fontSize, arabicFont, showTashkeel } = useSettingsStore();

  const displayText = showTashkeel ? token.tashkeel : token.text;

  const handlePress = (event: any) => {
    // Get the word's position for the popup
    event.target.measure((_x: number, _y: number, _w: number, _h: number, pageX: number, pageY: number) => {
      onPress(token, { x: pageX, y: pageY });
    });
  };

  return (
    <Pressable onPress={handlePress}>
      <Text style={[styles.word, { fontSize, fontFamily: arabicFont }]}>
        {displayText}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  word: {
    color: '#2C2417',
    lineHeight: 48,
    writingDirection: 'rtl',
  },
});
```

- [ ] **Step 2: Build ArabicBlock component**

Create `reader/components/reader/ArabicBlock.tsx`. Renders a single block (prose, hadith, poetry, etc.) as a flex-wrap row of ArabicWord components. Block type determines styling (e.g., hadith has different background).

- [ ] **Step 3: Build PageView component**

Create `reader/components/reader/PageView.tsx`. Renders a single page as a scrollable column of ArabicBlock components. Takes a `Page` object and renders all its blocks.

- [ ] **Step 4: Build TashkeelToggle component**

Create `reader/components/reader/TashkeelToggle.tsx`. Simple toggle button in the footer. Matches Paper design.

- [ ] **Step 5: Build Reading Session screen**

Create `reader/app/book/[id].tsx`. Header with book title + chapter. Horizontal FlatList of PageView components with pagingEnabled. Footer with page number and TashkeelToggle. Uses `useReaderStore` and `useLocalSearchParams` to get book ID.

```tsx
import { useEffect } from 'react';
import { View, FlatList, Text, StyleSheet, useWindowDimensions } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { useReaderStore } from '../../stores/reader';
import { PageView } from '../../components/reader/PageView';
import { TashkeelToggle } from '../../components/reader/TashkeelToggle';
import { Header } from '../../components/ui/Header';
import { colors, spacing } from '../../constants/theme';

export default function ReadingSession() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { width } = useWindowDimensions();
  const { pages, currentPage, loadBook, goToPage } = useReaderStore();

  useEffect(() => {
    if (id) loadBook(id);
  }, [id]);

  return (
    <View style={styles.container}>
      <Header title="Al-Da' wal-Dawa'" showBack />

      <FlatList
        data={pages}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        keyExtractor={(p) => p.id}
        renderItem={({ item }) => (
          <View style={{ width }}>
            <PageView page={item} />
          </View>
        )}
        onMomentumScrollEnd={(e) => {
          const page = Math.round(e.nativeEvent.contentOffset.x / width) + 1;
          goToPage(page);
        }}
        initialScrollIndex={currentPage - 1}
        getItemLayout={(_, index) => ({ length: width, offset: width * index, index })}
      />

      <View style={styles.footer}>
        <TashkeelToggle />
        <Text style={styles.pageNumber}>{currentPage} / {pages.length}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.screenPadding,
    paddingVertical: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.cardBorder,
  },
  pageNumber: { fontFamily: 'DMSans', fontSize: 14, color: colors.textSecondary },
});
```

- [ ] **Step 6: Test with mock data**

Insert sample book data into Supabase (or use SQLite directly with test data) and verify the reading session renders Arabic text correctly on the simulator. Check RTL direction, diacritics rendering, and page swiping.

- [ ] **Step 7: Commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add reader/app/book/ reader/components/reader/
git commit -m "feat(reader): build Reading Session with paginated Arabic text and word tap targets"
```

---

## Task 16: Word Selection Popup

**Files:**
- Create: `reader/components/reader/WordPopup.tsx`

- [ ] **Step 1: Build WordPopup component**

Create `reader/components/reader/WordPopup.tsx`. Floating popup that appears above a tapped word with three buttons: "Grammar ✏", "Translate ᚢ", and a copy icon. Positioned based on the word's measured coordinates. Matches Paper artboard `DCU-0`.

```tsx
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { useReaderStore } from '../../stores/reader';
import { colors, spacing, borderRadius } from '../../constants/theme';

export function WordPopup() {
  const { showWordPopup, wordPopupPosition, openGrammar, openTranslation, clearSelection } = useReaderStore();

  if (!showWordPopup || !wordPopupPosition) return null;

  return (
    <View style={[styles.container, { top: wordPopupPosition.y - 50, left: wordPopupPosition.x - 100 }]}>
      <Pressable style={styles.button} onPress={openGrammar}>
        <Text style={styles.buttonText}>Grammar ✏</Text>
      </Pressable>
      <View style={styles.divider} />
      <Pressable style={styles.button} onPress={openTranslation}>
        <Text style={styles.buttonText}>Translate ᚢ</Text>
      </Pressable>
      <View style={styles.divider} />
      <Pressable style={styles.button} onPress={clearSelection}>
        <Text style={styles.buttonText}>📋</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    flexDirection: 'row',
    backgroundColor: colors.white,
    borderRadius: borderRadius.md,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
    elevation: 4,
    zIndex: 100,
  },
  button: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  buttonText: { fontFamily: 'DMSans-Medium', fontSize: 14, color: colors.textPrimary },
  divider: { width: 1, backgroundColor: colors.cardBorder },
});
```

- [ ] **Step 2: Integrate popup into Reading Session**

Add `<WordPopup />` to the `book/[id].tsx` screen, positioned as an overlay.

- [ ] **Step 3: Test word tap → popup flow**

Tap a word in the simulator. Verify popup appears at the correct position with Grammar/Translate/Copy options.

- [ ] **Step 4: Commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add reader/components/reader/WordPopup.tsx reader/app/book/
git commit -m "feat(reader): add word selection popup (Grammar / Translate / Copy)"
```

---

## Task 17: Word Detail Bottom Sheet

**Files:**
- Create: `reader/components/word-detail/WordDetailSheet.tsx`, `reader/components/word-detail/TranslationTab.tsx`, `reader/components/word-detail/IrabTab.tsx`, `reader/components/word-detail/AskAiTab.tsx`, `reader/components/word-detail/LoadingState.tsx`

- [ ] **Step 1: Build LoadingState component**

Create `reader/components/word-detail/LoadingState.tsx`. Skeleton placeholders matching the bottom sheet content layout.

- [ ] **Step 2: Build TranslationTab component**

Create `reader/components/word-detail/TranslationTab.tsx`. Match Paper artboard `6GH-0` (Word Detail — Translation). Shows: word header with large Arabic + English meaning, tags row, translation explanation card, related words list.

- [ ] **Step 3: Build IrabTab component**

Create `reader/components/word-detail/IrabTab.tsx`. Match Paper artboard `6HZ-0` (Word Detail — I3rab). Shows: word header, grammatical tags (role, case), "Why is it X here?" expanding explanation card with grammar rule.

- [ ] **Step 4: Build AskAiTab component**

Create `reader/components/word-detail/AskAiTab.tsx`. Match Paper artboards `6S8-0` and `6TT-0`. Chat interface with suggested questions at top, message history, text input with send button.

- [ ] **Step 5: Build WordDetailSheet container**

Create `reader/components/word-detail/WordDetailSheet.tsx`. Uses `@gorhom/bottom-sheet` with snap points. Tab bar at top (Translation / I'rab / Ask AI). Renders the active tab content. Back arrow and "+ Ask AI" button in header row.

```tsx
import { useCallback, useMemo, useRef } from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import BottomSheet, { BottomSheetView } from '@gorhom/bottom-sheet';
import { useReaderStore } from '../../stores/reader';
import { TranslationTab } from './TranslationTab';
import { IrabTab } from './IrabTab';
import { AskAiTab } from './AskAiTab';
import { LoadingState } from './LoadingState';
import { colors, spacing, borderRadius, typography } from '../../constants/theme';

export function WordDetailSheet() {
  const bottomSheetRef = useRef<BottomSheet>(null);
  const {
    showWordDetail, activeTab, selectedToken, isLoadingAnalysis,
    irabResult, translationResult, closeWordDetail,
  } = useReaderStore();

  const snapPoints = useMemo(() => ['50%', '85%'], []);

  const handleSheetChanges = useCallback((index: number) => {
    if (index === -1) closeWordDetail();
  }, []);

  if (!showWordDetail || !selectedToken) return null;

  const tabs = ['translation', 'irab', 'ask-ai'] as const;
  const tabLabels = { translation: 'Translate', irab: 'Grammar', 'ask-ai': 'Ask AI' };

  return (
    <BottomSheet
      ref={bottomSheetRef}
      index={0}
      snapPoints={snapPoints}
      onChange={handleSheetChanges}
      enablePanDownToClose
      backgroundStyle={styles.background}
      handleIndicatorStyle={styles.handleIndicator}
    >
      <BottomSheetView style={styles.content}>
        {/* Word header */}
        <View style={styles.wordHeader}>
          <Pressable onPress={closeWordDetail}>
            <Text style={styles.backArrow}>{'‹'}</Text>
          </Pressable>
          <Text style={styles.wordArabic}>{selectedToken.tashkeel}</Text>
          <Text style={styles.wordMeaning}>
            {irabResult?.meaning ?? '...'}
          </Text>
          <Pressable
            style={styles.askAiButton}
            onPress={() => useReaderStore.getState().openAskAi()}
          >
            <Text style={styles.askAiText}>+ Ask AI</Text>
          </Pressable>
        </View>

        {/* Tab bar */}
        <View style={styles.tabBar}>
          {tabs.map((tab) => (
            <Pressable
              key={tab}
              style={[styles.tab, activeTab === tab && styles.tabActive]}
              onPress={() => useReaderStore.setState({ activeTab: tab })}
            >
              <Text style={[styles.tabText, activeTab === tab && styles.tabTextActive]}>
                {tabLabels[tab]}
              </Text>
            </Pressable>
          ))}
        </View>

        {/* Tab content */}
        {isLoadingAnalysis ? (
          <LoadingState />
        ) : (
          <>
            {activeTab === 'translation' && <TranslationTab />}
            {activeTab === 'irab' && <IrabTab />}
            {activeTab === 'ask-ai' && <AskAiTab />}
          </>
        )}
      </BottomSheetView>
    </BottomSheet>
  );
}

const styles = StyleSheet.create({
  background: { backgroundColor: colors.white, borderRadius: borderRadius.xl },
  handleIndicator: { backgroundColor: colors.cardBorder, width: 40 },
  content: { flex: 1, paddingHorizontal: spacing.screenPadding },
  wordHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
  },
  backArrow: { fontSize: 24, color: colors.textSecondary },
  wordArabic: { fontFamily: 'NotoNaskhArabic-Bold', fontSize: 32, color: colors.textPrimary },
  wordMeaning: { fontFamily: 'DMSans', fontSize: 14, color: colors.textSecondary, flex: 1 },
  askAiButton: {
    backgroundColor: colors.background,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: borderRadius.full,
  },
  askAiText: { fontFamily: 'DMSans-Medium', fontSize: 13, color: colors.textPrimary },
  tabBar: { flexDirection: 'row', gap: spacing.xs, marginBottom: spacing.md },
  tab: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.full,
    backgroundColor: colors.background,
  },
  tabActive: { backgroundColor: colors.primary },
  tabText: { fontFamily: 'DMSans-Medium', fontSize: 13, color: colors.textSecondary },
  tabTextActive: { color: colors.white },
});
```

- [ ] **Step 6: Integrate bottom sheet into Reading Session**

Add `<WordDetailSheet />` to `book/[id].tsx`.

- [ ] **Step 7: Test full word tap flow**

Tap word → popup appears → tap Grammar → bottom sheet opens with loading → i'rab result shows. Test switching tabs. Test Ask AI chat.

- [ ] **Step 8: Compare all states with Paper artboards**

Compare with Paper artboards: `6GH-0` (Translation), `6HZ-0` (I'rab), `6S8-0` (Ask AI), `6TT-0` (Ask AI Active), `6PR-0` (Loading), `6JZ-0` (Error).

- [ ] **Step 9: Commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add reader/components/word-detail/
git commit -m "feat(reader): build Word Detail bottom sheet with Translation, I'rab, and Ask AI tabs"
```

---

## Task 18: Settings Screen

**Files:**
- Create: `reader/app/settings.tsx`

- [ ] **Step 1: Build Settings screen**

Create `reader/app/settings.tsx`. Match Paper artboard `7FD-0`. Sections: Font size slider, Arabic font picker, AI language toggle, grammar detail level, notifications toggle, data & privacy. Use `useSettingsStore`.

- [ ] **Step 2: Screenshot and compare with Paper**

Compare with artboard `7FD-0`.

- [ ] **Step 3: Commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add reader/app/settings.tsx
git commit -m "feat(reader): build Settings screen"
```

---

## Task 19: Profile Screen

**Files:**
- Create: `reader/app/profile.tsx`

- [ ] **Step 1: Build Profile screen**

Create `reader/app/profile.tsx`. Match Paper artboard `7BL-0` but **without auth-specific sections** (no subscription, no account name/email, no sign out). Show: generic avatar, local-only stats (hours read, books active, completed, words learned). Use `useStatsStore`.

- [ ] **Step 2: Screenshot and compare with Paper**

Compare with artboard `7BL-0` (stats section only).

- [ ] **Step 3: Commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add reader/app/profile.tsx
git commit -m "feat(reader): build Profile screen with local stats"
```

---

## Task 20: End-to-End Testing + Polish

**Files:**
- Various adjustments across all screens

- [ ] **Step 1: Insert sample book data into Supabase**

Use Supabase dashboard or CLI to insert 3-5 sample books with pages into the `books` and `pages` tables. Use real OpenITI content if available from the ingestion pipeline team, otherwise create realistic test data.

- [ ] **Step 2: Full flow test on iPad simulator**

Walk through the complete flow:
1. App launch → Library Main with stats and catalog
2. Tap a book → download → reading session
3. Swipe pages → text renders correctly (RTL)
4. Tap a word → popup appears
5. Tap Grammar → bottom sheet → i'rab analysis loads
6. Switch to Translation tab → translation loads
7. Switch to Ask AI → ask a question → response arrives
8. Navigate to Settings → change font size → return to reader → font changes
9. Navigate to Profile → stats show correctly
10. Navigate to Discover → search → filter by category

- [ ] **Step 3: Full flow test on iPhone simulator**

Repeat the above on an iPhone simulator. Check responsive layout — book grid should show 2-3 columns, reading text should fit smaller screen.

- [ ] **Step 4: Visual polish pass**

Compare every screen side-by-side with Paper designs. Extract exact values using `get_computed_styles` for any mismatches. Fix spacing, font sizes, colors, border radii.

- [ ] **Step 5: Run all tests**

```bash
cd reader
npx jest --coverage
```

Expected: All tests pass. Coverage report shows key logic covered.

- [ ] **Step 6: Final commit**

```bash
cd /Users/yousefh/Desktop/Cool\ Code/suhuf
git add -A
git commit -m "feat(reader): end-to-end testing and visual polish pass"
```

---

## Summary

| Task | Description | Key Files |
|------|-------------|-----------|
| 1 | Expo project scaffolding | `reader/` (entire project) |
| 2 | Supabase book schema | `supabase/migrations/` |
| 3 | Types + theme constants | `reader/types/`, `reader/constants/` |
| 4 | Supabase client | `reader/lib/supabase.ts` |
| 5 | SQLite database layer | `reader/lib/database.ts` |
| 6 | Hash utility | `reader/lib/hash.ts` |
| 7 | Book download service | `reader/lib/book-download.ts` |
| 8 | Word analysis service | `reader/lib/word-analysis.ts` |
| 9 | Zustand stores | `reader/stores/` |
| 10 | Root layout (fonts, DB) | `reader/app/_layout.tsx` |
| 11 | Edge Functions | `supabase/functions/` |
| 12 | UI components (Header, BookCard) | `reader/components/ui/`, `reader/components/library/` |
| 13 | Library Main screen | `reader/app/index.tsx` |
| 14 | Library Discover screen | `reader/app/discover.tsx` |
| 15 | Reading Session | `reader/app/book/[id].tsx`, `reader/components/reader/` |
| 16 | Word Selection Popup | `reader/components/reader/WordPopup.tsx` |
| 17 | Word Detail Bottom Sheet | `reader/components/word-detail/` |
| 18 | Settings screen | `reader/app/settings.tsx` |
| 19 | Profile screen | `reader/app/profile.tsx` |
| 20 | E2E testing + polish | All files |
