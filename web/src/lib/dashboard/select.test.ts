import { describe, it, expect } from "vitest";
import { selectLibrary, selectDiscover } from "./select";
import type { LibraryEntry, DiscoverBook } from "./types";

const baseBook = (overrides: Partial<DiscoverBook> = {}): DiscoverBook => ({
  openitiId: "test.Book",
  titleAr: "كتاب",
  titleLat: "Test Book",
  authorName: "Author",
  genre: "Nahw",
  level: "Beginner",
  popularity: 50,
  ...overrides,
});

const baseEntry = (overrides: Partial<LibraryEntry> = {}): LibraryEntry => ({
  openitiId: "test.Book",
  titleAr: "كتاب",
  titleLat: "Test Book",
  authorName: "Author",
  status: "in_progress",
  progressPercent: 10,
  lastOpenedAt: "2026-06-01T00:00:00Z",
  ...overrides,
});

describe("selectLibrary", () => {
  const entries: LibraryEntry[] = [
    baseEntry({ openitiId: "a", status: "in_progress" }),
    baseEntry({ openitiId: "b", status: "saved" }),
    baseEntry({ openitiId: "c", status: "completed" }),
    baseEntry({ openitiId: "d", status: "in_progress" }),
  ];

  it("returns only entries matching the given status", () => {
    const result = selectLibrary(entries, "in_progress");
    expect(result).toHaveLength(2);
    expect(result.every((e) => e.status === "in_progress")).toBe(true);
  });

  it("returns saved entries", () => {
    const result = selectLibrary(entries, "saved");
    expect(result).toHaveLength(1);
    expect(result[0].openitiId).toBe("b");
  });

  it("returns completed entries", () => {
    const result = selectLibrary(entries, "completed");
    expect(result).toHaveLength(1);
    expect(result[0].openitiId).toBe("c");
  });

  it("returns empty array when no entries match", () => {
    const result = selectLibrary([], "in_progress");
    expect(result).toEqual([]);
  });

  it("does not mutate input", () => {
    const copy = [...entries];
    selectLibrary(entries, "in_progress");
    expect(entries).toEqual(copy);
  });
});

describe("selectDiscover", () => {
  const books: DiscoverBook[] = [
    baseBook({ openitiId: "n1", titleLat: "Al-Ajrumiyyah", titleAr: "الأجرومية", authorName: "Ibn Ajurrum", genre: "Nahw", popularity: 80 }),
    baseBook({ openitiId: "n2", titleLat: "Qatr al-Nada", titleAr: "قطر الندى", authorName: "Ibn Hisham", genre: "Nahw", popularity: 60 }),
    baseBook({ openitiId: "h1", titleLat: "Sahih al-Bukhari", titleAr: "صحيح البخاري", authorName: "Imam al-Bukhari", genre: "Hadith", popularity: 100 }),
    baseBook({ openitiId: "f1", titleLat: "Umdat al-Ahkam", titleAr: "عمدة الأحكام", authorName: "Al-Maqdisi", genre: "Fiqh", popularity: 70 }),
  ];

  describe("genre filter", () => {
    it("returns only books matching the genre slug (case-insensitive)", () => {
      const result = selectDiscover(books, { genre: "nahw" });
      expect(result).toHaveLength(2);
      expect(result.every((b) => b.genre === "Nahw")).toBe(true);
    });

    it("matches genre slug against slugified label", () => {
      const result = selectDiscover(books, { genre: "hadith" });
      expect(result).toHaveLength(1);
      expect(result[0].openitiId).toBe("h1");
    });

    it("returns empty when genre matches nothing", () => {
      const result = selectDiscover(books, { genre: "lugha" });
      expect(result).toEqual([]);
    });
  });

  describe("query substring filter", () => {
    it("filters by titleLat (case-insensitive substring)", () => {
      const result = selectDiscover(books, { query: "ajrumiyyah" });
      expect(result).toHaveLength(1);
      expect(result[0].openitiId).toBe("n1");
    });

    it("filters by titleAr substring", () => {
      const result = selectDiscover(books, { query: "قطر" });
      expect(result).toHaveLength(1);
      expect(result[0].openitiId).toBe("n2");
    });

    it("filters by authorName (case-insensitive)", () => {
      const result = selectDiscover(books, { query: "ibn hisham" });
      expect(result).toHaveLength(1);
      expect(result[0].openitiId).toBe("n2");
    });

    it("returns empty when query matches nothing", () => {
      const result = selectDiscover(books, { query: "zzznomatch" });
      expect(result).toEqual([]);
    });
  });

  describe("sort", () => {
    it("sorts by title alphabetically when sort=title", () => {
      const result = selectDiscover(books, { sort: "title" });
      const titles = result.map((b) => b.titleLat ?? b.titleAr);
      const sorted = [...titles].sort((a, b) => a.localeCompare(b));
      expect(titles).toEqual(sorted);
    });

    it("sorts by popularity descending when sort=popularity", () => {
      const result = selectDiscover(books, { sort: "popularity" });
      const pops = result.map((b) => b.popularity);
      for (let i = 1; i < pops.length; i++) {
        expect(pops[i]).toBeLessThanOrEqual(pops[i - 1]);
      }
    });

    it("preserves original order when sort=relevance", () => {
      const result = selectDiscover(books, { sort: "relevance" });
      expect(result.map((b) => b.openitiId)).toEqual(books.map((b) => b.openitiId));
    });

    it("preserves original order when sort is undefined", () => {
      const result = selectDiscover(books, {});
      expect(result.map((b) => b.openitiId)).toEqual(books.map((b) => b.openitiId));
    });
  });

  describe("combined filters", () => {
    it("applies genre + query together", () => {
      const result = selectDiscover(books, { genre: "nahw", query: "ajrumiyyah" });
      expect(result).toHaveLength(1);
      expect(result[0].openitiId).toBe("n1");
    });

    it("applies genre + sort together", () => {
      const result = selectDiscover(books, { genre: "nahw", sort: "popularity" });
      expect(result).toHaveLength(2);
      expect(result[0].popularity).toBeGreaterThanOrEqual(result[1].popularity);
    });
  });

  it("does not mutate input", () => {
    const ids = books.map((b) => b.openitiId);
    selectDiscover(books, { sort: "popularity" });
    expect(books.map((b) => b.openitiId)).toEqual(ids);
  });
});
