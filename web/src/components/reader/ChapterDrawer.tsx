import Link from "next/link";
import type { Chapter, ReaderMode } from "@/lib/reader/types";

type Props = {
  chapters: Chapter[];
  currentSortOrder: number;
  openitiId: string;
  mode: ReaderMode;
};

export function ChapterDrawer({ chapters, currentSortOrder, openitiId, mode }: Props) {
  const base = `/internal/${mode}/${encodeURIComponent(openitiId)}`;
  return (
    <details className="text-sm">
      <summary className="cursor-pointer font-mono px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200">
        Chapters ({chapters.length})
      </summary>
      <ul className="mt-2 max-h-96 overflow-y-auto border border-zinc-200 rounded bg-white p-2 absolute z-10">
        {chapters.map((c) => (
          <li
            key={c.sort_order}
            style={{ paddingInlineStart: `${(c.level ?? 0) * 12}px` }}
            className={c.sort_order === currentSortOrder ? "font-bold" : ""}
          >
            <Link href={`${base}/${c.sort_order}`} className="block py-0.5 hover:bg-zinc-50">
              {c.synthesized ? (
                <span className="text-zinc-500">{c.title}</span>
              ) : (
                c.title
              )}
            </Link>
          </li>
        ))}
      </ul>
    </details>
  );
}
