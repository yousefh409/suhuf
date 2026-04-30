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
  --dump web/data --dry-run --skip-enrich \\
  --tashkeel-engine shakkala`}</pre>
        </div>
      ) : (
        <ul className="space-y-3">
          {books.map((b) => {
            const id = encodeURIComponent(b.openiti_id);
            return (
              <li key={b.openiti_id} className="border border-zinc-200 rounded p-3">
                <div className="flex items-baseline justify-between gap-3">
                  <div dir="rtl" className="text-lg font-[Amiri,serif]">{b.title_ar}</div>
                  <div className="text-xs font-mono text-zinc-500">{b.openiti_id}</div>
                </div>
                {b.title_lat && <div className="text-sm text-zinc-700">{b.title_lat}</div>}
                <div className="text-xs text-zinc-500 mt-1">
                  {b.author_name_ar ?? "—"} · {b.total_pages ?? "?"} pages
                  {b.total_volumes && b.total_volumes > 1 ? ` · ${b.total_volumes} volumes` : ""}
                  {b.has_tashkeel ? " · tashkeeled" : ""}
                </div>
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
