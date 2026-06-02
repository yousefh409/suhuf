import type { BlockType } from "./types";

// Tailwind classes for inspector mode block borders + badges.
// Pick distinct hues per block type to make boundaries scannable.
export const BLOCK_BORDER: Record<BlockType, string> = {
  prose:   "border-zinc-300",
  heading: "border-amber-400",
  poetry:  "border-rose-400",
  isnad:   "border-sky-400",
  matn:    "border-violet-400",
  takhrij: "border-fuchsia-400",
  quran:   "border-emerald-500",
};

export const BLOCK_BADGE: Record<BlockType, string> = {
  prose:   "bg-zinc-100 text-zinc-700",
  heading: "bg-amber-100 text-amber-800",
  poetry:  "bg-rose-100 text-rose-800",
  isnad:   "bg-sky-100 text-sky-800",
  matn:    "bg-violet-100 text-violet-800",
  takhrij: "bg-fuchsia-100 text-fuchsia-800",
  quran:   "bg-emerald-100 text-emerald-800",
};
