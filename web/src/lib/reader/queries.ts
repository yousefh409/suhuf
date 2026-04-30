import "server-only";
import type { Chapter, Page } from "./types";

type PageRange = { volume: number; page_number: number };

/** If real chapters exist, return them. Otherwise generate one synthetic
 *  chapter per distinct volume, titled "Volume N", at that volume's earliest
 *  page_number. */
export function synthesizeChapters(
  real: Chapter[],
  pageRanges: PageRange[],
): Chapter[] {
  if (real.length > 0) return real;
  if (pageRanges.length === 0) return [];

  const earliestByVolume = new Map<number, number>();
  for (const { volume, page_number } of pageRanges) {
    const cur = earliestByVolume.get(volume);
    if (cur === undefined || page_number < cur) {
      earliestByVolume.set(volume, page_number);
    }
  }

  return [...earliestByVolume.entries()]
    .sort(([a], [b]) => a - b)
    .map(([volume, firstPage], i) => ({
      title: `Volume ${volume}`,
      level: 0,
      page_number: firstPage,
      volume,
      sort_order: i + 1,
      synthesized: true,
    }));
}

/** Filter all pages of a book to those that belong to the given chapter.
 *  - Synthesized chapter: one volume == one chapter, return all of that volume.
 *  - Real chapter: return same-volume pages with page_number in
 *    [chapter.page_number, nextChapter.page_number) on the same volume.
 *    If nextChapter is null, return through end of that volume.
 *    Real chapters spanning volumes are out of scope for v1; we cut at the
 *    volume boundary. */
export function pagesInChapter(
  allPages: Page[],
  chapter: Chapter,
  nextChapter: Chapter | null,
): Page[] {
  if (chapter.synthesized) {
    return allPages.filter((p) => p.volume === chapter.volume);
  }
  return allPages.filter((p) => {
    if (p.volume !== chapter.volume) return false;
    if (p.page_number < chapter.page_number) return false;
    if (
      nextChapter &&
      nextChapter.volume === chapter.volume &&
      p.page_number >= nextChapter.page_number
    ) {
      return false;
    }
    return true;
  });
}
