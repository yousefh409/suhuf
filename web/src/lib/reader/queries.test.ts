import { describe, it, expect } from "vitest";
import { synthesizeChapters, pagesInChapter } from "./queries";
import type { Chapter, Page } from "./types";

describe("synthesizeChapters", () => {
  it("returns real chapters unchanged when present", () => {
    const real: Chapter[] = [
      { title: "باب", level: 1, page_number: 1, volume: 1, sort_order: 1 },
      { title: "فصل", level: 2, page_number: 5, volume: 1, sort_order: 2 },
    ];
    const result = synthesizeChapters(real, [
      { volume: 1, page_number: 1 },
      { volume: 1, page_number: 2 },
    ]);
    expect(result).toEqual(real);
    expect(result[0].synthesized).toBeUndefined();
  });

  it("synthesizes one chapter per volume when chapters are empty", () => {
    const result = synthesizeChapters([], [
      { volume: 1, page_number: 1 },
      { volume: 1, page_number: 2 },
      { volume: 2, page_number: 1 },
      { volume: 2, page_number: 2 },
      { volume: 3, page_number: 1 },
    ]);
    expect(result).toHaveLength(3);
    expect(result[0]).toMatchObject({
      title: "Volume 1",
      level: 0,
      page_number: 1,
      volume: 1,
      sort_order: 1,
      synthesized: true,
    });
    expect(result[1].volume).toBe(2);
    expect(result[2].sort_order).toBe(3);
  });

  it("uses each volume's earliest page_number", () => {
    const result = synthesizeChapters([], [
      { volume: 1, page_number: 5 },
      { volume: 1, page_number: 6 },
      { volume: 2, page_number: 3 },
    ]);
    expect(result[0].page_number).toBe(5);
    expect(result[1].page_number).toBe(3);
  });

  it("returns empty when no chapters and no pages", () => {
    expect(synthesizeChapters([], [])).toEqual([]);
  });
});

describe("pagesInChapter", () => {
  const mkPage = (volume: number, page_number: number): Page => ({
    volume,
    page_number,
    content_blocks: [],
  });

  it("returns only the volume's pages for a synthesized chapter", () => {
    const all = [mkPage(1, 1), mkPage(1, 2), mkPage(2, 1), mkPage(2, 2)];
    const ch: Chapter = {
      title: "Volume 2",
      level: 0,
      page_number: 1,
      volume: 2,
      sort_order: 2,
      synthesized: true,
    };
    const next: Chapter = {
      title: "Volume 3",
      level: 0,
      page_number: 1,
      volume: 3,
      sort_order: 3,
      synthesized: true,
    };
    expect(pagesInChapter(all, ch, next)).toEqual([mkPage(2, 1), mkPage(2, 2)]);
  });

  it("slices real chapter by [start, next.start) on the same volume", () => {
    const all = [mkPage(1, 1), mkPage(1, 2), mkPage(1, 3), mkPage(1, 4)];
    const ch: Chapter = { title: "A", level: 1, page_number: 1, volume: 1, sort_order: 1 };
    const next: Chapter = { title: "B", level: 1, page_number: 3, volume: 1, sort_order: 2 };
    expect(pagesInChapter(all, ch, next)).toEqual([mkPage(1, 1), mkPage(1, 2)]);
  });

  it("returns all pages from start to end when nextChapter is null", () => {
    const all = [mkPage(1, 1), mkPage(1, 2), mkPage(1, 3)];
    const ch: Chapter = { title: "A", level: 1, page_number: 2, volume: 1, sort_order: 1 };
    expect(pagesInChapter(all, ch, null)).toEqual([mkPage(1, 2), mkPage(1, 3)]);
  });

  it("respects volume boundary on real chapter — does not bleed into next volume", () => {
    const all = [mkPage(1, 1), mkPage(1, 2), mkPage(2, 1)];
    const ch: Chapter = { title: "A", level: 1, page_number: 1, volume: 1, sort_order: 1 };
    expect(pagesInChapter(all, ch, null)).toEqual([mkPage(1, 1), mkPage(1, 2)]);
  });
});
