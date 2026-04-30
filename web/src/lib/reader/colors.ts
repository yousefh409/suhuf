import type { BlockType } from "./types";

// Tailwind classes for inspector mode block borders + badges.
// Pick distinct hues per block type to make boundaries scannable.
export const BLOCK_BORDER: Record<BlockType, string> = {
  prose:     "border-zinc-300",
  heading:   "border-amber-400",
  hadith:    "border-emerald-400",
  isnad:     "border-sky-400",
  matn:      "border-violet-400",
  poetry:    "border-rose-400",
  biography: "border-teal-400",
};

export const BLOCK_BADGE: Record<BlockType, string> = {
  prose:     "bg-zinc-100 text-zinc-700",
  heading:   "bg-amber-100 text-amber-800",
  hadith:    "bg-emerald-100 text-emerald-800",
  isnad:     "bg-sky-100 text-sky-800",
  matn:      "bg-violet-100 text-violet-800",
  poetry:    "bg-rose-100 text-rose-800",
  biography: "bg-teal-100 text-teal-800",
};
