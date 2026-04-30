"use client";

import { useEffect, useMemo, useState } from "react";
import type { Chapter, Page, ReaderMode } from "@/lib/reader/types";
import { Block } from "./Block";
import { PageBoundary } from "./PageBoundary";

type Props = {
  pages: Page[];
  chapters: Chapter[];
  mode: ReaderMode;
};

// page_number → block_index → chapter sort_order. Lets the renderer stamp
// `id="h-<sort_order>"` on the right heading block in O(1) without scanning
// the chapter list for each block.
function buildChapterAnchorMap(
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

const TASHKEEL_KEY = "suhuf.reader.tashkeel";
const DIFF_KEY = "suhuf.reader.diff";
const PAGE_MARKERS_KEY = "suhuf.reader.pageMarkers";

export function ChapterScroll({ pages, chapters, mode }: Props) {
  const [showTashkeel, setShowTashkeel] = useState(true);
  const [showDiff, setShowDiff] = useState(false);
  const [showPageMarkers, setShowPageMarkers] = useState(true);
  const anchors = useMemo(() => buildChapterAnchorMap(chapters), [chapters]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const t = window.localStorage.getItem(TASHKEEL_KEY);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (t !== null) setShowTashkeel(t === "1");
    const d = window.localStorage.getItem(DIFF_KEY);
    if (d !== null) setShowDiff(d === "1");
    const pm = window.localStorage.getItem(PAGE_MARKERS_KEY);
    if (pm !== null) setShowPageMarkers(pm === "1");

    const onStorage = (e: StorageEvent) => {
      if (e.key === TASHKEEL_KEY && e.newValue !== null) setShowTashkeel(e.newValue === "1");
      if (e.key === DIFF_KEY && e.newValue !== null) setShowDiff(e.newValue === "1");
      if (e.key === PAGE_MARKERS_KEY && e.newValue !== null) setShowPageMarkers(e.newValue === "1");
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  return (
    <article dir="rtl" className="font-[Amiri,serif] text-lg leading-loose text-zinc-900 max-w-[720px] mx-auto px-4 py-8">
      {pages.map((page) => {
        const pageAnchors = anchors.get(page.page_number);
        return (
          <section key={`${page.volume}-${page.page_number}`}>
            <PageBoundary volume={page.volume} pageNumber={page.page_number} mode={mode} visible={showPageMarkers} />
            {page.content_blocks.map((block, blockIdx) => {
              const sortOrder = pageAnchors?.get(blockIdx);
              const anchorId = sortOrder !== undefined ? `h-${sortOrder}` : undefined;
              return (
                <Block
                  key={block.key}
                  block={block}
                  pageNumber={page.page_number}
                  mode={mode}
                  showTashkeel={showTashkeel}
                  showDiff={showDiff}
                  anchorId={anchorId}
                />
              );
            })}
          </section>
        );
      })}
    </article>
  );
}
