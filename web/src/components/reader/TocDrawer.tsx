"use client";

import { useState } from "react";
import { createPortal } from "react-dom";
import { List, X } from "lucide-react";
import type { Chapter, Page } from "@/lib/reader/types";

type Props = {
  chapters: Chapter[];
  pages: Page[];
};

type Tab = "chapters" | "pages";

const pageHash = (volume: number, pageNumber: number) =>
  `#p-V${String(volume).padStart(2, "0")}P${String(pageNumber).padStart(3, "0")}`;

/**
 * Reader table of contents: a quiet TOC icon in the header that opens a
 * full-height drawer from the start edge. Replaces the old monospace dropdown.
 */
export function TocDrawer({ chapters, pages }: Props) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("chapters");
  const multiVolume = new Set(pages.map((p) => p.volume)).size > 1;

  const close = () => setOpen(false);

  return (
    <>
      <button
        type="button"
        className="reader-iconbtn"
        onClick={() => setOpen(true)}
        title="Chapters"
        aria-label="Open chapters"
      >
        <List size={19} />
      </button>

      {open &&
        typeof document !== "undefined" &&
        createPortal(
          <>
            <div className="reader-scrim" onClick={close} aria-hidden />
            <aside
              className="reader-toc-sheet"
              dir="ltr"
              role="dialog"
              aria-label="Table of contents"
            >
              {/* Header: tabs + close */}
              <div
                className="flex items-center justify-between px-4 py-3 border-b"
                style={{ borderColor: "var(--reader-rule)" }}
              >
                <div className="flex items-center gap-1">
                  <TabButton active={tab === "chapters"} onClick={() => setTab("chapters")}>
                    Chapters · {chapters.length}
                  </TabButton>
                  <TabButton active={tab === "pages"} onClick={() => setTab("pages")}>
                    Pages · {pages.length}
                  </TabButton>
                </div>
                <button
                  type="button"
                  className="reader-iconbtn"
                  style={{ width: 32, height: 32 }}
                  onClick={close}
                  aria-label="Close"
                >
                  <X size={18} />
                </button>
              </div>

              {/* List */}
              <div className="overflow-y-auto p-2">
                {tab === "chapters" ? (
                  <ul>
                    {chapters.map((c) => {
                      const href = c.synthesized
                        ? pageHash(c.volume, c.page_number)
                        : `#h-${c.sort_order}`;
                      return (
                        <li
                          key={`${c.sort_order}-${c.title}`}
                          style={{ paddingInlineStart: `${(c.level ?? 0) * 14}px` }}
                        >
                          <a
                            href={href}
                            onClick={close}
                            className="block rounded-lg px-3 py-2 transition-colors hover:bg-[var(--reader-chip-bg)]"
                          >
                            <span
                              dir="rtl"
                              style={{
                                fontFamily: "var(--font-arabic), serif",
                                fontSize: 17,
                                color: c.synthesized
                                  ? "var(--reader-fg-faint)"
                                  : "var(--reader-fg)",
                              }}
                            >
                              {c.title}
                            </span>
                          </a>
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <div className="flex flex-wrap gap-1 p-1">
                    {pages.map((p) => (
                      <a
                        key={`${p.volume}-${p.page_number}`}
                        href={pageHash(p.volume, p.page_number)}
                        onClick={close}
                        className="rounded-md px-2.5 py-1 text-sm tabular-nums transition-colors hover:bg-[var(--reader-chip-bg)]"
                        style={{ color: "var(--reader-fg-muted)" }}
                      >
                        {multiVolume ? `${p.volume}·${p.page_number}` : p.page_number}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            </aside>
          </>,
          document.body,
        )}
    </>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-lg px-2.5 py-1 text-[11px] uppercase tracking-wider transition-colors"
      style={{
        color: active ? "var(--reader-fg)" : "var(--reader-fg-faint)",
        background: active ? "var(--reader-chip-bg)" : "transparent",
      }}
    >
      {children}
    </button>
  );
}
