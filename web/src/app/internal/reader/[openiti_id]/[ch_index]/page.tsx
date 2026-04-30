import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getBook,
  getEffectiveChapters,
  getAllPagesForBook,
  pagesInChapter,
} from "@/lib/reader/queries";
import { ChapterScroll } from "@/components/reader/ChapterScroll";
import { ChapterDrawer } from "@/components/reader/ChapterDrawer";
import { ModeToggle } from "@/components/reader/ModeToggle";
import { TashkeelToggle } from "@/components/reader/TashkeelToggle";

export const dynamic = "force-dynamic";

export default async function ReaderChapter({
  params,
}: {
  params: Promise<{ openiti_id: string; ch_index: string }>;
}) {
  const { openiti_id, ch_index } = await params;
  const decoded = decodeURIComponent(openiti_id);
  const chIdx = parseInt(ch_index, 10);
  if (Number.isNaN(chIdx)) notFound();

  const result = await getBook(decoded);
  if (!result) notFound();
  const chapters = await getEffectiveChapters(result.book.id);
  const idx = chapters.findIndex((c) => c.sort_order === chIdx);
  if (idx === -1) notFound();

  const chapter = chapters[idx];
  const next = chapters[idx + 1] ?? null;
  const allPages = await getAllPagesForBook(result.book.id);
  const pages = pagesInChapter(allPages, chapter, next);

  const id = encodeURIComponent(decoded);
  const prev = chapters[idx - 1] ?? null;

  return (
    <>
      <header className="sticky top-0 z-10 bg-white/90 backdrop-blur border-b border-zinc-200 px-4 py-2 flex items-center gap-3 flex-wrap">
        <Link href="/internal/library" className="text-xs font-mono text-zinc-600 hover:text-zinc-900">
          ← library
        </Link>
        <div className="text-sm" dir="rtl">{result.book.title_ar}</div>
        <div className="text-xs text-zinc-500">— {chapter.title}</div>
        <div className="flex-1" />
        <ChapterDrawer chapters={chapters} currentSortOrder={chIdx} openitiId={decoded} mode="reader" />
        <TashkeelToggle />
        <ModeToggle mode="reader" />
      </header>

      <ChapterScroll pages={pages} mode="reader" />

      <footer className="sticky bottom-0 bg-white/90 backdrop-blur border-t border-zinc-200 px-4 py-2 flex items-center justify-between text-xs font-mono">
        {prev ? (
          <Link href={`/internal/reader/${id}/${prev.sort_order}`} className="px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200">
            ← {prev.title}
          </Link>
        ) : <span />}
        <span className="text-zinc-500">{idx + 1} / {chapters.length}</span>
        {next ? (
          <Link href={`/internal/reader/${id}/${next.sort_order}`} className="px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200">
            {next.title} →
          </Link>
        ) : <span />}
      </footer>
    </>
  );
}
