"use client";

import { useEffect, useState } from "react";
import type { Page, ReaderMode } from "@/lib/reader/types";
import { Block } from "./Block";
import { PageBoundary } from "./PageBoundary";

type Props = {
  pages: Page[];
  mode: ReaderMode;
};

const TASHKEEL_KEY = "suhuf.reader.tashkeel";
const DIFF_KEY = "suhuf.reader.diff";

export function ChapterScroll({ pages, mode }: Props) {
  const [showTashkeel, setShowTashkeel] = useState(true);
  const [showDiff, setShowDiff] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const t = window.localStorage.getItem(TASHKEEL_KEY);
    if (t !== null) setShowTashkeel(t === "1");
    const d = window.localStorage.getItem(DIFF_KEY);
    if (d !== null) setShowDiff(d === "1");

    const onStorage = (e: StorageEvent) => {
      if (e.key === TASHKEEL_KEY && e.newValue !== null) setShowTashkeel(e.newValue === "1");
      if (e.key === DIFF_KEY && e.newValue !== null) setShowDiff(e.newValue === "1");
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  return (
    <article dir="rtl" className="font-[Amiri,serif] text-lg leading-loose text-zinc-900 max-w-[720px] mx-auto px-4 py-8">
      {pages.map((page) => (
        <section key={`${page.volume}-${page.page_number}`}>
          <PageBoundary volume={page.volume} pageNumber={page.page_number} mode={mode} />
          {page.content_blocks.map((block) => (
            <Block
              key={block.key}
              block={block}
              pageNumber={page.page_number}
              mode={mode}
              showTashkeel={showTashkeel}
              showDiff={showDiff}
            />
          ))}
        </section>
      ))}
    </article>
  );
}
