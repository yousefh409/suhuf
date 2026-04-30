import Link from "next/link";
import { listBooks } from "@/lib/reader/queries";

export const dynamic = "force-dynamic";

export default async function LibraryPage() {
  const books = await listBooks();

  return (
    <main className="max-w-3xl mx-auto px-4 py-8">
      <h1 className="text-xl font-bold mb-1">Library</h1>
      <p className="text-sm text-zinc-500 mb-6">{books.length} ingested book{books.length === 1 ? "" : "s"}</p>

      {books.length === 0 ? (
        <div className="text-sm text-zinc-600 space-y-2">
          <p>No books in <code>web/data/</code>. Dump one with:</p>
          <pre className="bg-zinc-50 border border-zinc-200 rounded p-3 text-xs overflow-x-auto">{`python -m ingestion ingest <openiti-uri> \\
  --dump web/data --dry-run \\
  --tashkeel-engine shakkala`}</pre>
          <p className="text-xs text-zinc-500">
            Drop <code>--dry-run</code> to also upload to Supabase. Drop nothing else
            — full pipeline runs Claude enrichment too. Set <code>ANTHROPIC_API_KEY</code> in
            <code>web/.env.local</code> or your shell.
          </p>
        </div>
      ) : (
        <ul className="space-y-3">
          {books.map((b) => {
            const id = encodeURIComponent(b.openiti_id);
            const displayTitleEn = b.title_en ?? b.title_lat ?? null;
            return (
              <li key={b.openiti_id} className="border border-zinc-200 rounded p-3">
                <div className="flex items-baseline justify-between gap-3">
                  <div dir="rtl" className="text-lg font-[Amiri,serif]">{b.title_ar}</div>
                  <div className="text-xs font-mono text-zinc-500">{b.openiti_id}</div>
                </div>
                {displayTitleEn && <div className="text-sm text-zinc-700">{displayTitleEn}</div>}
                {b.description && (
                  <div className="text-sm text-zinc-600 mt-2 leading-relaxed">{b.description}</div>
                )}
                <div className="text-xs text-zinc-500 mt-2 flex flex-wrap gap-x-1.5">
                  <span>{b.author_name_en ?? b.author_name_ar ?? "—"}</span>
                  <span>·</span>
                  <span>{b.total_pages ?? "?"} pages</span>
                  {b.total_volumes && b.total_volumes > 1 && (
                    <>
                      <span>·</span>
                      <span>{b.total_volumes} volumes</span>
                    </>
                  )}
                  {b.has_tashkeel && (
                    <>
                      <span>·</span>
                      <span>tashkeeled</span>
                    </>
                  )}
                </div>
                {b.genres && b.genres.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {b.genres.map((g) => (
                      <span key={g} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-700">
                        {g}
                      </span>
                    ))}
                  </div>
                )}
                <div className="mt-2 flex gap-2 text-xs font-mono">
                  <Link href={`/internal/reader/${id}`} className="px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200">
                    Reader
                  </Link>
                  <Link href={`/internal/inspector/${id}`} className="px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200">
                    Inspector
                  </Link>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
