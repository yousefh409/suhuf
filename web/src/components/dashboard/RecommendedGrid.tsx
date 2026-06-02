import type { FC } from "react";
import type { RecommendedBook } from "@/lib/dashboard/types";
import BookCard from "./BookCard";

interface RecommendedGridProps {
  books: RecommendedBook[];
}

const RecommendedGrid: FC<RecommendedGridProps> = ({ books }) => {
  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-serif text-2xl text-ink">Recommended for You</h2>
        <span className="text-sm text-ink/40">Based on your reading</span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-5">
        {books.map((book) => (
          <BookCard key={book.openitiId} book={book} />
        ))}
      </div>
    </section>
  );
};

export default RecommendedGrid;
