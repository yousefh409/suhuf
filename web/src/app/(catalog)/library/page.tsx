import { Suspense } from "react";
import { getGenres, getDiscover } from "@/lib/dashboard/data";
import type { DiscoverSort } from "@/lib/dashboard/types";
import DiscoverHeader from "@/components/dashboard/discover/DiscoverHeader";
import DiscoverSearch from "@/components/dashboard/discover/DiscoverSearch";
import GenreChips from "@/components/dashboard/discover/GenreChips";
import DiscoverGrid from "@/components/dashboard/discover/DiscoverGrid";

export const dynamic = "force-dynamic";

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function LibraryPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;
  const genre = first(params.genre);
  const query = first(params.q);
  const sort = first(params.sort) as DiscoverSort | undefined;

  const [genres, books] = await Promise.all([
    getGenres(),
    getDiscover({ genre, query, sort }),
  ]);

  const totalCount = genres.reduce((sum, g) => sum + g.count, 0);
  const activeGenre = genre ? genres.find((g) => g.slug === genre) : undefined;
  const captionLabel = activeGenre?.label ?? "All texts";
  const captionCount = activeGenre?.count ?? totalCount;

  return (
    <main className="min-h-screen bg-parchment text-ink">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8 space-y-6">
        <DiscoverHeader />
        <Suspense fallback={null}>
          <DiscoverSearch totalCount={totalCount} />
        </Suspense>
        <Suspense fallback={null}>
          <GenreChips genres={genres} />
        </Suspense>
        <p className="text-sm text-ink/50">
          {captionLabel} · {captionCount.toLocaleString()} texts
        </p>
        <DiscoverGrid books={books} />
      </div>
    </main>
  );
}
