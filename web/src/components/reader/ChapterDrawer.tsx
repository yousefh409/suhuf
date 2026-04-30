"use client";

import { useState } from "react";
import type { Chapter, Page } from "@/lib/reader/types";

type Props = {
  chapters: Chapter[];
  pages: Page[];
};

type Tab = "chapters" | "pages";

export function ChapterDrawer({ chapters, pages }: Props) {
  const [tab, setTab] = useState<Tab>("chapters");

  return (
    <details className="text-sm relative">
      <summary className="cursor-pointer font-mono px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200">
        {tab === "chapters" ? `Chapters (${chapters.length})` : `Pages (${pages.length})`}
      </summary>
      <div className="absolute z-10 mt-2 border border-zinc-200 rounded bg-white shadow-sm w-72">
        <div className="flex border-b border-zinc-200 text-xs font-mono">
          <button
            onClick={() => setTab("chapters")}
            className={`flex-1 py-1.5 ${tab === "chapters" ? "bg-zinc-100" : "hover:bg-zinc-50"}`}
          >
            Chapters
          </button>
          <button
            onClick={() => setTab("pages")}
            className={`flex-1 py-1.5 ${tab === "pages" ? "bg-zinc-100" : "hover:bg-zinc-50"}`}
          >
            Pages
          </button>
        </div>
        {tab === "chapters" ? (
          <ChaptersList chapters={chapters} />
        ) : (
          <PagesList pages={pages} />
        )}
      </div>
    </details>
  );
}

function ChaptersList({ chapters }: { chapters: Chapter[] }) {
  return (
    <ul className="max-h-96 overflow-y-auto p-2">
      {chapters.map((c) => {
        const href = c.synthesized
          ? `#p-V${String(c.volume).padStart(2, "0")}P${String(c.page_number).padStart(3, "0")}`
          : `#h-${c.sort_order}`;
        return (
          <li
            key={`${c.sort_order}-${c.title}`}
            style={{ paddingInlineStart: `${(c.level ?? 0) * 12}px` }}
          >
            <a href={href} className="block py-0.5 hover:bg-zinc-50">
              {c.synthesized ? (
                <span className="text-zinc-500">{c.title}</span>
              ) : (
                c.title
              )}
            </a>
          </li>
        );
      })}
    </ul>
  );
}

function PagesList({ pages }: { pages: Page[] }) {
  return (
    <ul className="max-h-96 overflow-y-auto p-2 font-mono text-xs">
      {pages.map((p) => {
        const label = `V${String(p.volume).padStart(2, "0")}P${String(p.page_number).padStart(3, "0")}`;
        return (
          <li key={`${p.volume}-${p.page_number}`}>
            <a href={`#p-${label}`} className="block py-0.5 hover:bg-zinc-50">
              {label}
            </a>
          </li>
        );
      })}
    </ul>
  );
}
