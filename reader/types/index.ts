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
  title_en: string | null;
  author_ar: string | null;
  author_en: string | null;
  category: BookCategory | null;
  level: BookLevel | null;
  cover_color: string;
  page_count: number;
  content_hash: string | null;
}

export type BlockType = 'prose' | 'hadith' | 'isnad' | 'matn' | 'poetry' | 'biography' | 'heading';

export interface Token {
  id: string;       // e.g. "p42_b1_w5"
  text: string;     // Arabic word (with diacritics)
  tashkeel?: string; // Optional separate diacritized form
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
  pos_ar: string;
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
