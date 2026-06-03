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
import { queryDiscover, queryGenres } from "./catalog";
import { queryLibrary, queryContinueReading, queryRecommended } from "./library";
import { queryStats } from "./stats";

export async function getStats(): Promise<DashboardStats> {
  return queryStats();
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
