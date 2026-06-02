import Link from "next/link";
import type { DiscoverBook } from "@/lib/dashboard/types";
import BookCard from "@/components/dashboard/BookCard";

interface DiscoverGridProps {
  books: DiscoverBook[];
}

const DiscoverGrid = ({ books }: DiscoverGridProps) => {
  if (books.length === 0) {
    return (
      <div className="py-16 text-center">
        <p className="text-ink/50">No texts match</p>
        <Link
          href="/library"
          className="block mt-2 text-gold hover:underline text-sm"
        >
          Clear filters
        </Link>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-5">
      {books.map((book) => (
        <BookCard
          key={book.openitiId}
          book={book}
          meta={`${book.authorName} · ${book.level}`}
        />
      ))}
    </div>
  );
};

export default DiscoverGrid;
