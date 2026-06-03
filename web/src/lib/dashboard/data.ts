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
import { mockStats, mockContinueReading, mockLibrary, mockRecommended } from "./mock";
import { selectLibrary } from "./select";
import { queryDiscover, queryGenres } from "./catalog";

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

export async function getGenres(): Promise<Genre[]> {
  return queryGenres();
}

export async function getDiscover(query: DiscoverQuery): Promise<DiscoverBook[]> {
  return queryDiscover(query);
}
