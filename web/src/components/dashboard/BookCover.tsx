import type { FC } from "react";
import type { BookIdentity } from "@/lib/dashboard/types";

interface BookCoverProps {
  book: BookIdentity;
  className?: string;
}

const BookCover: FC<BookCoverProps> = ({ book, className }) => {
  const base = "relative w-full h-full overflow-hidden rounded-xl";

  if (book.coverUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={book.coverUrl}
        alt={book.titleLat ?? book.titleEn ?? book.titleAr}
        className={`${base} object-cover ${className ?? ""}`}
      />
    );
  }

  return (
    <div
      className={`${base} bg-parchment-light border border-ink/10 flex items-center justify-center p-2 ${className ?? ""}`}
    >
      <p
        dir="rtl"
        className="font-arabic text-ink/70 text-sm text-center leading-relaxed line-clamp-4"
      >
        {book.titleAr}
      </p>
    </div>
  );
};

export default BookCover;
