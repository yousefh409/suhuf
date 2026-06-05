"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ChevronDown } from "lucide-react";
import type { Chapter, Page } from "@/lib/reader/types";

type Props = { chapters: Chapter[]; pages: Page[] };

const pageAnchorId = (volume: number, pageNumber: number) =>
  `p-V${String(volume).padStart(2, "0")}P${String(pageNumber).padStart(3, "0")}`;

/**
 * Centered chapter control that sits under the Recite button. Shows the current
 * chapter (tracked by scroll position) and opens a dropdown to jump to another.
 *
 * Chapters carry no in-text heading anchor (block_index is null in OpenITI
 * data), so navigation is keyed to each chapter's page: we resolve every
 * chapter to the page it starts on and use the always-present page-boundary
 * anchor for both scroll tracking and jumping.
 */
export function ChapterSelect({ chapters, pages }: Props) {
  const [open, setOpen] = useState(false);
  const reduce = useReducedMotion();
  const [currentIdx, setCurrentIdx] = useState(0);
  const btnRef = useRef<HTMLButtonElement>(null);
  const [menuPos, setMenuPos] = useState<{ top: number; left: number } | null>(null);

  // Resolve each chapter to a page index (exact page, else the first page at or
  // after the chapter's printed page, else the first page).
  const chapterPageIdx = useMemo(
    () =>
      chapters.map((c) => {
        const exact = pages.findIndex(
          (p) => p.volume === c.volume && p.page_number === c.page_number,
        );
        if (exact >= 0) return exact;
        const after = pages.findIndex(
          (p) => p.volume === c.volume && p.page_number >= c.page_number,
        );
        return after >= 0 ? after : 0;
      }),
    [chapters, pages],
  );

  // Scroll-spy: find the current page (last page anchor scrolled past the top),
  // then the current chapter is the last one that starts on or before it.
  // Throttled with a timer (not rAF) so it fires even when the tab isn't painting.
  useEffect(() => {
    if (chapters.length === 0 || pages.length === 0) return;
    const compute = () => {
      let curPage = 0;
      for (let i = 0; i < pages.length; i++) {
        const el = document.getElementById(pageAnchorId(pages[i].volume, pages[i].page_number));
        if (el && el.getBoundingClientRect().top <= 120) curPage = i;
      }
      let cur = 0;
      for (let i = 0; i < chapterPageIdx.length; i++) {
        if (chapterPageIdx[i] <= curPage) cur = i;
      }
      setCurrentIdx(cur);
    };
    let timer: ReturnType<typeof setTimeout> | null = null;
    const schedule = () => {
      if (timer !== null) return;
      timer = setTimeout(() => {
        timer = null;
        compute();
      }, 100);
    };
    compute();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("hashchange", schedule);
    return () => {
      if (timer !== null) clearTimeout(timer);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("hashchange", schedule);
    };
  }, [chapters, pages, chapterPageIdx]);

  if (chapters.length === 0) return null;
  const current = chapters[Math.min(currentIdx, chapters.length - 1)];

  const toggle = () => {
    if (open) return setOpen(false);
    const r = btnRef.current?.getBoundingClientRect();
    if (r) setMenuPos({ top: r.bottom + 6, left: r.left + r.width / 2 });
    setOpen(true);
  };
  const close = () => setOpen(false);

  // Navigate via an anchor href so the browser handles the hash + scroll (and
  // fires hashchange, which paged mode and the scroll-spy both listen for).
  const hrefFor = (i: number) => {
    const p = pages[chapterPageIdx[i]];
    return p ? `#${pageAnchorId(p.volume, p.page_number)}` : "#";
  };

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        onClick={toggle}
        className="flex max-w-[15rem] items-center gap-1.5 rounded-lg px-2.5 py-1 text-[13px] transition-colors hover:bg-[var(--reader-chip-bg)]"
        style={{ color: "var(--reader-fg-muted)" }}
        aria-haspopup="listbox"
        aria-expanded={open}
        title="Jump to chapter"
      >
        <span
          dir="rtl"
          className="truncate"
          style={{ fontFamily: "var(--font-arabic), serif", fontSize: 15, color: "var(--reader-fg)" }}
        >
          {current.title}
        </span>
        <ChevronDown size={15} style={{ flexShrink: 0 }} />
      </button>

      {typeof document !== "undefined" &&
        createPortal(
          <AnimatePresence>
            {open && menuPos && (
              <div>
                <motion.div
                  className="reader-scrim"
                  style={{ background: "transparent" }}
                  onClick={close}
                  aria-hidden
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.12 }}
                />
                <motion.div
                  role="listbox"
                  className="reader-chapter-menu"
                  style={{ top: menuPos.top, left: menuPos.left, transformOrigin: "top center" }}
                  initial={reduce ? { opacity: 0, x: "-50%" } : { opacity: 0, scale: 0.96, y: -4, x: "-50%" }}
                  animate={{ opacity: 1, scale: 1, y: 0, x: "-50%" }}
                  exit={reduce ? { opacity: 0, x: "-50%" } : { opacity: 0, scale: 0.96, y: -4, x: "-50%" }}
                  transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
                >
                  {chapters.map((c, i) => (
                    <a
                      key={`${c.sort_order}-${c.title}`}
                      href={hrefFor(i)}
                      role="option"
                      aria-selected={i === currentIdx}
                      onClick={close}
                      className="block w-full rounded-md px-3 py-2 text-right transition-colors hover:bg-[var(--reader-chip-bg)]"
                      style={{ paddingInlineStart: `${0.75 + (c.level ?? 0) * 0.875}rem` }}
                    >
                      <span
                        dir="rtl"
                        style={{
                          fontFamily: "var(--font-arabic), serif",
                          fontSize: 16,
                          color: i === currentIdx ? "var(--reader-accent)" : "var(--reader-fg)",
                        }}
                      >
                        {c.title}
                      </span>
                    </a>
                  ))}
                </motion.div>
              </div>
            )}
          </AnimatePresence>,
          document.body,
        )}
    </>
  );
}
