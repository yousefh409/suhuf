export type BookIdentity = {
  openitiId: string;
  titleAr: string;
  titleLat?: string;
  titleEn?: string;
  authorName: string;
  coverUrl?: string;
};

export type LibraryStatus = "in_progress" | "saved" | "completed";

export type DiscoverSort = "relevance" | "title" | "popularity";

export type DashboardStats = {
  pagesToday: number;
  wordsLearnedThisWeek: number;
  streakDays: number;
  timeReadMinutes: number;
};

export type ContinueReadingItem = BookIdentity & {
  genre?: string;
  level?: string;
  progressPercent: number;
  lastOpenedAt: string;
};

export type LibraryEntry = BookIdentity & {
  status: LibraryStatus;
  progressPercent: number;
  lastOpenedAt: string;
  genre?: string;
  level?: string;
};

export type RecommendedBook = BookIdentity & {
  genre: string;
  level?: string;
};

export type DiscoverBook = BookIdentity & {
  genre: string;
  level: string;
  popularity: number;
};

export type Genre = {
  slug: string;
  label: string;
  count: number;
};

export type DiscoverQuery = {
  genre?: string;
  query?: string;
  sort?: DiscoverSort;
};
