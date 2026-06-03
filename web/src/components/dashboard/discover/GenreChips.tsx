"use client";

import { useSearchParams, usePathname, useRouter } from "next/navigation";
import type { Genre } from "@/lib/dashboard/types";

interface GenreChipsProps {
  genres: Genre[];
}

const GenreChips = ({ genres }: GenreChipsProps) => {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();

  const activeSlug = searchParams.get("genre");

  const handleChipClick = (slug: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (activeSlug === slug) {
      params.delete("genre");
    } else {
      params.set("genre", slug);
    }
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  };

  return (
    <div className="flex gap-2 overflow-x-auto scrollbar-hide">
      {genres.map((genre) => {
        const isActive = genre.slug === activeSlug;
        return (
          <button
            key={genre.slug}
            onClick={() => handleChipClick(genre.slug)}
            className={`rounded-full px-4 py-2 text-sm whitespace-nowrap shrink-0 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/25 ${
              isActive
                ? "bg-cta-dark text-parchment-warm"
                : "bg-parchment-warm text-ink border border-ink/10 hover:border-ink/25"
            }`}
          >
            {genre.label}{" "}
            <span className={isActive ? "text-parchment-warm/60" : "text-ink/40"}>
              {genre.count.toLocaleString()}
            </span>
          </button>
        );
      })}
    </div>
  );
};

export default GenreChips;
