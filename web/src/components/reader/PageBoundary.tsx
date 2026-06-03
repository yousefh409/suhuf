import type { ReaderMode } from "@/lib/reader/types";

type Props = {
  volume: number;
  pageNumber: number;
  // Sequential reader page number (1-based position in the book). The reader
  // shows this so pages read 1, 2, 3…; the printed pageNumber lives only in the
  // anchor id (for citations/deep links) and the inspector label.
  seq: number;
  mode: ReaderMode;
  visible: boolean;
};

export function PageBoundary({ volume, pageNumber, seq, mode, visible }: Props) {
  const label = `V${String(volume).padStart(2, "0")}P${String(pageNumber).padStart(3, "0")}`;
  // Anchor id matches the visible label so the URL hash (#p-V01P054) reads
  // identically to the citation. scroll-mt offset keeps the anchor below
  // the sticky header when navigated to via hash. The id stays on the DOM
  // even when the divider is hidden, so deep links keep working.
  const id = `p-${label}`;

  if (!visible) {
    return <div id={id} className="scroll-mt-16" aria-hidden />;
  }

  if (mode === "reader") {
    return (
      <div
        id={id}
        className="my-10 flex select-none flex-col items-center gap-1.5 scroll-mt-16"
        dir="ltr"
      >
        <span
          aria-hidden
          className="text-lg leading-none"
          style={{ color: "var(--reader-accent)", opacity: 0.5 }}
        >
          ✦
        </span>
        <span
          className="text-xs tabular-nums"
          style={{ color: "var(--reader-fg-faint)", letterSpacing: "0.05em" }}
        >
          {seq}
        </span>
      </div>
    );
  }

  return (
    <div id={id} className="flex items-center gap-2 my-6 scroll-mt-16" dir="ltr">
      <hr className="flex-1 border-zinc-300" />
      <span className="px-2 py-0.5 rounded-full bg-zinc-200 text-zinc-700 text-xs font-mono">
        {label}
      </span>
      <hr className="flex-1 border-zinc-300" />
    </div>
  );
}
