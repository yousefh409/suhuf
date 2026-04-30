import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getBook,
  getEffectiveChapters,
  getAllPagesForBook,
} from "@/lib/reader/queries";
import { ChapterScroll } from "@/components/reader/ChapterScroll";
import { ChapterDrawer } from "@/components/reader/ChapterDrawer";
import { ModeToggle } from "@/components/reader/ModeToggle";
import { TashkeelToggle } from "@/components/reader/TashkeelToggle";
import { PageMarkersToggle } from "@/components/reader/PageMarkersToggle";

export const dynamic = "force-dynamic";

export default async function ReaderPage({
  params,
}: {
  params: Promise<{ openiti_id: string }>;
}) {
  const { openiti_id } = await params;
  const decoded = decodeURIComponent(openiti_id);
  const result = await getBook(decoded);
  if (!result) notFound();

  const [chapters, pages] = await Promise.all([
    getEffectiveChapters(result.book.id),
    getAllPagesForBook(result.book.id),
  ]);

  return (
    <>
      <header className="sticky top-0 z-10 bg-white/90 backdrop-blur border-b border-zinc-200 px-4 py-2 flex items-center gap-3 flex-wrap">
        <Link href="/internal/library" className="text-xs font-mono text-zinc-600 hover:text-zinc-900">
          ← library
        </Link>
        <div className="text-sm" dir="rtl">{result.book.title_ar}</div>
        <div className="flex-1" />
        <ChapterDrawer chapters={chapters} pages={pages} />
        <TashkeelToggle />
        <PageMarkersToggle />
        <ModeToggle mode="reader" />
      </header>

      <ChapterScroll pages={pages} chapters={chapters} mode="reader" />
    </>
  );
}
