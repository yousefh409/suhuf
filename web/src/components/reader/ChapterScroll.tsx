"use client";

import { useEffect, useMemo, useState } from "react";
import type { Block as BlockT, Chapter, Page, ReaderMode } from "@/lib/reader/types";
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
const HADITH_CARD_KEY = "suhuf.reader.hadithCard";

type RenderItem =
  | { kind: "block"; block: BlockT; blockIdx: number }
  | { kind: "card"; blocks: { block: BlockT; blockIdx: number }[]; number: number };

/**
 * Group adjacent isnad+matn (and standalone hadith blocks) into cards when
 * the user opts in. Cards are numbered chapter-wide via a running counter.
 */
function groupBlocks(blocks: BlockT[], counter: { n: number }): RenderItem[] {
  const out: RenderItem[] = [];
  let i = 0;
  while (i < blocks.length) {
    const b = blocks[i];
    if (b.type === "isnad") {
      const run: { block: BlockT; blockIdx: number }[] = [{ block: b, blockIdx: i }];
      let j = i + 1;
      while (j < blocks.length && (blocks[j].type === "matn" || blocks[j].type === "isnad")) {
        run.push({ block: blocks[j], blockIdx: j });
        j++;
      }
      const hasMatn = run.some((x) => x.block.type === "matn");
      if (hasMatn) {
        counter.n += 1;
        out.push({ kind: "card", blocks: run, number: counter.n });
        i = j;
        continue;
      }
    }
    if (b.type === "hadith") {
      counter.n += 1;
      out.push({ kind: "card", blocks: [{ block: b, blockIdx: i }], number: counter.n });
      i += 1;
      continue;
    }
    out.push({ kind: "block", block: b, blockIdx: i });
    i += 1;
  }
  return out;
}

export function ChapterScroll({ pages, chapters, mode }: Props) {
  const [showTashkeel, setShowTashkeel] = useState(true);
  const [showDiff, setShowDiff] = useState(false);
  const [showPageMarkers, setShowPageMarkers] = useState(true);
  const [hadithCard, setHadithCard] = useState(false);
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
    const hc = window.localStorage.getItem(HADITH_CARD_KEY);
    if (hc !== null) setHadithCard(hc === "1");

    const onStorage = (e: StorageEvent) => {
      if (e.key === TASHKEEL_KEY && e.newValue !== null) setShowTashkeel(e.newValue === "1");
      if (e.key === DIFF_KEY && e.newValue !== null) setShowDiff(e.newValue === "1");
      if (e.key === PAGE_MARKERS_KEY && e.newValue !== null) setShowPageMarkers(e.newValue === "1");
      if (e.key === HADITH_CARD_KEY && e.newValue !== null) setHadithCard(e.newValue === "1");
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  // In inspector mode we always render flat — grouping is a reader-only affordance.
  const cardsOn = hadithCard && mode === "reader";

  // Compute grouped items per page (book-wide hadith numbering).
  const itemsByPage = useMemo(() => {
    const counter = { n: 0 };
    return pages.map((page) =>
      cardsOn
        ? groupBlocks(page.content_blocks, counter)
        : page.content_blocks.map((b, i): RenderItem => ({ kind: "block", block: b, blockIdx: i })),
    );
  }, [pages, cardsOn]);

  const articleClass =
    mode === "reader"
      ? "reader-article font-[Amiri,serif] text-[20px] leading-[2] max-w-[640px] mx-auto px-4 py-10"
      : "font-[Amiri,serif] text-lg leading-loose text-zinc-900 max-w-[720px] mx-auto px-4 py-8";

  return (
    <article
      dir="rtl"
      className={articleClass}
      style={mode === "reader" ? { color: "var(--reader-fg)" } : undefined}
    >
      {pages.map((page, pi) => {
        const pageAnchors = anchors.get(page.page_number);
        const items = itemsByPage[pi];
        return (
          <section key={`${page.volume}-${page.page_number}`}>
            <PageBoundary
              volume={page.volume}
              pageNumber={page.page_number}
              mode={mode}
              visible={showPageMarkers}
            />
            {items.map((item, idx) => {
              if (item.kind === "card") {
                return (
                  <div key={`card-${idx}`} className="reader-hadith-card">
                    <span className="reader-hadith-num" aria-hidden>
                      №{item.number}
                    </span>
                    {item.blocks.map(({ block: b, blockIdx }) => {
                      const sortOrder = pageAnchors?.get(blockIdx);
                      const anchorId = sortOrder !== undefined ? `h-${sortOrder}` : undefined;
                      return (
                        <Block
                          key={b.key}
                          block={b}
                          pageNumber={page.page_number}
                          mode={mode}
                          showTashkeel={showTashkeel}
                          showDiff={showDiff}
                          anchorId={anchorId}
                        />
                      );
                    })}
                  </div>
                );
              }
              const sortOrder = pageAnchors?.get(item.blockIdx);
              const anchorId = sortOrder !== undefined ? `h-${sortOrder}` : undefined;
              return (
                <Block
                  key={item.block.key}
                  block={item.block}
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
