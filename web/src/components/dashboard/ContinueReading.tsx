import type { FC } from "react";
import Link from "next/link";
import type { ContinueReadingItem } from "@/lib/dashboard/types";
import BookCover from "./BookCover";
import ProgressBar from "./ProgressBar";

interface ContinueReadingRowProps {
  item: ContinueReadingItem;
  featured: boolean;
}

const ContinueReadingRow: FC<ContinueReadingRowProps> = ({ item, featured }) => {
  const displayTitle = item.titleLat ?? item.titleEn ?? null;
  const isArabicTitle = displayTitle === null;
  const titleText = displayTitle ?? item.titleAr;

  const meta = [item.authorName, item.genre, item.level].filter(Boolean).join(" · ");

  return (
    <div className="bg-parchment-warm rounded-2xl border border-ink/8 p-4 flex items-center gap-4">
      {/* Small cover */}
      <div className="shrink-0 w-14 aspect-[3/4] rounded-lg overflow-hidden">
        <BookCover book={item} className="rounded-lg" />
      </div>

      {/* Middle column */}
      <div className="flex-1 min-w-0 space-y-1">
        <p
          dir={isArabicTitle ? "rtl" : undefined}
          className={`font-serif text-lg text-ink truncate leading-snug ${
            isArabicTitle ? "font-arabic" : ""
          }`}
        >
          {titleText}
        </p>
        {meta && (
          <p className="text-xs text-ink/50 truncate">{meta}</p>
        )}
        <div className={featured ? "pr-2" : ""}>
          <ProgressBar percent={item.progressPercent} />
        </div>
      </div>

      {/* Resume button — featured only */}
      {featured && (
        <Link
          href={`/reader/${encodeURIComponent(item.openitiId)}`}
          className="shrink-0 bg-cta-dark text-parchment-warm text-sm rounded-full px-5 py-2 hover:opacity-90 transition-opacity"
        >
          Resume
        </Link>
      )}
    </div>
  );
};

interface ContinueReadingProps {
  items: ContinueReadingItem[];
}

const ContinueReading: FC<ContinueReadingProps> = ({ items }) => {
  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-serif text-2xl text-ink">Continue Reading</h2>
        <span className="text-sm text-ink/40">Last opened</span>
      </div>

      <div className="space-y-3">
        {items.map((item, idx) => (
          <ContinueReadingRow key={item.openitiId} item={item} featured={idx === 0} />
        ))}
      </div>
    </section>
  );
};

export default ContinueReading;
