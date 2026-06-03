import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getBook,
  getEffectiveChapters,
  getAllPagesForBook,
  hasTashkeel,
} from "@/lib/reader/queries";
import { ChapterScroll } from "@/components/reader/ChapterScroll";
import { ChapterDrawer } from "@/components/reader/ChapterDrawer";
import { ModeToggle } from "@/components/reader/ModeToggle";
import { TashkeelToggle } from "@/components/reader/TashkeelToggle";
import { PageMarkersToggle } from "@/components/reader/PageMarkersToggle";
import { ThemeToggle } from "@/components/reader/ThemeToggle";
import { HadithCardToggle } from "@/components/reader/HadithCardToggle";
import { ReaderThemeShell } from "@/components/reader/ReaderThemeShell";
import {
  ReciteShell,
  ReciteShellToggle,
  ReciteShellContent,
} from "@/components/reader/recite/ReciteShell";
import { WordPopoverShell } from "@/components/reader/word/WordPopoverShell";
import ReadingTracker from "@/components/reader/ReadingTracker";
import { createClient } from "@/lib/supabase/server";

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

  const recitable = hasTashkeel(pages, Number.POSITIVE_INFINITY);
  const chapterBlocks = pages.flatMap((p) => p.content_blocks);

  // Record reading activity only for signed-in readers (the route is public).
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <ReaderThemeShell>
      <ReciteShell chapterBlocks={chapterBlocks} recitable={recitable}>
        <header
          className="sticky top-0 z-10 backdrop-blur px-4 py-2 flex items-center gap-3 flex-wrap border-b"
          style={{
            background: "var(--reader-chrome-bg)",
            borderColor: "var(--reader-rule)",
          }}
        >
          <Link
            href="/library"
            className="text-xs font-mono hover:opacity-80"
            style={{ color: "var(--reader-fg-muted)" }}
          >
            ← library
          </Link>
          <div className="text-sm" dir="rtl">{result.book.title_ar}</div>
          <div className="flex-1" />
          <ChapterDrawer chapters={chapters} pages={pages} />
          <ThemeToggle />
          <TashkeelToggle />
          <PageMarkersToggle />
          <HadithCardToggle />
          <ReciteShellToggle />
          <ModeToggle mode="reader" />
        </header>

        <ReciteShellContent>
          <WordPopoverShell>
            <ChapterScroll pages={pages} chapters={chapters} mode="reader" />
            {user && <ReadingTracker openitiId={decoded} />}
          </WordPopoverShell>
        </ReciteShellContent>
      </ReciteShell>
    </ReaderThemeShell>
  );
}
