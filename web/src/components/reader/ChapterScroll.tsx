"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { Block as BlockT, Chapter, Page, ReaderMode } from "@/lib/reader/types";
import { chapterAnchorMap } from "@/lib/reader/chapters";
import {
  TASHKEEL_KEY,
  DIFF_KEY,
  PAGE_MARKERS_KEY,
  HADITH_CARD_KEY,
  READER_LAYOUT_KEY,
} from "@/lib/reader/storageKeys";
import { usePreferences } from "@/components/preferences/PreferencesProvider";
import { Block } from "./Block";
import { PageBoundary } from "./PageBoundary";
import { TokenText } from "./TokenText";

type Props = {
  pages: Page[];
  chapters: Chapter[];
  mode: ReaderMode;
};

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
    out.push({ kind: "block", block: b, blockIdx: i });
    i += 1;
  }
  return out;
}

export function ChapterScroll({ pages, chapters, mode }: Props) {
  const { prefs } = usePreferences();
  // Reader diacritics follow the saved preference (set from the Display panel),
  // so the toggle there applies live. The inspector keeps its own localStorage
  // override (its TashkeelToggle writes TASHKEEL_KEY).
  const [tashkeelOverride, setTashkeelOverride] = useState<boolean | null>(null);
  const [showDiff, setShowDiff] = useState(false);
  const [showPageMarkers, setShowPageMarkers] = useState(true);
  const [hadithCard, setHadithCard] = useState(false);
  const [layout, setLayout] = useState<"scroll" | "paged">("scroll");
  const [pageIndex, setPageIndex] = useState(0);
  const anchors = useMemo(() => chapterAnchorMap(chapters), [chapters]);
  const showTashkeel =
    mode === "reader" ? prefs.tashkeel : tashkeelOverride ?? prefs.tashkeel;
  // Paged layout is a reader-only affordance; the inspector always scrolls.
  const paged = mode === "reader" && layout === "paged";

  useEffect(() => {
    if (typeof window === "undefined") return;
    const t = window.localStorage.getItem(TASHKEEL_KEY);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (t !== null) setTashkeelOverride(t === "1");
    const d = window.localStorage.getItem(DIFF_KEY);
    if (d !== null) setShowDiff(d === "1");
    const pm = window.localStorage.getItem(PAGE_MARKERS_KEY);
    if (pm !== null) setShowPageMarkers(pm === "1");
    const hc = window.localStorage.getItem(HADITH_CARD_KEY);
    if (hc !== null) setHadithCard(hc === "1");
    const lo = window.localStorage.getItem(READER_LAYOUT_KEY);
    if (lo === "paged" || lo === "scroll") setLayout(lo);

    const onStorage = (e: StorageEvent) => {
      if (e.key === TASHKEEL_KEY && e.newValue !== null) setTashkeelOverride(e.newValue === "1");
      if (e.key === DIFF_KEY && e.newValue !== null) setShowDiff(e.newValue === "1");
      if (e.key === PAGE_MARKERS_KEY && e.newValue !== null) setShowPageMarkers(e.newValue === "1");
      if (e.key === HADITH_CARD_KEY && e.newValue !== null) setHadithCard(e.newValue === "1");
      if (e.key === READER_LAYOUT_KEY && (e.newValue === "paged" || e.newValue === "scroll"))
        setLayout(e.newValue);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  // Resolve a URL hash (#p-V01P035 page anchor, or #h-12 chapter anchor) to the
  // page index that contains it — lets TOC links jump pages in paged mode.
  const pageIndexFromHash = useCallback(
    (hash: string): number | null => {
      const pm = hash.match(/^#p-V(\d+)P(\d+)$/);
      if (pm) {
        const vol = Number(pm[1]);
        const pg = Number(pm[2]);
        const i = pages.findIndex((p) => p.volume === vol && p.page_number === pg);
        return i >= 0 ? i : null;
      }
      const hm = hash.match(/^#h-(\d+)$/);
      if (hm) {
        const so = Number(hm[1]);
        const ch = chapters.find((c) => c.sort_order === so);
        if (ch) {
          const i = pages.findIndex(
            (p) => p.volume === ch.volume && p.page_number === ch.page_number,
          );
          return i >= 0 ? i : null;
        }
      }
      return null;
    },
    [pages, chapters],
  );

  // Paged mode: keep the visible page in sync with the URL hash and add keyboard
  // paging (← previous, → next).
  useEffect(() => {
    if (!paged || typeof window === "undefined") return;
    const initial = pageIndexFromHash(window.location.hash);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (initial !== null) setPageIndex(initial);

    const onHash = () => {
      const i = pageIndexFromHash(window.location.hash);
      if (i !== null) setPageIndex(i);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") setPageIndex((i) => Math.min(i + 1, pages.length - 1));
      else if (e.key === "ArrowLeft") setPageIndex((i) => Math.max(i - 1, 0));
    };
    window.addEventListener("hashchange", onHash);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("hashchange", onHash);
      window.removeEventListener("keydown", onKey);
    };
  }, [paged, pages.length, pageIndexFromHash]);

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
      ? "reader-article text-[length:var(--reading-size)] leading-[var(--reading-leading)] max-w-[44rem] mx-auto px-6 py-12"
      : "font-arabic text-lg leading-loose text-zinc-900 max-w-[720px] mx-auto px-4 py-8";

  const renderPage = (page: Page, pi: number) => {
    const pageAnchors = anchors.get(page.page_number);
    const items = itemsByPage[pi];
    return (
      <section
        // Include the page index: some sources reprint a marker out of order
        // (Alfiyya prints v1p60/p62 twice), so volume+page is not unique. Only
        // the key must be unique; reading order is unchanged.
        key={`${page.volume}-${page.page_number}-${pi}`}
        data-page-number={page.page_number}
        data-volume={page.volume}
      >
        <PageBoundary
          volume={page.volume}
          pageNumber={page.page_number}
          seq={pi + 1}
          mode={mode}
          visible={showPageMarkers && !paged}
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
                      // blockIdx is unique within a page; b.key is not after a
                      // duplicate-page merge (each page numbers blocks b0..bN).
                      key={`${b.key}-${blockIdx}`}
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
              key={`${item.block.key}-${item.blockIdx}`}
              block={item.block}
              pageNumber={page.page_number}
              mode={mode}
              showTashkeel={showTashkeel}
              showDiff={showDiff}
              anchorId={anchorId}
            />
          );
        })}
        {mode === "reader" && page.footnotes && page.footnotes.length > 0 && (
          <div className="reader-footnotes">
            {page.footnotes.map((fn) => (
              <p key={fn.marker} className="reader-footnote">
                <span className="reader-footnote-marker">{fn.marker}</span>{" "}
                {fn.tokens.map((t) => (
                  <TokenText
                    key={t.id}
                    token={t}
                    mode={mode}
                    showTashkeel={showTashkeel}
                    showDiff={showDiff}
                  />
                ))}
              </p>
            ))}
          </div>
        )}
      </section>
    );
  };

  if (paged) {
    const current = pages[Math.min(pageIndex, pages.length - 1)];
    const goTo = (i: number) => {
      setPageIndex(i);
      window.scrollTo({ top: 0 });
    };
    return (
      <>
        <article
          dir="rtl"
          className={`${articleClass} pb-28`}
          style={{ color: "var(--reader-fg)" }}
        >
          {renderPage(current, Math.min(pageIndex, pages.length - 1))}
        </article>
        <PageNav
          index={Math.min(pageIndex, pages.length - 1)}
          total={pages.length}
          onPrev={() => goTo(Math.max(pageIndex - 1, 0))}
          onNext={() => goTo(Math.min(pageIndex + 1, pages.length - 1))}
        />
      </>
    );
  }

  return (
    <article
      dir="rtl"
      className={articleClass}
      style={mode === "reader" ? { color: "var(--reader-fg)" } : undefined}
    >
      {pages.map((page, pi) => renderPage(page, pi))}
    </article>
  );
}

function PageNav({
  index,
  total,
  onPrev,
  onNext,
}: {
  index: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  return (
    <div className="reader-pagenav" dir="ltr">
      <button
        type="button"
        className="reader-iconbtn"
        onClick={onPrev}
        disabled={index === 0}
        aria-label="Previous page"
      >
        <ChevronLeft size={20} />
      </button>
      <span className="reader-pagenav-label tabular-nums">
        Page {index + 1}
        <span style={{ color: "var(--reader-fg-faint)" }}> / {total}</span>
      </span>
      <button
        type="button"
        className="reader-iconbtn"
        onClick={onNext}
        disabled={index === total - 1}
        aria-label="Next page"
      >
        <ChevronRight size={20} />
      </button>
    </div>
  );
}
