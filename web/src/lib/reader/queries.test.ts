import { describe, it, expect } from "vitest";
import { synthesizeChapters, chapterAnchorMap } from "./queries";
import type { Chapter } from "./types";

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

describe("chapterAnchorMap", () => {
  it("indexes real chapters by (page_number, block_index) → sort_order", () => {
    const chapters: Chapter[] = [
      { title: "A", level: 1, page_number: 5, volume: 1, sort_order: 1, block_index: 0 },
      { title: "B", level: 1, page_number: 5, volume: 1, sort_order: 2, block_index: 4 },
      { title: "C", level: 1, page_number: 7, volume: 1, sort_order: 3, block_index: 0 },
    ];
    const map = chapterAnchorMap(chapters);
    expect(map.get(5)?.get(0)).toBe(1);
    expect(map.get(5)?.get(4)).toBe(2);
    expect(map.get(7)?.get(0)).toBe(3);
  });

  it("skips synthesized chapters (no real heading block to anchor)", () => {
    const chapters: Chapter[] = [
      { title: "Volume 1", level: 0, page_number: 1, volume: 1, sort_order: 1, synthesized: true },
    ];
    expect(chapterAnchorMap(chapters).size).toBe(0);
  });

  it("skips chapters without block_index (older dumps)", () => {
    const chapters: Chapter[] = [
      { title: "Legacy", level: 1, page_number: 5, volume: 1, sort_order: 1 },
    ];
    expect(chapterAnchorMap(chapters).size).toBe(0);
  });
});
