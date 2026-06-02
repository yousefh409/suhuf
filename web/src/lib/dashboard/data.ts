import "server-only";

import type {
  DashboardStats,
  ContinueReadingItem,
  LibraryEntry,
  LibraryStatus,
  RecommendedBook,
  Genre,
  DiscoverBook,
  DiscoverQuery,
} from "./types";
import {
  mockStats,
  mockContinueReading,
  mockLibrary,
  mockRecommended,
  mockGenres,
  mockDiscover,
} from "./mock";
import { selectLibrary, selectDiscover } from "./select";

// TODO(group0): swap to Supabase — reading_sessions aggregate (sum pages_read, words_learned, streak, minutes)
export async function getStats(): Promise<DashboardStats> {
  return mockStats;
}

// TODO(group0): swap to Supabase — user_library ⋈ books ordered by last_opened_at, joined with user_reading_positions for progress over books.total_pages
export async function getContinueReading(): Promise<ContinueReadingItem[]> {
  return mockContinueReading;
}

// TODO(group0): swap to Supabase — user_library ⋈ books filtered by status, with progress from user_reading_positions over books.total_pages
export async function getLibrary(status: LibraryStatus): Promise<LibraryEntry[]> {
  return selectLibrary(mockLibrary, status);
}

// TODO(group0): swap to Supabase — future recommender service keyed on user reading history and preferences
export async function getRecommended(): Promise<RecommendedBook[]> {
  return mockRecommended;
}

// TODO(group0): swap to Supabase — books/authors table grouped by genre with count aggregation
export async function getGenres(): Promise<Genre[]> {
  return mockGenres;
}

// TODO(group0): swap to Supabase — books/authors table with genre filter + full-text search, sorted server-side
export async function getDiscover(query: DiscoverQuery): Promise<DiscoverBook[]> {
  return selectDiscover(mockDiscover, query);
}
