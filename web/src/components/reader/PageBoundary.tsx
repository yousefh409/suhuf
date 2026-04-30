import type { ReaderMode } from "@/lib/reader/types";

type Props = {
  volume: number;
  pageNumber: number;
  mode: ReaderMode;
};

export function PageBoundary({ volume, pageNumber, mode }: Props) {
  const id = `v${volume}p${pageNumber}`;
  const label = `V${String(volume).padStart(2, "0")}P${String(pageNumber).padStart(3, "0")}`;

  if (mode === "reader") {
    return (
      <div id={id} className="flex items-center gap-2 my-6 text-xs text-zinc-400" dir="ltr">
        <hr className="flex-1 border-zinc-200" />
        <span>{label}</span>
        <hr className="flex-1 border-zinc-200" />
      </div>
    );
  }

  return (
    <div id={id} className="flex items-center gap-2 my-6" dir="ltr">
      <hr className="flex-1 border-zinc-300" />
      <span className="px-2 py-0.5 rounded-full bg-zinc-200 text-zinc-700 text-xs font-mono">
        {label}
      </span>
      <hr className="flex-1 border-zinc-300" />
    </div>
  );
}
