import type { FC } from "react";
import Link from "next/link";
import type { BookIdentity } from "@/lib/dashboard/types";
import BookCover from "./BookCover";

interface BookCardProps {
  book: BookIdentity;
  percentBadge?: number;
  meta?: string;
}

const BookCard: FC<BookCardProps> = ({ book, percentBadge, meta }) => {
  const displayTitle = book.titleLat ?? book.titleEn ?? null;
  const isArabicTitle = displayTitle === null;
  const titleText = displayTitle ?? book.titleAr;

  return (
    <Link
      href={`/reader/${encodeURIComponent(book.openitiId)}`}
      className="group flex flex-col gap-2"
    >
      {/* Cover */}
      <div className="relative aspect-[3/4] rounded-xl overflow-hidden">
        <BookCover book={book} className="rounded-xl" />

        {/* Badge */}
        {percentBadge !== undefined && (
          <span className="absolute top-2 right-2 bg-parchment-warm/90 text-gold text-[11px] font-sans font-medium px-2 py-0.5 rounded-full leading-tight">
            {Math.round(Math.min(100, Math.max(0, percentBadge)))}%
          </span>
        )}
      </div>

      {/* Meta */}
      <div className="space-y-0.5">
        <p
          dir={isArabicTitle ? "rtl" : undefined}
          className={`text-sm text-ink line-clamp-2 leading-snug group-hover:text-gold transition-colors ${
            isArabicTitle ? "font-arabic" : ""
          }`}
        >
          {titleText}
        </p>
        <p className="text-xs text-ink/50 truncate">{meta ?? book.authorName}</p>
      </div>
    </Link>
  );
};

export default BookCard;
