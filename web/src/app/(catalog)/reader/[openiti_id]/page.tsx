import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import {
  getBook,
  getEffectiveChapters,
  getAllPagesForBook,
  hasTashkeel,
} from "@/lib/reader/queries";
import { ChapterScroll } from "@/components/reader/ChapterScroll";
import { TocDrawer } from "@/components/reader/TocDrawer";
import { DisplayPanel } from "@/components/reader/DisplayPanel";
import { TashkeelButton } from "@/components/reader/TashkeelButton";
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
          className="sticky top-0 z-10 grid items-center gap-3 border-b px-4 py-2.5 backdrop-blur sm:px-5"
          style={{
            gridTemplateColumns: "1fr auto 1fr",
            background: "var(--reader-chrome-bg)",
            borderColor: "var(--reader-rule)",
          }}
        >
          {/* Left: back · table of contents · title */}
          <div className="flex min-w-0 items-center gap-1 justify-self-start">
            <Link
              href="/library"
              className="reader-iconbtn"
              title="Library"
              aria-label="Back to library"
            >
              <ChevronLeft size={20} />
            </Link>
            <TocDrawer chapters={chapters} pages={pages} />
            <div
              className="ms-1 truncate text-[17px]"
              dir="rtl"
              style={{ fontFamily: "var(--font-arabic), serif", color: "var(--reader-fg)" }}
            >
              {result.book.title_ar}
            </div>
          </div>

          {/* Center: the one focal action */}
          <div className="justify-self-center">
            <ReciteShellToggle />
          </div>

          {/* Right: diacritics toggle · display & reading settings */}
          <div className="flex items-center gap-1 justify-self-end">
            <TashkeelButton />
            <DisplayPanel />
          </div>
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
