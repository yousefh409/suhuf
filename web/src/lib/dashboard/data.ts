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
import { mockStats } from "./mock";
import { queryDiscover, queryGenres } from "./catalog";
import { queryLibrary, queryContinueReading, queryRecommended } from "./library";

// TODO(group0): swap to Supabase — reading_sessions aggregate (sum pages_read, words_learned, streak, minutes)
export async function getStats(): Promise<DashboardStats> {
  return mockStats;
}

export async function getContinueReading(): Promise<ContinueReadingItem[]> {
  return queryContinueReading();
}

export async function getLibrary(status: LibraryStatus): Promise<LibraryEntry[]> {
  return queryLibrary(status);
}

export async function getRecommended(): Promise<RecommendedBook[]> {
  return queryRecommended();
}

export async function getGenres(): Promise<Genre[]> {
  return queryGenres();
}

export async function getDiscover(query: DiscoverQuery): Promise<DiscoverBook[]> {
  return queryDiscover(query);
}
