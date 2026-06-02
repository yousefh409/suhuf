import Link from "next/link";
import type { LibraryStatus, LibraryEntry } from "@/lib/dashboard/types";
import { getLibrary } from "@/lib/dashboard/data";
import BookCard from "./BookCard";
import LibraryTabs from "./LibraryTabs";

function buildGrid(entries: LibraryEntry[], status: LibraryStatus) {
  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center py-10 gap-2">
        <p className="text-sm text-ink/40">Nothing here yet</p>
        <Link href="/library" className="text-sm text-gold hover:underline">
          Browse the library →
        </Link>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-5">
      {entries.map((entry) => {
        let badge: number | undefined;
        if (status === "in_progress") {
          badge = entry.progressPercent;
        } else if (status === "completed") {
          badge = 100;
        }
        return <BookCard key={entry.openitiId} book={entry} percentBadge={badge} />;
      })}
    </div>
  );
}

export default async function LibraryShelf() {
  const [inProgress, saved, completed] = await Promise.all([
    getLibrary("in_progress"),
    getLibrary("saved"),
    getLibrary("completed"),
  ]);

  const tabs = [
    {
      status: "in_progress" as LibraryStatus,
      label: "In Progress",
      count: inProgress.length,
      dotClass: "bg-gold",
    },
    {
      status: "saved" as LibraryStatus,
      label: "Saved",
      count: saved.length,
      dotClass: "bg-ink/30",
    },
    {
      status: "completed" as LibraryStatus,
      label: "Completed",
      count: completed.length,
      dotClass: "bg-emerald-600/70",
    },
  ];

  const grids: Record<LibraryStatus, React.ReactNode> = {
    in_progress: buildGrid(inProgress, "in_progress"),
    saved: buildGrid(saved, "saved"),
    completed: buildGrid(completed, "completed"),
  };

  return (
    <section className="space-y-4">
      <LibraryTabs tabs={tabs} grids={grids} fullLibraryHref="/library" />
    </section>
  );
}
