import type { LibraryEntry, LibraryStatus, DiscoverBook, DiscoverQuery } from "./types";

export function selectLibrary(
  entries: LibraryEntry[],
  status: LibraryStatus,
): LibraryEntry[] {
  return entries.filter((e) => e.status === status);
}

function slugify(label: string): string {
  return label.toLowerCase().replace(/\s+/g, "-");
}

export function selectDiscover(
  books: DiscoverBook[],
  query: DiscoverQuery,
): DiscoverBook[] {
  let result = [...books];

  if (query.genre) {
    const targetSlug = query.genre.toLowerCase();
    result = result.filter((b) => slugify(b.genre) === targetSlug);
  }

  if (query.query) {
    const needle = query.query.toLowerCase();
    result = result.filter((b) => {
      return (
        b.titleAr.includes(needle) ||
        (b.titleLat ?? "").toLowerCase().includes(needle) ||
        (b.titleEn ?? "").toLowerCase().includes(needle) ||
        b.authorName.toLowerCase().includes(needle)
      );
    });
  }

  if (query.sort === "title") {
    result = result.sort((a, b) => {
      const aTitle = a.titleLat ?? a.titleEn ?? a.titleAr;
      const bTitle = b.titleLat ?? b.titleEn ?? b.titleAr;
      return aTitle.localeCompare(bTitle);
    });
  } else if (query.sort === "popularity") {
    result = result.sort((a, b) => b.popularity - a.popularity);
  }
  // "relevance" or undefined: original order (already preserved by the spread)

  return result;
}
