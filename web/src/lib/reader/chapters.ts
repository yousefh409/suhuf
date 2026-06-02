import type { Chapter } from "./types";

/** Build a lookup so the renderer can stamp chapter anchors on heading
 *  blocks without scanning the chapter list per block.
 *  Map shape: page_number → block_index → sort_order.
 *  Synthesized chapters are skipped — they have no real heading block to
 *  anchor onto (volume markers, not in-text headings). */
export function chapterAnchorMap(
  chapters: Chapter[],
): Map<number, Map<number, number>> {
  const out = new Map<number, Map<number, number>>();
  for (const c of chapters) {
    if (c.synthesized) continue;
    if (typeof c.block_index !== "number") continue;
    let inner = out.get(c.page_number);
    if (!inner) {
      inner = new Map();
      out.set(c.page_number, inner);
    }
    inner.set(c.block_index, c.sort_order);
  }
  return out;
}
